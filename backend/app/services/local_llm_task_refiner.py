from __future__ import annotations

import json
import os
import re
from difflib import SequenceMatcher

from app.schemas import AssessmentItemRead
from app.services.assessment_item_smart_builder import normalize_topic
from app.services.discipline_knowledge_base import get_topic_knowledge_context
from app.services.local_llm_client import LocalLLMClient, get_local_llm_settings

SYSTEM_PROMPT = """
Ты вузовский преподаватель, методист и разработчик фонда оценочных средств.
Твоя задача — улучшить ОДНО оценочное задание по дисциплине.
Используй только переданный контекст, не выдумывай лишние темы.
Сделай задание предметным, проверяемым и отличающимся от уже созданных заданий.
Не повторяй формулировки из списка запретов.
Верни строго JSON без markdown и без пояснений.
JSON-схема:
{
  "text": "формулировка задания",
  "answer": "краткий эталонный ответ или структура эталонного решения",
  "criteria": ["критерий 1", "критерий 2", "критерий 3"],
  "uniqueness_reason": "чем это задание отличается"
}
""".strip()


def refine_items_with_local_llm(
    *,
    items: list[AssessmentItemRead],
    discipline_name: str,
    all_topics: list[str],
) -> tuple[list[AssessmentItemRead], list[str]]:
    settings = get_local_llm_settings()
    if not settings.enabled:
        return items, []

    client = LocalLLMClient(settings)
    max_items = int(os.getenv("LOCAL_LLM_MAX_ITEMS", "24"))
    refined: list[AssessmentItemRead] = []
    warnings: list[str] = []
    used_texts: list[str] = []
    refined_count = 0
    failed_count = 0
    skipped_similar = 0

    for index, item in enumerate(items):
        if index >= max_items:
            refined.append(item)
            used_texts.append(item.text)
            continue

        context = get_topic_knowledge_context(
            discipline_name=discipline_name,
            topic=normalize_topic(item.topic),
            all_topics=all_topics,
        )
        prompt = _build_prompt(item=item, discipline_name=discipline_name, context=context, used_texts=used_texts[-12:])
        data = client.chat_json(system_prompt=SYSTEM_PROMPT, user_prompt=prompt)
        if not data:
            refined.append(item)
            used_texts.append(item.text)
            failed_count += 1
            continue

        candidate = _sanitize_llm_result(data)
        if not candidate:
            refined.append(item)
            used_texts.append(item.text)
            failed_count += 1
            continue

        text = candidate["text"]
        if _too_similar(text, used_texts, threshold=0.86):
            refined.append(item)
            used_texts.append(item.text)
            skipped_similar += 1
            continue

        updated = item.model_copy(update={
            "text": text,
            "answer": candidate["answer"],
            "criteria": candidate["criteria"],
            "source_kind": "local_llm_qwen3",
            "source_context": (
                f"Local LLM refiner; model={settings.model}; "
                f"topic=«{normalize_topic(item.topic)}»; reason={candidate.get('uniqueness_reason', '')}"
            ),
        })
        refined.append(updated)
        used_texts.append(text)
        refined_count += 1

    if refined_count:
        warnings.append(f"Локальная LLM улучшила формулировки заданий: {refined_count}; модель: {settings.model}.")
    if failed_count:
        warnings.append(f"Локальная LLM не ответила или вернула некорректный JSON для заданий: {failed_count}; оставлены базовые задания.")
    if skipped_similar:
        warnings.append(f"Локальная LLM предложила слишком похожие формулировки: {skipped_similar}; оставлены базовые задания.")
    return refined, warnings


def _build_prompt(*, item: AssessmentItemRead, discipline_name: str, context, used_texts: list[str]) -> str:
    payload = {
        "discipline_name": discipline_name,
        "topic": normalize_topic(item.topic),
        "assessment_type": item.assessment_type,
        "item_type": item.item_type,
        "difficulty": item.difficulty,
        "competency_code": item.competency_code,
        "indicator": item.indicator,
        "base_task": {
            "text": item.text,
            "answer": item.answer,
            "criteria": item.criteria,
        },
        "knowledge_context": {
            "profile_name": context.profile_name,
            "related_topics": context.related_topics,
            "learning_outcomes": context.learning_outcomes,
            "competencies": context.competencies,
            "key_terms": context.key_terms,
            "source": context.source,
        },
        "already_created_tasks_do_not_repeat": used_texts,
        "requirements": [
            "Сделай задание конкретным для темы и дисциплины.",
            "Добавь проверяемый результат: артефакт, расчёт, фрагмент кода, чек-лист, схема, SQL-запрос, тест-кейс или анализ кейса — в зависимости от темы.",
            "Не используй общую формулировку вида 'раскройте тему' без предметного действия.",
            "Ответ и критерии должны соответствовать заданию.",
            "Верни только JSON по схеме из system prompt.",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _sanitize_llm_result(data: dict) -> dict | None:
    text = _clean_text(data.get("text"))
    answer = _clean_text(data.get("answer"))
    criteria_raw = data.get("criteria")
    if not isinstance(criteria_raw, list):
        criteria_raw = []
    criteria = [_clean_text(item) for item in criteria_raw if _clean_text(item)]
    uniqueness_reason = _clean_text(data.get("uniqueness_reason"))

    if len(text) < 30 or len(text) > 1200:
        return None
    if len(answer) < 20:
        return None
    if len(criteria) < 2:
        return None
    if _looks_like_meta_text(text):
        return None
    return {
        "text": text,
        "answer": answer,
        "criteria": criteria[:5],
        "uniqueness_reason": uniqueness_reason,
    }


def _clean_text(value) -> str:
    value = str(value or "").replace("#default#", "")
    value = re.sub(r"\s+", " ", value).strip(" .;:-—\t\n\r")
    return value


def _too_similar(text: str, used_texts: list[str], threshold: float) -> bool:
    current = _norm(text)
    return any(SequenceMatcher(None, current, _norm(value)).ratio() >= threshold for value in used_texts if value)


def _looks_like_meta_text(value: str) -> bool:
    lower = value.lower()
    bad = (
        "перечень компетенций",
        "методические, оценочные материалы",
        "код и наименование индикатора",
        "уровни их сформированности",
        "я не могу",
        "как языковая модель",
    )
    return any(item in lower for item in bad)


def _norm(value: str) -> str:
    value = (value or "").lower().replace("ё", "е")
    value = re.sub(r"[^a-zа-я0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()
