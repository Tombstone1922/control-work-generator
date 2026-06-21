from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

DEFAULT_CATALOG_PATH = Path(__file__).resolve().parents[1] / "storage" / "discipline_catalog" / "discipline_profiles.json"
DISCIPLINE_CATALOG_PATH = Path(os.getenv("DISCIPLINE_CATALOG_PATH", str(DEFAULT_CATALOG_PATH)))

STOP_TERMS = {
    "дисциплина", "дисциплины", "рабочая", "программа", "программы", "образования", "подготовки",
    "направления", "направлению", "профиль", "обучения", "студент", "должен", "знать", "уметь",
    "владеть", "тема", "раздел", "основные", "основы", "общие", "материалы", "оценочные",
    "лекция", "практика", "занятие", "самостоятельная", "работа", "изучение", "изучения",
}


@dataclass
class TopicKnowledgeContext:
    discipline_name: str
    topic: str
    profile_name: str
    related_topics: list[str]
    learning_outcomes: list[str]
    competencies: list[str]
    key_terms: list[str]
    source: str


def get_topic_knowledge_context(
    *,
    discipline_name: str,
    topic: str,
    all_topics: list[str] | None = None,
) -> TopicKnowledgeContext:
    profile = _find_profile(discipline_name, topic, all_topics or [])
    if profile:
        related_topics = _pick_related_topics(topic, profile.get("topics", []), all_topics or [])
        outcomes = [str(value).strip() for value in profile.get("learning_outcomes", []) if str(value).strip()]
        competencies = [str(value).strip() for value in profile.get("competencies", []) if str(value).strip()]
        key_terms = _extract_key_terms(" ".join([topic, " ".join(related_topics), " ".join(outcomes), " ".join(profile.get("tokens", []))]))
        return TopicKnowledgeContext(
            discipline_name=discipline_name or profile.get("discipline_name", ""),
            topic=topic,
            profile_name=profile.get("discipline_name", ""),
            related_topics=related_topics[:5],
            learning_outcomes=outcomes[:4],
            competencies=competencies[:8],
            key_terms=key_terms[:8],
            source="discipline_catalog",
        )

    related = [value for value in (all_topics or []) if _normalize(value) != _normalize(topic)]
    return TopicKnowledgeContext(
        discipline_name=discipline_name,
        topic=topic,
        profile_name=discipline_name,
        related_topics=related[:5],
        learning_outcomes=[],
        competencies=[],
        key_terms=_extract_key_terms(" ".join([discipline_name, topic, " ".join(related)]))[:8],
        source="runtime_topics",
    )


def _load_profiles() -> list[dict]:
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


def _find_profile(discipline_name: str, topic: str, all_topics: list[str]) -> dict | None:
    profiles = _load_profiles()
    if not profiles:
        return None
    query = " ".join([discipline_name or "", topic or "", " ".join(all_topics or [])])
    query_norm = _normalize(query)
    best_profile = None
    best_score = 0.0
    for profile in profiles:
        profile_name = str(profile.get("discipline_name", ""))
        profile_text = " ".join([
            profile_name,
            " ".join(profile.get("topics", [])),
            " ".join(profile.get("learning_outcomes", [])),
        ])
        score = SequenceMatcher(None, query_norm, _normalize(profile_text[:3000])).ratio()
        name_norm = _normalize(profile_name)
        if name_norm and name_norm in query_norm:
            score += 0.45
        else:
            score += _token_overlap_score(query, profile_text) * 0.35
        if score > best_score:
            best_score = score
            best_profile = profile
    return best_profile if best_profile and best_score >= 0.18 else None


def _pick_related_topics(topic: str, profile_topics: list[str], runtime_topics: list[str]) -> list[str]:
    topic_norm = _normalize(topic)
    candidates = []
    for value in [*(runtime_topics or []), *(profile_topics or [])]:
        value = str(value).strip()
        if not value or _normalize(value) == topic_norm:
            continue
        score = _token_overlap_score(topic, value)
        candidates.append((score, value))
    candidates.sort(key=lambda item: item[0], reverse=True)
    result = []
    seen = set()
    for _, value in candidates:
        key = _normalize(value)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _extract_key_terms(value: str) -> list[str]:
    tokens = []
    for token in re.findall(r"[A-Za-zА-Яа-я0-9+#.-]{3,}", _normalize(value)):
        token = token.strip(".-_")
        if not token or token in STOP_TERMS or token.isdigit():
            continue
        tokens.append(token)
    freq: dict[str, int] = {}
    for token in tokens:
        freq[token] = freq.get(token, 0) + 1
    return [token for token, _ in sorted(freq.items(), key=lambda item: (-item[1], item[0]))]


def _token_overlap_score(left: str, right: str) -> float:
    left_tokens = set(_extract_key_terms(left))
    right_tokens = set(_extract_key_terms(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _normalize(value: str) -> str:
    return (value or "").lower().replace("ё", "е")
