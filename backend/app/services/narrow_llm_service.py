from dataclasses import dataclass
from difflib import SequenceMatcher

from app.schemas import AssessmentItemRead, TrainingExampleRead
from app.services.example_based_generator import apply_example_based_generation

MODEL_VERSION = "narrow-fos-generator-v0.1"


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


def apply_narrow_llm_generation(*, items, training_examples, requested_mode, narrow_max_items, fallback_to_template):
    good = [x for x in training_examples if x.quality_label == "good"]
    if not good:
        if not fallback_to_template:
            raise ValueError("No expert-approved examples for narrow generator.")
        fallback = apply_example_based_generation(items=items, training_examples=training_examples, requested_mode="template", learned_max_items=0, fallback_to_template=True)
        return NarrowGenerationResult(fallback.items, requested_mode, "template", 0, 0, len(items), MODEL_VERSION, ["No expert examples; template fallback was used."])

    limit = len(items) if requested_mode == "narrow_llm" else min(narrow_max_items, len(items))
    result = []
    for index, item in enumerate(items):
        if index >= limit:
            result.append(item)
            continue
        example = max(good, key=lambda x: _score(item, x))
        result.append(_adapt(item, example))
    return NarrowGenerationResult(result, requested_mode, "narrow_llm" if limit == len(items) else "hybrid", 0, limit, len(items) - limit, MODEL_VERSION, [])


def _score(item, example):
    score = 0.0
    if item.assessment_type == example.assessment_type:
        score += 5
    if item.item_type == example.item_type:
        score += 2
    score += SequenceMatcher(None, item.topic.lower(), example.topic.lower()).ratio()
    return score


def _adapt(item, example):
    topic = item.topic or "topic"
    text = example.text.replace(example.topic, topic) if example.topic else example.text
    answer = example.answer.replace(example.topic, topic) if example.topic else example.answer
    return item.model_copy(update={"text": text or item.text, "answer": answer or item.answer, "criteria": (example.criteria or item.criteria)[:6], "source_context": f"Narrow FOS generator {MODEL_VERSION}; example {example.id}.", "source_kind": "narrow_llm"})
