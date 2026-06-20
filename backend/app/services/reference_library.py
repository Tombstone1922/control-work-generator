from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

from app.schemas import TrainingExampleRead
from app.services.document_parser import SUPPORTED_EXTENSIONS, UnsupportedDocumentFormat, extract_text

DEFAULT_REFERENCE_DIR = Path(__file__).resolve().parents[1] / "storage" / "reference_library"
REFERENCE_DIR = Path(os.getenv("REFERENCE_LIBRARY_DIR", str(DEFAULT_REFERENCE_DIR)))
REFERENCE_DIR.mkdir(parents=True, exist_ok=True)

OM_MARKERS = (
    "om",
    "ом",
    "оценоч",
    "оценочные",
    "материал",
    "фос",
    "фонд",
)
RP_MARKERS = (
    "rp",
    "рп",
    "рпд",
    "рабоч",
    "программа",
)
ASSESSMENT_MARKERS = {
    "exam_questions": ("экзаменационные вопросы", "вопросы к экзамену", "экзамен"),
    "exam_practice": ("практические задания к экзамену", "экзаменационные задания"),
    "credit": ("зачет", "вопросы к зачету"),
    "practice": ("практическое занятие", "практическая работа", "практические задания"),
    "laboratory": ("лабораторная", "лабораторные работы"),
    "test_bank": ("тест", "тестовые задания"),
    "control_work": ("контрольная работа", "контрольные задания"),
    "coursework": ("курсовая работа",),
    "course_project": ("курсовой проект",),
    "diagnostic": ("диагност", "оценочное средство"),
    "oral": ("устный опрос", "собеседование", "вопросы для опроса"),
}


@dataclass
class ReferenceDocument:
    path: Path
    document_type: str
    discipline_key: str
    score: float = 0.0


@dataclass
class ReferenceMatchResult:
    examples: list[TrainingExampleRead]
    matched_documents: list[ReferenceDocument]
    warnings: list[str]


def get_reference_library_path() -> Path:
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    return REFERENCE_DIR


def find_om_examples_for_program(
    *,
    program_filename: str,
    program_text: str,
    fund_id: str,
    discipline_name: str,
    topics: list[str],
    max_examples: int = 300,
) -> ReferenceMatchResult:
    documents = _scan_reference_documents()
    if not documents:
        return ReferenceMatchResult([], [], [f"Локальная библиотека RP/OM пуста: {REFERENCE_DIR}"])

    rp_key = _discipline_key(program_filename) or _discipline_key(discipline_name)
    text_key = _discipline_key(_guess_discipline_from_text(program_text))
    target_key = rp_key or text_key or _discipline_key(discipline_name)

    om_documents = [document for document in documents if document.document_type == "om"]
    if not om_documents:
        return ReferenceMatchResult([], [], [f"В локальной библиотеке не найдены OM/оценочные материалы: {REFERENCE_DIR}"])

    ranked: list[ReferenceDocument] = []
    for document in om_documents:
        score = _match_score(target_key, document.discipline_key, program_filename, document.path.name)
        if score >= 0.22:
            ranked.append(ReferenceDocument(document.path, document.document_type, document.discipline_key, score))

    ranked.sort(key=lambda document: document.score, reverse=True)
    selected = ranked[:5]
    if not selected:
        selected = [max(om_documents, key=lambda document: _text_similarity(target_key, document.discipline_key))]
        selected[0].score = _text_similarity(target_key, selected[0].discipline_key)

    examples: list[TrainingExampleRead] = []
    warnings: list[str] = []
    for document in selected:
        try:
            examples.extend(
                parse_om_document_to_examples(
                    document.path,
                    fund_id=fund_id,
                    discipline_name=discipline_name,
                    topics=topics,
                    source="om_direct" if document.score >= 0.55 else "om_similar",
                    limit=max(20, max_examples // max(len(selected), 1)),
                )
            )
        except (UnsupportedDocumentFormat, OSError, ValueError) as exc:
            warnings.append(f"Не удалось прочитать OM {document.path.name}: {exc}")

    if not examples:
        warnings.append("OM найдены, но из них не удалось извлечь задания. Проверьте структуру документов.")
    else:
        warnings.append(
            "Подключены локальные OM-документы: "
            + ", ".join(f"{doc.path.name} ({doc.score:.2f})" for doc in selected)
        )
    return ReferenceMatchResult(examples[:max_examples], selected, warnings)


def parse_om_document_to_examples(
    path: Path,
    *,
    fund_id: str,
    discipline_name: str,
    topics: list[str],
    source: str,
    limit: int,
) -> list[TrainingExampleRead]:
    text = extract_text(path)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    examples: list[TrainingExampleRead] = []
    current_topic = ""
    current_assessment_type = "practice"
    current_block: list[str] = []
    counter = 0

    def flush() -> None:
        nonlocal current_block, counter
        raw = "\n".join(current_block).strip()
        current_block = []
        if len(raw) < 25 or len(raw) > 2500:
            return
        question_text, answer = _split_answer(raw)
        if len(question_text) < 20:
            return
        counter += 1
        topic = current_topic or _infer_topic(question_text, topics)
        examples.append(
            TrainingExampleRead(
                id=f"om:{_hash_path(path)}:{counter}",
                fund_id=fund_id,
                item_id=None,
                discipline_name=discipline_name,
                topic=topic,
                competency_code="",
                indicator="",
                assessment_type=current_assessment_type,
                item_type=_item_type_for_assessment(current_assessment_type, question_text),
                difficulty=_difficulty_from_text(question_text),
                text=question_text,
                answer=answer,
                criteria=_criteria_for_om(current_assessment_type),
                quality_label="good",
                teacher_comment=f"Автоматически извлечено из локального OM: {path.name}",
                source=source,
                created_at=datetime.utcnow().isoformat(),
            )
        )

    for line in lines:
        lower = line.lower()
        topic = _topic_from_line(line, topics)
        if topic:
            flush()
            current_topic = topic
            continue
        detected_type = _assessment_type_from_line(lower)
        if detected_type:
            flush()
            current_assessment_type = detected_type
            continue
        if _looks_like_new_item(line):
            flush()
            current_block = [_clean_numbering(line)]
            if len(examples) >= limit:
                break
            continue
        if current_block:
            current_block.append(line)
            if len(" ".join(current_block)) > 1800:
                flush()
        if len(examples) >= limit:
            break
    flush()
    return examples[:limit]


def _scan_reference_documents() -> list[ReferenceDocument]:
    documents: list[ReferenceDocument] = []
    for path in REFERENCE_DIR.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        name = path.name.lower()
        document_type = "om" if any(marker in name for marker in OM_MARKERS) else "rp" if any(marker in name for marker in RP_MARKERS) else "unknown"
        if document_type == "unknown":
            continue
        documents.append(ReferenceDocument(path=path, document_type=document_type, discipline_key=_discipline_key(path.stem)))
    return documents


def _match_score(target_key: str, candidate_key: str, program_filename: str, om_filename: str) -> float:
    if not target_key or not candidate_key:
        return 0.0
    score = 0.7 * _text_similarity(target_key, candidate_key)
    score += 0.3 * _token_overlap(target_key, candidate_key)
    if _course_number(program_filename) and _course_number(program_filename) == _course_number(om_filename):
        score += 0.08
    return min(score, 1.0)


def _discipline_key(value: str) -> str:
    value = (value or "").lower()
    value = re.sub(r"\.(docx|pdf|txt)$", "", value)
    value = re.sub(r"\b(rp|om)\b", " ", value)
    value = re.sub(r"\b[рp][пp]д?\b", " ", value)
    value = re.sub(r"оценоч\w*|материал\w*|фос|фонд\w*|рабоч\w*|программ\w*|дисциплин\w*", " ", value)
    value = re.sub(r"\d+\s*курс|курс\s*\d+|семестр\s*\d+|\d+\s*семестр", " ", value)
    value = re.sub(r"[^0-9a-zа-яё]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _guess_discipline_from_text(text: str) -> str:
    for line in text.splitlines()[:80]:
        lower = line.lower()
        if "дисциплин" in lower and len(line) < 220:
            return line
    return ""


def _topic_from_line(line: str, known_topics: list[str]) -> str:
    clean = line.strip()
    lower = clean.lower()
    if re.match(r"^(тема|раздел)\s*\d+", lower):
        return re.sub(r"^(тема|раздел)\s*\d+\s*[.:\-–—]*\s*", "", clean, flags=re.IGNORECASE).strip() or clean
    for topic in known_topics:
        if topic and _text_similarity(clean, topic) >= 0.86:
            return topic
    return ""


def _assessment_type_from_line(lower: str) -> str:
    if len(lower) > 180:
        return ""
    for assessment_type, markers in ASSESSMENT_MARKERS.items():
        if any(marker in lower for marker in markers):
            return assessment_type
    return ""


def _looks_like_new_item(line: str) -> bool:
    clean = line.strip()
    if len(clean) < 8:
        return False
    if re.match(r"^(\d+|[а-яa-z])\s*[\).]\s+", clean, flags=re.IGNORECASE):
        return True
    if re.match(r"^(вопрос|задание|задача|пример|тест)\s*\d*\s*[.:\-–—]", clean, flags=re.IGNORECASE):
        return True
    return "?" in clean and len(clean) <= 450


def _clean_numbering(line: str) -> str:
    return re.sub(r"^(\d+|[а-яa-z])\s*[\).]\s+", "", line.strip(), flags=re.IGNORECASE)


def _split_answer(raw: str) -> tuple[str, str]:
    patterns = [r"\bответ\s*[:\-–—]", r"\bрешение\s*[:\-–—]", r"\bкритерии\s*[:\-–—]"]
    for pattern in patterns:
        match = re.search(pattern, raw, flags=re.IGNORECASE)
        if match:
            return raw[: match.start()].strip(), raw[match.end():].strip()
    return raw, ""


def _infer_topic(text: str, topics: list[str]) -> str:
    if not topics:
        return _shorten(text, 90)
    return max(topics, key=lambda topic: _text_similarity(text, topic))


def _difficulty_from_text(text: str) -> str:
    lower = text.lower()
    if any(marker in lower for marker in ("обосну", "разработ", "проанализ", "сравните", "проект")):
        return "hard"
    if any(marker in lower for marker in ("объясните", "решите", "опишите", "укажите")):
        return "medium"
    return "easy"


def _item_type_for_assessment(assessment_type: str, text: str) -> str:
    lower = text.lower()
    if assessment_type == "test_bank" or any(marker in lower for marker in ("варианты ответа", "выберите", "а)", "б)")):
        return "test"
    if assessment_type in {"practice", "exam_practice", "laboratory", "control_work"}:
        return "practice"
    if assessment_type in {"coursework", "course_project", "report_topics"}:
        return "project"
    return "open"


def _criteria_for_om(assessment_type: str) -> list[str]:
    if assessment_type in {"practice", "exam_practice", "laboratory", "control_work"}:
        return ["Корректность решения", "Обоснованность хода выполнения", "Полнота вывода"]
    if assessment_type == "test_bank":
        return ["Выбран правильный вариант", "Дано краткое обоснование ответа"]
    return ["Полнота раскрытия темы", "Корректность терминологии", "Логичность и структурированность ответа"]


def _course_number(value: str) -> str:
    match = re.search(r"(\d+)\s*курс", value.lower())
    return match.group(1) if match else ""


def _hash_path(path: Path) -> str:
    return hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:12]


def _token_overlap(left: str, right: str) -> float:
    left_tokens = set(_normalize(left).split())
    right_tokens = set(_normalize(right).split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _text_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, _normalize(left), _normalize(right)).ratio()


def _normalize(value: str) -> str:
    value = (value or "").lower().strip()
    value = re.sub(r"[^0-9a-zа-яё]+", " ", value)
    return re.sub(r"\s+", " ", value)


def _shorten(value: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "..."
