import argparse
from pathlib import Path

from app.ml.narrow_fos_model import NarrowFOSModel, load_jsonl_records


def main() -> None:
    parser = argparse.ArgumentParser(description="Train local narrow FOS model from JSONL OM corpus and teacher examples.")
    parser.add_argument(
        "--om-corpus",
        default="storage/om_corpus/om_examples.jsonl",
        help="Path to JSONL corpus built from ready OM/FOS documents.",
    )
    parser.add_argument(
        "--training-dataset",
        action="append",
        default=[],
        help="Optional JSONL exported from teacher expert feedback. Can be passed multiple times.",
    )
    parser.add_argument(
        "--output",
        default="storage/models/narrow_fos_model.json",
        help="Output model artifact path.",
    )
    args = parser.parse_args()

    sources = [args.om_corpus, *args.training_dataset]
    records = load_jsonl_records([Path(path) for path in sources])
    model = NarrowFOSModel.train_from_records(records)
    output = model.save(args.output)

    print(f"Records loaded: {len(records)}")
    print(f"Model examples: {model.metadata.get('examples_total', 0)}")
    print(f"Assessment types: {', '.join(model.metadata.get('assessment_types', []))}")
    print(f"Sources: {model.metadata.get('sources', {})}")
    print(f"Saved model: {output}")


if __name__ == "__main__":
    main()
