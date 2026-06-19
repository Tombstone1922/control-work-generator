import re
from dataclasses import dataclass, field


SECTION_PATTERNS = {
    "Цели и задачи дисциплины": ("цель дисциплины", "цели дисциплины", "задачи дисциплины"),
    "Компетенции": ("компетенц", "планируемые результаты освоения"),
    "Результаты обучения": ("результаты обучения", "знать", "уметь", "владеть"),
    "Содержание дисциплины": ("содержание дисциплины", "тематический план", "разделы дисциплины", "темы дисциплины"),
    "Оценочные материалы": ("оценочные материалы", "фонд оценочных средств", "контрольные задания"),
    "Литература": ("литература", "список литературы", "основная литература", "дополнительная литература", "перечень ресурсов"),
}

NOISE_WORDS = (
    "министерство", "федеральное государственное", "кафедра", "утверждаю", "рабочая программа",
    "страница", "лист согласования", "разработчик", "рецензент", "протокол", "учебный план",
    "форма обучения", "год набора", "семестр", "зачетных единиц", "часов", "таблица",
    "высшего образования", "саратовский государственный", "имени гагарина", "аннотация к рабочей программе",
    "аннотация практики", "направления подготовки", "направлению подготовки", "профиль",
)

REFERENCE_WORDS = (
    "литература", "учебник", "учебное пособие", "монография", "издательство", "изд-во",
    "copyright", "isbn", "doi", "http", "https", "www.", "электронный ресурс", "режим доступа",
    "онлайн учебник", "нэб", "e-library", "elibrary", "библиотек", "для инвалидов", "лицами с ограниченными возможностями",
)

TOPIC_STOP_MARKERS = (
    "перечень практических", "практических занятий", "лабораторных работ", "самостоятельной работы",
    "задания для самостоятельной", "расчетно-графическая работа", "курсовая работа", "курсовой проект",
    "контрольная работа", "оценочные средства", "учебно-методическое обеспечение", "рекомендуемая литература",
)

SECTION_HEADING_WORDS = (
    "цели и задачи", "место дисциплины", "требования к результатам", "объем дисциплины",
    "вид учебной деятельности", "аудиторные занятия", "занятия лекционного", "занятия семинарского",
    "самостоятельная работа", "промежуточная аттестация", "консультации", "общая трудоемкость",
    "содержание дисциплины", "структура дисциплины", "перечень практических", "перечень лабораторных",
    "оценочные средства", "учебно-методическое", "материально-техническое", "информационные технологии",
    "заочная форма обучения", "очная форма обучения", "итого", "направления подготовки", "направлению подготовки",
)

COMPETENCY_CODE_PATTERN = re.compile(r"\b(?:УК|ОПК|ПК|ПКО|ПКС|ОК)-?\d+(?:\.\d+)?\b", re.IGNORECASE)
INDICATOR_CODE_PATTERN = re.compile(r"\bИД[-–—]?[А-Яа-яA-Za-z]*\s*[-–—]?\s*(?:УК|ОПК|ПК|ПКО|ПКС|ОК)[-–—]?\d+(?:\.\d+)?\b", re.IGNORECASE)
EXPLICIT_TOPIC_PATTERN = re.compile(r"^(?:тема|раздел)\s*\d+(?:\.\d+)*[\.\)]?\s*(.+)$", re.IGNORECASE)
NUMBERED_TOPIC_PATTERN = re.compile(r"^\d+(?:\.\d+)*[\.\)]\s+(.{4,180})$", re.IGNORECASE)
BULLET_TOPIC_PATTERN = re.compile(r"^[\-–—•]\s*(.{4,180})$", re.IGNORECASE)
OUTCOME_SEGMENT_PATTERN = re.compile(
    r"(?:^|\|\s*|\s)(Знать|Уметь|Владеть)\s*:?\s*(.*?)(?=\s+(?:Знать|Уметь|Владеть)\s*:|$)",
    re.IGNORECASE,
)
OUTCOME_HEADER_PATTERN = re.compile(r"\s*(?:студент\s+должен\s+)?(?:знать|уметь|владеть)\s*:?\.?\s*$", re.IGNORECASE)


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

    topics, topic_sources = _extract_topics(clean_lines, sections, raw_lines)
    competencies, competency_sources = _extract_competencies(normalized)
    outcomes, outcome_sources = _extract_learning_outcomes(clean_lines, sections)

    strategy = "rules+sections"
    if not topics:
        discipline_topic = _extract_discipline_topic(raw_lines)
        if discipline_topic:
            topics = [discipline_topic]
            topic_sources = [discipline_topic]
            strategy = "discipline-title"
        else:
            topics = []
            topic_sources = []
            strategy = "empty"

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


def _extract_topics(
    lines: list[str],
    sections: dict[str, list[str]],
    raw_lines: list[str] | None = None,
) -> tuple[list[str], list[str]]:
    has_content_section = bool(sections.get("Содержание дисциплины"))
    candidates = _topic_candidate_lines(sections.get("Содержание дисциплины", []) if has_content_section else lines)

    explicit_topics, explicit_sources = _collect_topic_matches(candidates, [EXPLICIT_TOPIC_PATTERN])
    if explicit_topics:
        return explicit_topics, explicit_sources

    if has_content_section:
        table_topics, table_sources = _collect_topic_matches(candidates, [NUMBERED_TOPIC_PATTERN, BULLET_TOPIC_PATTERN])
        if table_topics:
            return table_topics, table_sources

    all_explicit, all_sources = _collect_topic_matches(_topic_candidate_lines(lines), [EXPLICIT_TOPIC_PATTERN])
    if all_explicit:
        return all_explicit, all_sources

    discipline_topic = _extract_discipline_topic(raw_lines or lines)
    if discipline_topic:
        return [discipline_topic], [discipline_topic]

    return [], []


def _topic_candidate_lines(lines: list[str]) -> list[str]:
    result: list[str] = []
    for line in lines:
        lower = line.lower()
        if any(marker in lower for marker in TOPIC_STOP_MARKERS):
            break
        result.append(line)
    return result


def _merge_topic_lines(lines: list[str]) -> list[str]:
    merged: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        match = EXPLICIT_TOPIC_PATTERN.match(line) or NUMBERED_TOPIC_PATTERN.match(line)
        if not match:
            merged.append(line)
            index += 1
            continue

        source = line
        title = match.group(1).strip()
        lookahead = index + 1
        added = 0
        while lookahead < len(lines) and added < 2 and len(title) < 150 and _is_topic_continuation(lines[lookahead]):
            source += " " + lines[lookahead].strip()
            title += " " + lines[lookahead].strip()
            lookahead += 1
            added += 1
        merged.append(source)
        index = lookahead
    return merged


def _is_topic_continuation(line: str) -> bool:
    line = line.strip()
    if not line or len(line) > 100:
        return False
    lower = line.lower()
    if EXPLICIT_TOPIC_PATTERN.match(line) or NUMBERED_TOPIC_PATTERN.match(line) or BULLET_TOPIC_PATTERN.match(line):
        return False
    if _is_noise(line) or _is_reference_line(line) or _contains_competency_code(line) or _looks_like_hours_row(line):
        return False
    if _is_section_heading(line) or any(marker in lower for marker in TOPIC_STOP_MARKERS):
        return False
    if any(word in lower for word in ("знать", "уметь", "владеть", "изучить", "выполнить", "подготовить", "решить")):
        return False
    return True


def _collect_topic_matches(lines: list[str], patterns: list[re.Pattern]) -> tuple[list[str], list[str]]:
    topics: list[str] = []
    sources: list[str] = []
    for line in _merge_topic_lines(lines):
        if _is_noise(line) or _is_reference_line(line) or _contains_competency_code(line) or _looks_like_hours_row(line):
            continue
        if _is_section_heading(line):
            continue
        for pattern in patterns:
            match = pattern.match(line)
            if not match:
                continue
            candidate = _clean_candidate(match.group(1))
            if _is_reasonable_topic(candidate):
                topics.append(candidate)
                sources.append(line)
            break
    return topics, sources


def _extract_discipline_topic(lines: list[str]) -> str:
    for index, line in enumerate(lines):
        lower = line.lower().strip()
        if lower == "по дисциплине" or lower.endswith("по дисциплине"):
            candidate = _collect_title_after_line(lines, index)
            if candidate:
                return candidate
        if "аннотация практики" in lower or "рабочей программе практики" in lower:
            candidate = _collect_title_after_line(lines, index)
            if candidate:
                return candidate

    for index, line in enumerate(lines[:40]):
        if re.match(r"^[А-ЯA-ZБ]\.?\d", line.strip()) or re.search(r"[«\"][^»\"]+$", line):
            combined = [line]
            for next_line in lines[index + 1:index + 4]:
                lower = next_line.lower()
                if "направлен" in lower or "профиль" in lower or "форма" in lower:
                    break
                combined.append(next_line)
                if "»" in next_line or '"' in next_line:
                    break
            candidate = _normalize_discipline_name(" ".join(combined))
            if _is_reasonable_discipline_title(candidate):
                return candidate

    for line in lines:
        match = re.search(r"Дисциплина\s+(.+?)\s+относится", line, re.IGNORECASE)
        if match:
            candidate = _normalize_discipline_name(match.group(1))
            if _is_reasonable_discipline_title(candidate):
                return candidate

    return ""


def _collect_title_after_line(lines: list[str], index: int) -> str:
    combined: list[str] = []
    for next_line in lines[index + 1:index + 8]:
        lower = next_line.lower()
        if "направлен" in lower or "профиль" in lower or "форма обучения" in lower or "формы обучения" in lower:
            break
        combined.append(next_line)
    candidate = _normalize_discipline_name(" ".join(combined))
    return candidate if _is_reasonable_discipline_title(candidate) else ""


def _normalize_discipline_name(value: str) -> str:
    value = _clean_candidate(value)
    value = re.sub(r"^[А-ЯA-ZБ]?\.?\d+(?:\.\d+)*\s*", "", value)
    value = value.replace("«", "").replace("»", "").replace('"', "")
    return _clean_candidate(value)


def _extract_competencies(text: str) -> tuple[list[str], list[str]]:
    matches = re.findall(COMPETENCY_CODE_PATTERN, text)
    normalized = [match.upper().replace(" ", "") for match in matches]
    return normalized, normalized[:]


def _extract_learning_outcomes(lines: list[str], sections: dict[str, list[str]] | None = None) -> tuple[list[str], list[str]]:
    outcomes: list[str] = []
    sources: list[str] = []
    candidates = sections.get("Результаты обучения", []) if sections else []
    if not candidates or not any(re.search(r"\b(знать|уметь|владеть)\b", item, flags=re.IGNORECASE) for item in candidates):
        candidates = lines

    index = 0
    while index < len(candidates):
        line = candidates[index]
        if _is_noise(line) or _is_reference_line(line):
            index += 1
            continue

        segments = _extract_outcome_segments(line)
        if segments:
            for segment in segments:
                outcomes.append(segment)
                sources.append(line)
            index += 1
            continue

        if OUTCOME_HEADER_PATTERN.fullmatch(line):
            collected: list[str] = []
            lookahead = index + 1
            while lookahead < len(candidates) and len(" ".join(collected)) < 900:
                next_line = candidates[lookahead].strip()
                if OUTCOME_HEADER_PATTERN.fullmatch(next_line):
                    break
                if _extract_outcome_segments(next_line) or _is_reference_line(next_line) or _is_section_heading(next_line):
                    break
                if _contains_competency_code(next_line) or _contains_indicator_code(next_line):
                    break
                if _is_noise(next_line):
                    lookahead += 1
                    continue
                collected.append(next_line)
                lookahead += 1
                if len(collected) >= 12:
                    break
            outcome = _clean_candidate(" ".join(collected))
            if _is_reasonable_outcome(outcome):
                outcomes.append(outcome)
                sources.append(line)

        index += 1

    return outcomes, sources


def _extract_outcome_segments(line: str) -> list[str]:
    segments: list[str] = []
    for match in OUTCOME_SEGMENT_PATTERN.finditer(line):
        segment = _clean_candidate(match.group(2))
        if _is_reasonable_outcome(segment):
            segments.append(segment)
    return segments


def _is_reasonable_outcome(value: str) -> bool:
    if not 18 <= len(value) <= 1000:
        return False
    if _contains_competency_code(value) or _contains_indicator_code(value):
        return False
    if _is_reference_line(value) or _is_section_heading(value):
        return False
    return True


def _is_reasonable_discipline_title(value: str) -> bool:
    if not 4 <= len(value) <= 180:
        return False
    if _is_noise(value) or _is_reference_line(value) or _is_section_heading(value):
        return False
    if _contains_competency_code(value) or _contains_indicator_code(value) or _looks_like_hours_row(value):
        return False
    return True


def _fallback_topics(lines: list[str]) -> list[str]:
    candidates: list[str] = []
    for line in lines:
        cleaned = _clean_candidate(line)
        if _is_reasonable_topic(cleaned) and not line.endswith(":") and not _looks_like_hours_row(line):
            candidates.append(cleaned)
    return candidates[:12]


def _is_noise(line: str) -> bool:
    lower = line.lower()
    if len(line) < 3:
        return True
    if re.fullmatch(r"[\d\s.,;/\-|]+", line):
        return True
    return any(word in lower for word in NOISE_WORDS)


def _is_reference_line(line: str) -> bool:
    lower = line.lower()
    if any(word in lower for word in REFERENCE_WORDS):
        return True
    if "©" in line or "copyright" in lower:
        return True
    if re.search(r"\b(19|20)\d{2}\b", line) and re.search(r"[А-ЯЁA-Z][а-яёa-z]+\s+[А-ЯЁA-Z]\.\s*[А-ЯЁA-Z]?\.?", line):
        return True
    return False


def _is_section_heading(value: str) -> bool:
    lower = value.lower().strip(" .")
    if any(word in lower for word in SECTION_HEADING_WORDS):
        return True
    return bool(re.match(
        r"^\d+\.\s*(цели|место|требования|объем|содержание|расчетно|курсов|контрольная|оценочные|учебно|материально|информацион)",
        lower,
    ))


def _contains_competency_code(value: str) -> bool:
    return bool(COMPETENCY_CODE_PATTERN.search(value))


def _contains_indicator_code(value: str) -> bool:
    return bool(INDICATOR_CODE_PATTERN.search(value))


def _looks_like_hours_row(value: str) -> bool:
    value = value.strip()
    if "|" in value and len(re.findall(r"\b\d+\b", value)) >= 2:
        return True
    return bool(re.search(r"\s\|\s*\d+\s*\|", value))


def _is_reasonable_topic(value: str) -> bool:
    if not 4 <= len(value) <= 180:
        return False
    lower = value.lower()
    if _is_noise(value) or _is_reference_line(value) or _is_section_heading(value):
        return False
    if _contains_competency_code(value) or _contains_indicator_code(value) or _looks_like_hours_row(value):
        return False
    if any(word in lower for word in ("компетенц", "результат обучения", "итого", "всего", "знать", "уметь", "владеть")):
        return False
    if any(word in lower for word in ("подготовиться", "изучить", "выполнить", "решить", "рассмотреть", "разобрать")):
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
    value = re.sub(r"\|\s*ИД[-–—]?.*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+\|\s*\d+\s*(?:\|\s*\d+\s*)+$", "", value)
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
