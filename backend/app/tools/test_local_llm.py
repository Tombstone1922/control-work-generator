from __future__ import annotations

import json
import sys

from app.services.local_llm_diagnostics import check_local_llm, generate_local_llm_sample_task


def main() -> None:
    profile = sys.argv[1] if len(sys.argv) > 1 else None
    status = check_local_llm(profile).as_dict()
    print("=== Local LLM status ===")
    print(json.dumps(status, ensure_ascii=False, indent=2))

    print("\n=== Local LLM sample task ===")
    sample = generate_local_llm_sample_task(profile)
    print(json.dumps(sample, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
