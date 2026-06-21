import json
import os
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from app.schemas import AssessmentItemRead, TrainingExampleRead
from app.services.example_based_generator import apply_example_based_generation

MODEL_VERSION = "narrow-fos-generator-v0.3"
DEFAULT_OM_CORPUS_PATH = Path(__file__).resolve().parents[1] / "storage" / "om_corpus" / "om_examples.jsonl"
OM_CORPUS_PATH = Path(os.getenv("OM_CORPUS_PATH", str(DEFAULT_OM_CORPUS_PATH)))
SOURCE_WEIGHTS = {
    "om_reference": 1.60,
    "om_direct": 1.45,
    "expert_feedback": 1.25,
    "om_similar": 0.95,
}


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


@dataclass
class OMReferenceExample:
    id: str
    discipline_name: str
    topic: str
    competency_code: str
    indicator: str
    assessment_type: str
    item_type: str
    difficulty: str
    text: str
    answer: str
    criteria: list[str]
    quality_label: str = "good"
    teacher_comment: str = ""
    source: str = "om_reference"
    created_at: str = ""


def apply_narrow_llm_generation(*, items, training_examples, requested_mode, narrow_max_items, fallback_to_template):
    expert_good = [x for x in training_examples if x.quality_label == "good"]
    om_examples = _load_om_reference_examples()
    good = expert_good + om_examples
    if not good:
        if not fallback_to_template:
            raise ValueError("No expert-approved or OM examples for narrow generator.")
        fallback = apply_example_based_generation(items=items, training_examples=training_examples, requested_mode="template", learned_max_items=0, fallback_to_template=True)
        return NarrowGenerationResult(fallback.items, requested_mode, "template", 0, 0, len(items), MODEL_VERSION, ["Нет OM/экспертных примеров; использованы шаблоны."])

    limit = len(items) if requested_mode == "narrow_llm" else min(narrow_max_items, len(items))
    result = []
    for index, item in enumerate(items):
        if index >= limit:
            result.append(item)
            continue
        example = max(good, key=lambda x: _score(item, x))
        result.append(_adapt(item, example))

    warnings = []
    if om_examples:
        warnings.append(f"Подключен корпус готовых оценочных материалов: {len(om_examples)} OM-примеров.")
    if expert_good:
        warnings.append(f"Подключены экспертные примеры преподавателя: {len(expert_good)} шт.")
    return NarrowGenerationResult(result, requested_mode, "narrow_llm" if limit == len(items) else "hybrid", 0, limit, len(items) - limit, MODEL_VERSION, warnings)


def _load_om_reference_examples() -> list[OMReferenceExample]:
    if not OM_CORPUS_PATH.exists():
        return []
    examples: list[OMReferenceExample] = []
    try:
        with OM_CORPUS_PATH.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                input_data = record.get("input", {}) or {}
                output_data = record.get("output", {}) or {}
                text = str(output_data.get("text") or "").strip()
                if not text:
                    continue
                examples.append(
                    OMReferenceExample(
                        id=str(record.get("id") or f"om-{len(examples) + 1}"),
                        discipline_name=str(input_data.get("discipline_name") or ""),
                        topic=str(input_data.get("topic") or ""),
                        competency_code=str(input_data.get("competency_code") or ""),
                        indicator=str(input_data.get("indicator") or ""),
                        assessment_type=str(input_data.get("assessment_type") or "oral"),
                        item_type=str(input_data.get("item_type") or "theoretical_open"),
                        difficulty=str(input_data.get("difficulty") or "medium"),
                        text=text,
                        answer=str(output_data.get("answer") or ""),
                        criteria=[str(item).strip() for item in output_data.get("criteria", []) if str(item).strip()],
                        source=str(record.get("source") or "om_reference"),
                    )
                )
    except (OSError, json.JSONDecodeError):
        return []
    return examples[:5000]


def _score(item, example):
    score = 0.0
    score += 0.30 * SOURCE_WEIGHTS.get(example.source, 0.75)
    score += 0.20 * (1.0 if item.assessment_type == example.assessment_type else 0.0)
    score += 0.20 * SequenceMatcher(None, (item.topic or "").lower(), (example.topic or "").lower()).ratio()
    score += 0.15 * (1.0 if item.competency_code and item.competency_code == example.competency_code else 0.0)
    score += 0.07 * (1.0 if item.item_type == example.item_type else 0.0)
    score += 0.05 * (1.0 if example.answer and example.criteria else 0.25)
    score += 0.03
    return score


def _adapt(item, example):
    topic = item.topic or "теме дисциплины"
    text = _adapt_text(example.text, example.topic, topic) or item.text
    answer = _adapt_text(example.answer, example.topic, topic) or item.answer
    source_kind = "om_reference" if example.source.startswith("om") else "narrow_llm"
    source_label = "готовый OM-корпус" if example.source.startswith("om") else "expert example"
    return item.model_copy(update={
        "text": text,
        "answer": answer,
        "criteria": (example.criteria or item.criteria)[:6],
        "source_context": f"Narrow FOS generator {MODEL_VERSION}; {source_label}: {example.id}.",
        "source_kind": source_kind,
    })


def _adapt_text(text: str, source_topic: str, target_topic: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    if source_topic and source_topic.lower() in text.lower():
        return text.replace(source_topic, target_topic)
    return text
