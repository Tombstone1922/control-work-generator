from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

DEFAULT_CATALOG_PATH = Path(__file__).resolve().parents[1] / "storage" / "discipline_catalog" / "discipline_profiles.json"
DISCIPLINE_CATALOG_PATH = Path(os.getenv("DISCIPLINE_CATALOG_PATH", str(DEFAULT_CATALOG_PATH)))

STOP_TERMS = {
    "дисциплина", "дисциплины", "рабочая", "программа", "программы", "образования", "подготовки",
    "направления", "направлению", "профиль", "обучения", "студент", "должен", "знать", "уметь",
    "владеть", "тема", "раздел", "основные", "основы", "общие", "материалы", "оценочные",
    "лекция", "практика", "занятие", "самостоятельная", "работа", "изучение", "изучения",
}

ACTION_VERBS = (
    "знать", "уметь", "владеть", "понимать", "применять", "использовать", "анализировать",
    "оценивать", "разрабатывать", "создавать", "проектировать", "реализовывать", "формировать",
    "выбирать", "обосновывать", "настраивать", "тестировать", "отлаживать", "оптимизировать",
    "составлять", "строить", "определять", "выявлять", "сравнивать", "классифицировать",
)


@dataclass(frozen=True)
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
    return _get_topic_knowledge_context_cached(
        discipline_name or "",
        topic or "",
        tuple(all_topics or ()),
    )


@lru_cache(maxsize=4096)
def _get_topic_knowledge_context_cached(
    discipline_name: str,
    topic: str,
    all_topics_tuple: tuple[str, ...],
) -> TopicKnowledgeContext:
    all_topics = list(all_topics_tuple)
    profile = _find_profile(discipline_name, topic, all_topics)
    if profile:
        related_topics = _pick_related_topics(topic, profile.get("topics", []), all_topics)
        raw_outcomes = [str(value).strip() for value in profile.get("learning_outcomes", []) if str(value).strip()]
        outcomes = _normalize_learning_outcomes(raw_outcomes, topic=topic)[:4]
        competencies = [str(value).strip() for value in profile.get("competencies", []) if str(value).strip()]
        key_terms = _extract_key_terms(" ".join([topic, " ".join(related_topics), " ".join(outcomes), " ".join(profile.get("tokens", []))]))
        return TopicKnowledgeContext(
            discipline_name=discipline_name or profile.get("discipline_name", ""),
            topic=topic,
            profile_name=profile.get("discipline_name", ""),
            related_topics=related_topics[:5],
            learning_outcomes=outcomes,
            competencies=competencies[:8],
            key_terms=key_terms[:8],
            source="discipline_catalog",
        )

    related = [value for value in all_topics if _normalize(value) != _normalize(topic)]
    return TopicKnowledgeContext(
        discipline_name=discipline_name,
        topic=topic,
        profile_name=discipline_name,
        related_topics=related[:5],
        learning_outcomes=_fallback_learning_outcomes(topic),
        competencies=[],
        key_terms=_extract_key_terms(" ".join([discipline_name, topic, " ".join(related)]))[:8],
        source="runtime_topics",
    )


@lru_cache(maxsize=1)
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


@lru_cache(maxsize=1)
def _profile_descriptors() -> tuple[tuple[int, str, str, str], ...]:
    descriptors = []
    for index, profile in enumerate(_load_profiles()):
        profile_name = str(profile.get("discipline_name", ""))
        profile_text = " ".join([
            profile_name,
            " ".join(profile.get("topics", [])),
            " ".join(profile.get("learning_outcomes", [])),
        ])
        descriptors.append((index, profile_name, _normalize(profile_name), _normalize(profile_text[:3000])))
    return tuple(descriptors)


def _find_profile(discipline_name: str, topic: str, all_topics: list[str]) -> dict | None:
    profiles = _load_profiles()
    if not profiles:
        return None
    query = " ".join([discipline_name or "", topic or "", " ".join(all_topics or [])])
    query_norm = _normalize(query)
    best_index = -1
    best_score = 0.0
    for index, profile_name, name_norm, profile_text_norm in _profile_descriptors():
        score = SequenceMatcher(None, query_norm, profile_text_norm).ratio()
        if name_norm and name_norm in query_norm:
            score += 0.45
        else:
            score += _token_overlap_score(query, profile_name + " " + profile_text_norm) * 0.35
        if score > best_score:
            best_score = score
            best_index = index
    return profiles[best_index] if best_index >= 0 and best_score >= 0.18 else None


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


def _normalize_learning_outcomes(values: list[str], *, topic: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        for part in _split_outcome(value):
            normalized = _normalize_learning_outcome(part, topic=topic)
            key = _normalize(normalized)
            if not normalized or key in seen:
                continue
            seen.add(key)
            result.append(normalized)
    return result or _fallback_learning_outcomes(topic)


def _split_outcome(value: str) -> list[str]:
    value = _clean_sentence(value)
    if not value:
        return []
    parts = re.split(r"\s*;\s*", value)
    cleaned = [_clean_sentence(part) for part in parts if _clean_sentence(part)]
    return cleaned or [value]


def _normalize_learning_outcome(value: str, *, topic: str) -> str:
    value = _clean_sentence(value)
    if not value:
        return ""
    lower = value.lower().replace("ё", "е")

    if _starts_with_action_verb(lower):
        return _capitalize_sentence(value)

    if lower.startswith(("навыки ", "навыками ", "методами ", "инструментами ", "технологиями ")):
        return _capitalize_sentence(f"Владеть {value}")

    if any(marker in lower for marker in ("интерфейс", "прилож", "api", "html", "css", "javascript", "typescript", "react", "vue", "php", "sql", "компонент", "тест")):
        if lower.startswith(("основ", "фактор", "принцип", "понят", "концепц", "архитектур")):
            return _capitalize_sentence(f"Знать {value}")
        return _capitalize_sentence(f"Уметь применять {value}")

    if lower.startswith(("основ", "фактор", "принцип", "понят", "концепц", "классификац", "характеристик", "структур")):
        return _capitalize_sentence(f"Знать {value}")

    if lower.startswith(("метод", "способ", "алгоритм", "подход", "практик", "прием")):
        return _capitalize_sentence(f"Применять {value}")

    if topic and _token_overlap_score(value, topic) > 0.0:
        return _capitalize_sentence(f"Уметь применять {value}")

    return _capitalize_sentence(f"Знать {value}")


def _fallback_learning_outcomes(topic: str) -> list[str]:
    topic = _clean_sentence(topic)
    if not topic:
        return []
    return [
        f"Знать основные понятия и принципы по теме «{topic}»",
        f"Уметь применять методы и инструменты по теме «{topic}» при решении учебных задач",
        f"Владеть навыками анализа и проверки решений по теме «{topic}»",
    ]


def _starts_with_action_verb(value: str) -> bool:
    return any(value.startswith(f"{verb} ") or value == verb for verb in ACTION_VERBS)


def _clean_sentence(value: str) -> str:
    value = str(value or "").replace("#default#", "")
    value = re.sub(r"\s+", " ", value).strip(" .;:-—\t\n\r")
    return value


def _capitalize_sentence(value: str) -> str:
    value = _clean_sentence(value)
    return f"{value[:1].upper()}{value[1:]}" if value else ""


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
