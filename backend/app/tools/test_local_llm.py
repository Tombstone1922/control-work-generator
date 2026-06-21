from __future__ import annotations

import json

from app.services.local_llm_diagnostics import check_local_llm, generate_local_llm_sample_task


def main() -> None:
    status = check_local_llm().as_dict()
    print("=== Local LLM status ===")
    print(json.dumps(status, ensure_ascii=False, indent=2))

    print("\n=== Local LLM sample task ===")
    sample = generate_local_llm_sample_task()
    print(json.dumps(sample, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
