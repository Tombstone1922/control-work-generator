from dataclasses import dataclass
from itertools import cycle
from uuid import uuid4

from app.schemas import AssessmentCompetencyRead, AssessmentFundSection, AssessmentItemRead
from app.services.discipline_profile import detect_discipline_profile


TEMPLATES = {
    "oral": [
        "Раскройте содержание темы «{topic}» и поясните ее значение для дисциплины.",
        "Дайте определение ключевых понятий по теме «{topic}» и приведите пример.",
        "Перечислите основные элементы темы «{topic}» и объясните их взаимосвязь.",
        "Сравните основные подходы, применяемые в рамках темы «{topic}».",
        "Опишите типичные ошибки, возникающие при изучении темы «{topic}», и способы их устранения.",
    ],
    "practice": [
        "Выполните практическое задание по теме «{topic}»: разработайте алгоритм решения и обоснуйте выбранный подход.",
        "Проанализируйте прикладную ситуацию по теме «{topic}» и предложите решение.",
        "Составьте последовательность действий для решения задачи по теме «{topic}».",
        "Найдите возможные ошибки при решении задачи по теме «{topic}» и предложите способы их устранения.",
        "Разработайте фрагмент решения по теме «{topic}» и поясните, как проверить его корректность.",
    ],
    "exam_questions": [
        "Раскройте теоретические положения темы «{topic}». Приведите классификацию и пример применения.",
        "Объясните назначение и основные принципы темы «{topic}». Укажите ограничения применения.",
        "Проведите сравнительный анализ подходов в рамках темы «{topic}».",
        "Опишите алгоритм решения типовой задачи по теме «{topic}».",
    ],
    "exam_practice": [
        "Решите комплексную практическую задачу по теме «{topic}». Представьте ход решения и обоснуйте результат.",
        "Разработайте решение прикладной задачи по теме «{topic}» и оцените его корректность.",
        "Проанализируйте исходные данные по теме «{topic}» и предложите проверяемый способ решения.",
    ],
    "diagnostic": [
        "Выберите утверждение, наиболее точно характеризующее тему «{topic}».",
        "Определите корректный подход к решению задачи по теме «{topic}».",
        "Выберите признак, который является ключевым для темы «{topic}».",
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

DOMAIN_PRACTICE_TASKS = {
    "history_russia": [
        "Проанализируйте историческую ситуацию по теме «{topic}»: укажите причины, ключевые события, последствия и разные точки зрения исследователей.",
        "Составьте краткий исторический комментарий по теме «{topic}» с опорой на факты, даты и причинно-следственные связи.",
        "Сравните два исторических процесса или явления, связанных с темой «{topic}», и сформулируйте аргументированный вывод.",
    ],
    "databases": [
        "Спроектируйте фрагмент базы данных по теме «{topic}»: выделите сущности, атрибуты, первичные и внешние ключи.",
        "Составьте SQL-запрос по теме «{topic}» для выборки, фильтрации и агрегирования данных в учебной предметной области.",
        "Проанализируйте схему базы данных по теме «{topic}» и предложите способ нормализации или устранения нарушения целостности.",
    ],
    "programming": [
        "Напишите небольшую программу по теме «{topic}»: используйте ввод данных, обработку результата и вывод ответа.",
        "Разработайте алгоритм решения задачи по теме «{topic}» и приведите псевдокод или фрагмент программы.",
        "Найдите ошибку в простом фрагменте кода по теме «{topic}» и предложите исправленный вариант.",
    ],
    "web_development": [
        "Разработайте фрагмент веб-интерфейса по теме «{topic}» с использованием HTML, CSS и JavaScript.",
        "Опишите компонент React/Vue по теме «{topic}»: входные свойства, состояние, обработчики событий и взаимодействие с API.",
        "Проанализируйте ошибку frontend-кода по теме «{topic}» и предложите исправление с учетом адаптивности и доступности интерфейса.",
    ],
    "computer_networks": [
        "Решите задачу по теме «{topic}»: выполните расчет IP-адресации, маски подсети или маршрута передачи данных.",
        "Проанализируйте сетевую ситуацию по теме «{topic}» и предложите способ диагностики неисправности.",
        "Опишите настройку сетевого взаимодействия по теме «{topic}» и укажите команды или параметры проверки.",
    ],
    "physics": [
        "Решите расчетную задачу по теме «{topic}»: запишите исходные данные, используемые физические законы, ход решения и ответ с единицами измерения.",
        "Проанализируйте физический эксперимент по теме «{topic}»: определите измеряемые величины, возможные погрешности и вывод.",
        "Объясните техническую ситуацию по теме «{topic}» на основе физических законов и приведите расчетный пример.",
    ],
}

DOMAIN_DIAGNOSTIC_TASKS = {
    "databases": "Выберите SQL-конструкцию или проектное решение, корректное для ситуации по теме «{topic}».",
    "programming": "Выберите фрагмент алгоритма или кода, корректно решающий задачу по теме «{topic}».",
    "web_development": "Выберите корректный вариант HTML/CSS/JavaScript/React-решения по теме «{topic}».",
    "history_russia": "Выберите утверждение, корректно отражающее исторический факт или причинно-следственную связь по теме «{topic}».",
    "computer_networks": "Выберите корректное сетевое решение или параметр настройки по теме «{topic}».",
    "physics": "Выберите физический закон или расчетный подход, применимый к задаче по теме «{topic}».",
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
    domain_key, _ = detect_discipline_profile("", " ".join(topics), topics)

    topic_cycle = cycle(topics)
    competency_cycle = cycle(competencies) if competencies else None
    result: list[AssessmentItemRead] = []

    for index in range(count):
        topic = next(topic_cycle)
        competency = next(competency_cycle) if competency_cycle else None
        difficulty = _difficulty_for_index(index)
        item_type = _item_type_for_assessment(context.section.assessment_type)
        text = _build_task_text(context.section.assessment_type, topic, index, templates, domain_key)
        criteria = _criteria_for_item(topic, item_type, domain_key)
        answer = _answer_for_item(topic, item_type, domain_key)
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
                source_context=f"РПД/доменный профиль: тема «{topic}»",
                source_kind="template_domain" if domain_key else "template",
                status="draft",
            )
        )

    return result


def _build_task_text(assessment_type: str, topic: str, index: int, templates: list[str], domain_key: str) -> str:
    if assessment_type in {"practice", "exam_practice", "control_work", "laboratory"} and domain_key in DOMAIN_PRACTICE_TASKS:
        domain_templates = DOMAIN_PRACTICE_TASKS[domain_key]
        return domain_templates[index % len(domain_templates)].format(topic=topic)
    if assessment_type in {"diagnostic", "test_bank"} and domain_key in DOMAIN_DIAGNOSTIC_TASKS:
        return DOMAIN_DIAGNOSTIC_TASKS[domain_key].format(topic=topic)
    return templates[index % len(templates)].format(topic=topic)


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


def _criteria_for_item(topic: str, item_type: str, domain_key: str) -> list[str]:
    if item_type in {"diagnostic", "single_choice"}:
        return _diagnostic_options(topic, domain_key)
    if item_type in {"practice", "control_work", "laboratory", "project_topic", "coursework_topic"}:
        return [
            "Корректно выбран способ решения с учетом предметной области.",
            "Результат соответствует условию задания.",
            "Приведено обоснование, проверка результата и вывод.",
        ]
    return [
        "Раскрыты ключевые понятия темы.",
        "Ответ логично структурирован.",
        "Приведен релевантный предметный пример или обоснование.",
    ]


def _diagnostic_options(topic: str, domain_key: str) -> list[str]:
    correct = {
        "databases": f"Проектное или SQL-решение, корректно учитывающее структуру данных по теме «{topic}».",
        "programming": f"Алгоритм или фрагмент кода, корректно решающий задачу по теме «{topic}».",
        "web_development": f"Frontend-решение, корректно использующее HTML/CSS/JavaScript или компонентный подход по теме «{topic}».",
        "history_russia": f"Утверждение, верно отражающее факт, периодизацию или причинно-следственную связь по теме «{topic}».",
        "computer_networks": f"Сетевое решение, корректно учитывающее протоколы и параметры по теме «{topic}».",
        "physics": f"Физический закон или расчетный подход, корректно применимый к теме «{topic}».",
    }.get(domain_key, f"Основные понятия и способы применения темы «{topic}».")
    return [
        correct,
        "Ответ, содержащий только общие рассуждения без связи с предметной областью.",
        "Вариант, в котором нарушена логика решения или допущена фактическая ошибка.",
        "Описание, не позволяющее проверить сформированность компетенции.",
    ]


def _answer_for_item(topic: str, item_type: str, domain_key: str) -> str:
    if item_type in {"diagnostic", "single_choice"}:
        return _diagnostic_options(topic, domain_key)[0]
    if item_type in {"practice", "control_work", "laboratory"}:
        return f"Эталонное решение по теме «{topic}» должно содержать исходные данные, ход выполнения, предметное обоснование, проверку результата и итоговый вывод."
    return f"Эталонный ответ по теме «{topic}» должен раскрывать основные понятия, привести предметный пример применения и связать ответ с формируемой компетенцией."
