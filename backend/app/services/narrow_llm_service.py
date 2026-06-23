import json
import os
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from app.ml.narrow_fos_model import NarrowFOSModel
from app.schemas import AssessmentItemRead, TrainingExampleRead
from app.services.example_based_generator import apply_example_based_generation

MODEL_VERSION = "narrow-fos-generator-v0.4"
DEFAULT_MODEL_PATH = Path(__file__).resolve().parents[1] / "storage" / "models" / "narrow_fos_model.json"
DEFAULT_OM_CORPUS_PATH = Path(__file__).resolve().parents[1] / "storage" / "om_corpus" / "om_examples.jsonl"
NARROW_MODEL_PATH = Path(os.getenv("NARROW_LLM_MODEL_PATH", str(DEFAULT_MODEL_PATH)))
OM_CORPUS_PATH = Path(os.getenv("OM_CORPUS_PATH", str(DEFAULT_OM_CORPUS_PATH)))
SOURCE_WEIGHTS = {
    "om_reference": 1.60,
    "om_direct": 1.45,
    "expert_feedback": 1.25,
    "om_similar": 0.95,
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
    model = _load_trained_model()
    expert_good = [x for x in training_examples if x.quality_label == "good"]
    om_examples = _load_om_reference_examples() if model is None else []
    good = expert_good + om_examples

    if model is None and not good:
        if not fallback_to_template:
            raise ValueError("No trained model, expert-approved examples or OM/FOS examples for narrow generator.")
        fallback = apply_example_based_generation(items=items, training_examples=training_examples, requested_mode="template", learned_max_items=0, fallback_to_template=True)
        return NarrowGenerationResult(fallback.items, requested_mode, "template", 0, 0, len(items), MODEL_VERSION, ["Нет обученной модели и OM/ФОС/экспертных примеров; использованы шаблоны."])

    limit = len(items) if requested_mode == "narrow_llm" else min(narrow_max_items, len(items))
    result = []
    trained_count = 0
    skipped_incompatible = 0
    for index, item in enumerate(items):
        if index >= limit:
            result.append(item)
            continue
        if model is not None:
            prediction = model.predict(
                discipline_name="",
                topic=item.topic,
                competency_code=item.competency_code,
                indicator=item.indicator,
                assessment_type=item.assessment_type,
                item_type=item.item_type,
                difficulty=item.difficulty,
            )
            if prediction is not None and _is_compatible_assessment_type(item.assessment_type, prediction.example.assessment_type):
                adapted = _adapt_from_prediction(item, prediction)
                if not _violates_target_type(adapted):
                    result.append(adapted)
                    trained_count += 1
                    continue
            elif prediction is not None:
                skipped_incompatible += 1
        compatible_good = [example for example in good if _is_compatible_assessment_type(item.assessment_type, example.assessment_type)]
        if not compatible_good:
            result.append(item)
            skipped_incompatible += 1
            continue
        example = max(compatible_good, key=lambda x: _score(item, x))
        adapted = _adapt(item, example)
        if _violates_target_type(adapted):
            result.append(item)
            skipped_incompatible += 1
            continue
        result.append(adapted)
        trained_count += 1

    warnings = []
    model_version = MODEL_VERSION
    if model is not None:
        model_version = model.metadata.get("model_version", MODEL_VERSION)
        warnings.append(f"Использована обученная локальная модель ФОС: {model_version}; примеров в модели: {model.metadata.get('examples_total', 0)}.")
    if om_examples:
        warnings.append(f"Подключен корпус готовых оценочных материалов ФОС: {len(om_examples)} OM/ФОС-примеров.")
    if expert_good:
        warnings.append(f"Подключены экспертные примеры преподавателя: {len(expert_good)} шт.")
    if skipped_incompatible:
        warnings.append(f"Узкая модель не применяла OM/ФОС-примеры с несовместимым типом раздела: {skipped_incompatible}.")
    return NarrowGenerationResult(result, requested_mode, "narrow_llm" if trained_count == len(items[:limit]) else "hybrid", 0, trained_count, len(items) - trained_count, model_version, warnings)


def _load_trained_model() -> NarrowFOSModel | None:
    if not NARROW_MODEL_PATH.exists():
        return None
    try:
        return NarrowFOSModel.load(NARROW_MODEL_PATH)
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return None


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


def _adapt_from_prediction(item: AssessmentItemRead, prediction) -> AssessmentItemRead:
    example = prediction.example
    return item.model_copy(update={
        "text": _repair_text_for_target_type(item, prediction.generated_text or item.text),
        "answer": prediction.generated_answer or item.answer,
        "criteria": (prediction.generated_criteria or item.criteria)[:6],
        "source_context": f"Trained narrow FOS model; compatible example {example.id}; type={example.assessment_type}; score={prediction.score:.3f}; source={example.source}.",
        "source_kind": "trained_narrow_llm",
    })


def _score(item, example):
    score = 0.0
    score += 0.26 * SOURCE_WEIGHTS.get(example.source, 0.75)
    score += 0.24 * (1.0 if item.assessment_type == example.assessment_type else 0.55)
    score += 0.22 * SequenceMatcher(None, (item.topic or "").lower(), (example.topic or "").lower()).ratio()
    score += 0.15 * (1.0 if item.competency_code and item.competency_code == example.competency_code else 0.0)
    score += 0.08 * (1.0 if item.item_type == example.item_type else 0.0)
    score += 0.05 * (1.0 if example.answer and example.criteria else 0.25)
    return score


def _adapt(item, example):
    topic = item.topic or "теме дисциплины"
    text = _repair_text_for_target_type(item, _adapt_text(example.text, example.topic, topic) or item.text)
    answer = _adapt_text(example.answer, example.topic, topic) or item.answer
    source_kind = "om_reference" if example.source.startswith("om") else "narrow_llm"
    source_label = "готовый OM/ФОС-корпус" if example.source.startswith("om") else "expert example"
    return item.model_copy(update={
        "text": text,
        "answer": answer,
        "criteria": (example.criteria or item.criteria)[:6],
        "source_context": f"Narrow FOS generator {MODEL_VERSION}; {source_label}: {example.id}; type={example.assessment_type}.",
        "source_kind": source_kind,
    })


def _adapt_text(text: str, source_topic: str, target_topic: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    if source_topic and source_topic.lower() in text.lower():
        return text.replace(source_topic, target_topic)
    return text


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
