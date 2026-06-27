from __future__ import annotations

import json
import re
import time
from itertools import cycle
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models
from app.repositories_assessment_items import list_items, replace_items_for_sections
from app.schemas import AssessmentCompetencyRead, AssessmentFundSection, AssessmentItemRead
from app.services.assessment_fund_builder import validate_assessment_fund
from app.services.local_llm_client import LocalLLMClient, get_local_llm_settings

BANK_TITLE = "Подготовленный банк заданий"
SOURCE_KIND = "prepared_task_bank"
QWEN_SOURCE_KIND = "prepared_qwen_bank"
MODEL_VERSION = "prepared-qwen-bank-v2.0"
SECTIONS = [
    ("current_oral", "2.1 Вопросы для устного опроса", "oral", 40),
    ("current_practice", "2.1 Практические задания текущего контроля", "practice", 20),
    ("intermediate_credit", "2.2 Вопросы к зачету", "credit", 32),
    ("intermediate_credit_practice", "2.2 Практические задания к зачету", "credit_practice", 13),
    ("diagnostic", "2.3 Итоговая диагностическая работа", "diagnostic", 40),
]
TOTAL = sum(item[3] for item in SECTIONS)
DIFF = ("easy", "medium", "medium", "hard")
SCENARIOS = (
    "модуля анализа рабочей программы дисциплины",
    "функции извлечения тем и компетенций",
    "компонента формирования контрольной работы",
    "банка заданий ФОС",
    "модуля проверки качества задания",
    "функции экспорта материалов в DOCX",
    "рабочего режима преподавателя",
    "административной панели",
)
ARTIFACTS = (
    "псевдокод функции",
    "таблицу входных и выходных данных",
    "набор тест-кейсов",
    "чек-лист проверки результата",
    "описание пользовательского сценария",
    "фрагмент алгоритма",
)
QWEN_BATCH_SIZE = 8

SYSTEM_PROMPT = """
/no_think
Ты методист и преподаватель программной инженерии. Нужно подготовить адекватные задания ФОС по РПД.
Пиши конкретно, без воды. Для устного опроса делай вопросы вида: "Назовите назначение...", "Что делает функция...", "Объясните, зачем нужен модуль...".
Для практики требуй конкретный проверяемый результат: алгоритм, псевдокод, тест-кейсы, таблицу, схему.
Для diagnostic делай тестовый вопрос с 4 вариантами A-D и одним правильным ответом.
Верни только JSON: {"items":[{"index":0,"text":"...","answer":"...","criteria":["...","..."]}]}.
""".strip()


def ensure_bank(db: Session, program: models.Program, rebuild: bool = False) -> dict:
    fund = _get_or_create_fund(db, program)
    items = list_items(db, fund.id)
    built_now = False
    if rebuild or len(items) < TOTAL:
        base_items = _build_items(fund, program)
        refined_items, llm_meta = _refine_with_qwen(base_items, program)
        items = replace_items_for_sections(db, fund, [item[0] for item in SECTIONS], refined_items, True)
        fund = _find_fund_by_program(db, program.id) or fund
        built_now = True
    else:
        llm_meta = {"enabled": False, "used": False, "calls": 0, "refined": 0, "seconds": 0}
    return _summary(program, fund, items, built_now, llm_meta)


def get_bank(db: Session, program: models.Program, auto_build: bool = False) -> dict:
    fund = _find_fund_by_program(db, program.id)
    if fund is None:
        matched = _find_matching_fund_by_filename(db, program)
        if matched is not None:
            fund = _clone_bank_to_program(db, source_fund=matched, target_program=program)
        elif auto_build:
            return ensure_bank(db, program, True)
        else:
            return _empty(program)
    items = list_items(db, fund.id)
    if auto_build and len(items) < TOTAL:
        return ensure_bank(db, program, True)
    return _summary(program, fund, items, False, {"enabled": False, "used": False, "calls": 0, "refined": 0, "seconds": 0})


def _get_or_create_fund(db: Session, program: models.Program) -> models.AssessmentFund:
    fund = _find_fund_by_program(db, program.id)
    topics = _topics(program)
    codes = _competencies(program)
    sections = _sections(topics)
    validation = validate_assessment_fund(sections, _competency_schemas(codes), topics)
    if fund is None:
        fund = models.AssessmentFund(
            id=str(uuid4()),
            program_id=program.id,
            title=f"{BANK_TITLE} — {program.filename}",
            discipline_name=_discipline_name(program),
            status="generated",
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


def _find_fund_by_program(db: Session, program_id: str) -> models.AssessmentFund | None:
    return db.scalar(
        select(models.AssessmentFund)
        .where(models.AssessmentFund.program_id == program_id, models.AssessmentFund.title.like(f"{BANK_TITLE}%"))
        .options(selectinload(models.AssessmentFund.competencies), selectinload(models.AssessmentFund.program))
        .order_by(models.AssessmentFund.updated_at.desc())
    )


def _find_matching_fund_by_filename(db: Session, program: models.Program) -> models.AssessmentFund | None:
    target = _name_key(program.filename)
    if not target:
        return None
    funds = db.scalars(
        select(models.AssessmentFund)
        .join(models.Program, models.AssessmentFund.program_id == models.Program.id)
        .where(models.AssessmentFund.title.like(f"{BANK_TITLE}%"), models.AssessmentFund.program_id != program.id)
        .options(selectinload(models.AssessmentFund.program), selectinload(models.AssessmentFund.competencies))
        .order_by(models.AssessmentFund.updated_at.desc())
    ).all()
    for fund in funds:
        source = _name_key(fund.program.filename if fund.program else fund.discipline_name)
        if source == target or target in source or source in target:
            return fund
    return None


def _clone_bank_to_program(db: Session, *, source_fund: models.AssessmentFund, target_program: models.Program) -> models.AssessmentFund:
    target_fund = _get_or_create_fund(db, target_program)
    source_items = list_items(db, source_fund.id)
    cloned = [
        item.model_copy(update={
            "id": str(uuid4()),
            "fund_id": target_fund.id,
            "source_context": f"Рабочий режим: банк найден по совпадению имени РПД «{source_fund.program.filename if source_fund.program else source_fund.discipline_name}» и скопирован без генерации.",
        })
        for item in source_items
    ]
    replace_items_for_sections(db, target_fund, [item[0] for item in SECTIONS], cloned, True)
    return _find_fund_by_program(db, target_program.id) or target_fund


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
                source_context="Подготовленный банк заданий. На этапе набора формулировка может улучшаться локальной моделью Qwen.",
                source_kind=SOURCE_KIND, status="approved",
            ))
    return items


def _refine_with_qwen(items: list[AssessmentItemRead], program: models.Program) -> tuple[list[AssessmentItemRead], dict]:
    settings = get_local_llm_settings(None)
    if not settings.enabled:
        return items, {"enabled": False, "used": False, "calls": 0, "refined": 0, "seconds": 0}
    settings.max_tokens = max(settings.max_tokens, 2600)
    settings.timeout_seconds = max(settings.timeout_seconds, 140)
    client = LocalLLMClient(settings)
    started = time.perf_counter()
    result = list(items)
    refined = 0
    calls = 0
    for start in range(0, len(items), QWEN_BATCH_SIZE):
        batch = items[start:start + QWEN_BATCH_SIZE]
        data = client.chat_json(system_prompt=SYSTEM_PROMPT, user_prompt=_prompt(batch, program, start))
        calls += 1
        for raw in _extract(data):
            idx = raw.get("index")
            if not isinstance(idx, int) or idx < 0 or idx >= len(result):
                continue
            item = result[idx]
            text = _clean(raw.get("text"))
            if len(text) < 40:
                continue
            answer = _clean(raw.get("answer")) or item.answer
            criteria = raw.get("criteria") if isinstance(raw.get("criteria"), list) else item.criteria
            result[idx] = item.model_copy(update={
                "text": _repair_prefix(text, item.assessment_type),
                "answer": answer,
                "criteria": [str(value).strip() for value in criteria if str(value).strip()][:5] or item.criteria,
                "source_kind": QWEN_SOURCE_KIND,
                "source_context": f"Подготовленный банк: формулировка улучшена локальной Qwen до защиты; профиль={settings.profile}; модель={settings.model}.",
            })
            refined += 1
    return result, {"enabled": True, "used": refined > 0, "calls": calls, "refined": refined, "seconds": int(time.perf_counter() - started), "model": settings.model}


def _prompt(batch: list[AssessmentItemRead], program: models.Program, start: int) -> str:
    rows = [
        f"РПД: {program.filename}",
        f"Дисциплина: {_discipline_name(program)}",
        "Формат: index|type|topic|competency|draft",
    ]
    for offset, item in enumerate(batch):
        rows.append("|".join([str(start + offset), item.assessment_type, _compact(item.topic, 90), _compact(item.competency_code, 40), _compact(item.text, 240)]))
    return "\n".join(rows)


def _extract(data) -> list[dict]:
    if not isinstance(data, dict):
        return []
    raw = data.get("items")
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def _text(kind: str, topic: str, index: int) -> str:
    scenario = SCENARIOS[index % len(SCENARIOS)]
    artifact = ARTIFACTS[index % len(ARTIFACTS)]
    if kind == "oral":
        stems = (
            f"Вопрос: назовите назначение функции или модуля, связанного с темой «{topic}», и объясните, какие данные он обрабатывает.",
            f"Вопрос: что делает компонент по теме «{topic}» в составе {scenario} и какой результат он должен вернуть пользователю?",
            f"Вопрос: объясните, зачем нужна тема «{topic}» при разработке программного обеспечения, и приведите пример функции или метода.",
        )
        return stems[index % len(stems)]
    if kind == "credit":
        return f"Вопрос: объясните, что выполняет модуль или функция по теме «{topic}», какие входные данные используются и какой результат должен быть получен."
    if kind == "diagnostic":
        return f"Тестовое задание: что делает функция, отвечающая за обработку темы «{topic}» в рамках {scenario}?\nA. Выполняет основную обработку данных и возвращает проверяемый результат\nB. Только изменяет цвет интерфейса\nC. Удаляет исходные данные без проверки\nD. Запускает приложение без учета входных параметров"
    return f"Практическое задание: для {scenario} подготовьте {artifact} по теме «{topic}», укажите входные данные, результат работы и способ проверки корректности."


def _answer(kind: str, topic: str) -> str:
    if kind == "diagnostic":
        return f"Правильный ответ: A. Функция должна выполнять основную обработку по теме «{topic}» и возвращать проверяемый результат."
    if kind in {"oral", "credit"}:
        return f"Ответ должен объяснять назначение функции, метода или модуля по теме «{topic}», входные данные, результат и пример применения."
    return f"Результат должен быть проверяемым, соответствовать теме «{topic}», содержать краткое обоснование и способ проверки."


def _criteria(kind: str) -> list[str]:
    if kind in {"oral", "credit"}:
        return ["Назначение функции или модуля объяснено корректно.", "Указаны входные данные и результат.", "Приведен пример применения.", "Есть вывод по теме."]
    if kind == "diagnostic":
        return ["Выбран один вариант ответа.", "Ответ соответствует теме.", "Приведено краткое обоснование."]
    return ["Результат проверяем.", "Решение соответствует условию.", "Описан способ проверки.", "Есть обоснование."]


def _summary(program: models.Program, fund: models.AssessmentFund, items: list[AssessmentItemRead], built_now: bool, llm_meta: dict) -> dict:
    counts = {code: 0 for code, *_ in SECTIONS}
    for item in items:
        counts[item.section_code] = counts.get(item.section_code, 0) + 1
    return {"ready": len(items) >= TOTAL, "built_now": built_now, "program_id": program.id, "filename": program.filename, "fund_id": fund.id, "mode": QWEN_SOURCE_KIND if llm_meta.get("used") else SOURCE_KIND, "model_version": MODEL_VERSION, "total_items": len(items), "planned_items": TOTAL, "sections": [{"code": code, "title": title, "assessment_type": typ, "planned_items": plan, "generated_items": counts.get(code, 0)} for code, title, typ, plan in SECTIONS], "sample_items": items[:18], "llm": llm_meta, "matched_by_name": not built_now and fund.program_id == program.id}


def _empty(program: models.Program) -> dict:
    return {"ready": False, "built_now": False, "program_id": program.id, "filename": program.filename, "fund_id": "", "mode": SOURCE_KIND, "model_version": MODEL_VERSION, "total_items": 0, "planned_items": TOTAL, "sections": [{"code": code, "title": title, "assessment_type": typ, "planned_items": plan, "generated_items": 0} for code, title, typ, plan in SECTIONS], "sample_items": [], "llm": {"enabled": False, "used": False, "calls": 0, "refined": 0, "seconds": 0}}


def _sections(topics: list[str]) -> list[AssessmentFundSection]:
    return [AssessmentFundSection(code=code, title=title, description=f"Подготовленный Qwen-банк заданий. План: {plan}.", assessment_type=typ, enabled=True, topics=topics, planned_items=plan, generated_items=plan) for code, title, typ, plan in SECTIONS]


def _competency_schemas(codes: list[str]) -> list[AssessmentCompetencyRead]:
    return [AssessmentCompetencyRead(id=str(uuid4()), code=code, description=f"Компетенция {code}", indicators=[f"Применяет знания для выполнения заданий {code}."], levels=["Пороговый", "Повышенный", "Продвинутый"]) for code in codes]


def _topics(program: models.Program) -> list[str]:
    return [str(item).strip() for item in _load(program.topics_json) if str(item).strip()] or ["Общие положения дисциплины"]


def _competencies(program: models.Program) -> list[str]:
    return [str(item).strip() for item in _load(program.competencies_json) if str(item).strip()] or ["ПК-1"]


def _discipline_name(program: models.Program) -> str:
    return program.filename.rsplit(".", 1)[0].replace("_", " ").strip() or "Наименование дисциплины"


def _item_type(kind: str) -> str:
    return {"oral": "theoretical_open", "credit": "theoretical_open", "practice": "practice", "credit_practice": "practice", "diagnostic": "single_choice"}.get(kind, "open")


def _repair_prefix(text: str, kind: str) -> str:
    lower = text.lower()
    if kind in {"oral", "credit"} and not lower.startswith("вопрос"):
        return f"Вопрос: {text[:1].lower()}{text[1:]}"
    if kind == "diagnostic" and not ("a." in lower and "b." in lower and "c." in lower):
        return f"Тестовое задание: {text}"
    if kind in {"practice", "credit_practice"} and not lower.startswith("практическое задание"):
        return f"Практическое задание: {text}"
    return text


def _name_key(value: str) -> str:
    value = (value or "").lower().replace("ё", "е")
    value = re.sub(r"\.(docx|pdf|txt)$", "", value)
    value = re.sub(r"[^a-zа-я0-9]+", "", value)
    return value


def _compact(value: str, limit: int) -> str:
    value = _clean(value).replace("|", "/")
    return value if len(value) <= limit else f"{value[:limit].rstrip()}..."


def _clean(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _load(value: str) -> list:
    try:
        data = json.loads(value or "[]")
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []
