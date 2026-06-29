from contextlib import contextmanager

from app.services import demo_task_bank_service as bank_service


FAST_MODE_META = {
    "enabled": False,
    "used": False,
    "calls": 0,
    "refined": 0,
    "rejected": 0,
    "seconds": 0,
    "pipeline": "bulk-fast-context-builder",
}


def _skip_refinement(items, program):
    return items, dict(FAST_MODE_META)


@contextmanager
def bulk_fast_mode():
    original = bank_service._refine_with_qwen
    bank_service._refine_with_qwen = _skip_refinement
    try:
        yield
    finally:
        bank_service._refine_with_qwen = original
