from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

MODEL_VERSION = "narrow-fos-local-model-v0.2"
BAD_MODEL_PHRASES = (
    "перечень компетенций",
    "уровни их сформированности",
    "в процессе освоения образовательной программы",
    "критерии определения сформированности",
    "индекс компетенции",
    "содержание компетенции",
    "код и наименование индикатора",
    "виды занятий для формирования",
    "оценочные средства для оценки",
    "методические, оценочные материалы",
    "процедуры оценивания сформированности",
    "#default#",
)


@dataclass
class ModelExample:
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
    source: str
    tokens: list[str]


@dataclass
class Prediction:
    example: ModelExample
    score: float
    generated_text: str
    generated_answer: str
    generated_criteria: list[str]


class NarrowFOSModel:
    def __init__(self, examples: list[ModelExample], idf: dict[str, float], phrase_bank: dict[str, list[str]], metadata: dict):
        self.examples = examples
        self.idf = idf
        self.phrase_bank = phrase_bank
        self.metadata = metadata

    @classmethod
    def train_from_records(cls, records: list[dict]) -> "NarrowFOSModel":
        examples: list[ModelExample] = []
        document_frequency: Counter[str] = Counter()
        phrase_bank: dict[str, list[str]] = defaultdict(list)
        seen_texts: set[str] = set()
        skipped_noisy = 0
        skipped_duplicates = 0

        for index, record in enumerate(records):
            if record.get("quality_label") not in {None, "good"}:
                continue
            input_data = record.get("input", {}) or {}
            output_data = record.get("output", {}) or {}
            text = _clean_text(str(output_data.get("text") or ""))
            if len(text) < 8 or _is_bad_model_text(text):
                skipped_noisy += 1
                continue
            key = _normalize_key(text)
            if key in seen_texts:
                skipped_duplicates += 1
                continue
            seen_texts.add(key)
            example = ModelExample(
                id=str(record.get("id") or f"model-example-{index}"),
                discipline_name=str(input_data.get("discipline_name") or ""),
                topic=_clean_text(str(input_data.get("topic") or "")),
                competency_code=str(input_data.get("competency_code") or ""),
                indicator=str(input_data.get("indicator") or ""),
                assessment_type=str(input_data.get("assessment_type") or "oral"),
                item_type=str(input_data.get("item_type") or "theoretical_open"),
                difficulty=str(input_data.get("difficulty") or "medium"),
                text=text,
                answer=_clean_text(str(output_data.get("answer") or "")),
                criteria=[_clean_text(str(item)) for item in output_data.get("criteria", []) if _clean_text(str(item))],
                source=str(record.get("source") or "training_dataset"),
                tokens=_tokenize(" ".join([
                    str(input_data.get("discipline_name") or ""),
                    str(input_data.get("topic") or ""),
                    str(input_data.get("competency_code") or ""),
                    str(input_data.get("assessment_type") or ""),
                    text,
                ])),
            )
            examples.append(example)
            document_frequency.update(set(example.tokens))
            phrase_bank[example.assessment_type].append(text)

        total = max(len(examples), 1)
        idf = {token: math.log((1 + total) / (1 + count)) + 1 for token, count in document_frequency.items()}
        metadata = {
            "model_version": MODEL_VERSION,
            "created_at": datetime.utcnow().isoformat(),
            "examples_total": len(examples),
            "skipped_noisy": skipped_noisy,
            "skipped_duplicates": skipped_duplicates,
            "assessment_types": sorted({example.assessment_type for example in examples}),
            "sources": dict(Counter(example.source for example in examples)),
        }
        return cls(examples=examples, idf=idf, phrase_bank=dict(phrase_bank), metadata=metadata)

    @classmethod
    def load(cls, path: str | Path) -> "NarrowFOSModel":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        examples = [
            ModelExample(
                id=item["id"],
                discipline_name=item.get("discipline_name", ""),
                topic=item.get("topic", ""),
                competency_code=item.get("competency_code", ""),
                indicator=item.get("indicator", ""),
                assessment_type=item.get("assessment_type", "oral"),
                item_type=item.get("item_type", "theoretical_open"),
                difficulty=item.get("difficulty", "medium"),
                text=item.get("text", ""),
                answer=item.get("answer", ""),
                criteria=item.get("criteria", []),
                source=item.get("source", "model_artifact"),
                tokens=item.get("tokens", []),
            )
            for item in data.get("examples", [])
            if not _is_bad_model_text(item.get("text", ""))
        ]
        return cls(examples=examples, idf=data.get("idf", {}), phrase_bank=data.get("phrase_bank", {}), metadata=data.get("metadata", {}))

    def save(self, path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "metadata": self.metadata,
            "idf": self.idf,
            "phrase_bank": self.phrase_bank,
            "examples": [example.__dict__ for example in self.examples],
        }
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return output

    def predict(self, *, discipline_name: str, topic: str, competency_code: str, indicator: str, assessment_type: str, item_type: str, difficulty: str) -> Prediction | None:
        if not self.examples:
            return None
        query = _tokenize(" ".join([discipline_name, topic, competency_code, indicator, assessment_type, item_type, difficulty]))
        candidates = [example for example in self.examples if example.assessment_type == assessment_type] or self.examples
        best = max(candidates, key=lambda example: self._score(query, topic, competency_code, assessment_type, item_type, difficulty, example))
        score = self._score(query, topic, competency_code, assessment_type, item_type, difficulty, best)
        return Prediction(
            example=best,
            score=score,
            generated_text=_adapt_text(best.text, best.topic, topic),
            generated_answer=_adapt_text(best.answer, best.topic, topic),
            generated_criteria=(best.criteria or _default_criteria(item_type))[:6],
        )

    def _score(self, query_tokens: list[str], topic: str, competency_code: str, assessment_type: str, item_type: str, difficulty: str, example: ModelExample) -> float:
        query_vector = _tfidf(query_tokens, self.idf)
        example_vector = _tfidf(example.tokens, self.idf)
        lexical = _cosine(query_vector, example_vector)
        score = lexical
        score += 0.25 if assessment_type == example.assessment_type else 0.0
        score += 0.10 if item_type == example.item_type else 0.0
        score += 0.08 if difficulty == example.difficulty else 0.0
        score += 0.12 if competency_code and competency_code == example.competency_code else 0.0
        score += 0.20 * _simple_similarity(topic, example.topic)
        score += 0.12 if example.source.startswith("om") else 0.0
        return score


def load_jsonl_records(paths: list[str | Path]) -> list[dict]:
    records: list[dict] = []
    for path in paths:
        source = Path(path)
        if not source.exists():
            continue
        with source.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                records.append(json.loads(line))
    return records


def _tokenize(value: str) -> list[str]:
    value = value.lower().replace("ё", "е")
    return re.findall(r"[a-zа-я0-9]{3,}", value)


def _tfidf(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    counts = Counter(tokens)
    total = max(sum(counts.values()), 1)
    return {token: (count / total) * idf.get(token, 1.0) for token, count in counts.items()}


def _cosine(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    shared = set(left) & set(right)
    numerator = sum(left[token] * right[token] for token in shared)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def _simple_similarity(left: str, right: str) -> float:
    left_tokens = set(_tokenize(left))
    right_tokens = set(_tokenize(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _adapt_text(text: str, source_topic: str, target_topic: str) -> str:
    text = _clean_text(text)
    if not text:
        return ""
    if source_topic and target_topic and source_topic.lower() in text.lower():
        return re.sub(re.escape(source_topic), target_topic, text, flags=re.IGNORECASE)
    return text


def _default_criteria(item_type: str) -> list[str]:
    if item_type in {"practice", "control_work", "laboratory"}:
        return ["Практическое задание выполнено полностью.", "Ход решения обоснован.", "Сформулирован корректный вывод."]
    return ["Раскрыты ключевые понятия темы.", "Ответ логично структурирован.", "Приведен пример или обоснование."]


def _clean_text(value: str) -> str:
    value = (value or "").replace("\ufffe", "-").replace("\u00ad", "")
    value = value.replace("#default#", "")
    value = re.sub(r"\s+", " ", value).strip(" .;:-—\t\n\r")
    return value


def _is_bad_model_text(value: str) -> bool:
    lower = _clean_text(value).lower()
    return any(phrase in lower for phrase in BAD_MODEL_PHRASES)


def _normalize_key(value: str) -> str:
    value = value.lower().replace("ё", "е")
    value = re.sub(r"[^a-zа-я0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()
