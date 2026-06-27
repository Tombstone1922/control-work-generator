import re
from dataclasses import dataclass
from uuid import uuid4

from app.schemas import (
    AssessmentCompetencyRead,
    AssessmentFundSection,
    AssessmentFundValidation,
    ProgramAnalysis,
)
from app.services.assessment_item_smart_builder import normalize_topic

DEFAULT_LEVELS = [
    "Пороговый (удовлетворительно)",
    "Повышенный (хорошо)",
    "Продвинутый (отлично)",
]

OM_PROFILE_PLANNED_ITEMS = {
    "oral": 40,
    "practice": 20,
    "credit": 32,
    "credit_practice": 13,
    "diagnostic": 40,
}

BASE_SECTIONS = [
    ("competency_matrix", "1. Перечень компетенций и уровни их сформированности", "competency_matrix"),
    ("current_oral", "2.1 Вопросы для устного опроса", "oral"),
    ("current_practice", "2.1 Практические задания для текущего контроля", "practice"),
    ("diagnostic", "2.3 Итоговая диагностическая работа по дисциплине", "diagnostic"),
    ("grading_rubric", "4. Критерии выставления оценок", "grading_rubric"),
]

OPTIONAL_SECTIONS = [
    ("intermediate_exam_questions", "2.2 Вопросы для экзамена", "exam_questions"),
    ("intermediate_exam_practice", "2.2 Практические задания для экзамена", "exam_practice"),
    ("intermediate_credit", "2.2 Вопросы к зачету", "credit"),
    ("intermediate_credit_practice", "2.2 Практические задания для проведения зачета", "credit_practice"),
    ("control_work", "2.3 Контрольная работа", "control_work"),
    ("coursework", "2.4 Курсовая работа", "coursework"),
    ("course_project", "2.4 Курсовой проект", "course_project"),
    ("laboratory", "2.5 Лабораторные работы", "laboratory"),
    ("test_bank", "2.6 Банк тестовых заданий", "test_bank"),
    ("report_topics", "2.7 Темы рефератов и докладов", "report_topics"),
]

ASSESSMENT_TYPE_LABELS = {
    "oral": "Устный опрос",
    "practice": "Практические задания",
    "exam_questions": "Вопросы для экзамена",
    "exam_practice": "Практические задания для экзамена",
    "credit": "Вопросы к зачету",
    "credit_practice": "Практические задания к зачету",
    "control_work": "Контрольная работа",
    "coursework": "Курсовая работа",
    "course_project": "Курсовой проект",
    "laboratory": "Лабораторные работы",
    "test_bank": "Банк тестовых заданий",
    "report_topics": "Темы рефератов и докладов",
    "diagnostic": "Итоговая диагностическая работа",
    "grading_rubric": "Критерии оценивания",
    "competency_matrix": "Матрица компетенций",
}

SERVICE_ASSESSMENT_TYPES = {"competency_matrix", "grading_rubric"}
COMPACT_HIGH_VOLUME_TYPES = {"oral", "control_work"}


@dataclass
class AssessmentFundDraft:
    discipline_name: str
    title: str
    assessment_types: list[str]
    sections: list[AssessmentFundSection]
    competencies: list[AssessmentCompetencyRead]
    validation: AssessmentFundValidation


def build_assessment_fund(
    program: ProgramAnalysis,
    discipline_name: str | None = None,
    source_text: str | None = None,
) -> AssessmentFundDraft:
    source_text = source_text or program.text_preview
    name = (discipline_name or _extract_discipline_name(source_text) or _guess_discipline_name(program.filename)).strip()
    topics = _clean_topics(program.topics or ["Общие положения дисциплины"])
    competencies = _build_competencies(program)
    assessment_types = _detect_assessment_types(source_text or program.text_preview)
    sections = _build_sections(topics, assessment_types)
    validation = validate_assessment_fund(sections, competencies, topics)

    return AssessmentFundDraft(
        discipline_name=name,
        title=f"Фонд оценочных средств по дисциплине «{name}»",
        assessment_types=assessment_types,
        sections=sections,
        competencies=competencies,
        validation=validation,
    )


def validate_assessment_fund(
    sections: list[AssessmentFundSection],
    competencies: list[AssessmentCompetencyRead],
    topics: list[str],
) -> AssessmentFundValidation:
    enabled = [section for section in sections if section.enabled]
    covered_topics = {topic for section in enabled for topic in section.topics}
    missing_sections = [section.title for section in sections if not section.enabled]
    warnings: list[str] = []

    if not competencies:
        warnings.append("Компетенции из РПД не распознаны. Необходимо заполнить матрицу вручную.")
    if not topics:
        warnings.append("Темы дисциплины не распознаны.")
    if any(
        section.planned_items == 0
        for section in enabled
        if section.assessment_type not in SERVICE_ASSESSMENT_TYPES
    ):
        warnings.append("Для некоторых разделов не рассчитано количество заданий.")

    required_types = {"competency_matrix", "oral", "practice", "diagnostic", "grading_rubric"}
    enabled_types = {section.assessment_type for section in enabled}
    missing_required = required_types - enabled_types
    if missing_required:
        warnings.append("Отключены базовые разделы ФОС: " + ", ".join(sorted(missing_required)) + ".")

    completeness_score = round(100 * len(enabled) / max(len(sections), 1))
    topics_score = round(100 * len(covered_topics) / max(len(topics), 1))
    competencies_score = 100 if competencies else 0

    return AssessmentFundValidation(
        completeness_score=completeness_score,
        topics_coverage_score=topics_score,
        competencies_coverage_score=competencies_score,
        missing_sections=missing_sections,
        warnings=warnings,
    )


def _build_competencies(program: ProgramAnalysis) -> list[AssessmentCompetencyRead]:
    result: list[AssessmentCompetencyRead] = []
    outcome_lines = program.learning_outcomes[:20]

    for code in program.competencies:
        indicators = [line for line in outcome_lines if code.lower() in line.lower()]
        if not indicators:
            indicators = [f"Индикатор достижения {code}: способность применять знания и умения по дисциплине."]
        result.append(
            AssessmentCompetencyRead(
                id=str(uuid4()),
                code=code,
                description=f"Компетенция {code}, формируемая в рамках освоения дисциплины.",
                indicators=indicators[:5],
                levels=DEFAULT_LEVELS,
            )
        )
    return result


def _build_sections(topics: list[str], assessment_types: list[str]) -> list[AssessmentFundSection]:
    sections: list[AssessmentFundSection] = []
    all_sections = BASE_SECTIONS + OPTIONAL_SECTIONS
    for code, title, assessment_type in all_sections:
        enabled = assessment_type in assessment_types or assessment_type in {"competency_matrix", "grading_rubric"}
        planned_items = _planned_items(assessment_type, topics) if enabled else 0
        sections.append(
            AssessmentFundSection(
                code=code,
                title=title,
                description=_section_description(assessment_type),
                assessment_type=assessment_type,
                enabled=enabled,
                topics=topics if assessment_type not in {"competency_matrix", "grading_rubric"} else [],
                planned_items=planned_items,
                generated_items=0,
            )
        )
    return sections


def _planned_items(assessment_type: str, topics: list[str]) -> int:
    if assessment_type in SERVICE_ASSESSMENT_TYPES:
        return 0
    if assessment_type in OM_PROFILE_PLANNED_ITEMS:
        return OM_PROFILE_PLANNED_ITEMS[assessment_type]
    if assessment_type in COMPACT_HIGH_VOLUME_TYPES:
        return 15
    return 10


def _detect_assessment_types(source_text: str) -> list[str]:
    lower = source_text.lower()
    types = ["oral", "practice", "diagnostic", "grading_rubric", "competency_matrix"]

    if re.search(r"\bэкзамен\w*", lower):
        types.extend(["exam_questions", "exam_practice"])
    if re.search(r"\bзач[её]т\w*", lower):
        types.extend(["credit", "credit_practice"])
    if re.search(r"контрольн\w*\s+работ", lower):
        types.append("control_work")
    if re.search(r"курсов\w*\s+работ", lower):
        types.append("coursework")
    if re.search(r"курсов\w*\s+проект", lower):
        types.append("course_project")
    if re.search(r"лабораторн\w*\s+работ", lower):
        types.append("laboratory")
    if re.search(r"тестов\w*\s+задан|тестирован", lower):
        types.append("test_bank")
    if re.search(r"реферат|доклад", lower):
        types.append("report_topics")

    return list(dict.fromkeys(types))


def _extract_discipline_name(text: str) -> str:
    patterns = [
        r"по дисциплине\s+(.+?)\s+(?:направления|направлению|профиль|формы обучения|форма обучения)",
        r"дисциплин[ые]\s+«([^»]+)»",
        r"дисциплина\s+«([^»]+)»",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        value = _clean_discipline_name(match.group(1))
        if _is_valid_discipline_name(value):
            return value
    return ""


def _clean_topics(topics: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for topic in topics:
        cleaned = normalize_topic(topic)
        key = cleaned.lower().replace("ё", "е")
        if not cleaned or key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result or ["Общие положения дисциплины"]


def _guess_discipline_name(filename: str) -> str:
    value = re.sub(r"\.(docx|pdf|txt)$", "", filename, flags=re.IGNORECASE)
    value = re.sub(r"[_-]+", " ", value)
    value = re.sub(r"\b(рпд|рабочая программа|program|rp)\b", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\b\d{1,5}(?:\.\d{1,5})*\b", "", value)
    return re.sub(r"\s+", " ", value).strip() or "Наименование дисциплины"


def _clean_discipline_name(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" .;:-—\t\n\r\"«»")
    value = re.sub(r"^[А-ЯA-ZБ]?\.?\d+(?:\.\d+)*\s*", "", value)
    return value[:180].strip(" .;:-—\t\n\r\"«»")


def _is_valid_discipline_name(value: str) -> bool:
    if not 4 <= len(value) <= 180:
        return False
    lower = value.lower()
    return not any(word in lower for word in ("министерство", "университет", "кафедра", "направления подготовки"))


def _section_description(assessment_type: str) -> str:
    label = ASSESSMENT_TYPE_LABELS.get(assessment_type, assessment_type)
    return f"Раздел ФОС: {label}. Формируется на основании тем и компетенций, извлеченных из РПД."
