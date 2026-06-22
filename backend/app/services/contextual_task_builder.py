from __future__ import annotations

import re
from dataclasses import replace
from difflib import SequenceMatcher

from app.services.assessment_item_smart_builder import SmartTaskDraft, build_smart_task
from app.services.discipline_knowledge_base import TopicKnowledgeContext, get_topic_knowledge_context

OPERATIONS = [
    "проанализируйте",
    "сравните",
    "спроектируйте",
    "разработайте",
    "найдите ошибку",
    "обоснуйте выбор",
    "составьте чек-лист",
    "сформулируйте критерии",
    "постройте алгоритм",
    "подготовьте мини-кейс",
]

PRACTICE_OPERATIONS = [
    "разработайте",
    "спроектируйте",
    "составьте",
    "реализуйте",
    "проанализируйте",
    "подготовьте",
]

ORAL_QUESTION_STEMS = [
    "Вопрос: объясните, какую роль играет тема «{topic}» в дисциплине «{discipline}» и приведите предметный пример.",
    "Вопрос: раскройте основные понятия темы «{topic}» и покажите их связь с темой «{related}».",
    "Вопрос: назовите типовые ошибки по теме «{topic}» и объясните, как их обнаружить или предотвратить.",
    "Вопрос: сравните два подхода к теме «{topic}» и укажите, в каких ситуациях каждый из них применим.",
]

COURSEWORK_TEMPLATES = [
    "Тема курсовой работы: «Разработка решения по направлению “{topic}” для ситуации “{scenario}”».",
    "Тема курсового проекта: «Проектирование и реализация компонента по теме “{topic}” в рамках проекта “{scenario}”».",
    "Тема курсовой работы: «Анализ, проектирование и проверка решения по теме “{topic}”».",
]

SCENARIOS = [
    "учебный программный проект",
    "информационная система кафедры",
    "личный кабинет пользователя",
    "сервис записи на мероприятие",
    "мобильное приложение для студентов",
    "веб-сервис обработки заявок",
    "аналитический модуль для отчетности",
    "модуль контроля качества",
    "прототип клиент-серверного приложения",
    "система хранения и обработки данных",
]

ARTIFACTS = [
    "таблицу решений",
    "перечень требований",
    "алгоритм действий",
    "фрагмент проектной документации",
    "набор тест-кейсов",
    "чек-лист проверки",
    "схему компонентов",
    "пример входных и выходных данных",
    "критерии приемки",
    "план проверки результата",
]


def build_contextual_task(
    *,
    discipline_name: str,
    topic: str,
    all_topics: list[str],
    assessment_type: str,
    item_type: str,
    index: int,
    difficulty: str,
    used_texts: list[str] | None = None,
) -> SmartTaskDraft:
    context = get_topic_knowledge_context(
        discipline_name=discipline_name,
        topic=topic,
        all_topics=all_topics,
    )
    base = build_smart_task(topic=topic, assessment_type=assessment_type, item_type=item_type, index=index, difficulty=difficulty)
    candidates = []
    for offset in range(12):
        candidates.append(_contextualize(base, context, assessment_type, item_type, index + offset))
    used_texts = used_texts or []
    best = _select_least_similar(candidates, used_texts)
    return best


def _contextualize(
    base: SmartTaskDraft,
    context: TopicKnowledgeContext,
    assessment_type: str,
    item_type: str,
    variant: int,
) -> SmartTaskDraft:
    operation = OPERATIONS[variant % len(OPERATIONS)]
    practice_operation = PRACTICE_OPERATIONS[variant % len(PRACTICE_OPERATIONS)]
    scenario = SCENARIOS[variant % len(SCENARIOS)]
    artifact = ARTIFACTS[variant % len(ARTIFACTS)]
    terms = _short_terms(context.key_terms, max_terms=3)
    related = _short_related(context.related_topics, base.topic) or base.topic
    discipline = context.discipline_name or context.profile_name or "дисциплины"
    context_tail = _context_tail(terms, related)

    bucket = _bucket(assessment_type, item_type)
    if bucket == "oral":
        text = ORAL_QUESTION_STEMS[variant % len(ORAL_QUESTION_STEMS)].format(
            topic=base.topic,
            related=related,
            discipline=discipline,
        )
        text += f" В ответе используйте понятия: {terms or 'ключевые понятия темы'}."
    elif bucket == "coursework":
        text = COURSEWORK_TEMPLATES[variant % len(COURSEWORK_TEMPLATES)].format(topic=base.topic, scenario=scenario)
        text += (
            f" В работе необходимо раскрыть актуальность, сформулировать цель и задачи, выполнить анализ предметной области, "
            f"подготовить {artifact}, применить понятия: {terms or 'ключевые понятия темы'}, "
            f"описать ожидаемый результат и критерии его проверки."
        )
    elif bucket == "diagnostic":
        text = (
            f"Диагностическое задание: выберите или сформулируйте корректное решение для ситуации «{scenario}» по теме «{base.topic}». "
            f"При решении учитывайте: {terms or 'ключевые понятия темы'}{context_tail}."
        )
    else:
        text = (
            f"Практическое задание: для ситуации «{scenario}» {practice_operation} результат по теме «{base.topic}». "
            f"Необходимо подготовить {artifact}; использовать понятия: {terms or 'ключевые понятия темы'}{context_tail}. "
            f"Результат должен быть представлен в проверяемом виде и сопровождаться кратким обоснованием."
        )

    answer = _answer(base.topic, bucket, terms, related, artifact)
    criteria = _criteria(bucket, terms, artifact)
    return replace(base, text=_cleanup(text), answer=_cleanup(answer), criteria=criteria)


def _select_least_similar(candidates: list[SmartTaskDraft], used_texts: list[str]) -> SmartTaskDraft:
    if not used_texts:
        return candidates[0]
    best = candidates[0]
    best_score = 10.0
    normalized_used = [_norm(value) for value in used_texts if value]
    for candidate in candidates:
        candidate_norm = _norm(candidate.text)
        score = max((SequenceMatcher(None, candidate_norm, value).ratio() for value in normalized_used), default=0.0)
        if score < best_score:
            best = candidate
            best_score = score
    return best


def is_too_similar(text: str, used_texts: list[str], threshold: float = 0.84) -> bool:
    normalized = _norm(text)
    return any(SequenceMatcher(None, normalized, _norm(value)).ratio() >= threshold for value in used_texts if value)


def _bucket(assessment_type: str, item_type: str) -> str:
    if assessment_type in {"exam_questions", "credit", "oral"}:
        return "oral"
    if assessment_type in {"coursework", "course_project"} or item_type in {"coursework_topic", "project_topic"}:
        return "coursework"
    if assessment_type in {"diagnostic", "test_bank"}:
        return "diagnostic"
    return "practice"


def _short_terms(terms: list[str], max_terms: int = 3) -> str:
    selected = []
    for term in terms:
        if term not in selected and len(term) >= 3:
            selected.append(term)
        if len(selected) >= max_terms:
            break
    return ", ".join(selected)


def _short_related(related_topics: list[str], topic: str) -> str:
    topic_norm = _norm(topic)
    for value in related_topics:
        if _norm(value) != topic_norm:
            return value[:120]
    return ""


def _context_tail(terms: str, related: str) -> str:
    tail = []
    if related:
        tail.append(f" связь с темой «{related}»")
    if terms:
        tail.append(" предметную терминологию")
    return ";" + ";".join(tail) if tail else ""


def _answer(topic: str, bucket: str, terms: str, related: str, artifact: str) -> str:
    if bucket == "oral":
        return f"Ожидаемый ответ: раскрыты ключевые понятия темы «{topic}», использованы понятия {terms or 'предметной области'}, показана связь с темой «{related or topic}» и приведен корректный пример."
    if bucket == "coursework":
        return f"Ожидаемая структура курсовой работы: актуальность, цель и задачи, анализ предметной области, проектное решение, {artifact}, проверка результата, выводы и список источников."
    if bucket == "diagnostic":
        return f"Правильный ответ должен учитывать тему «{topic}», понятия {terms or 'предметной области'} и проверяемый практический результат."
    return f"Ожидаемый результат: подготовлен {artifact}, применены понятия {terms or 'предметной области'}, показана связь с темой «{related or topic}», результат проверен и кратко обоснован."


def _criteria(bucket: str, terms: str, artifact: str) -> list[str]:
    if bucket == "oral":
        return [
            "Ответ прямо отвечает на поставленный вопрос.",
            "Раскрыты ключевые понятия темы.",
            "Показана связь с соседними темами дисциплины.",
            "Приведен корректный предметный пример.",
        ]
    if bucket == "coursework":
        return [
            "Тема курсовой работы соответствует дисциплине и заявленной проблематике.",
            "Сформулированы цель, задачи и ожидаемый результат работы.",
            f"Предусмотрен практический или проектный результат: {artifact}.",
            "Указаны критерии проверки результата и выводы.",
        ]
    return [
        f"Подготовлен требуемый результат: {artifact}.",
        f"Использованы предметные понятия: {terms or 'ключевые понятия темы'}.",
        "Решение проверяемо и связано с практической ситуацией.",
        "Сформулирован обоснованный вывод.",
    ]


def _cleanup(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip(" .;:-—\t\n\r")
    return value


def _norm(value: str) -> str:
    value = (value or "").lower().replace("ё", "е")
    value = re.sub(r"[^a-zа-я0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()
