from dataclasses import dataclass
from itertools import cycle
from uuid import uuid4

from app.schemas import AssessmentCompetencyRead, AssessmentFundSection, AssessmentItemRead


TEMPLATES = {
    "oral": [
        "Раскройте содержание темы «{topic}» и поясните ее значение для дисциплины.",
        "Дайте определение ключевых понятий по теме «{topic}» и приведите пример.",
        "Перечислите основные элементы темы «{topic}» и объясните их взаимосвязь.",
        "Сравните основные подходы, применяемые в рамках темы «{topic}».",
    ],
    "practice": [
        "Выполните практическое задание по теме «{topic}»: разработайте алгоритм решения и обоснуйте выбранный подход.",
        "Проанализируйте прикладную ситуацию по теме «{topic}» и предложите решение.",
        "Составьте последовательность действий для решения задачи по теме «{topic}».",
        "Найдите возможные ошибки при решении задачи по теме «{topic}» и предложите способы их устранения.",
    ],
    "exam_questions": [
        "Раскройте теоретические положения темы «{topic}». Приведите классификацию и пример применения.",
        "Объясните назначение и основные принципы темы «{topic}». Укажите ограничения применения.",
        "Проведите сравнительный анализ подходов в рамках темы «{topic}».",
    ],
    "exam_practice": [
        "Решите комплексную практическую задачу по теме «{topic}». Представьте ход решения и обоснуйте результат.",
        "Разработайте решение прикладной задачи по теме «{topic}» и оцените его корректность.",
    ],
    "diagnostic": [
        "Выберите и обоснуйте корректный способ решения задачи по теме «{topic}».",
        "Определите, какое утверждение наиболее точно характеризует тему «{topic}», и поясните ответ.",
        "Выполните краткое диагностическое задание по теме «{topic}».",
    ],
    "control_work": [
        "Выполните контрольное задание по теме «{topic}». Представьте решение и краткое обоснование.",
        "Подготовьте развернутый ответ по теме «{topic}» с практическим примером.",
    ],
    "coursework": [
        "Разработайте курсовую работу по теме «{topic}»: проведите анализ предметной области, предложите решение и обоснуйте результат.",
    ],
    "course_project": [
        "Разработайте курсовой проект по теме «{topic}»: спроектируйте решение, опишите архитектуру и этапы реализации.",
    ],
    "laboratory": [
        "Выполните лабораторную работу по теме «{topic}». Зафиксируйте исходные данные, ход выполнения и выводы.",
    ],
    "test_bank": [
        "Выберите верное утверждение по теме «{topic}».",
        "Определите корректное описание понятия по теме «{topic}».",
    ],
    "report_topics": [
        "Подготовьте доклад по теме «{topic}» с анализом основных подходов и примеров применения.",
    ],
    "credit": [
        "Дайте развернутый ответ по теме «{topic}» и приведите практический пример.",
    ],
}


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
    templates = TEMPLATES.get(context.section.assessment_type, TEMPLATES["oral"])
    planned = max(context.section.planned_items, 0)
    count = min(planned, context.max_items)

    topic_cycle = cycle(topics)
    competency_cycle = cycle(competencies) if competencies else None
    result: list[AssessmentItemRead] = []

    for index in range(count):
        topic = next(topic_cycle)
        competency = next(competency_cycle) if competency_cycle else None
        template = templates[index % len(templates)]
        difficulty = _difficulty_for_index(index)
        item_type = _item_type_for_assessment(context.section.assessment_type)
        text = template.format(topic=topic)
        criteria = _criteria_for_type(item_type)
        answer = _answer_stub(topic, item_type)
        indicator = competency.indicators[0] if competency and competency.indicators else ""

        result.append(
            AssessmentItemRead(
                id=str(uuid4()),
                fund_id=context.fund_id,
                section_code=context.section.code,
                assessment_type=context.section.assessment_type,
                item_type=item_type,
                topic=topic,
                competency_code=competency.code if competency else "",
                indicator=indicator,
                difficulty=difficulty,
                text=text,
                answer=answer,
                criteria=criteria,
                source_context=f"РПД: тема «{topic}»",
                source_kind="template",
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


def _criteria_for_type(item_type: str) -> list[str]:
    if item_type in {"practice", "control_work", "laboratory", "project_topic", "coursework_topic"}:
        return [
            "Корректно выбран способ решения.",
            "Результат соответствует условию задания.",
            "Приведено обоснование и сформулирован вывод.",
        ]
    if item_type == "single_choice":
        return ["Выбран корректный вариант ответа."]
    return [
        "Раскрыты ключевые понятия темы.",
        "Ответ логично структурирован.",
        "Приведен релевантный пример или обоснование.",
    ]


def _answer_stub(topic: str, item_type: str) -> str:
    if item_type == "single_choice":
        return "Эталонный вариант ответа необходимо уточнить преподавателю после генерации банка заданий."
    return f"Эталонный ответ по теме «{topic}» формируется и уточняется преподавателем в ходе экспертной проверки."
