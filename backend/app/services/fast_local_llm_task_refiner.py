from __future__ import annotations

import os

from app.schemas import AssessmentItemRead
from app.services.local_llm_client import get_local_llm_settings
from app.services.local_llm_task_refiner import (
    DEFAULT_SKIP_TYPES,
    LocalLLMRefinementProfile,
    _env_bool,
    _env_int,
    _env_set,
    _refine_items_batch,
    _refine_items_single,
    _should_skip_item,
)


def refine_items_with_local_llm(
    *,
    items: list[AssessmentItemRead],
    discipline_name: str,
    all_topics: list[str],
) -> tuple[list[AssessmentItemRead], list[str], dict]:
    """Fast router for the local Qwen refinement stage.

    Old projects often have LOCAL_LLM_REFINEMENT_MODE=single in .env. In that mode
    24 items become 24 sequential Qwen requests, which dominates total generation
    time. The auto-batch layer keeps the old setting compatible, but switches large
    runs to the existing batch refiner unless LOCAL_LLM_AUTO_BATCH=false.
    """
    settings = get_local_llm_settings()
    if not settings.enabled:
        profile = LocalLLMRefinementProfile(enabled=False, requested_items=len(items)).as_dict()
        return items, [], profile

    mode = os.getenv("LOCAL_LLM_REFINEMENT_MODE", "auto").strip().lower()
    if mode in {"off", "disabled", "false", "0", "none"}:
        profile = LocalLLMRefinementProfile(
            enabled=False,
            mode="disabled_by_mode",
            model=settings.model,
            requested_items=len(items),
        ).as_dict()
        return items, ["Локальная LLM-прокачка отключена режимом LOCAL_LLM_REFINEMENT_MODE."], profile

    if mode == "batch":
        return _refine_items_batch(items=items, discipline_name=discipline_name, all_topics=all_topics)

    if mode in {"auto", "single"} and _should_use_batch(items):
        return _refine_items_batch(items=items, discipline_name=discipline_name, all_topics=all_topics)

    return _refine_items_single(items=items, discipline_name=discipline_name, all_topics=all_topics)


def _should_use_batch(items: list[AssessmentItemRead]) -> bool:
    if not _env_bool("LOCAL_LLM_AUTO_BATCH", True):
        return False
    max_items = _env_int("LOCAL_LLM_MAX_ITEMS", 10, minimum=1, maximum=max(len(items), 1))
    min_items = _env_int("LOCAL_LLM_AUTO_BATCH_MIN_ITEMS", 6, minimum=2, maximum=max(len(items), 2))
    skip_types = _env_set("LOCAL_LLM_SKIP_TYPES", DEFAULT_SKIP_TYPES)
    target_count = 0
    for item in items:
        if _should_skip_item(item, skip_types):
            continue
        target_count += 1
        if target_count >= max_items:
            break
    return target_count >= min_items
