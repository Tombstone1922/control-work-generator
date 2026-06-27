from __future__ import annotations

import json
from itertools import cycle
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models
from app.repositories_assessment_items import list_items, replace_items_for_sections
from app.schemas import AssessmentCompetencyRead, AssessmentFundSection, AssessmentItemRead
from app.services.assessment_fund_builder import validate_assessment_fund

BANK_TITLE = "Подготовленный банк заданий"
SOURCE_KIND = "prepared_task_bank"
MODEL_VERSION = "prepared-task-bank-v1.0"
SECTIONS = [
    ("current_oral", "2.1 Вопросы для устного опроса", "oral", 40),
    ("current_practice", "2.1 Практические задания текущего контроля", "practice", 20),
    ("intermediate_credit", "2.2 Вопросы к зачету", "credit", 32),
    ("intermediate_credit_practice", "2.2 Практические задания к зачету", "credit_practice", 13),
    ("diagnostic", "2.3 Итоговая диагностическая работа", "diagnostic", 40),
]
TOTAL = sum(item[3] for item in SECTIONS)
DIFF = ("easy", "medium", "medium", "hard")
SCENARIOS = ("веб-приложения", "личного кабинета", "банка заданий", "модуля экспорта", "панели администратора", "сервиса обработки РПД")
ARTIFACTS = ("таблицу требований", "алгоритм", "набор тест-кейсов", "чек-лист", "пример данных", "схему компонентов")


def ensure_bank(db: Session, program: models.Program, rebuild: bool = False) -> dict:
    fund = _get_or_create_fund(db, program)
    items = list_items(db, fund.id)
    built_now = False
    if rebuild or len(items) < TOTAL:
        items = replace_items_for_sections(db, fund, [item[0] for item in SECTIONS], _build_items(fund, program), True)
        fund = _find_fund(db, program.id) or fund
        built_now = True
    return _summary(program, fund, items, built_now)


def get_bank(db: Session, program: models.Program, auto_build: bool = False) -> dict:
    fund = _find_fund(db, program.id)
    if fund is None:
        return ensure_bank(db, program, True) if auto_build else _empty(program)
    items = list_items(db, fund.id)
    if auto_build and len(items) < TOTAL:
        return ensure_bank(db, program, True)
    return _summary(program, fund, items, False)


def _get_or_create_fund(db: Session, program: models.Program) -> models.AssessmentFund:
    fund = _find_fund(db, program.id)
    topics = _topics(program)
    codes = _competencies(program)
    sections = _sections(topics)
    validation = validate_assessment_fund(sections, _competency_schemas(codes), topics)
    if fund is None:
        fund = models.AssessmentFund(
            id=str(uuid4()), program_id=program.id, title=f"{BANK_TITLE} — {program.filename}",
            discipline_name=_discipline_name(program), status="generated",
            assessment_types_json=_dump([item[2] for item in SECTIONS]),
            sections_json=_dump([section.model_dump() for section in sections]),
            validation_json=_dump(validation.model_dump()),
        )
        db.add(fund)
        db.flush()
    else:
        fund.title = f"{BANK_TITLE} — {program.filename}"
        fund.discipline_name = _discipline_name(program)
        fund.status = "generated"
        fund.assessment_types_json = _dump([item[2] for item in SECTIONS])
        fund.sections_json = _dump([section.model_dump() for section in sections])
        fund.validation_json = _dump(validation.model_dump())
    _ensure_competencies(db, fund, codes)
    db.commit()
    db.refresh(fund)
    return fund


def _find_fund(db: Session, program_id: str) -> models.AssessmentFund | None:
    return db.scalar(select(models.AssessmentFund).where(models.AssessmentFund.program_id == program_id, models.AssessmentFund.title.like(f"{BANK_TITLE}%")).options(selectinload(models.AssessmentFund.competencies)).order_by(models.AssessmentFund.updated_at.desc()))


def _ensure_competencies(db: Session, fund: models.AssessmentFund, codes: list[str]) -> None:
    existing = {item.code for item in fund.competencies}
    for code in codes:
        if code not in existing:
            db.add(models.AssessmentCompetency(id=str(uuid4()), fund_id=fund.id, code=code, description=f"Компетенция {code}", indicators_json=_dump([f"Применяет знания по дисциплине для выполнения заданий {code}."]), levels_json=_dump(["Пороговый", "Повышенный", "Продвинутый"])))


def _build_items(fund: models.AssessmentFund, program: models.Program) -> list[AssessmentItemRead]:
    topics = cycle(_topics(program))
    comps = cycle(_competencies(program))
    items: list[AssessmentItemRead] = []
    for code, _title, assessment_type, count in SECTIONS:
        for index in range(count):
            topic = next(topics)
            comp = next(comps)
            items.append(AssessmentItemRead(
                id=str(uuid4()), fund_id=fund.id, section_code=code, assessment_type=assessment_type,
                item_type=_item_type(assessment_type), topic=topic, competency_code=comp,
                indicator=f"Проверяется тема «{topic}» и компетенция {comp}.", difficulty=DIFF[index % len(DIFF)],
                text=_text(assessment_type, topic, index), answer=_answer(assessment_type, topic), criteria=_criteria(assessment_type),
                source_context="Заранее подготовленный банк: без локальной модели, быстро открывается в рабочем режиме.",
                source_kind=SOURCE_KIND, status="approved",
            ))
    return items


def _text(kind: str, topic: str, index: int) -> str:
    scenario = SCENARIOS[index % len(SCENARIOS)]
    artifact = ARTIFACTS[index % len(ARTIFACTS)]
    if kind == "oral":
        return f"Вопрос: раскройте тему «{topic}», объясните основные понятия и приведите пример применения в рамках {scenario}."
    if kind == "credit":
        return f"Вопрос: дайте развернутую характеристику темы «{topic}», опишите этапы решения типовой задачи и приведите пример."
    if kind == "diagnostic":
        return f"Диагностическое задание: выберите корректное решение для ситуации «{scenario}» по теме «{topic}», обоснуйте выбор и укажите способ проверки."
    return f"Практическое задание: для {scenario} подготовьте {artifact} по теме «{topic}», укажите результат и способ проверки корректности."


def _answer(kind: str, topic: str) -> str:
    if kind in {"oral", "credit"}:
        return f"Ответ должен раскрывать тему «{topic}», содержать основные понятия, пример применения и обоснованный вывод."
    return f"Результат должен быть проверяемым, соответствовать теме «{topic}», содержать краткое обоснование и способ проверки."


def _criteria(kind: str) -> list[str]:
    if kind in {"oral", "credit"}:
        return ["Ответ соответствует теме.", "Раскрыты ключевые понятия.", "Приведен пример.", "Есть вывод."]
    return ["Результат проверяем.", "Решение соответствует условию.", "Описан способ проверки.", "Есть обоснование."]


def _summary(program: models.Program, fund: models.AssessmentFund, items: list[AssessmentItemRead], built_now: bool) -> dict:
    counts = {code: 0 for code, *_ in SECTIONS}
    for item in items:
        counts[item.section_code] = counts.get(item.section_code, 0) + 1
    return {"ready": len(items) >= TOTAL, "built_now": built_now, "program_id": program.id, "filename": program.filename, "fund_id": fund.id, "mode": SOURCE_KIND, "model_version": MODEL_VERSION, "total_items": len(items), "planned_items": TOTAL, "sections": [{"code": code, "title": title, "assessment_type": typ, "planned_items": plan, "generated_items": counts.get(code, 0)} for code, title, typ, plan in SECTIONS], "sample_items": items[:18]}


def _empty(program: models.Program) -> dict:
    return {"ready": False, "built_now": False, "program_id": program.id, "filename": program.filename, "fund_id": "", "mode": SOURCE_KIND, "model_version": MODEL_VERSION, "total_items": 0, "planned_items": TOTAL, "sections": [{"code": code, "title": title, "assessment_type": typ, "planned_items": plan, "generated_items": 0} for code, title, typ, plan in SECTIONS], "sample_items": []}


def _sections(topics: list[str]) -> list[AssessmentFundSection]:
    return [AssessmentFundSection(code=code, title=title, description=f"Подготовленный банк заданий. План: {plan}.", assessment_type=typ, enabled=True, topics=topics, planned_items=plan, generated_items=plan) for code, title, typ, plan in SECTIONS]


def _competency_schemas(codes: list[str]) -> list[AssessmentCompetencyRead]:
    return [AssessmentCompetencyRead(id=str(uuid4()), code=code, description=f"Компетенция {code}", indicators=[f"Применяет знания для выполнения заданий {code}."], levels=["Пороговый", "Повышенный", "Продвинутый"]) for code in codes]


def _topics(program: models.Program) -> list[str]:
    return [str(item).strip() for item in _load(program.topics_json) if str(item).strip()] or ["Общие положения дисциплины"]


def _competencies(program: models.Program) -> list[str]:
    return [str(item).strip() for item in _load(program.competencies_json) if str(item).strip()] or ["ПК-1"]


def _discipline_name(program: models.Program) -> str:
    return program.filename.rsplit(".", 1)[0].replace("_", " ").strip() or "Наименование дисциплины"


def _item_type(kind: str) -> str:
    return {"oral": "theoretical_open", "credit": "theoretical_open", "practice": "practice", "credit_practice": "practice", "diagnostic": "diagnostic"}.get(kind, "open")


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _load(value: str) -> list:
    try:
        data = json.loads(value or "[]")
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []
