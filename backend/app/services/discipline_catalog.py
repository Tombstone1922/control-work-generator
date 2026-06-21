from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from dataclasses import replace
from pathlib import Path

from app.services.rpd_analyzer import RpdAnalysisResult

DEFAULT_CATALOG_PATH = Path(__file__).resolve().parents[1] / "storage" / "discipline_catalog" / "discipline_profiles.json"
DISCIPLINE_CATALOG_PATH = Path(os.getenv("DISCIPLINE_CATALOG_PATH", str(DEFAULT_CATALOG_PATH)))
MIN_SCORE = 0.18


def enrich_analysis_with_catalog(filename: str, text: str, analysis: RpdAnalysisResult) -> RpdAnalysisResult:
    profiles = load_catalog_profiles()
    if not profiles or not _needs_catalog_enrichment(analysis):
        return analysis

    match = find_best_profile(filename, text, analysis.topics, profiles)
    if match is None:
        return analysis
    profile, score = match
    topics = _merge_unique(analysis.topics, profile.get("topics", []))
    outcomes = _merge_unique(analysis.learning_outcomes, profile.get("learning_outcomes", []))
    if len(topics) <= len(analysis.topics):
        return analysis

    warnings = list(analysis.diagnostics.warnings)
    warnings.append(
        "РПД содержит мало предметного содержания; применено обогащение из каталога дисциплин: "
        f"{profile.get('discipline_name', 'неизвестная дисциплина')} (score={score:.2f})."
    )
    diagnostics = replace(
        analysis.diagnostics,
        topics_count=len(topics),
        learning_outcomes_count=len(outcomes),
        extraction_strategy=f"{analysis.diagnostics.extraction_strategy}+discipline-catalog",
        warnings=warnings,
        quality_score=min(max(analysis.diagnostics.quality_score, 72), 100),
    )
    return replace(
        analysis,
        topics=topics,
        learning_outcomes=outcomes,
        topic_sources=list(analysis.topic_sources) + [f"Каталог дисциплин: {profile.get('discipline_name', '')}"],
        outcome_sources=list(analysis.outcome_sources) + [f"Каталог дисциплин: {profile.get('discipline_name', '')}"],
        diagnostics=diagnostics,
    )


def load_catalog_profiles() -> list[dict]:
    if not DISCIPLINE_CATALOG_PATH.exists():
        return []
    try:
        data = json.loads(DISCIPLINE_CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, dict):
        return data.get("profiles", []) or []
    if isinstance(data, list):
        return data
    return []


def find_best_profile(filename: str, text: str, topics: list[str], profiles: list[dict]) -> tuple[dict, float] | None:
    query_text = " ".join([filename or "", " ".join(topics or []), text[:5000] or ""])
    query_tokens = _tokens(query_text)
    if not query_tokens:
        return None
    query_counter = Counter(query_tokens)

    best_profile: dict | None = None
    best_score = 0.0
    haystack = _normalize(query_text)
    for profile in profiles:
        profile_tokens = profile.get("tokens") or _tokens(" ".join([
            profile.get("discipline_name", ""),
            " ".join(profile.get("topics", [])),
            " ".join(profile.get("learning_outcomes", [])),
        ]))
        if not profile_tokens:
            continue
        score = _cosine_counter(query_counter, Counter(profile_tokens))
        discipline_name = _normalize(profile.get("discipline_name", ""))
        if discipline_name and discipline_name in haystack:
            score += 0.45
        elif discipline_name:
            name_tokens = set(_tokens(discipline_name))
            if name_tokens:
                score += 0.25 * (len(name_tokens & set(query_tokens)) / len(name_tokens))
        if score > best_score:
            best_score = score
            best_profile = profile

    if best_profile is None or best_score < MIN_SCORE:
        return None
    return best_profile, best_score


def _needs_catalog_enrichment(analysis: RpdAnalysisResult) -> bool:
    if len(analysis.topics) < 5:
        return True
    short = [topic for topic in analysis.topics if len(_tokens(topic)) <= 2]
    return len(short) >= max(2, len(analysis.topics) // 2)


def _merge_unique(primary: list[str], secondary: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in [*(primary or []), *(secondary or [])]:
        value = str(value).strip()
        key = _normalize(value)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result[:40]


def _tokens(value: str) -> list[str]:
    value = _normalize(value)
    return [token for token in re.findall(r"[a-zа-я0-9]{3,}", value) if token not in STOP_WORDS]


def _normalize(value: str) -> str:
    return (value or "").lower().replace("ё", "е")


def _cosine_counter(left: Counter, right: Counter) -> float:
    common = set(left) & set(right)
    numerator = sum(left[token] * right[token] for token in common)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


STOP_WORDS = {
    "дисциплина", "дисциплины", "рабочая", "программа", "программы", "образования", "подготовки",
    "направления", "направлению", "профиль", "обучения", "студент", "должен", "знать", "уметь",
    "владеть", "тема", "раздел", "основные", "основы", "общие", "материалы", "оценочные",
}
