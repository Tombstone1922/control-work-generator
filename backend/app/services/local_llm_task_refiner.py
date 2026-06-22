from __future__ import annotations

import json
import os
import re
from difflib import SequenceMatcher

from app.schemas import AssessmentItemRead
from app.services.assessment_item_smart_builder import normalize_topic
from app.services.discipline_knowledge_base import get_topic_knowledge_context
from app.services.local_llm_client import LocalLLMClient, get_local_llm_settings

SINGLE_SYSTEM_PROMPT = """
Ты вузовский преподаватель, методист и разработчик фонда оценочных средств.
Твоя задача — улучшить ОДНО оценочное задание по дисциплине.
Используй только переданный контекст, не выдумывай лишние темы.
Сделай задание предметным, проверяемым и отличающимся от уже созданных заданий.
Строго соблюдай жанр задания по assessment_type.
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

BATCH_SYSTEM_PROMPT = """
Ты вузовский преподаватель, методист и разработчик фонда оценочных средств.
Ты улучшаешь пакет оценочных заданий по дисциплине.
Используй только переданный контекст и не выдумывай темы вне дисциплины.
Каждое задание должно быть предметным, проверяемым и отличаться от остальных.
Строго соблюдай жанр каждого задания по assessment_type.
Не оставляй шаблонные формулировки. Не пиши markdown. Не пиши рассуждения.
Верни строго JSON-объект:
{
  "items": [
    {
      "index": 0,
      "text": "формулировка задания",
      "answer": "краткий эталонный ответ или структура эталонного решения",
      "criteria": ["критерий 1", "критерий 2", "критерий 3"],
      "uniqueness_reason": "чем это задание отличается"
    }
  ]
}
""".strip()

TYPE_CONTRACTS = {
    "oral": "Устное задание должно быть именно вопросом для ответа студента. Начни с 'Вопрос:'. Не проси разрабатывать проект, писать код или выполнять практическую работу. answer должен описывать ожидаемый устный ответ.",
    "exam_questions": "Экзаменационный вопрос должен быть именно вопросом для ответа студента. Начни с 'Вопрос:'. answer должен быть краткой структурой правильного ответа.",
    "credit": "Зачетный вопрос должен быть именно вопросом для ответа студента. Начни с 'Вопрос:'. answer должен быть краткой структурой правильного ответа.",
    "practice": "Практическое задание должно требовать выполнить конкретное действие и получить проверяемый результат: код, схему, таблицу, SQL-запрос, тест-кейс, чек-лист, прототип, документ или анализ кейса. Начни с 'Практическое задание:'.",
    "exam_practice": "Практическое экзаменационное задание должно требовать выполнить конкретную практическую задачу с проверяемым результатом. Начни с 'Практическое задание:'.",
    "laboratory": "Лабораторное задание должно требовать выполнить эксперимент/реализацию/проверку и зафиксировать результат. Начни с 'Лабораторное задание:'.",
    "coursework": "Курсовая должна быть темой курсовой работы, а не обычным практическим заданием. Начни с 'Тема курсовой работы:'. В answer дай ожидаемую структуру курсовой.",
    "course_project": "Курсовой проект должен быть темой курсового проекта, а не обычным заданием. Начни с 'Тема курсового проекта:'. В answer дай ожидаемую структуру проекта.",
    "control_work": "Контрольная работа должна быть самостоятельным проверочным заданием с условиями, ходом решения и проверяемым результатом. Начни с 'Контрольное задание:'.",
    "diagnostic": "Диагностическое задание должно проверять текущий уровень освоения темы через выбор, краткое решение или анализ ситуации. Начни с 'Диагностическое задание:'.",
    "test_bank": "Тестовое задание должно быть проверочным вопросом или мини-задачей с однозначной проверкой. Не превращай его в курсовую или лабораторную.",
}


def refine_items_with_local_llm(
    *,
    items: list[AssessmentItemRead],
    discipline_name: str,
    all_topics: list[str],
) -> tuple[list[AssessmentItemRead], list[str]]:
    settings = get_local_llm_settings()
    if not settings.enabled:
        return items, []

    mode = os.getenv("LOCAL_LLM_REFINEMENT_MODE", "single").strip().lower()
    if mode == "batch":
        return _refine_items_batch(items=items, discipline_name=discipline_name, all_topics=all_topics)
    return _refine_items_single(items=items, discipline_name=discipline_name, all_topics=all_topics)


def _refine_items_single(
    *,
    items: list[AssessmentItemRead],
    discipline_name: str,
    all_topics: list[str],
) -> tuple[list[AssessmentItemRead], list[str]]:
    settings = get_local_llm_settings()
    client = LocalLLMClient(settings)
    max_items = _env_int("LOCAL_LLM_MAX_ITEMS", 24, minimum=1, maximum=max(len(items), 1))
    force_rewrite = _env_bool("LOCAL_LLM_FORCE_REWRITE", False)

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
        prompt = _build_single_prompt(
            item=item,
            discipline_name=discipline_name,
            context=context,
            used_texts=used_texts[-12:],
        )
        data = client.chat_json(system_prompt=SINGLE_SYSTEM_PROMPT, user_prompt=prompt)
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
        if not _matches_type_contract(text, item.assessment_type, item.item_type):
            refined.append(item)
            used_texts.append(item.text)
            failed_count += 1
            continue
        if not force_rewrite and _too_similar(text, used_texts, threshold=0.86):
            refined.append(item)
            used_texts.append(item.text)
            skipped_similar += 1
            continue
        if _too_similar(text, used_texts, threshold=0.96):
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
                f"Local LLM single refiner; model={settings.model}; "
                f"topic=«{normalize_topic(item.topic)}»; reason={candidate.get('uniqueness_reason', '')}"
            ),
        })
        refined.append(updated)
        used_texts.append(text)
        refined_count += 1

    if refined_count:
        warnings.append(f"Локальная LLM улучшила формулировки заданий: {refined_count}; режим: single; модель: {settings.model}.")
    if failed_count:
        warnings.append(f"Локальная LLM не ответила, вернула некорректный JSON или нарушила тип задания: {failed_count}; оставлены базовые задания.")
    if skipped_similar:
        warnings.append(f"Локальная LLM предложила слишком похожие формулировки: {skipped_similar}; оставлены базовые задания.")
    return refined, warnings


def _refine_items_batch(
    *,
    items: list[AssessmentItemRead],
    discipline_name: str,
    all_topics: list[str],
) -> tuple[list[AssessmentItemRead], list[str]]:
    settings = get_local_llm_settings()
    client = LocalLLMClient(settings)
    max_items = _env_int("LOCAL_LLM_MAX_ITEMS", 60, minimum=1, maximum=max(len(items), 1))
    batch_size = _env_int("LOCAL_LLM_BATCH_SIZE", 6, minimum=1, maximum=10)
    force_rewrite = _env_bool("LOCAL_LLM_FORCE_REWRITE", True)

    refined: list[AssessmentItemRead] = []
    warnings: list[str] = []
    used_texts: list[str] = []
    refined_count = 0
    failed_count = 0
    skipped_similar = 0
    batches_count = 0

    target_items = items[:max_items]
    tail_items = items[max_items:]

    for batch_start in range(0, len(target_items), batch_size):
        batch = target_items[batch_start : batch_start + batch_size]
        prompt = _build_batch_prompt(
            batch=batch,
            batch_start=batch_start,
            discipline_name=discipline_name,
            all_topics=all_topics,
            used_texts=used_texts[-18:],
        )
        data = client.chat_json(system_prompt=BATCH_SYSTEM_PROMPT, user_prompt=prompt)
        batches_count += 1
        if not data:
            refined.extend(batch)
            used_texts.extend(item.text for item in batch)
            failed_count += len(batch)
            continue

        candidates = _sanitize_batch_result(data)
        if not candidates:
            refined.extend(batch)
            used_texts.extend(item.text for item in batch)
            failed_count += len(batch)
            continue

        candidate_by_index = {candidate["index"]: candidate for candidate in candidates}
        for local_index, item in enumerate(batch):
            candidate = candidate_by_index.get(batch_start + local_index) or candidate_by_index.get(local_index)
            if not candidate:
                refined.append(item)
                used_texts.append(item.text)
                failed_count += 1
                continue

            text = candidate["text"]
            if not _matches_type_contract(text, item.assessment_type, item.item_type):
                refined.append(item)
                used_texts.append(item.text)
                failed_count += 1
                continue
            if not force_rewrite and _too_similar(text, used_texts, threshold=0.88):
                refined.append(item)
                used_texts.append(item.text)
                skipped_similar += 1
                continue
            if _too_similar(text, used_texts, threshold=0.96):
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
                    f"Local LLM batch refiner; model={settings.model}; "
                    f"batch_size={batch_size}; topic=«{normalize_topic(item.topic)}»; "
                    f"reason={candidate.get('uniqueness_reason', '')}"
                ),
            })
            refined.append(updated)
            used_texts.append(text)
            refined_count += 1

    refined.extend(tail_items)

    if refined_count:
        warnings.append(
            f"Локальная LLM агрессивно улучшила формулировки заданий: {refined_count}; "
            f"режим: batch; пакетов: {batches_count}; модель: {settings.model}."
        )
    if failed_count:
        warnings.append(
            f"Локальная LLM не вернула корректный JSON или нарушила тип задания: {failed_count}; "
            "для них оставлены базовые задания."
        )
    if skipped_similar:
        warnings.append(f"Локальная LLM предложила слишком похожие формулировки: {skipped_similar}; оставлены базовые задания.")
    return refined, warnings


def _build_single_prompt(*, item: AssessmentItemRead, discipline_name: str, context, used_texts: list[str]) -> str:
    payload = {
        "discipline_name": discipline_name,
        "topic": normalize_topic(item.topic),
        "assessment_type": item.assessment_type,
        "item_type": item.item_type,
        "type_contract": _type_contract(item.assessment_type, item.item_type),
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
            "Строго соблюдай type_contract.",
            "Сделай формулировку конкретной для темы и дисциплины.",
            "Не смешивай жанры: устный вопрос не должен быть практическим заданием, курсовая не должна быть обычным заданием.",
            "Для практических заданий добавь проверяемый результат: артефакт, расчёт, фрагмент кода, чек-лист, схема, SQL-запрос, тест-кейс или анализ кейса — в зависимости от темы.",
            "Ответ и критерии должны соответствовать именно этому типу задания.",
            "Верни только JSON по схеме из system prompt.",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _build_batch_prompt(
    *,
    batch: list[AssessmentItemRead],
    batch_start: int,
    discipline_name: str,
    all_topics: list[str],
    used_texts: list[str],
) -> str:
    payload_items = []
    for local_index, item in enumerate(batch):
        context = get_topic_knowledge_context(
            discipline_name=discipline_name,
            topic=normalize_topic(item.topic),
            all_topics=all_topics,
        )
        payload_items.append({
            "index": batch_start + local_index,
            "topic": normalize_topic(item.topic),
            "assessment_type": item.assessment_type,
            "item_type": item.item_type,
            "type_contract": _type_contract(item.assessment_type, item.item_type),
            "difficulty": item.difficulty,
            "competency_code": item.competency_code,
            "indicator": _trim(item.indicator, 260),
            "base_task": {
                "text": _trim(item.text, 420),
                "answer": _trim(item.answer, 260),
                "criteria": item.criteria[:4],
            },
            "knowledge_context": {
                "profile_name": context.profile_name,
                "related_topics": context.related_topics[:4],
                "learning_outcomes": [_trim(value, 180) for value in context.learning_outcomes[:3]],
                "competencies": context.competencies[:4],
                "key_terms": context.key_terms[:8],
                "source": context.source,
            },
        })

    payload = {
        "discipline_name": discipline_name,
        "already_created_tasks_do_not_repeat": [_trim(value, 260) for value in used_texts],
        "items": payload_items,
        "requirements": [
            "Строго соблюдай type_contract для каждого item.",
            "Не смешивай жанры: oral/exam/credit — это вопрос; practice/laboratory — практическое выполнение; coursework/course_project — тема курсовой.",
            "Перепиши каждое задание сильнее базового варианта, но не меняй его тип.",
            "Для каждого входного item верни один выходной item с тем же index.",
            "Ответ и критерии должны соответствовать типу задания.",
            "Верни только JSON по схеме из system prompt.",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _sanitize_batch_result(data: dict) -> list[dict]:
    raw_items = data.get("items")
    if not isinstance(raw_items, list):
        raw_items = [data]
    result: list[dict] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        candidate = _sanitize_llm_result(raw)
        if not candidate:
            continue
        try:
            candidate["index"] = int(raw.get("index", len(result)))
        except (TypeError, ValueError):
            candidate["index"] = len(result)
        result.append(candidate)
    return result


def _sanitize_llm_result(data: dict) -> dict | None:
    text = _clean_text(data.get("text"))
    answer = _clean_text(data.get("answer"))
    criteria_raw = data.get("criteria")
    if not isinstance(criteria_raw, list):
        criteria_raw = []
    criteria = [_clean_text(item) for item in criteria_raw if _clean_text(item)]
    uniqueness_reason = _clean_text(data.get("uniqueness_reason"))

    if len(text) < 30 or len(text) > 1400:
        return None
    if len(answer) < 15:
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


def _type_contract(assessment_type: str, item_type: str) -> str:
    if item_type in {"coursework_topic", "project_topic"}:
        return TYPE_CONTRACTS.get("course_project") if item_type == "project_topic" else TYPE_CONTRACTS.get("coursework")
    return TYPE_CONTRACTS.get(assessment_type, TYPE_CONTRACTS["practice"])


def _matches_type_contract(text: str, assessment_type: str, item_type: str) -> bool:
    lower = _clean_text(text).lower()
    if assessment_type in {"oral", "exam_questions", "credit"}:
        return lower.startswith("вопрос") or "?" in text[:240]
    if assessment_type in {"coursework", "course_project"} or item_type in {"coursework_topic", "project_topic"}:
        return lower.startswith("тема курсов")
    if assessment_type in {"practice", "exam_practice"}:
        return lower.startswith("практическое задание") or any(word in lower[:120] for word in ("разработайте", "выполните", "спроектируйте", "реализуйте", "составьте"))
    if assessment_type == "laboratory":
        return lower.startswith("лабораторное задание") or "лаборатор" in lower[:140]
    if assessment_type == "control_work":
        return lower.startswith("контрольное задание") or "контрольн" in lower[:140]
    return True


def _clean_text(value) -> str:
    value = str(value or "").replace("#default#", "")
    value = re.sub(r"\s+", " ", value).strip(" .;:-—\t\n\r")
    return value


def _trim(value: str, limit: int) -> str:
    value = _clean_text(value)
    return value if len(value) <= limit else f"{value[:limit].rstrip()}…"


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


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "да"}


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))
