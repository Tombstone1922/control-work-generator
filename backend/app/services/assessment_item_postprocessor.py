from __future__ import annotations

import re
from collections import Counter

from app.schemas import AssessmentItemRead
from app.services.assessment_item_smart_builder import build_smart_task, normalize_topic, should_rebuild_text

FORBIDDEN_PHRASES = (
    "перечень компетенций",
    "уровни их сформированности",
    "в процессе освоения образовательной программы",
    "критерии определения сформированности",
    "индекс компетенции",
    "содержание компетенции",
    "код и наименование индикатора",
    "виды занятий для формирования",
    "оценочные средства для оценки",
    "методические, оценочные материалы",
    "процедуры оценивания сформированности",
    "оценочные средства для текущего контроля",
    "вопросы для устного опроса",
    "#default#",
)

SECTION_HEADING_RE = re.compile(r"^(?:\d+(?:\.\d+)*\s+)?(?:перечень|методические|оценочные|критерии|таблица)\b", re.IGNORECASE)


def postprocess_generated_items(items: list[AssessmentItemRead]) -> tuple[list[AssessmentItemRead], list[str]]:
    cleaned: list[AssessmentItemRead] = []
    warnings: list[str] = []
    seen: set[tuple[str, str]] = set()
    removed_bad = 0
    removed_duplicates = 0
    rebuilt_generic = 0

    for index, item in enumerate(items):
        text = clean_text(item.text)
        answer = clean_text(item.answer)
        topic = clean_topic(item.topic)
        criteria = [clean_text(value) for value in (item.criteria or [])]
        criteria = [value for value in criteria if value and not is_bad_text(value)]

        if is_bad_text(text) or len(text) < 8:
            removed_bad += 1
            continue

        if should_rebuild_text(text, answer):
            task = build_smart_task(
                topic=topic,
                assessment_type=item.assessment_type,
                item_type=item.item_type,
                index=index,
                difficulty=item.difficulty,
            )
            topic = task.topic
            text = task.text
            answer = task.answer
            criteria = task.criteria
            rebuilt_generic += 1

        normalized_key = normalize_for_key(text)
        key = (item.section_code, normalized_key)
        if key in seen:
            removed_duplicates += 1
            continue
        seen.add(key)

        cleaned.append(item.model_copy(update={
            "text": text,
            "answer": answer,
            "topic": topic,
            "criteria": criteria[:6],
        }))

    if removed_bad:
        warnings.append(f"Очистка банка заданий удалила мусорные OM-фрагменты: {removed_bad}.")
    if rebuilt_generic:
        warnings.append(f"Умный конструктор перестроил слишком общие задания: {rebuilt_generic}.")
    if removed_duplicates:
        warnings.append(f"Очистка банка заданий удалила дубли заданий: {removed_duplicates}.")
    return cleaned, warnings


def clean_topic(value: str) -> str:
    return normalize_topic(value)


def clean_text(value: str | None) -> str:
    value = (value or "").replace("\ufffe", "-").replace("\u00ad", "")
    value = value.replace("#default#", "")
    value = re.sub(r"\s+", " ", value).strip(" .;:-—\t\n\r")
    return value


def is_bad_text(value: str) -> bool:
    lower = value.lower()
    if any(phrase in lower for phrase in FORBIDDEN_PHRASES):
        return True
    if SECTION_HEADING_RE.match(value):
        return True
    if _looks_like_table_dump(value):
        return True
    return False


def normalize_for_key(value: str) -> str:
    value = value.lower().replace("ё", "е")
    value = re.sub(r"[^a-zа-я0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _looks_like_table_dump(value: str) -> bool:
    tokens = re.findall(r"[А-Яа-яA-Za-z0-9-]+", value)
    if len(tokens) > 120:
        common = Counter(token.lower() for token in tokens)
        service_hits = sum(common[word] for word in ("компетенции", "сформированности", "оценочные", "обучающегося", "дисциплины"))
        return service_hits >= 5
    return False
