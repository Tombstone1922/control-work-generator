from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from app.services.document_parser import extract_text

SUPPORTED_EXTENSIONS = {".docx", ".pdf", ".txt"}
DEFAULT_CRITERIA = [
    "Ответ соответствует теме и проверяемой компетенции.",
    "Формулировка решения является полной и логически последовательной.",
    "Приведено обоснование ответа или способа решения.",
]
SECTION_MARKERS = {
    "oral": ("вопросы для устного опроса", "вопросы для текущего контроля"),
    "practice": ("практические задания для текущего контроля", "практические задания"),
    "exam_questions": ("вопросы для экзамена", "вопросы для зачета", "вопросы для зачёта"),
    "exam_practice": ("практические задания по дисциплине для экзамена", "практические задания для экзамена"),
    "diagnostic": ("итоговая диагностическая работа",),
}
STOP_HEADINGS = (
    "2.2", "2.3", "3.", "таблица 1", "критерии", "оценивание результатов", "правильный ответ", "итоговая диагностическая работа",
)
TOPIC_RE = re.compile(r"^Тема\s*\d+\.?\s*(.+)$", re.IGNORECASE)
NUMBERED_RE = re.compile(r"^\d+[\.)]\s+(.{8,})$")
COMPETENCY_RE = re.compile(r"\b(?:УК|ОПК|ПК|ППК|ПКО|ПКС|ОК)-?[А-ЯA-Z]?\d+(?:\.\d+)?\b", re.IGNORECASE)


@dataclass
class OMExtractionStats:
    files_total: int = 0
    files_processed: int = 0
    examples_total: int = 0
    zip_archives_extracted: int = 0
    errors: list[str] | None = None


def build_om_reference_corpus(input_path: str | Path, output_path: str | Path) -> OMExtractionStats:
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    stats = OMExtractionStats(errors=[])

    with output_path.open("w", encoding="utf-8") as output:
        if input_path.is_file() and input_path.suffix.lower() == ".zip":
            with TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                _extract_zip_recursive(input_path, temp_path, stats)
                _write_examples_from_folder(temp_path, output, stats)
        else:
            _extract_nested_zips(input_path, stats)
            _write_examples_from_folder(input_path, output, stats)
    return stats


def _extract_zip_recursive(zip_path: Path, destination: Path, stats: OMExtractionStats) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(destination)
    stats.zip_archives_extracted += 1
    _extract_nested_zips(destination, stats)


def _extract_nested_zips(root: Path, stats: OMExtractionStats) -> None:
    if not root.exists():
        return
    processed: set[Path] = set()
    while True:
        nested = [path for path in root.rglob("*.zip") if path.is_file() and path not in processed]
        if not nested:
            break
        for zip_path in nested:
            processed.add(zip_path)
            target = zip_path.with_suffix("")
            try:
                with zipfile.ZipFile(zip_path) as archive:
                    archive.extractall(target)
                stats.zip_archives_extracted += 1
            except Exception as exc:
                stats.errors.append(f"{zip_path.name}: nested zip extraction error: {exc}")


def _write_examples_from_folder(root: Path, output, stats: OMExtractionStats) -> None:
    files = [path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS]
    stats.files_total += len(files)
    for path in files:
        try:
            text = extract_text(path)
            examples = extract_om_examples(text, path.name)
            for record in examples:
                output.write(json.dumps(record, ensure_ascii=False) + "\n")
            stats.files_processed += 1
            stats.examples_total += len(examples)
        except Exception as exc:
            stats.errors.append(f"{path.name}: {exc}")


def extract_om_examples(text: str, filename: str = "") -> list[dict]:
    lines = _clean_lines(text)
    discipline_name = _extract_discipline_name(text, filename)
    competencies = _extract_competencies(text)
    records: list[dict] = []

    for assessment_type in ("oral", "practice", "exam_questions", "exam_practice", "diagnostic"):
        section_lines = _section_lines(lines, assessment_type)
        records.extend(_examples_from_section(section_lines, discipline_name, competencies, assessment_type, filename))

    return records


def _clean_lines(text: str) -> list[str]:
    result = []
    for line in text.replace("\r", "\n").splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            result.append(line)
    return result


def _extract_discipline_name(text: str, filename: str) -> str:
    patterns = [
        r"Оценочные материалы по дисциплине\s+(?:по дисциплине\s+)?(.+?)\s+направления подготовки",
        r"изучения дисциплины\s+«([^»]+)»",
        r"дисциплине\s+(.+?)\s+должны сформироваться компетенции",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            value = re.sub(r"\s+", " ", match.group(1)).strip(" .;:-—\n\t")
            value = re.sub(r"^[А-ЯA-ZБ]?\.\d+(?:\.\d+)*\s*", "", value)
            return value.strip("«»\" ")[:180]
    return Path(filename).stem


def _extract_competencies(text: str) -> list[str]:
    return list(dict.fromkeys(match.upper().replace(" ", "") for match in COMPETENCY_RE.findall(text)))[:20]


def _section_lines(lines: list[str], assessment_type: str) -> list[str]:
    markers = SECTION_MARKERS[assessment_type]
    start = None
    for index, line in enumerate(lines):
        lower = line.lower()
        if any(marker in lower for marker in markers):
            start = index + 1
            break
    if start is None:
        return []

    collected = []
    for line in lines[start:]:
        lower = line.lower()
        if assessment_type != "diagnostic" and any(lower.startswith(marker) for marker in STOP_HEADINGS):
            break
        if assessment_type == "diagnostic" and lower.startswith("таблица 1"):
            break
        collected.append(line)
    return collected


def _examples_from_section(lines: list[str], discipline: str, competencies: list[str], assessment_type: str, filename: str) -> list[dict]:
    result: list[dict] = []
    topic = "Общие вопросы дисциплины"
    competency = competencies[0] if competencies else ""
    item_type = _item_type(assessment_type)
    difficulty = "medium"

    for line in lines:
        topic_match = TOPIC_RE.match(line)
        if topic_match:
            topic = _clean_text(topic_match.group(1))
            continue
        question_match = NUMBERED_RE.match(line)
        if not question_match:
            continue
        text = _clean_text(question_match.group(1))
        if not _is_usable_question(text):
            continue
        result.append(_record(discipline, topic, competency, assessment_type, item_type, difficulty, text, filename))
    return result[:300]


def _record(discipline: str, topic: str, competency: str, assessment_type: str, item_type: str, difficulty: str, text: str, filename: str) -> dict:
    return {
        "id": f"om-{uuid4()}",
        "instruction": "Сформируй оценочное задание для фонда оценочных средств по дисциплине на основе корпуса готовых оценочных материалов.",
        "input": {
            "discipline_name": discipline,
            "topic": topic,
            "competency_code": competency,
            "indicator": "",
            "assessment_type": assessment_type,
            "item_type": item_type,
            "difficulty": difficulty,
            "source_file": filename,
        },
        "output": {
            "text": text,
            "answer": _default_answer(topic, item_type),
            "criteria": _criteria_for(item_type),
        },
        "quality_label": "good",
        "source": "om_reference",
    }


def _item_type(assessment_type: str) -> str:
    return {
        "oral": "theoretical_open",
        "practice": "practice",
        "exam_questions": "theoretical_open",
        "exam_practice": "practice",
        "diagnostic": "diagnostic",
    }.get(assessment_type, "open")


def _criteria_for(item_type: str) -> list[str]:
    if item_type == "diagnostic":
        return [
            "Корректный вариант выбран в соответствии с содержанием дисциплины.",
            "Ответ связан с проверяемой компетенцией.",
            "Отсутствуют фактические ошибки.",
        ]
    if item_type == "practice":
        return [
            "Практическое задание выполнено полностью.",
            "Ход решения логически обоснован.",
            "Результат проверен и представлен в требуемой форме.",
        ]
    return DEFAULT_CRITERIA


def _default_answer(topic: str, item_type: str) -> str:
    if item_type == "diagnostic":
        return "Правильный ответ определяется преподавателем при экспертной проверке диагностического задания."
    if item_type == "practice":
        return f"Эталонное решение по теме «{topic}» должно содержать ход выполнения, результат и обоснование."
    return f"Эталонный ответ по теме «{topic}» должен раскрывать ключевые понятия и содержать пример применения."


def _clean_text(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" .;:-—\t")
    return value


def _is_usable_question(value: str) -> bool:
    lower = value.lower()
    if len(value) < 12 or len(value) > 1200:
        return False
    if lower in {"знать", "уметь", "владеть"}:
        return False
    if any(marker in lower for marker in ("таблица", "страница", "критерии", "оценка", "шкала оценки")):
        return False
    return True
