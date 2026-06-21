from dataclasses import dataclass
from itertools import cycle
from uuid import uuid4

from app.schemas import AssessmentCompetencyRead, AssessmentFundSection, AssessmentItemRead
from app.services.assessment_item_smart_builder import build_smart_task


@dataclass
class ItemGenerationContext:
    fund_id: str
    section: AssessmentFundSection
    topics: list[str]
    competencies: list[AssessmentCompetencyRead]
    max_items: int


def generate_items_for_section(context: ItemGenerationContext) -> list[AssessmentItemRead]:
    if not context.section.enabled:
        return []
    if context.section.assessment_type in {"competency_matrix", "grading_rubric"}:
        return []

    topics = context.section.topics or context.topics or ["Общие положения дисциплины"]
    competencies = context.competencies or []
    planned = max(context.section.planned_items, 0)
    count = min(planned, context.max_items)

    topic_cycle = cycle(topics)
    competency_cycle = cycle(competencies) if competencies else None
    result: list[AssessmentItemRead] = []

    for index in range(count):
        raw_topic = next(topic_cycle)
        competency = next(competency_cycle) if competency_cycle else None
        difficulty = _difficulty_for_index(index)
        item_type = _item_type_for_assessment(context.section.assessment_type)
        task = build_smart_task(
            topic=raw_topic,
            assessment_type=context.section.assessment_type,
            item_type=item_type,
            index=index,
            difficulty=difficulty,
        )
        indicator = competency.indicators[0] if competency and competency.indicators else ""

        result.append(
            AssessmentItemRead(
                id=str(uuid4()),
                fund_id=context.fund_id,
                section_code=context.section.code,
                assessment_type=context.section.assessment_type,
                item_type=item_type,
                topic=task.topic,
                competency_code=competency.code if competency else "",
                indicator=indicator,
                difficulty=difficulty,
                text=task.text,
                answer=task.answer,
                criteria=task.criteria,
                source_context=f"Smart FOS task builder; topic_family={task.topic_family}; topic=«{task.topic}»",
                source_kind="smart_template",
                status="draft",
            )
        )

    return result


def _difficulty_for_index(index: int) -> str:
    return ("easy", "medium", "medium", "hard")[index % 4]


def _item_type_for_assessment(assessment_type: str) -> str:
    return {
        "oral": "theoretical_open",
        "practice": "practice",
        "exam_questions": "theoretical_open",
        "exam_practice": "practice",
        "diagnostic": "diagnostic",
        "control_work": "control_work",
        "coursework": "coursework_topic",
        "course_project": "project_topic",
        "laboratory": "laboratory",
        "test_bank": "single_choice",
        "report_topics": "report_topic",
        "credit": "theoretical_open",
    }.get(assessment_type, "open")
