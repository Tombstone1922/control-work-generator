from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.schemas import AssessmentItemRead, TrainingExampleRead

SUPPORTED_MODES = {"template", "learned", "hybrid"}
PLACEHOLDER_ANSWER_MARKERS = (
    "формируется и уточняется преподавателем",
    "необходимо уточнить преподавателю",
)
SOURCE_WEIGHTS = {
    "om_direct": 1.45,
    "expert_feedback": 1.20,
    "om_similar": 0.90,
    "generated": 0.10,
}
QUALITY_WEIGHTS = {
    "good": 1.0,
    "needs_revision": 0.35,
    "bad": -1.0,
}
ASSESSMENT_GROUPS = {
    "oral": {"oral", "exam_questions", "credit"},
    "practice": {"practice", "exam_practice", "laboratory", "control_work"},
    "coursework": {"coursework", "course_project"},
    "test": {"test_bank", "diagnostic"},
    "report": {"report_topics"},
}
PRACTICAL_ACTION_MARKERS = (
    "практическое задание",
    "лабораторное задание",
    "контрольное задание",
    "разработайте",
    "реализуйте",
    "спроектируйте",
    "выполните",
    "составьте",
    "подготовьте",
    "создайте",
)
COURSEWORK_MARKERS = (
    "тема курсовой",
    "курсовая работа",
    "курсовой проект",
)


@dataclass
class ExampleBasedGenerationResult:
    items: list[AssessmentItemRead]
    requested_mode: str
    used_mode: str
    learned_generated_items: int
    template_generated_items: int
    warnings: list[str]


def apply_example_based_generation(
    *,
    items: list[AssessmentItemRead],
    training_examples: list[TrainingExampleRead],
    requested_mode: str,
    learned_max_items: int,
    fallback_to_template: bool,
) -> ExampleBasedGenerationResult:
    mode = (requested_mode or "template").strip().lower()
    if mode not in SUPPORTED_MODES:
        raise ValueError("Недопустимый режим генерации. Используйте template, learned или hybrid.")

    good_examples = [example for example in training_examples if example.quality_label == "good"]
    bad_examples = [example for example in training_examples if example.quality_label == "bad"]
    revision_examples = [example for example in training_examples if example.quality_label == "needs_revision"]
    om_direct_count = sum(1 for example in good_examples if example.source == "om_direct")
    om_similar_count = sum(1 for example in good_examples if example.source == "om_similar")
    warnings: list[str] = []

    if mode == "template":
        return ExampleBasedGenerationResult(
            items=items,
            requested_mode=mode,
            used_mode="template",
            learned_generated_items=0,
            template_generated_items=len(items),
            warnings=[],
        )

    if not good_examples:
        message = "В обучающей выборке и локальной библиотеке OM/ФОС пока нет хороших примеров."
        if not fallback_to_template:
            raise ValueError(message)
        warnings.append(message + " Использован шаблонный генератор.")
        return ExampleBasedGenerationResult(
            items=items,
            requested_mode=mode,
            used_mode="template",
            learned_generated_items=0,
            template_generated_items=len(items),
            warnings=warnings,
        )

    result: list[AssessmentItemRead] = []
    learned_limit = len(items) if mode == "learned" else min(max(learned_max_items, 0), len(items))
    learned_count = 0
    skipped_incompatible = 0

    for index, item in enumerate(items):
        if index < learned_limit:
            example = _select_best_example(item, good_examples)
            if example is None:
                result.append(item)
                skipped_incompatible += 1
                continue
            learned_item = _build_item_from_example(item, example, bad_examples, revision_examples)
            if _violates_target_type(learned_item):
                result.append(item)
                skipped_incompatible += 1
                continue
            result.append(learned_item)
            learned_count += 1
        else:
            result.append(item)

    if om_direct_count:
        warnings.append(f"Использованы прямые OM/ФОС-примеры из локальной библиотеки: {om_direct_count} шт.")
    if om_similar_count:
        warnings.append(f"Использованы похожие OM/ФОС-примеры из локальной библиотеки: {om_similar_count} шт.")
    if skipped_incompatible:
        warnings.append(f"OM/ФОС-примеры с несовместимым типом раздела не применялись: {skipped_incompatible} шт.")
    if bad_examples:
        warnings.append(f"При генерации учитывались плохие примеры как анти-примеры: {len(bad_examples)} шт.")
    if revision_examples:
        warnings.append(f"В обучающей выборке есть примеры на доработку: {len(revision_examples)} шт.")
    if mode == "hybrid" and learned_count < len(items):
        warnings.append("Часть заданий сформирована по совместимым обучающим примерам/OM/ФОС, остальные оставлены шаблонными.")

    return ExampleBasedGenerationResult(
        items=result,
        requested_mode=mode,
        used_mode="learned" if learned_count == len(items) else "hybrid",
        learned_generated_items=learned_count,
        template_generated_items=len(items) - learned_count,
        warnings=warnings,
    )


def _select_best_example(item: AssessmentItemRead, examples: list[TrainingExampleRead]) -> TrainingExampleRead | None:
    compatible = [example for example in examples if _is_compatible_assessment_type(item.assessment_type, example.assessment_type)]
    if not compatible:
        return None
    scored = sorted(
        compatible,
        key=lambda example: _score_example(item, example),
        reverse=True,
    )
    return scored[0]


def _score_example(item: AssessmentItemRead, example: TrainingExampleRead) -> float:
    # OM/ФОС — это структурированные оценочные материалы, поэтому тип раздела является жестким фильтром,
    # а не просто мягким бонусом. До scoring доходят только совместимые примеры.
    source_weight = SOURCE_WEIGHTS.get(example.source, 0.75)
    quality_weight = QUALITY_WEIGHTS.get(example.quality_label, 0.5)
    answer_quality = 1.0 if example.answer and not any(marker in example.answer.lower() for marker in PLACEHOLDER_ANSWER_MARKERS) else 0.25
    criteria_quality = 1.0 if example.criteria else 0.25

    score = 0.0
    score += 0.26 * source_weight
    score += 0.24 * (1.0 if item.assessment_type == example.assessment_type else 0.55)
    score += 0.22 * _text_similarity(item.topic, example.topic)
    score += 0.15 * (1.0 if item.competency_code and item.competency_code == example.competency_code else _text_similarity(item.indicator, example.indicator))
    score += 0.07 * ((1.0 if item.item_type == example.item_type else 0.0) + (1.0 if item.difficulty == example.difficulty else 0.0)) / 2
    score += 0.04 * ((answer_quality + criteria_quality) / 2)
    score += 0.02 * quality_weight
    return score


def _build_item_from_example(
    item: AssessmentItemRead,
    example: TrainingExampleRead,
    bad_examples: list[TrainingExampleRead],
    revision_examples: list[TrainingExampleRead],
) -> AssessmentItemRead:
    text = _adapt_text_to_target(item, example)
    if _is_too_similar_to_negative(text, bad_examples):
        text = _make_more_specific(text, item)
    if _is_too_similar_to_negative(text, revision_examples):
        text = _make_more_controlled(text, item)

    criteria = example.criteria or item.criteria
    answer = _adapt_answer_to_target(item, example)
    source_kind = "om_reference" if example.source.startswith("om_") else "learned_example"
    source_label = "готового OM/ФОС" if example.source.startswith("om_") else "обучающего примера"

    return item.model_copy(
        update={
            "text": text,
            "answer": answer,
            "criteria": criteria,
            "source_context": f"Сформировано по аналогии с {source_label} {example.id}. Тип примера: {example.assessment_type}. Тема примера: «{example.topic}».",
            "source_kind": source_kind,
            "status": "draft",
        }
    )


def _adapt_text_to_target(item: AssessmentItemRead, example: TrainingExampleRead) -> str:
    source = example.text.strip()
    target_topic = item.topic.strip() or "изучаемой теме"
    source_topic = example.topic.strip()

    if source_topic and source_topic.lower() in source.lower():
        adapted = _replace_case_insensitive(source, source_topic, target_topic)
        return _repair_text_for_target_type(item, adapted)

    quoted = re.findall(r"[«\"]([^»\"]{3,120})[»\"]", source)
    if quoted:
        adapted = source
        for value in quoted[:2]:
            adapted = adapted.replace(value, target_topic)
        return _repair_text_for_target_type(item, adapted)

    action = _detect_action(source)
    details = _tail_for_assessment(item.assessment_type)
    return _repair_text_for_target_type(item, f"{action} по теме «{target_topic}». {details}")


def _adapt_answer_to_target(item: AssessmentItemRead, example: TrainingExampleRead) -> str:
    target_topic = item.topic.strip() or "изучаемой теме"
    source_topic = example.topic.strip()
    answer = example.answer.strip()

    if not answer or any(marker in answer.lower() for marker in PLACEHOLDER_ANSWER_MARKERS):
        return (
            f"Эталонный ответ должен раскрывать тему «{target_topic}», содержать основные понятия, "
            "обоснование выбранного решения и итоговый вывод. Структура ответа основана на OM/ФОС-примере."
        )
    if source_topic and source_topic.lower() in answer.lower():
        return _replace_case_insensitive(answer, source_topic, target_topic)
    return (
        f"Эталонный ответ формируется по структуре OM/ФОС-примера. Для темы «{target_topic}» необходимо раскрыть: "
        f"{_shorten(answer, 500)}"
    )


def _detect_action(text: str) -> str:
    lowered = text.lower()
    actions = [
        ("разработ", "Разработайте задание"),
        ("проанализ", "Проанализируйте учебную ситуацию"),
        ("сравн", "Сравните основные подходы"),
        ("объяс", "Объясните ключевые положения"),
        ("раскро", "Раскройте содержание вопроса"),
        ("реш", "Решите практическую задачу"),
        ("выберите", "Выберите и обоснуйте корректный вариант ответа"),
    ]
    for marker, action in actions:
        if marker in lowered:
            return action
    return "Сформулируйте развернутый ответ"


def _tail_for_assessment(assessment_type: str) -> str:
    return {
        "practice": "Представьте ход решения, обоснуйте выбранный способ и сформулируйте вывод.",
        "exam_practice": "Покажите ход решения, укажите ключевые этапы и критерии проверки результата.",
        "exam_questions": "Ответ должен включать определение, классификацию, пример и вывод.",
        "oral": "Ответ должен быть логически структурирован и сопровождаться примером.",
        "diagnostic": "Укажите правильный ответ и кратко обоснуйте выбор.",
        "control_work": "Решение должно содержать исходные данные, ход выполнения и итоговый результат.",
        "coursework": "Опишите цель, задачи, ожидаемый результат и критерии оценки курсовой работы.",
        "course_project": "Опишите проектное решение, архитектуру и ожидаемые результаты реализации.",
        "laboratory": "Зафиксируйте исходные данные, порядок выполнения и выводы по работе.",
        "test_bank": "Сформулируйте варианты ответа и отметьте корректный вариант.",
        "report_topics": "Раскройте актуальность, основные положения и практическое значение темы.",
    }.get(assessment_type, "Ответ должен быть связан с темой, компетенцией и ожидаемым результатом обучения.")


def _is_compatible_assessment_type(target_type: str, example_type: str) -> bool:
    if target_type == example_type:
        return True
    target_group = _assessment_group(target_type)
    example_group = _assessment_group(example_type)
    return bool(target_group and target_group == example_group)


def _assessment_group(value: str) -> str:
    for group, values in ASSESSMENT_GROUPS.items():
        if value in values:
            return group
    return value or ""


def _repair_text_for_target_type(item: AssessmentItemRead, text: str) -> str:
    text = (text or "").strip()
    target_topic = item.topic.strip() or "изучаемой теме"
    if item.assessment_type in {"oral", "exam_questions", "credit"} and _looks_practical(text):
        return f"Вопрос: раскройте основные понятия темы «{target_topic}» и приведите пример их применения."
    if item.assessment_type in {"coursework", "course_project"} and not text.lower().startswith("тема курсов"):
        label = "Тема курсового проекта" if item.assessment_type == "course_project" else "Тема курсовой работы"
        return f"{label}: «Разработка и обоснование решения по теме “{target_topic}”»."
    if item.assessment_type in {"practice", "exam_practice", "laboratory", "control_work"} and not _looks_practical(text):
        return f"Практическое задание: выполните прикладное задание по теме «{target_topic}» и представьте проверяемый результат."
    return text


def _violates_target_type(item: AssessmentItemRead) -> bool:
    text = (item.text or "").lower()
    if item.assessment_type in {"oral", "exam_questions", "credit"}:
        return _looks_practical(text) or any(marker in text for marker in COURSEWORK_MARKERS)
    if item.assessment_type in {"coursework", "course_project"}:
        return not text.startswith("тема курсов")
    return False


def _looks_practical(text: str) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered[:260] for marker in PRACTICAL_ACTION_MARKERS)


def _is_too_similar_to_negative(text: str, negative_examples: list[TrainingExampleRead]) -> bool:
    normalized = _normalize(text)
    for example in negative_examples:
        if SequenceMatcher(None, normalized, _normalize(example.text)).ratio() >= 0.86:
            return True
    return False


def _make_more_specific(text: str, item: AssessmentItemRead) -> str:
    return (
        f"{text} Дополнительно укажите, какие понятия темы «{item.topic}» проверяются данным заданием "
        "и какие признаки будут считаться корректным результатом."
    )


def _make_more_controlled(text: str, item: AssessmentItemRead) -> str:
    return (
        f"{text} Ответ должен содержать не менее трех структурных элементов: теоретическое положение, "
        "пример применения и краткий вывод."
    )


def _replace_case_insensitive(text: str, old: str, new: str) -> str:
    return re.sub(re.escape(old), new, text, flags=re.IGNORECASE)


def _text_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, _normalize(left), _normalize(right)).ratio()


def _normalize(value: str) -> str:
    value = (value or "").lower().replace("ё", "е")
    value = re.sub(r"[^a-zа-я0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _shorten(value: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", value.strip())
    return value if len(value) <= limit else f"{value[:limit].rstrip()}…"
