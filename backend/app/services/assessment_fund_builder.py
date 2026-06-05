import re
from dataclasses import dataclass
from uuid import uuid4

from app.schemas import (
    AssessmentCompetencyRead,
    AssessmentFundSection,
    AssessmentFundValidation,
    ProgramAnalysis,
)

DEFAULT_LEVELS = [
    "Пороговый (удовлетворительно)",
    "Повышенный (хорошо)",
    "Продвинутый (отлично)",
]

DEFAULT_SECTIONS = [
    ("competency_matrix", "1. Перечень компетенций и уровни их сформированности", "competency_matrix"),
    ("current_oral", "2.1 Вопросы для устного опроса", "oral"),
    ("current_practice", "2.1 Практические задания для текущего контроля", "practice"),
    ("intermediate_exam_questions", "2.2 Вопросы для экзамена", "exam_questions"),
    ("intermediate_exam_practice", "2.2 Практические задания для экзамена", "exam_practice"),
    ("diagnostic", "3. Итоговая диагностическая работа", "diagnostic"),
    ("grading_rubric", "4. Критерии выставления оценок", "grading_rubric"),
]

ASSESSMENT_TYPE_LABELS = {
    "oral": "Устный опрос",
    "practice": "Практические задания",
    "exam_questions": "Вопросы для экзамена",
    "exam_practice": "Практические задания для экзамена",
    "diagnostic": "Итоговая диагностическая работа",
    "grading_rubric": "Критерии оценивания",
    "competency_matrix": "Матрица компетенций",
}


@dataclass
class AssessmentFundDraft:
    discipline_name: str
    title: str
    assessment_types: list[str]
    sections: list[AssessmentFundSection]
    competencies: list[AssessmentCompetencyRead]
    validation: AssessmentFundValidation


def build_assessment_fund(program: ProgramAnalysis, discipline_name: str | None = None) -> AssessmentFundDraft:
    name = (discipline_name or _guess_discipline_name(program.filename)).strip()
    topics = program.topics or ["Общие положения дисциплины"]
    competencies = _build_competencies(program)
    assessment_types = _detect_assessment_types(program.text_preview)
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
    if any(section.planned_items == 0 for section in enabled if section.assessment_type not in {"competency_matrix", "grading_rubric"}):
        warnings.append("Для некоторых разделов не рассчитано количество заданий.")

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
    outcome_lines = program.learning_outcomes[:12]

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
    for code, title, assessment_type in DEFAULT_SECTIONS:
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
    count = max(len(topics), 1)
    return {
        "oral": count * 5,
        "practice": count * 4,
        "exam_questions": max(count * 2, 20),
        "exam_practice": max(count, 10),
        "diagnostic": max(count * 3, 30),
        "competency_matrix": 0,
        "grading_rubric": 0,
    }.get(assessment_type, 0)


def _detect_assessment_types(text_preview: str) -> list[str]:
    lower = text_preview.lower()
    types = ["oral", "practice", "diagnostic", "grading_rubric", "competency_matrix"]
    if any(word in lower for word in ("экзамен", "экзамена")):
        types.extend(["exam_questions", "exam_practice"])
    else:
        types.extend(["exam_questions", "exam_practice"])
    return list(dict.fromkeys(types))


def _guess_discipline_name(filename: str) -> str:
    value = re.sub(r"\.(docx|pdf|txt)$", "", filename, flags=re.IGNORECASE)
    value = re.sub(r"[_-]+", " ", value)
    value = re.sub(r"\b(рпд|рабочая программа|program)\b", "", value, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", value).strip() or "Наименование дисциплины"


def _section_description(assessment_type: str) -> str:
    label = ASSESSMENT_TYPE_LABELS.get(assessment_type, assessment_type)
    return f"Раздел ФОС: {label}. Формируется на основании тем и компетенций, извлеченных из РПД."
