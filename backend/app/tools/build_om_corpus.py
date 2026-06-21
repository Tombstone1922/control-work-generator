import argparse
from pathlib import Path

from app.services.om_reference_extractor import build_om_reference_corpus


def main() -> None:
    parser = argparse.ArgumentParser(description="Build JSONL corpus from ready assessment materials (OM/FOS) documents.")
    parser.add_argument("input", help="Path to OM/FOS ZIP archive or folder with PDF/DOCX/TXT files")
    parser.add_argument("--output", default="storage/om_corpus/om_examples.jsonl", help="Output JSONL path")
    args = parser.parse_args()

    stats = build_om_reference_corpus(Path(args.input), Path(args.output))
    print(f"Files found: {stats.files_total}")
    print(f"Files processed: {stats.files_processed}")
    print(f"Examples extracted: {stats.examples_total}")
    if stats.errors:
        print("Errors:")
        for error in stats.errors[:20]:
            print(f"- {error}")
        if len(stats.errors) > 20:
            print(f"... and {len(stats.errors) - 20} more")
    print(f"Saved corpus: {args.output}")


if __name__ == "__main__":
    main()
