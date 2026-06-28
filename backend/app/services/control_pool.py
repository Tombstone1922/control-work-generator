import json
import re
from pathlib import Path
from uuid import uuid4

from app import models
from app.schemas import ControlWorkVariant, GenerationRequest, Question

BANK_DIR = Path(__file__).resolve().parents[2] / "storage" / "prepared_banks"


def make_variants(program: models.Program, payload: GenerationRequest) -> list[ControlWorkVariant]:
    pool = read_questions(program.filename, payload.question_types or ["open", "practice"], payload.difficulty)
    total = payload.variants_count * payload.questions_per_variant
    if len(pool) < total:
        return []
    result: list[ControlWorkVariant] = []
    cursor = 0
    for variant_number in range(1, payload.variants_count + 1):
        questions: list[Question] = []
        for _ in range(payload.questions_per_variant):
            questions.append(pool[cursor % len(pool)].model_copy(update={"id": str(uuid4())}))
            cursor += 1
        result.append(ControlWorkVariant(variant_number=variant_number, questions=questions))
    return result


def make_replacement(program: models.Program, question_type: str, difficulty: str, used_texts: list[str], seed: int) -> Question | None:
    pool = read_questions(program.filename, [question_type], difficulty)
    if not pool:
        return None
    used = {sig(text) for text in used_texts}
    start = seed % len(pool)
    ordered = pool[start:] + pool[:start]
    for item in ordered:
        if sig(item.text) not in used:
            return item.model_copy(update={"id": str(uuid4())})
    return ordered[0].model_copy(update={"id": str(uuid4())})


def read_questions(filename: str, wanted: list[str], difficulty: str) -> list[Question]:
    data = read_bank(filename)
    raw_items = data.get("items") if data else []
    if not isinstance(raw_items, list):
        return []
    wanted_set = {item.strip().lower() for item in wanted if item.strip()}
    result: list[Question] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        q_type = map_type(str(raw.get("assessment_type") or ""), str(raw.get("item_type") or ""))
        if wanted_set and q_type not in wanted_set:
            continue
        text = str(raw.get("text") or "").strip()
        if not text:
            continue
        criteria = raw.get("criteria") if isinstance(raw.get("criteria"), list) else []
        result.append(Question(
            id=str(uuid4()),
            topic=str(raw.get("topic") or "Тема РПД"),
            text=text,
            type=q_type,
            difficulty=str(raw.get("difficulty") or difficulty or "medium"),
            answer=str(raw.get("answer") or ""),
            criteria=[str(item) for item in criteria if str(item).strip()],
        ))
    result.sort(key=lambda item: (sig(item.topic), sig(item.text)))
    return result


def read_bank(filename: str) -> dict | None:
    BANK_DIR.mkdir(parents=True, exist_ok=True)
    key = name_key(filename)
    direct = BANK_DIR / f"{key}.json"
    if direct.exists():
        data = read_json(direct)
        if data:
            return data
    for path in sorted(BANK_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        data = read_json(path)
        if not data:
            continue
        bank_key = name_key(data.get("source_filename") or data.get("bank_key") or path.stem)
        if key and (bank_key == key or key in bank_key or bank_key in key):
            return data
    return None


def read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def map_type(assessment_type: str, item_type: str) -> str:
    assessment_type = assessment_type.lower()
    item_type = item_type.lower()
    if assessment_type in {"diagnostic", "test_bank"} or item_type == "single_choice":
        return "test"
    if assessment_type in {"practice", "credit_practice", "exam_practice", "control_work", "laboratory"} or "practice" in item_type:
        return "practice"
    return "open"


def name_key(value: str) -> str:
    value = (value or "").lower().replace("ё", "е")
    value = re.sub(r"\.(docx|pdf|txt)$", "", value)
    value = re.sub(r"[^a-zа-я0-9]+", "", value)
    return value


def sig(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").lower().replace("ё", "е")).strip()
