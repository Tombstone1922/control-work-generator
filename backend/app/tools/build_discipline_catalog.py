import argparse
import json
import re
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.document_parser import extract_text
from app.services.rpd_analyzer import analyze_rpd_text

SUPPORTED_EXTENSIONS = {".docx", ".pdf", ".txt"}
STOP_WORDS = {
    "дисциплина", "дисциплины", "рабочая", "программа", "программы", "образования", "подготовки",
    "направления", "направлению", "профиль", "обучения", "студент", "должен", "знать", "уметь",
    "владеть", "тема", "раздел", "основные", "основы", "общие", "материалы", "оценочные",
}


def build_catalog(input_path: Path, output_path: Path) -> dict:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if input_path.is_file() and input_path.suffix.lower() == ".zip":
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            with zipfile.ZipFile(input_path) as archive:
                archive.extractall(temp_path)
            catalog = _build_from_folder(temp_path)
    else:
        catalog = _build_from_folder(input_path)
    output_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    return catalog


def _build_from_folder(root: Path) -> dict:
    grouped: dict[str, list[dict]] = defaultdict(list)
    files = [path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS]
    errors: list[str] = []

    for path in files:
        try:
            text = extract_text(path)
            analysis = analyze_rpd_text(text)
            discipline = _extract_discipline_name(text, path.stem)
            grouped[_key(discipline)].append({
                "discipline_name": discipline,
                "source_file": path.name,
                "topics": analysis.topics,
                "learning_outcomes": analysis.learning_outcomes,
                "competencies": analysis.competencies,
                "text_head": text[:4000],
            })
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")

    profiles = [_profile_from_group(items) for items in grouped.values()]
    profiles = [profile for profile in profiles if profile["topics"] or profile["learning_outcomes"]]
    profiles.sort(key=lambda item: item["discipline_name"].lower())
    return {
        "created_at": datetime.utcnow().isoformat(),
        "files_total": len(files),
        "profiles_total": len(profiles),
        "profiles": profiles,
        "errors": errors[:200],
    }


def _profile_from_group(items: list[dict]) -> dict:
    discipline_name = max((item["discipline_name"] for item in items), key=len)
    topics = _top_unique([topic for item in items for topic in item["topics"]], limit=24)
    outcomes = _top_unique([outcome for item in items for outcome in item["learning_outcomes"]], limit=12)
    competencies = _top_unique([competency for item in items for competency in item["competencies"]], limit=20)
    token_text = " ".join(
        [discipline_name, " ".join(topics), " ".join(outcomes), " ".join(item["text_head"] for item in items)]
    )
    return {
        "discipline_name": discipline_name,
        "topics": topics,
        "learning_outcomes": outcomes,
        "competencies": competencies,
        "tokens": _tokens(token_text)[:1200],
        "source_files": sorted({item["source_file"] for item in items})[:20],
    }


def _extract_discipline_name(text: str, fallback: str) -> str:
    patterns = [
        r"по дисциплине\s+(.+?)\s+(?:направления|направлению|профиль|формы обучения|форма обучения)",
        r"дисциплина\s+«([^»]+)»",
        r"дисциплины\s+«([^»]+)»",
        r"Б1\.[\w.]+\s+(.+?)\s+(?:направления|направлению|профиль)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            value = _clean_name(match.group(1))
            if _valid_name(value):
                return value
    return _clean_name(fallback)


def _clean_name(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" .;:-—_\t\n\r\"«»")
    value = re.sub(r"^(?:ОМ|РПД|RPД|RPD)?[_\-\s]*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^[А-ЯA-ZБ]?\.?\d+(?:\.\d+)*\s*", "", value)
    value = re.sub(r"_?\d{4,}.*$", "", value)
    return value[:180].strip(" .;:-—_\t\n\r\"«»")


def _valid_name(value: str) -> bool:
    if not 4 <= len(value) <= 180:
        return False
    lower = value.lower()
    banned = ["министерство", "университет", "кафедра", "направления подготовки", "форма обучения"]
    return not any(word in lower for word in banned)


def _key(value: str) -> str:
    return re.sub(r"[^a-zа-я0-9]+", " ", value.lower().replace("ё", "е")).strip()


def _top_unique(values: list[str], limit: int) -> list[str]:
    counter: Counter[str] = Counter()
    original: dict[str, str] = {}
    for value in values:
        cleaned = re.sub(r"\s+", " ", str(value)).strip(" .;:-—\t")
        if not cleaned:
            continue
        key = _key(cleaned)
        if key not in original:
            original[key] = cleaned
        counter[key] += 1
    return [original[key] for key, _ in counter.most_common(limit)]


def _tokens(value: str) -> list[str]:
    value = value.lower().replace("ё", "е")
    return [token for token in re.findall(r"[a-zа-я0-9]{3,}", value) if token not in STOP_WORDS]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build dynamic discipline profiles from a folder or ZIP archive of RPD files.")
    parser.add_argument("input", help="Path to RPD ZIP archive or folder")
    parser.add_argument("--output", default="storage/discipline_catalog/discipline_profiles.json")
    args = parser.parse_args()
    catalog = build_catalog(Path(args.input), Path(args.output))
    print(f"Files processed: {catalog['files_total']}")
    print(f"Discipline profiles: {catalog['profiles_total']}")
    print(f"Saved catalog: {args.output}")
    if catalog["errors"]:
        print(f"Errors: {len(catalog['errors'])}")


if __name__ == "__main__":
    main()
