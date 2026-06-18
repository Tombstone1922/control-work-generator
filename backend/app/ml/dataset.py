import json
from pathlib import Path


def load_jsonl_dataset(path: str | Path) -> list[dict]:
    records: list[dict] = []
    with Path(path).open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def good_examples(records: list[dict]) -> list[dict]:
    return [record for record in records if record.get("quality_label") == "good"]


def to_model_examples(records: list[dict]) -> list[dict]:
    examples: list[dict] = []
    for index, record in enumerate(good_examples(records)):
        source_input = record.get("input", {}) or {}
        output = record.get("output", {}) or {}
        examples.append({
            "id": f"jsonl-{index}",
            "topic": source_input.get("topic", ""),
            "competency_code": source_input.get("competency_code", ""),
            "indicator": source_input.get("indicator", ""),
            "assessment_type": source_input.get("assessment_type", ""),
            "item_type": source_input.get("item_type", ""),
            "difficulty": source_input.get("difficulty", "medium"),
            "text": output.get("text", ""),
            "answer": output.get("answer", ""),
            "criteria": output.get("criteria", []),
        })
    return examples
