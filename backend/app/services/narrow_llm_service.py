from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from app.schemas import AssessmentItemRead, TrainingExampleRead
from app.services.example_based_generator import apply_example_based_generation

MODEL_VERSION = "narrow-fos-generator-v0.1"
SUPPORTED_MODES = {"narrow_llm", "hybrid"}


@dataclass
class NarrowGenerationResult:
    items: list[AssessmentItemRead]
    requested_mode: str
    used_mode: str
    learned_generated_items: int
    narrow_llm_generated_items: int
    template_generated_items: int
    model_version: str
    warnings: list[str]


def apply_narrow_llm_generation(
    *,
    items: list[AssessmentItemRead],
    training_examples: list[TrainingExampleRead],
    requested_mode: str,
    narrow_max_items: int,
    fallback_to_template: bool,
) -> NarrowGenerationResult:
    mode = (requested_mode or "narrow_llm").strip().lower()
    if mode not in SUPPORTED_MODES:
        raise ValueError("Недопустимый режим генерации. Используйте narrow_llm или hybrid.")

    good_examples = [example for example in training_examples if example.quality_label == "good"]
    if not good_examples:
        message = "Для узкой модели ФОС пока нет экспертно подтвержденных примеров."
        if not fallback_to_template:
            raise ValueError(message)
        fallback = apply_example_based_generation(
            items=items,
            training_examples=training_examples,
            requested_mode="template",
            learned_max_items=0,
            fallback_to_template=True,
        )
        return NarrowGenerationResult(
            items=fallback.items,
            requested_mode=mode,
            used_mode="template",
            learned_generated_items=0,
            narrow_llm_generated_items=0,
            template_generated_items=len(items),
            model_version=MODEL_VERSION,
            warnings=[message + " Использован шаблонный генератор."],
        )

    target_count = len(items) if mode == "narrow_llm" else min(max(narrow_max_items, 0), len(items))
    result: list[AssessmentItemRead] = []
    generated_count = 0
    template_count = 0

    for index, item in enumerate(items):
        if index >= target_count:
            result.append(item)
            template_count += 1
            continue
        example = max(good_examples, key=lambda candidate: _score_example(item, candidate))
        result.append(_build_from_example(item, example))
        generated_count += 1

    warnings: list[str] = []
    if mode == "hybrid" and template_count:
        warnings.append("Часть заданий сформирована узкой моделью, остальные оставлены шаблонными.")

    return NarrowGenerationResult(
        items=result,
        requested_mode=mode,
        used_mode="narrow_llm" if generated_count == len(items) else "hybrid",
        learned_generated_items=0,
        narrow_llm_generated_items=generated_count,
        template_generated_items=template_count,
        model_version=MODEL_VERSION,
        warnings=warnings,
    )


def _score_example(item: AssessmentItemRead, example: TrainingExampleRead) -> float:
    score = 0.0
    if item.assessment_type == example.assessment_type:
        score += 5.0
    if item.item_type == example.item_type:
        score += 2.0
    if item.difficulty == example.difficulty:
        score += 1.0
    if item.competency_code and item.competency_code == example.competency_code:
        score += 2.0
    score += 3.0 * SequenceMatcher(None, _normalize(item.topic), _normalize(example.topic)).ratio()
    score += SequenceMatcher(None, _normalize(item.indicator), _normalize(example.indicator)).ratio()
    return score


def _build_from_example(item: AssessmentItemRead, example: TrainingExampleRead) -> AssessmentItemRead:
    topic = item.topic.strip() or "изучаемой теме"
    text = _replace_topic(example.text, example.topic, topic) or f"Сформулируйте развернутый ответ по теме «{topic}»."
    answer = _replace_topic(example.answer, example.topic, topic) or (
        f"Эталонный ответ должен раскрывать тему «{topic}", содержать основные понятия, обоснование и итоговый вывод."
    )
    criteria = example.criteria or item.criteria or [
        "Раскрыты ключевые понятия темы.",
        "Ответ связан с компетенцией и индикатором.",
        "Приведено обоснование и сформулирован вывод.",
    ]
    return item.model_copy(
        update={
            "text": text,
            "answer": answer,
            "criteria": criteria[:6],
            "source_context": f"Узкоспециализированная модель ФОС {MODEL_VERSION}; экспертный пример {example.id}.",
            "source_kind": "narrow_llm",
            "status": "draft",
        }
    )


def _replace_topic(text: str, source_topic: str, target_topic: str) -> str:
    if not text.strip():
        return ""
    if source_topic.strip() and source_topic.lower() in text.lower():
        return text.replace(source_topic, target_topic)
    return text


def _normalize(value: str) -> str:
    return " ".join((value or "").lower().split())
