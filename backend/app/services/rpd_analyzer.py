import re
from dataclasses import dataclass


@dataclass
class RpdAnalysisResult:
    topics: list[str]
    competencies: list[str]
    learning_outcomes: list[str]


def analyze_rpd_text(text: str) -> RpdAnalysisResult:
    normalized = _normalize_text(text)
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]

    topics = _extract_topics(lines)
    competencies = _extract_competencies(normalized)
    outcomes = _extract_learning_outcomes(lines)

    if not topics:
        topics = _fallback_topics(lines)

    return RpdAnalysisResult(
        topics=_unique_keep_order(topics)[:30],
        competencies=_unique_keep_order(competencies)[:30],
        learning_outcomes=_unique_keep_order(outcomes)[:30],
    )


def _normalize_text(text: str) -> str:
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_topics(lines: list[str]) -> list[str]:
    topics: list[str] = []
    topic_patterns = [
        r"^(?:тема|раздел)\s*\d+[\.\)]?\s*(.+)$",
        r"^\d+(?:\.\d+)*[\.\)]\s+(.{8,120})$",
    ]

    for line in lines:
        lower = line.lower()
        if any(skip in lower for skip in ["содержание", "компетен", "результат", "таблица"]):
            continue
        for pattern in topic_patterns:
            match = re.match(pattern, line, flags=re.IGNORECASE)
            if match:
                candidate = _clean_candidate(match.group(1))
                if 8 <= len(candidate) <= 160:
                    topics.append(candidate)
                break
    return topics


def _extract_competencies(text: str) -> list[str]:
    pattern = r"\b(?:УК|ОПК|ПК)-?\d+(?:\.\d+)?\b"
    return re.findall(pattern, text, flags=re.IGNORECASE)


def _extract_learning_outcomes(lines: list[str]) -> list[str]:
    outcomes: list[str] = []
    markers = ("знать", "уметь", "владеть", "способен", "должен")

    for line in lines:
        lower = line.lower()
        if any(marker in lower for marker in markers) and 20 <= len(line) <= 260:
            outcomes.append(_clean_candidate(line))
    return outcomes


def _fallback_topics(lines: list[str]) -> list[str]:
    candidates: list[str] = []
    for line in lines:
        if 20 <= len(line) <= 120 and not line.endswith(":"):
            lower = line.lower()
            if not any(word in lower for word in ["министерство", "федераль", "кафедра", "страница"]):
                candidates.append(_clean_candidate(line))
    return candidates[:10]


def _clean_candidate(value: str) -> str:
    value = re.sub(r"\s+", " ", value)
    value = value.strip(" .;:-—")
    return value


def _unique_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.lower()
        if key and key not in seen:
            seen.add(key)
            result.append(value)
    return result
