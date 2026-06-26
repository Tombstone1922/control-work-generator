from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from app.schemas import AssessmentItemRead
from app.services.assessment_item_smart_builder import normalize_topic
from app.services.discipline_knowledge_base import get_topic_knowledge_context
from app.services.local_llm_client import QWEN35_PROFILE, LocalLLMClient, get_local_llm_settings

SYSTEM_PROMPT = """
Ты методист вуза. Улучши оценочные задания по ФОС.
Не меняй тип задания. Используй только переданный контекст.
Главное поле результата — text. Если answer или criteria не меняются, их можно вернуть коротко.
Верни строго JSON без markdown: {"items":[{"index":0,"text":"...","answer":"...","criteria":["...","..."]}]}.
""".strip()

TYPE_CONTRACTS = {
    "oral": "Начни с 'Вопрос:'. Это устный вопрос, не практическая работа.",
    "exam_questions": "Начни с 'Вопрос:'. Это экзаменационный вопрос.",
    "credit": "Начни с 'Вопрос:'. Это зачетный вопрос.",
    "practice": "Начни с 'Практическое задание:'. Нужен проверяемый результат.",
    "exam_practice": "Начни с 'Практическое задание:'. Нужен проверяемый результат.",
    "laboratory": "Начни с 'Лабораторное задание:'. Нужен эксперимент или реализация.",
    "coursework": "Начни с 'Тема курсовой работы:'.",
    "course_project": "Начни с 'Тема курсового проекта:'.",
    "control_work": "Начни с 'Контрольное задание:'.",
    "diagnostic": "Начни с 'Диагностическое задание:'.",
    "test_bank": "Это тестовое задание с однозначной проверкой.",
}

DEFAULT_SKIP_TYPES = "oral,exam_questions,credit,test_bank,diagnostic"


@dataclass
class LocalLLMRefinementProfile:
    enabled: bool = False
    mode: str = "disabled"
    model: str = ""
    profile: str = "default"
    base_url: str = ""
    max_items: int = 0
    batch_size: int = 0
    requested_items: int = 0
    attempted_items: int = 0
    refined_items: int = 0
    failed_items: int = 0
    skipped_by_type: int = 0
    skipped_similar: int = 0
    calls: int = 0
    total_ms: int = 0
    llm_ms: int = 0
    avg_call_ms: int = 0
    call_ms: list[int] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "mode": self.mode,
            "model": self.model,
            "profile": self.profile,
            "base_url": self.base_url,
            "max_items": self.max_items,
            "batch_size": self.batch_size,
            "requested_items": self.requested_items,
            "attempted_items": self.attempted_items,
            "refined_items": self.refined_items,
            "failed_items": self.failed_items,
            "skipped_by_type": self.skipped_by_type,
            "skipped_similar": self.skipped_similar,
            "calls": self.calls,
            "total_ms": self.total_ms,
            "llm_ms": self.llm_ms,
            "avg_call_ms": self.avg_call_ms,
            "call_ms": self.call_ms[:12],
        }


def refine_items_with_local_llm(
    *,
    items: list[AssessmentItemRead],
    discipline_name: str,
    all_topics: list[str],
    mode_override: str | None = None,
    skip_types_override: set[str] | None = None,
    force_rewrite_override: bool | None = None,
    max_items_override: int | None = None,
    batch_size_override: int | None = None,
    llm_profile_override: str | None = None,
) -> tuple[list[AssessmentItemRead], list[str], dict]:
    settings = get_local_llm_settings(llm_profile_override)
    if not settings.enabled:
        profile = LocalLLMRefinementProfile(
            enabled=False,
            model=settings.model,
            profile=settings.profile,
            base_url=settings.base_url,
            requested_items=len(items),
        ).as_dict()
        return items, [], profile

    mode = (mode_override or os.getenv("LOCAL_LLM_REFINEMENT_MODE", "auto")).strip().lower()
    if mode in {"off", "disabled", "false", "0", "none"}:
        profile = LocalLLMRefinementProfile(
            enabled=False,
            mode="disabled_by_mode",
            model=settings.model,
            profile=settings.profile,
            base_url=settings.base_url,
            requested_items=len(items),
        ).as_dict()
        return items, ["Локальная LLM-прокачка отключена режимом LOCAL_LLM_REFINEMENT_MODE."], profile

    max_items = max_items_override if max_items_override is not None else _env_int("LOCAL_LLM_MAX_ITEMS", 10, minimum=1, maximum=max(len(items), 1))
    max_items = max(1, min(max(len(items), 1), int(max_items)))
    use_batch = mode == "batch" or (mode in {"auto", "single"} and _should_use_batch(items, max_items, skip_types_override))
    if batch_size_override is not None:
        batch_size = max(1, min(10, int(batch_size_override)))
    else:
        batch_size = _env_int("LOCAL_LLM_BATCH_SIZE", 4 if use_batch else 1, minimum=1, maximum=10)
    if not use_batch:
        batch_size = 1
    return _refine_items_batched(
        items=items,
        discipline_name=discipline_name,
        all_topics=all_topics,
        batch_size=batch_size,
        max_items=max_items,
        skip_types_override=skip_types_override,
        force_rewrite_override=force_rewrite_override,
        llm_profile_override=llm_profile_override,
    )


def _refine_items_batched(
    *,
    items: list[AssessmentItemRead],
    discipline_name: str,
    all_topics: list[str],
    batch_size: int,
    max_items: int,
    skip_types_override: set[str] | None = None,
    force_rewrite_override: bool | None = None,
    llm_profile_override: str | None = None,
) -> tuple[list[AssessmentItemRead], list[str], dict]:
    settings = get_local_llm_settings(llm_profile_override)
    client = LocalLLMClient(settings)
    skip_types = skip_types_override if skip_types_override is not None else _env_set("LOCAL_LLM_SKIP_TYPES", DEFAULT_SKIP_TYPES)
    force_rewrite = force_rewrite_override if force_rewrite_override is not None else _env_bool("LOCAL_LLM_FORCE_REWRITE", True)
    started = time.perf_counter()
    profile = LocalLLMRefinementProfile(
        enabled=True,
        mode="batch-fast" if batch_size > 1 else "single-fast",
        model=settings.model,
        profile=settings.profile,
        base_url=settings.base_url,
        max_items=max_items,
        batch_size=batch_size,
        requested_items=len(items),
    )

    target_items: list[AssessmentItemRead] = []
    tail_items: list[AssessmentItemRead] = []
    for item in items:
        if _should_skip_item(item, skip_types):
            tail_items.append(item)
            profile.skipped_by_type += 1
        elif len(target_items) < max_items:
            target_items.append(item)
        else:
            tail_items.append(item)
    profile.attempted_items = len(target_items)

    refined: list[AssessmentItemRead] = []
    warnings: list[str] = []
    used_texts: list[str] = []
    for batch_start in range(0, len(target_items), batch_size):
        batch = target_items[batch_start: batch_start + batch_size]
        prompt = _build_prompt(batch=batch, batch_start=batch_start, discipline_name=discipline_name, all_topics=all_topics, used_texts=used_texts[-10:])
        call_started = time.perf_counter()
        data = client.chat_json(system_prompt=SYSTEM_PROMPT, user_prompt=prompt)
        call_ms = int((time.perf_counter() - call_started) * 1000)
        profile.calls += 1
        profile.llm_ms += call_ms
        profile.call_ms.append(call_ms)
        candidates = _sanitize_batch_result(data or {})
        candidate_by_index = {candidate["index"]: candidate for candidate in candidates}

        for local_index, item in enumerate(batch):
            candidate = candidate_by_index.get(batch_start + local_index) or candidate_by_index.get(local_index)
            if not candidate:
                refined.append(item)
                used_texts.append(item.text)
                profile.failed_items += 1
                continue
            text = _repair_text_for_target_type(candidate["text"], item)
            if not _matches_type_contract(text, item.assessment_type, item.item_type):
                refined.append(item)
                used_texts.append(item.text)
                profile.failed_items += 1
                continue
            if not force_rewrite and _too_similar(text, used_texts, threshold=0.90):
                refined.append(item)
                used_texts.append(item.text)
                profile.skipped_similar += 1
                continue
            source_kind = "local_llm_qwen35" if settings.profile == QWEN35_PROFILE else "local_llm_qwen3"
            updated = item.model_copy(update={
                "text": text,
                "answer": candidate.get("answer") or item.answer,
                "criteria": candidate.get("criteria") or item.criteria,
                "source_kind": source_kind,
                "source_context": f"Local LLM {profile.mode}; profile={settings.profile}; model={settings.model}; batch_size={batch_size}; topic=«{normalize_topic(item.topic)}».",
            })
            refined.append(updated)
            used_texts.append(text)
            profile.refined_items += 1

    refined.extend(tail_items)
    profile.total_ms = int((time.perf_counter() - started) * 1000)
    profile.avg_call_ms = int(profile.llm_ms / profile.calls) if profile.calls else 0
    model_label = "Qwen3.5-9B" if settings.profile == QWEN35_PROFILE else "локальная LLM"
    if profile.refined_items:
        warnings.append(f"{model_label} улучшила задания: {profile.refined_items}; режим: {profile.mode}; запросов: {profile.calls}; модель: {settings.model}.")
    if profile.skipped_by_type:
        warnings.append(f"Локальная LLM пропустила быстрые типы заданий: {profile.skipped_by_type}.")
    if profile.failed_items:
        warnings.append(f"Локальная LLM не вернула пригодную формулировку для части заданий: {profile.failed_items}; оставлены базовые задания.")
    return refined, warnings, profile.as_dict()


def _build_prompt(*, batch: list[AssessmentItemRead], batch_start: int, discipline_name: str, all_topics: list[str], used_texts: list[str]) -> str:
    payload_items = []
    for local_index, item in enumerate(batch):
        context = get_topic_knowledge_context(discipline_name=discipline_name, topic=normalize_topic(item.topic), all_topics=all_topics)
        payload_items.append({
            "index": batch_start + local_index,
            "topic": normalize_topic(item.topic),
            "assessment_type": item.assessment_type,
            "item_type": item.item_type,
            "type_contract": _type_contract(item.assessment_type, item.item_type),
            "difficulty": item.difficulty,
            "competency_code": item.competency_code,
            "indicator": _trim(item.indicator, 120),
            "base_task": {"text": _trim(item.text, 240), "answer": _trim(item.answer, 80), "criteria": item.criteria[:2]},
            "knowledge_context": {
                "related_topics": context.related_topics[:2],
                "learning_outcomes": [_trim(value, 90) for value in context.learning_outcomes[:1]],
                "key_terms": context.key_terms[:4],
                "source": context.source,
            },
        })
    payload = {
        "discipline_name": discipline_name,
        "do_not_repeat": [_trim(value, 100) for value in used_texts],
        "items": payload_items,
        "requirements": [
            "Верни один item на каждый входной item с тем же index.",
            "Строго соблюдай type_contract.",
            "Можно улучшить только text; answer и criteria сделай короткими или оставь близкими к базовым.",
            "Только JSON.",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _sanitize_batch_result(data: dict) -> list[dict]:
    raw_items = data.get("items") if isinstance(data, dict) else None
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
    if len(text) < 25 or len(text) > 1000 or _looks_like_meta_text(text):
        return None
    return {"text": text, "answer": answer, "criteria": criteria[:4]}


def _type_contract(assessment_type: str, item_type: str) -> str:
    if item_type in {"coursework_topic", "project_topic"}:
        return TYPE_CONTRACTS.get("course_project") if item_type == "project_topic" else TYPE_CONTRACTS.get("coursework")
    return TYPE_CONTRACTS.get(assessment_type, TYPE_CONTRACTS["practice"])


def _repair_text_for_target_type(text: str, item: AssessmentItemRead) -> str:
    text = _clean_text(text)
    lower = text.lower()
    if item.assessment_type in {"oral", "exam_questions", "credit"} and not lower.startswith("вопрос"):
        return f"Вопрос: {text[:1].lower()}{text[1:]}" if text else text
    if item.assessment_type == "control_work" and not lower.startswith("контрольное задание"):
        return f"Контрольное задание: {text}"
    if item.assessment_type in {"practice", "exam_practice"} and not lower.startswith("практическое задание"):
        return f"Практическое задание: {text}"
    if item.assessment_type == "laboratory" and not lower.startswith("лабораторное задание"):
        return f"Лабораторное задание: {text}"
    if item.assessment_type == "coursework" and not lower.startswith("тема курсовой работы"):
        return f"Тема курсовой работы: {text}"
    if item.assessment_type == "course_project" and not lower.startswith("тема курсового проекта"):
        return f"Тема курсового проекта: {text}"
    return text


def _matches_type_contract(text: str, assessment_type: str, item_type: str) -> bool:
    lower = _clean_text(text).lower()
    if assessment_type in {"oral", "exam_questions", "credit"}:
        return lower.startswith("вопрос") or "?" in text[:220]
    if assessment_type in {"coursework", "course_project"} or item_type in {"coursework_topic", "project_topic"}:
        return lower.startswith("тема курсов")
    if assessment_type in {"practice", "exam_practice"}:
        return lower.startswith("практическое задание") or any(word in lower[:120] for word in ("разработайте", "выполните", "спроектируйте", "реализуйте", "составьте"))
    if assessment_type == "laboratory":
        return lower.startswith("лабораторное задание") or "лаборатор" in lower[:140]
    if assessment_type == "control_work":
        return lower.startswith("контрольное задание") or "контрольн" in lower[:140]
    return True


def _should_use_batch(items: list[AssessmentItemRead], max_items: int, skip_types_override: set[str] | None = None) -> bool:
    if not _env_bool("LOCAL_LLM_AUTO_BATCH", True):
        return False
    min_items = _env_int("LOCAL_LLM_AUTO_BATCH_MIN_ITEMS", 6, minimum=2, maximum=max(len(items), 2))
    skip_types = skip_types_override if skip_types_override is not None else _env_set("LOCAL_LLM_SKIP_TYPES", DEFAULT_SKIP_TYPES)
    target_count = 0
    for item in items:
        if _should_skip_item(item, skip_types):
            continue
        target_count += 1
        if target_count >= max_items:
            break
    return target_count >= min_items


def _should_skip_item(item: AssessmentItemRead, skip_types: set[str]) -> bool:
    return item.assessment_type in skip_types or item.item_type in skip_types


def _clean_text(value) -> str:
    value = str(value or "").replace("#default#", "")
    return re.sub(r"\s+", " ", value).strip(" .;:-—\t\n\r")


def _trim(value: str, limit: int) -> str:
    value = _clean_text(value)
    return value if len(value) <= limit else f"{value[:limit].rstrip()}…"


def _too_similar(text: str, used_texts: list[str], threshold: float) -> bool:
    current = _norm(text)
    return any(SequenceMatcher(None, current, _norm(value)).ratio() >= threshold for value in used_texts if value)


def _looks_like_meta_text(value: str) -> bool:
    lower = value.lower()
    return any(item in lower for item in ("перечень компетенций", "методические, оценочные материалы", "я не могу", "как языковая модель"))


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


def _env_set(name: str, default_csv: str) -> set[str]:
    value = os.getenv(name, default_csv)
    return {part.strip() for part in value.split(",") if part.strip()}
