from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher


ASSESSMENT_MARKERS = [
    ("diagnostic", ("диагност", "тест", "закрыт", "выберите", "вариант ответа")),
    ("practice", ("практичес", "задание", "решите", "разработайте", "выполните")),
    ("exam_questions", ("экзамен", "вопрос", "промежуточ")),
    ("control_work", ("контрольная", "контрольн")),
    ("laboratory", ("лаборатор" ,)),
    ("coursework", ("курсовая работа",)),
    ("course_project", ("курсовой проект",)),
    ("report_topics", ("доклад", "реферат", "сообщение")),
]


@dataclass
class ParsedReferenceDocument:
    discipline_name: str
    text_hash: str
    summary: dict
    om_items: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def parse_reference_document(text: str, filename: str, document_type: str) -> ParsedReferenceDocument:
    clean_text = _normalize_text(text)
    discipline_name = _extract_discipline(clean_text, filename)
    text_hash = hashlib.sha256(clean_text.encode("utf-8", errors="ignore")).hexdigest()
    lines = [line.strip() for line in clean_text.splitlines() if line.strip()]
    summary = {
        "lines_count": len(lines),
        "discipline_name": discipline_name,
        "detected_assessment_types": _detect_assessment_types(clean_text),
        "topics": _extract_topics(lines),
        "competencies": _extract_competencies(clean_text),
    }
    items: list[dict] = []
    warnings: list[str] = []
    if document_type == "om":
        items = parse_om_items(clean_text, discipline_name)
        if not items:
            warnings.append("Не удалось надежно выделить задания из OM. Документ сохранен, но как источник заданий пока не использован.")
    return ParsedReferenceDocument(discipline_name, text_hash, summary, items, warnings)


def parse_om_items(text: str, discipline_name: str) -> list[dict]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    items: list[dict] = []
    current_section = ""
    current_topic = ""
    current_competency = ""

    for index, line in enumerate(lines):
        lowered = line.lower()
        if _looks_like_section(line):
            current_section = line[:240]
            detected_topic = _topic_from_line(line)
            if detected_topic:
                current_topic = detected_topic
            continue
        topic_candidate = _topic_from_line(line)
        if topic_candidate:
            current_topic = topic_candidate
            continue
        competency_candidate = _competency_from_line(line)
        if competency_candidate:
            current_competency = competency_candidate

        if not _looks_like_question_or_task(line):
            continue

        text_value = _strip_numbering(line)
        if len(text_value) < 25:
            continue
        answer = _find_nearby_answer(lines, index)
        criteria = _find_nearby_criteria(lines, index)
        assessment_type = _detect_assessment_type_for_line(current_section + " " + line)
        item_type = "test" if assessment_type == "diagnostic" or "выберите" in lowered else "open"
        items.append(
            {
                "topic": current_topic or _fallback_topic(text_value, discipline_name),
                "competency_code": current_competency,
                "indicator": "",
                "assessment_type": assessment_type,
                "item_type": item_type,
                "difficulty": "medium",
                "text": text_value,
                "answer": answer,
                "criteria": criteria,
                "source_section": current_section,
                "sample_weight": _initial_weight(assessment_type, answer, criteria),
            }
        )
    return _deduplicate_items(items)


def score_rp_om_pair(rp: ParsedReferenceDocument | dict, om: ParsedReferenceDocument | dict) -> float:
    rp_summary = rp.summary if isinstance(rp, ParsedReferenceDocument) else rp
    om_summary = om.summary if isinstance(om, ParsedReferenceDocument) else om
    rp_name = (rp_summary.get("discipline_name") or "").lower()
    om_name = (om_summary.get("discipline_name") or "").lower()
    name_score = SequenceMatcher(None, rp_name, om_name).ratio() if rp_name and om_name else 0.0
    rp_types = set(rp_summary.get("detected_assessment_types") or [])
    om_types = set(om_summary.get("detected_assessment_types") or [])
    type_score = len(rp_types & om_types) / max(len(rp_types | om_types), 1)
    rp_topics = " ".join(rp_summary.get("topics") or [])
    om_topics = " ".join(om_summary.get("topics") or [])
    topic_score = SequenceMatcher(None, rp_topics.lower(), om_topics.lower()).ratio() if rp_topics and om_topics else 0.0
    return round(min(1.0, 0.55 * name_score + 0.25 * type_score + 0.20 * topic_score), 3)


def _normalize_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_discipline(text: str, filename: str) -> str:
    patterns = [
        r"дисциплин[аы]\s*[:\-]\s*([^\n]{5,160})",
        r"по\s+дисциплин[еы]\s*[:\-]?\s*([^\n]{5,160})",
        r"оценочные\s+материалы\s+по\s+дисциплин[еы]\s*[:\-]?\s*([^\n]{5,160})",
        r"рабочая\s+программ[аы].{0,60}?дисциплин[аы]\s*[:\-]\s*([^\n]{5,160})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = _clean_title(match.group(1))
            if value:
                return value
    name = re.sub(r"\.(docx|pdf|txt)$", "", filename, flags=re.IGNORECASE)
    name = re.sub(r"\b(om|ом|rp|рп|rpd|рпд|фос|оценочные|материалы|рабочая|программа)\b", " ", name, flags=re.IGNORECASE)
    name = re.sub(r"[_\-]+", " ", name)
    return _clean_title(name) or filename


def _clean_title(value: str) -> str:
    value = value.strip(" .;:—-\t\r\n\"")
    value = re.sub(r"\s+", " ", value)
    value = value.split("|")[0].strip()
    return value[:255]


def _detect_assessment_types(text: str) -> list[str]:
    lowered = text.lower()
    result = []
    for assessment_type, markers in ASSESSMENT_MARKERS:
        if any(marker in lowered for marker in markers):
            result.append(assessment_type)
    return result or ["oral", "practice"]


def _extract_topics(lines: list[str]) -> list[str]:
    topics = []
    for line in lines:
        topic = _topic_from_line(line)
        if topic and topic.lower() not in {item.lower() for item in topics}:
            topics.append(topic)
        if len(topics) >= 40:
            break
    return topics


def _extract_competencies(text: str) -> list[str]:
    codes = re.findall(r"\b(?:ОПК|ПК|УК|ПСК|ОК)[\-–]?\d+(?:\.\d+)?\b", text, flags=re.IGNORECASE)
    result = []
    for code in codes:
        normalized = code.upper().replace("–", "-")
        if normalized not in result:
            result.append(normalized)
    return result[:50]


def _looks_like_section(line: str) -> bool:
    lowered = line.lower()
    return (
        len(line) < 180
        and any(marker in lowered for marker in ("вопрос", "задани", "контроль", "экзамен", "зачет", "диагност", "практичес", "тест"))
        and not line.endswith("?")
    )


def _topic_from_line(line: str) -> str:
    match = re.search(r"тема\s*\d*[\.\-–:]?\s*(.+)", line, flags=re.IGNORECASE)
    if match:
        return _clean_title(match.group(1))
    return ""


def _competency_from_line(line: str) -> str:
    match = re.search(r"\b(?:ОПК|ПК|УК|ПСК|ОК)[\-–]?\d+(?:\.\d+)?\b", line, flags=re.IGNORECASE)
    return match.group(0).upper().replace("–", "-") if match else ""


def _looks_like_question_or_task(line: str) -> bool:
    lowered = line.lower()
    if line.endswith("?") and len(line) > 25:
        return True
    if re.match(r"^(?:\d+[\.)]|[а-яa-z][\.)])\s+.{25,}$", line, flags=re.IGNORECASE):
        return True
    return any(marker in lowered for marker in ("объясните", "раскройте", "охарактеризуйте", "сравните", "решите", "разработайте", "выполните", "выберите", "укажите", "составьте")) and len(line) > 25


def _strip_numbering(line: str) -> str:
    return re.sub(r"^(?:\d+[\.)]|[а-яa-z][\.)])\s+", "", line, flags=re.IGNORECASE).strip()


def _find_nearby_answer(lines: list[str], index: int) -> str:
    for offset in range(1, 5):
        if index + offset >= len(lines):
            break
        line = lines[index + offset].strip()
        lowered = line.lower()
        if any(marker in lowered for marker in ("ответ", "правильный", "ключ", "эталон")):
            return re.sub(r"^(ответ|правильный ответ|ключ|эталон)\s*[:\-–]?\s*", "", line, flags=re.IGNORECASE).strip()
    return ""


def _find_nearby_criteria(lines: list[str], index: int) -> list[str]:
    criteria = []
    for offset in range(1, 8):
        if index + offset >= len(lines):
            break
        line = lines[index + offset].strip()
        lowered = line.lower()
        if any(marker in lowered for marker in ("критер", "балл", "оценив")):
            criteria.append(line[:300])
    return criteria[:5]


def _detect_assessment_type_for_line(value: str) -> str:
    lowered = value.lower()
    for assessment_type, markers in ASSESSMENT_MARKERS:
        if any(marker in lowered for marker in markers):
            return assessment_type
    return "oral" if value.endswith("?") else "practice"


def _fallback_topic(text: str, discipline_name: str) -> str:
    quoted = re.findall(r"[«\"]([^»\"]{3,120})[»\"]", text)
    if quoted:
        return _clean_title(quoted[0])
    return discipline_name or "Общая тема дисциплины"


def _initial_weight(assessment_type: str, answer: str, criteria: list[str]) -> float:
    weight = 1.0
    if answer:
        weight += 0.12
    if criteria:
        weight += 0.10
    if assessment_type in {"practice", "exam_practice", "control_work", "laboratory"}:
        weight += 0.05
    return round(min(weight, 1.3), 2)


def _deduplicate_items(items: list[dict]) -> list[dict]:
    result: list[dict] = []
    seen: set[str] = set()
    for item in items:
        key = re.sub(r"\W+", " ", item["text"].lower()).strip()[:180]
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result[:500]
