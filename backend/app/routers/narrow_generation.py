from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.repositories_training_examples import list_training_examples_for_user
from app.schemas import AssessmentItemRead
from app.security import get_current_user
from app.services.narrow_llm_service import apply_narrow_llm_generation

router = APIRouter(prefix="/api/narrow-generation", tags=["narrow-generation"])


@router.post("/preview")
def preview_narrow_generation(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:
        items = [AssessmentItemRead(**item) for item in payload.get("items", [])]
        result = apply_narrow_llm_generation(
            items=items,
            training_examples=list_training_examples_for_user(db, current_user),
            requested_mode=payload.get("generation_mode", "narrow_llm"),
            narrow_max_items=int(payload.get("narrow_max_items", len(items) or 1)),
            fallback_to_template=bool(payload.get("fallback_to_template", True)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "items": [item.model_dump() for item in result.items],
        "requested_mode": result.requested_mode,
        "used_mode": result.used_mode,
        "narrow_llm_generated_items": result.narrow_llm_generated_items,
        "template_generated_items": result.template_generated_items,
        "model_version": result.model_version,
        "warnings": result.warnings,
    }
