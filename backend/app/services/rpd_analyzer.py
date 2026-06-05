import re
from dataclasses import dataclass, field


SECTION_PATTERNS = {
    "Цели и задачи дисциплины": ("цель дисциплины", "цели дисциплины", "задачи дисциплины"),
    "Компетенции": ("компетенц", "планируемые результаты освоения"),
    "Результаты обучения": ("результаты обучения", "знать", "уметь", "владеть"),
    "Содержание дисциплины": ("содержание дисциплины", "тематический план", "разделы дисциплины", "темы дисциплины"),
    "Оценочные материалы": ("оценочные материалы", "фонд оценочных средств", "контрольные задания"),
}

NOISE_WORDS = (
    "министерство", "федеральное государственное", "кафедра", "утверждаю", "рабочая программа",
    "страница", "лист согласования", "разработчик", "рецензент", "протокол", "учебный план",
    "форма обучения", "год набора", "семестр", "зачетных единиц", "часов", "таблица",
)


@dataclass
class RpdDiagnosticsData:
    source_lines: int = 0
    analyzed_lines: int = 0
    ignored_lines: int = 0
    topics_count: int = 0
    competencies_count: int = 0
    learning_outcomes_count: int = 0
    detected_sections_count: int = 0
    quality_score: int = 0
    extraction_strategy: str = "rules+sections"
    warnings: list[str] = field(default_factory=list)


@dataclass
class RpdAnalysisResult:
    topics: list[str]
    competencies: list[str]
    learning_outcomes: list[str]
    detected_sections: list[str]
    topic_sources: list[str]
    competency_sources: list[str]
    outcome_sources: list[str]
    diagnostics: RpdDiagnosticsData


def analyze_rpd_text(text: str) -> RpdAnalysisResult:
    normalized = _normalize_text(text)
    raw_lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    clean_lines = [line for line in raw_lines if not _is_noise(line)]
    sections = _detect_sections(raw_lines)

    topics, topic_sources = _extract_topics(clean_lines, sections)
    competencies, competency_sources = _extract_competencies(normalized)
    outcomes, outcome_sources = _extract_learning_outcomes(clean_lines)

    strategy = "rules+sections"
    if not topics:
        topics = _fallback_topics(clean_lines)
        topic_sources = topics[:]
        strategy = "fallback"

    topics = _unique_keep_order(topics)[:40]
    competencies = _unique_keep_order(competencies)[:40]
    outcomes = _unique_keep_order(outcomes)[:40]
    detected_sections = list(sections.keys())

    warnings: list[str] = []
    if not topics:
        warnings.append("Темы дисциплины не обнаружены. Проверьте структуру РПД вручную.")
    if not competencies:
        warnings.append("Коды компетенций не обнаружены.")
    if not outcomes:
        warnings.append("Результаты обучения не обнаружены.")
    if len(detected_sections) < 2:
        warnings.append("Структура документа распознана частично.")

    score = _calculate_quality_score(topics, competencies, outcomes, detected_sections)
    diagnostics = RpdDiagnosticsData(
        source_lines=len(raw_lines),
        analyzed_lines=len(clean_lines),
        ignored_lines=max(len(raw_lines) - len(clean_lines), 0),
        topics_count=len(topics),
        competencies_count=len(competencies),
        learning_outcomes_count=len(outcomes),
        detected_sections_count=len(detected_sections),
        quality_score=score,
        extraction_strategy=strategy,
        warnings=warnings,
    )

    return RpdAnalysisResult(
        topics=topics,
        competencies=competencies,
        learning_outcomes=outcomes,
        detected_sections=detected_sections,
        topic_sources=_unique_keep_order(topic_sources)[:20],
        competency_sources=_unique_keep_order(competency_sources)[:20],
        outcome_sources=_unique_keep_order(outcome_sources)[:20],
        diagnostics=diagnostics,
    )


def _normalize_text(text: str) -> str:
    text = text.replace("\r", "\n").replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _detect_sections(lines: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    active_section: str | None = None

    for line in lines:
        lower = line.lower()
        matched_section = None
        for section_name, markers in SECTION_PATTERNS.items():
            if any(marker in lower for marker in markers) and len(line) <= 180:
                matched_section = section_name
                break
        if matched_section:
            active_section = matched_section
            sections.setdefault(active_section, [])
            continue
        if active_section:
            sections[active_section].append(line)
    return sections


def _extract_topics(lines: list[str], sections: dict[str, list[str]]) -> tuple[list[str], list[str]]:
    topics: list[str] = []
    sources: list[str] = []
    candidates = sections.get("Содержание дисциплины", []) or lines
    patterns = [
        r"^(?:тема|раздел)\s*\d+(?:\.\d+)*[\.\)]?\s*(.+)$",
        r"^\d+(?:\.\d+)*[\.\)]\s+(.{8,180})$",
        r"^[\-–—•]\s*(.{8,180})$",
    ]

    for line in candidates:
        if _is_noise(line):
            continue
        for pattern in patterns:
            match = re.match(pattern, line, flags=re.IGNORECASE)
            if match:
                candidate = _clean_candidate(match.group(1))
                if _is_reasonable_topic(candidate):
                    topics.append(candidate)
                    sources.append(line)
                break
    return topics, sources


def _extract_competencies(text: str) -> tuple[list[str], list[str]]:
    pattern = r"\b(?:УК|ОПК|ПК|ПКО|ПКС|ОК)-?\d+(?:\.\d+)?\b"
    matches = re.findall(pattern, text, flags=re.IGNORECASE)
    normalized = [match.upper() for match in matches]
    return normalized, normalized[:]


def _extract_learning_outcomes(lines: list[str]) -> tuple[list[str], list[str]]:
    outcomes: list[str] = []
    sources: list[str] = []
    markers = ("знать", "уметь", "владеть", "навык", "способен", "должен")

    for line in lines:
        lower = line.lower()
        if any(marker in lower for marker in markers) and 18 <= len(line) <= 360:
            cleaned = _clean_candidate(line)
            outcomes.append(cleaned)
            sources.append(line)
    return outcomes, sources


def _fallback_topics(lines: list[str]) -> list[str]:
    candidates: list[str] = []
    for line in lines:
        cleaned = _clean_candidate(line)
        if _is_reasonable_topic(cleaned) and not line.endswith(":"):
            candidates.append(cleaned)
    return candidates[:12]


def _is_noise(line: str) -> bool:
    lower = line.lower()
    if len(line) < 3:
        return True
    if re.fullmatch(r"[\d\s.,;/\-]+", line):
        return True
    return any(word in lower for word in NOISE_WORDS)


def _is_reasonable_topic(value: str) -> bool:
    if not 8 <= len(value) <= 180:
        return False
    lower = value.lower()
    if _is_noise(value):
        return False
    if any(word in lower for word in ("компетенц", "результат обучения", "итого", "всего")):
        return False
    return True


def _calculate_quality_score(
    topics: list[str],
    competencies: list[str],
    outcomes: list[str],
    sections: list[str],
) -> int:
    score = 0
    score += min(len(topics) * 4, 40)
    score += min(len(competencies) * 5, 20)
    score += min(len(outcomes) * 3, 24)
    score += min(len(sections) * 4, 16)
    return min(score, 100)


def _clean_candidate(value: str) -> str:
    value = re.sub(r"\s+", " ", value)
    return value.strip(" .;:-—|\t")


def _unique_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.lower().strip()
        if key and key not in seen:
            seen.add(key)
            result.append(value.strip())
    return result
