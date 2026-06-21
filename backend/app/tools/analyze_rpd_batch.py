import argparse
import csv
from pathlib import Path

from app.services.document_parser import extract_text
from app.services.rpd_analyzer import analyze_rpd_text

SUPPORTED_EXTENSIONS = {".docx", ".pdf", ".txt"}


def iter_files(root: Path):
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            yield path


def analyze_folder(input_dir: Path, output_csv: Path) -> None:
    rows = []
    for path in iter_files(input_dir):
        try:
            text = extract_text(path)
            result = analyze_rpd_text(text)
            rows.append({
                "file": str(path),
                "topics_count": len(result.topics),
                "competencies_count": len(result.competencies),
                "outcomes_count": len(result.learning_outcomes),
                "sections_count": len(result.detected_sections),
                "quality_score": result.diagnostics.quality_score,
                "topics": "; ".join(result.topics[:12]),
                "competencies": "; ".join(result.competencies[:12]),
                "warnings": "; ".join(result.diagnostics.warnings),
            })
        except Exception as exc:
            rows.append({
                "file": str(path),
                "topics_count": 0,
                "competencies_count": 0,
                "outcomes_count": 0,
                "sections_count": 0,
                "quality_score": 0,
                "topics": "",
                "competencies": "",
                "warnings": f"ERROR: {exc}",
            })

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()) if rows else ["file"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch check RPD parsing quality for a folder of DOCX/PDF/TXT files.")
    parser.add_argument("input_dir", help="Folder with RPD files")
    parser.add_argument("--output", default="storage/rpd_batch_report.csv", help="CSV report path")
    args = parser.parse_args()
    analyze_folder(Path(args.input_dir), Path(args.output))
    print(f"Report saved to {args.output}")


if __name__ == "__main__":
    main()
