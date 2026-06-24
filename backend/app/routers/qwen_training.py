from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.schemas import AssessmentItemsGenerateRequest, AssessmentItemsGenerateResponse
from app.security import get_current_user
from app.services.qwen_seed_generation_service import generate_qwen_seed_bank

router = APIRouter(prefix="/api/qwen-training", tags=["qwen-training"])


@router.post("/{fund_id}/generate-good", response_model=AssessmentItemsGenerateResponse)
def generate_qwen_good_examples(
    fund_id: str,
    payload: AssessmentItemsGenerateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> AssessmentItemsGenerateResponse:
    try:
        result = generate_qwen_seed_bank(
            db=db,
            fund_id=fund_id,
            payload=payload,
            current_user=current_user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="ФОС не найден или нет доступа.")
    return result
