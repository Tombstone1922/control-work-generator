from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from itertools import cycle
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models
from app.repositories_assessment_items import list_items, replace_items_for_sections
from app.schemas import AssessmentCompetencyRead, AssessmentFundSection, AssessmentItemRead
from app.services.assessment_fund_builder import validate_assessment_fund
from app.services.contextual_task_builder import build_contextual_task
from app.services.local_llm_client import LocalLLMClient, get_local_llm_settings

BACKEND_DIR = Path(__file__).resolve().parents[2]
PERSISTENT_BANK_DIR = BACKEND_DIR / 'storage' / 'prepared_banks'

BANK_TITLE = 'Подготовленный банк заданий'
SOURCE_KIND = 'prepared_system_bank'
QWEN_SOURCE_KIND = 'prepared_system_qwen_bank'
MODEL_VERSION = 'prepared-system-bank-v3.0-context-qwen'
SECTIONS = [
    ('current_oral', '2.1 Вопросы для устного опроса', 'oral', 40),
    ('current_practice', '2.1 Практические задания текущего контроля', 'practice', 20),
    ('intermediate_credit', '2.2 Вопросы к зачету', 'credit', 32),
    ('intermediate_credit_practice', '2.2 Практические задания к зачету', 'credit_practice', 13),
    ('diagnostic', '2.3 Итоговая диагностическая работа', 'diagnostic', 40),
]
TOTAL = sum(item[3] for item in SECTIONS)
DIFF = ('easy', 'medium', 'medium', 'hard')
QWEN_BATCH_SIZE = 5

SYSTEM_PROMPT = '''
/no_think
Ты методист и преподаватель программной инженерии. Работай не как свободный чат-бот, а как часть системы генерации ФОС.
У тебя есть: тема из РПД, компетенция, контекст РПД, черновик context-builder и черновой ответ.
Сделай реальное задание и реальный эталонный ответ. Не пиши общую воду.

Правила:
1. Для oral и credit формулируй конкретный устный вопрос: «Назовите назначение...», «Что делает функция...», «Объясните, зачем нужен модуль...», «Какие входные данные и результат...». 
2. Для practice и credit_practice требуй проверяемый артефакт: псевдокод, алгоритм, таблицу входных/выходных данных, тест-кейсы, чек-лист или схему.
3. Для diagnostic обязательно сделай тестовый вопрос с вариантами A, B, C, D и одним правильным вариантом.
4. Ответ должен быть содержательным: не «ответ должен раскрывать», а конкретно что должен сказать/выбрать студент.
5. Используй только переданный контекст РПД и тему. Не выдумывай случайные технологии, которых нет в контексте.
6. Верни только JSON: {"items":[{"index":0,"text":"...","answer":"...","criteria":["...","..."]}]}.
'''.strip()


def ensure_bank(db: Session, program: models.Program, rebuild: bool = False) -> dict:
    fund = _get_or_create_fund(db, program)
    items = list_items(db, fund.id)
    built_now = False
    restored_from_file = False
    llm_meta = {'enabled': False, 'used': False, 'calls': 0, 'refined': 0, 'seconds': 0}

    if not rebuild and len(items) < TOTAL:
        bank_file = _load_bank_file_for_program(program)
        if bank_file is not None:
            fund = _restore_bank_file_to_program(db, program=program, bank_data=bank_file)
            items = list_items(db, fund.id)
            restored_from_file = True

    if rebuild or len(items) < TOTAL:
        base_items = _build_items(fund, program)
        refined_items, llm_meta = _refine_with_qwen(base_items, program)
        items = replace_items_for_sections(db, fund, [item[0] for item in SECTIONS], refined_items, True)
        fund = _find_fund_by_program(db, program.id) or fund
        _save_bank_file(program=program, items=items, llm_meta=llm_meta)
        built_now = True

    return _summary(program, fund, items, built_now, llm_meta, restored_from_file=restored_from_file)


def get_bank(db: Session, program: models.Program, auto_build: bool = False) -> dict:
    fund = _find_fund_by_program(db, program.id)
    restored_from_file = False
    matched_by_name = False

    if fund is None:
        matched = _find_matching_fund_by_filename(db, program)
        if matched is not None:
            fund = _clone_bank_to_program(db, source_fund=matched, target_program=program)
            matched_by_name = True
        else:
            bank_file = _load_bank_file_for_program(program)
            if bank_file is not None:
                fund = _restore_bank_file_to_program(db, program=program, bank_data=bank_file)
                restored_from_file = True
                matched_by_name = True
            elif auto_build:
                return ensure_bank(db, program, True)
            else:
                return _empty(program)

    items = list_items(db, fund.id)
    if len(items) < TOTAL:
        bank_file = _load_bank_file_for_program(program)
        if bank_file is not None:
            fund = _restore_bank_file_to_program(db, program=program, bank_data=bank_file)
            items = list_items(db, fund.id)
            restored_from_file = True
            matched_by_name = True
    if auto_build and len(items) < TOTAL:
        return ensure_bank(db, program, True)
    return _summary(program, fund, items, False, {'enabled': False, 'used': False, 'calls': 0, 'refined': 0, 'seconds': 0}, restored_from_file=restored_from_file, matched_by_name=matched_by_name)


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
            title=f'{BANK_TITLE} — {program.filename}',
            discipline_name=_discipline_name(program),
            status='generated',
            assessment_types_json=_dump([item[2] for item in SECTIONS]),
            sections_json=_dump([section.model_dump() for section in sections]),
            validation_json=_dump(validation.model_dump()),
        )
        db.add(fund)
        db.flush()
    else:
        fund.title = f'{BANK_TITLE} — {program.filename}'
        fund.discipline_name = _discipline_name(program)
        fund.status = 'generated'
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
        .where(models.AssessmentFund.program_id == program_id, models.AssessmentFund.title.like(f'{BANK_TITLE}%'))
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
        .where(models.AssessmentFund.title.like(f'{BANK_TITLE}%'), models.AssessmentFund.program_id != program.id)
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
            'id': str(uuid4()),
            'fund_id': target_fund.id,
            'source_context': f'Рабочий режим: банк найден по совпадению имени РПД «{source_fund.program.filename if source_fund.program else source_fund.discipline_name}» и скопирован без генерации.',
        })
        for item in source_items
    ]
    replace_items_for_sections(db, target_fund, [item[0] for item in SECTIONS], cloned, True)
    return _find_fund_by_program(db, target_program.id) or target_fund


def _restore_bank_file_to_program(db: Session, *, program: models.Program, bank_data: dict) -> models.AssessmentFund:
    target_fund = _get_or_create_fund(db, program)
    raw_items = bank_data.get('items') if isinstance(bank_data, dict) else []
    restored: list[AssessmentItemRead] = []
    for raw in raw_items if isinstance(raw_items, list) else []:
        if not isinstance(raw, dict):
            continue
        raw = dict(raw)
        raw['id'] = str(uuid4())
        raw['fund_id'] = target_fund.id
        raw['source_context'] = f'Рабочий режим: задание восстановлено из постоянного подготовленного банка по имени РПД. Исходный файл банка: {bank_data.get("source_filename", "unknown")}.'
        restored.append(AssessmentItemRead(**raw))
    if restored:
        replace_items_for_sections(db, target_fund, [item[0] for item in SECTIONS], restored, True)
    return _find_fund_by_program(db, program.id) or target_fund


def _ensure_competencies(db: Session, fund: models.AssessmentFund, codes: list[str]) -> None:
    existing = {item.code for item in fund.competencies}
    for code in codes:
        if code not in existing:
            db.add(models.AssessmentCompetency(
                id=str(uuid4()),
                fund_id=fund.id,
                code=code,
                description=f'Компетенция {code}',
                indicators_json=_dump([f'Применяет знания по дисциплине для выполнения заданий {code}.']),
                levels_json=_dump(['Пороговый', 'Повышенный', 'Продвинутый']),
            ))


def _build_items(fund: models.AssessmentFund, program: models.Program) -> list[AssessmentItemRead]:
    topics = _topics(program)
    competencies = _competencies(program)
    topic_cycle = cycle(topics)
    comp_cycle = cycle(competencies)
    items: list[AssessmentItemRead] = []
    used_texts: list[str] = []

    for code, _title, assessment_type, count in SECTIONS:
        for index in range(count):
            topic = next(topic_cycle)
            comp = next(comp_cycle)
            difficulty = DIFF[index % len(DIFF)]
            item_type = _item_type(assessment_type)
            draft = build_contextual_task(
                discipline_name=_discipline_name(program),
                topic=topic,
                all_topics=topics,
                assessment_type=assessment_type,
                item_type=item_type,
                index=index,
                difficulty=difficulty,
                used_texts=used_texts,
            )
            text, answer, criteria = _adapt_system_draft(assessment_type, topic, index, draft.text, draft.answer, draft.criteria)
            used_texts.append(text)
            items.append(AssessmentItemRead(
                id=str(uuid4()),
                fund_id=fund.id,
                section_code=code,
                assessment_type=assessment_type,
                item_type=item_type,
                topic=topic,
                competency_code=comp,
                indicator=_indicator(program, topic, comp),
                difficulty=difficulty,
                text=text,
                answer=answer,
                criteria=criteria,
                source_context=f'Общая система: РПД + context-builder + предметный контекст + Qwen-refiner. Контекст темы: {_topic_context(program, topic, 220)}',
                source_kind=SOURCE_KIND,
                status='approved',
            ))
    return items


def _adapt_system_draft(kind: str, topic: str, index: int, draft_text: str, draft_answer: str, draft_criteria: list[str]) -> tuple[str, str, list[str]]:
    context_hint = _function_or_module_hint(topic, index)
    if kind in {'oral', 'credit'}:
        stems = (
            f'Вопрос: назовите назначение {context_hint} по теме «{topic}». Какие входные данные он использует и какой результат должен вернуть?',
            f'Вопрос: что делает {context_hint} по теме «{topic}» и как проверить корректность его работы?',
            f'Вопрос: объясните, зачем нужен {context_hint} по теме «{topic}» в составе программного обеспечения.',
        )
        text = stems[index % len(stems)]
        answer = f'Эталонный ответ: {context_hint.capitalize()} нужен для выполнения операции по теме «{topic}»: принимает исходные данные, обрабатывает их по заданным правилам, возвращает проверяемый результат и должен обрабатывать ошибочные входные данные.'
        criteria = ['Назначение функции или модуля объяснено конкретно.', 'Указаны входные данные и результат.', 'Описана проверка корректности.', 'Ответ связан с темой РПД.']
    elif kind == 'diagnostic':
        text = f'Тестовое задание: что делает {context_hint} по теме «{topic}»?\nA. Принимает входные данные, выполняет обработку по правилам темы и возвращает проверяемый результат\nB. Только изменяет внешний вид страницы без обработки данных\nC. Удаляет исходные данные без сохранения результата\nD. Запускает приложение без учета входных параметров'
        answer = f'Правильный ответ: A. {context_hint.capitalize()} должен выполнять обработку по теме «{topic}», возвращать проверяемый результат и не сводиться к изменению интерфейса или удалению данных.'
        criteria = ['Выбран вариант A.', 'Дано краткое обоснование выбора.', 'Пояснение связано с назначением функции или модуля.']
    else:
        artifact = _artifact(index)
        text = f'Практическое задание: по теме «{topic}» разработайте {artifact} для {context_hint}. Укажите входные данные, шаги обработки, ожидаемый результат и способ проверки корректности.'
        answer = f'Эталонный ответ: должен быть представлен {artifact}; в нем указаны входные данные, последовательность обработки, ожидаемый результат, обработка ошибок и проверка результата по теме «{topic}».'
        criteria = ['Артефакт соответствует теме и условию.', 'Указаны входные данные и результат.', 'Описан алгоритм или порядок действий.', 'Есть способ проверки корректности.']

    if draft_text and len(text) < 90:
        text = draft_text
    if not answer and draft_answer:
        answer = draft_answer
    if not criteria and draft_criteria:
        criteria = draft_criteria
    return text, answer, criteria


def _refine_with_qwen(items: list[AssessmentItemRead], program: models.Program) -> tuple[list[AssessmentItemRead], dict]:
    settings = get_local_llm_settings(None)
    if not settings.enabled:
        return items, {'enabled': False, 'used': False, 'calls': 0, 'refined': 0, 'seconds': 0, 'pipeline': 'context-builder-only'}
    settings.max_tokens = max(settings.max_tokens, 3200)
    settings.timeout_seconds = max(settings.timeout_seconds, 180)
    client = LocalLLMClient(settings)
    started = time.perf_counter()
    result = list(items)
    refined = 0
    calls = 0
    rejected = 0

    for start in range(0, len(items), QWEN_BATCH_SIZE):
        batch = items[start:start + QWEN_BATCH_SIZE]
        data = client.chat_json(system_prompt=SYSTEM_PROMPT, user_prompt=_prompt(batch, program, start))
        calls += 1
        for raw in _extract(data):
            idx = raw.get('index')
            if not isinstance(idx, int) or idx < 0 or idx >= len(result):
                continue
            item = result[idx]
            text = _repair_prefix(_clean(raw.get('text')), item.assessment_type)
            answer = _clean(raw.get('answer'))
            criteria = raw.get('criteria') if isinstance(raw.get('criteria'), list) else []
            criteria = [str(value).strip() for value in criteria if str(value).strip()][:5]
            if not _usable_refinement(item, text, answer):
                rejected += 1
                continue
            result[idx] = item.model_copy(update={
                'text': text,
                'answer': answer,
                'criteria': criteria or item.criteria,
                'source_kind': QWEN_SOURCE_KIND,
                'source_context': f'Общая система: РПД-контекст + context-builder + локальный Qwen-refiner; профиль={settings.profile}; модель={settings.model}.',
            })
            refined += 1
    return result, {'enabled': True, 'used': refined > 0, 'calls': calls, 'refined': refined, 'rejected': rejected, 'seconds': int(time.perf_counter() - started), 'model': settings.model, 'pipeline': 'rpd-context-builder-qwen'}


def _prompt(batch: list[AssessmentItemRead], program: models.Program, start: int) -> str:
    parts = [
        f'РПД: {program.filename}',
        f'Дисциплина: {_discipline_name(program)}',
        'Нужно улучшить элементы, не теряя тему и тип задания.',
    ]
    for offset, item in enumerate(batch):
        idx = start + offset
        context = _topic_context(program, item.topic, 520)
        parts.extend([
            f'ITEM {idx}',
            f'type: {item.assessment_type}',
            f'topic: {_compact(item.topic, 120)}',
            f'competency: {_compact(item.competency_code, 80)}',
            f'context: {context}',
            f'draft_question: {_compact(item.text, 420)}',
            f'draft_answer: {_compact(item.answer, 360)}',
            f'contract: {_contract(item.assessment_type)}',
        ])
    return '\n'.join(parts)


def _extract(data) -> list[dict]:
    if not isinstance(data, dict):
        return []
    raw = data.get('items')
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def _usable_refinement(item: AssessmentItemRead, text: str, answer: str) -> bool:
    lower = text.lower()
    if len(text) < 45 or len(answer) < 35:
        return False
    if any(bad in lower for bad in ('как языковая модель', 'невозможно определить', 'нет данных', 'json')):
        return False
    if item.assessment_type == 'diagnostic':
        return all(mark in text for mark in ('A.', 'B.', 'C.', 'D.')) and ('правиль' in answer.lower() or 'ответ' in answer.lower())
    if item.assessment_type in {'practice', 'credit_practice'}:
        return lower.startswith('практическое задание') or any(word in lower[:180] for word in ('разработайте', 'составьте', 'подготовьте', 'опишите'))
    return lower.startswith('вопрос') or '?' in text[:260]


def _text(kind: str, topic: str, index: int) -> str:
    text, _, _ = _adapt_system_draft(kind, topic, index, '', '', [])
    return text


def _answer(kind: str, topic: str) -> str:
    _, answer, _ = _adapt_system_draft(kind, topic, 0, '', '', [])
    return answer


def _criteria(kind: str) -> list[str]:
    _, _, criteria = _adapt_system_draft(kind, 'тема дисциплины', 0, '', '', [])
    return criteria


def _summary(program: models.Program, fund: models.AssessmentFund, items: list[AssessmentItemRead], built_now: bool, llm_meta: dict, *, restored_from_file: bool = False, matched_by_name: bool = False) -> dict:
    counts = {code: 0 for code, *_ in SECTIONS}
    for item in items:
        counts[item.section_code] = counts.get(item.section_code, 0) + 1
    bank_path = _bank_file_path(program)
    return {
        'ready': len(items) >= TOTAL,
        'built_now': built_now,
        'program_id': program.id,
        'filename': program.filename,
        'fund_id': fund.id,
        'mode': QWEN_SOURCE_KIND if llm_meta.get('used') else SOURCE_KIND,
        'model_version': MODEL_VERSION,
        'total_items': len(items),
        'planned_items': TOTAL,
        'sections': [{'code': code, 'title': title, 'assessment_type': typ, 'planned_items': plan, 'generated_items': counts.get(code, 0)} for code, title, typ, plan in SECTIONS],
        'sample_items': items[:18],
        'llm': llm_meta,
        'matched_by_name': matched_by_name,
        'restored_from_file': restored_from_file,
        'persistent': bank_path.exists(),
        'persistent_path': str(bank_path),
    }


def _empty(program: models.Program) -> dict:
    bank_path = _bank_file_path(program)
    return {
        'ready': False,
        'built_now': False,
        'program_id': program.id,
        'filename': program.filename,
        'fund_id': '',
        'mode': SOURCE_KIND,
        'model_version': MODEL_VERSION,
        'total_items': 0,
        'planned_items': TOTAL,
        'sections': [{'code': code, 'title': title, 'assessment_type': typ, 'planned_items': plan, 'generated_items': 0} for code, title, typ, plan in SECTIONS],
        'sample_items': [],
        'llm': {'enabled': False, 'used': False, 'calls': 0, 'refined': 0, 'seconds': 0, 'pipeline': 'not-ready'},
        'matched_by_name': False,
        'restored_from_file': False,
        'persistent': bank_path.exists(),
        'persistent_path': str(bank_path),
    }


def _save_bank_file(*, program: models.Program, items: list[AssessmentItemRead], llm_meta: dict) -> None:
    PERSISTENT_BANK_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        'schema_version': 2,
        'model_version': MODEL_VERSION,
        'source_filename': program.filename,
        'bank_key': _name_key(program.filename),
        'discipline_name': _discipline_name(program),
        'saved_at': datetime.now(timezone.utc).isoformat(),
        'planned_items': TOTAL,
        'sections': [{'code': code, 'title': title, 'assessment_type': typ, 'planned_items': plan} for code, title, typ, plan in SECTIONS],
        'llm': llm_meta,
        'items': [item.model_dump() for item in items],
    }
    _bank_file_path(program).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def _load_bank_file_for_program(program: models.Program) -> dict | None:
    PERSISTENT_BANK_DIR.mkdir(parents=True, exist_ok=True)
    direct_path = _bank_file_path(program)
    if direct_path.exists():
        return _read_bank_file(direct_path)
    target = _name_key(program.filename)
    for path in sorted(PERSISTENT_BANK_DIR.glob('*.json'), key=lambda item: item.stat().st_mtime, reverse=True):
        data = _read_bank_file(path)
        if not data:
            continue
        key = _name_key(data.get('source_filename') or data.get('bank_key') or path.stem)
        if key == target or target in key or key in target:
            return data
    return None


def _read_bank_file(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _bank_file_path(program: models.Program) -> Path:
    key = _name_key(program.filename) or str(program.id)
    return PERSISTENT_BANK_DIR / f'{key}.json'


def _sections(topics: list[str]) -> list[AssessmentFundSection]:
    return [AssessmentFundSection(code=code, title=title, description=f'Подготовленный банк общей системы. План: {plan}.', assessment_type=typ, enabled=True, topics=topics, planned_items=plan, generated_items=plan) for code, title, typ, plan in SECTIONS]


def _competency_schemas(codes: list[str]) -> list[AssessmentCompetencyRead]:
    return [AssessmentCompetencyRead(id=str(uuid4()), code=code, description=f'Компетенция {code}', indicators=[f'Применяет знания для выполнения заданий {code}.'], levels=['Пороговый', 'Повышенный', 'Продвинутый']) for code in codes]


def _topics(program: models.Program) -> list[str]:
    return [str(item).strip() for item in _load(program.topics_json) if str(item).strip()] or ['Общие положения дисциплины']


def _competencies(program: models.Program) -> list[str]:
    return [str(item).strip() for item in _load(program.competencies_json) if str(item).strip()] or ['ПК-1']


def _learning_outcomes(program: models.Program) -> list[str]:
    return [str(item).strip() for item in _load(program.learning_outcomes_json) if str(item).strip()]


def _discipline_name(program: models.Program) -> str:
    return program.filename.rsplit('.', 1)[0].replace('_', ' ').strip() or 'Наименование дисциплины'


def _item_type(kind: str) -> str:
    return {'oral': 'theoretical_open', 'credit': 'theoretical_open', 'practice': 'practice', 'credit_practice': 'practice', 'diagnostic': 'single_choice'}.get(kind, 'open')


def _indicator(program: models.Program, topic: str, competency: str) -> str:
    context = _topic_context(program, topic, 180)
    if context:
        return f'Проверяется тема «{topic}», компетенция {competency}. Контекст РПД: {context}'
    return f'Проверяется тема «{topic}» и компетенция {competency}.'


def _topic_context(program: models.Program, topic: str, limit: int = 420) -> str:
    topic_words = [word for word in re.split(r'\W+', topic.lower().replace('ё', 'е')) if len(word) >= 5]
    candidates: list[str] = []
    for value in _learning_outcomes(program):
        if _has_topic_overlap(value, topic_words):
            candidates.append(value)
    for raw_line in re.split(r'[\n\r]+', program.text_preview or ''):
        line = _clean(raw_line)
        if 20 <= len(line) <= 260 and _has_topic_overlap(line, topic_words):
            candidates.append(line)
        if len(' '.join(candidates)) > limit * 1.5:
            break
    if not candidates:
        outcomes = _learning_outcomes(program)
        candidates = outcomes[:2] if outcomes else [f'Тема РПД: {topic}']
    value = '; '.join(dict.fromkeys(candidates))
    return _compact(value, limit)


def _has_topic_overlap(value: str, topic_words: list[str]) -> bool:
    if not topic_words:
        return False
    normalized = value.lower().replace('ё', 'е')
    return any(word in normalized for word in topic_words[:6])


def _function_or_module_hint(topic: str, index: int) -> str:
    topic_lower = topic.lower()
    if any(word in topic_lower for word in ('данн', 'баз', 'sql', 'хранен')):
        variants = ('функции сохранения и получения данных', 'модуля работы с данными', 'метода проверки структуры данных')
    elif any(word in topic_lower for word in ('интерфейс', 'react', 'пользоват', 'форм')):
        variants = ('компонента пользовательского интерфейса', 'функции обработки действия пользователя', 'модуля отображения результата')
    elif any(word in topic_lower for word in ('тест', 'качеств', 'провер')):
        variants = ('функции проверки качества результата', 'модуля валидации', 'набора тест-кейсов')
    elif any(word in topic_lower for word in ('алгоритм', 'генерац', 'нейро', 'модель')):
        variants = ('алгоритма генерации задания', 'модуля интеллектуальной обработки', 'функции формирования результата')
    else:
        variants = ('функции обработки выбранной темы', 'модуля решения прикладной задачи', 'компонента программного обеспечения')
    return variants[index % len(variants)]


def _artifact(index: int) -> str:
    artifacts = ('псевдокод функции', 'таблицу входных и выходных данных', 'набор тест-кейсов', 'чек-лист проверки', 'описание алгоритма', 'схему компонентов')
    return artifacts[index % len(artifacts)]


def _contract(kind: str) -> str:
    if kind in {'oral', 'credit'}:
        return 'Сделай один конкретный устный вопрос и конкретный эталонный ответ.'
    if kind in {'practice', 'credit_practice'}:
        return 'Сделай практическое задание с проверяемым результатом и эталонным описанием результата.'
    if kind == 'diagnostic':
        return 'Сделай тест с вариантами A-D и правильным ответом с объяснением.'
    return 'Сделай задание по типу раздела ФОС.'


def _repair_prefix(text: str, kind: str) -> str:
    lower = text.lower()
    if kind in {'oral', 'credit'} and not lower.startswith('вопрос'):
        return f'Вопрос: {text[:1].lower()}{text[1:]}'
    if kind == 'diagnostic' and not ('a.' in lower and 'b.' in lower and 'c.' in lower):
        return f'Тестовое задание: {text}'
    if kind in {'practice', 'credit_practice'} and not lower.startswith('практическое задание'):
        return f'Практическое задание: {text}'
    return text


def _name_key(value: str) -> str:
    value = (value or '').lower().replace('ё', 'е')
    value = re.sub(r'\.(docx|pdf|txt)$', '', value)
    value = re.sub(r'[^a-zа-я0-9]+', '', value)
    return value


def _compact(value: str, limit: int) -> str:
    value = _clean(value).replace('|', '/')
    return value if len(value) <= limit else f'{value[:limit].rstrip()}...'


def _clean(value) -> str:
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _load(value: str) -> list:
    try:
        data = json.loads(value or '[]')
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []
