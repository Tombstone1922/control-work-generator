from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.repositories import get_program_entity_for_user, program_to_schema
from app.repositories_assessment_funds import (
    create_assessment_fund,
    get_assessment_fund_for_user,
    list_assessment_funds_for_user,
    revalidate_assessment_fund_for_user,
    update_assessment_fund_for_user,
)
from app.schemas import (
    AssessmentFundCreateRequest,
    AssessmentFundResponse,
    AssessmentFundUpdateRequest,
)
from app.security import get_current_user
from app.services.assessment_fund_builder import build_assessment_fund

router = APIRouter(prefix="/api/assessment-funds", tags=["assessment-funds"])
ALLOWED_STATUSES = {"draft", "generated", "in_review", "revision_required", "approved"}


@router.post("/", response_model=AssessmentFundResponse)
def create_fund(
    payload: AssessmentFundCreateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> AssessmentFundResponse:
    program = get_program_entity_for_user(db, payload.program_id, current_user)
    if program is None:
        raise HTTPException(status_code=404, detail="РПД не найдена или нет доступа.")

    draft = build_assessment_fund(program_to_schema(program), payload.discipline_name)
    return create_assessment_fund(db, program, draft)


@router.get("/", response_model=list[AssessmentFundResponse])
def list_funds(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> list[AssessmentFundResponse]:
    return list_assessment_funds_for_user(db, current_user)


@router.get("/{fund_id}", response_model=AssessmentFundResponse)
def get_fund(
    fund_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> AssessmentFundResponse:
    fund = get_assessment_fund_for_user(db, fund_id, current_user)
    if fund is None:
        raise HTTPException(status_code=404, detail="ФОС не найден или нет доступа.")
    return fund


@router.put("/{fund_id}", response_model=AssessmentFundResponse)
def update_fund(
    fund_id: str,
    payload: AssessmentFundUpdateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> AssessmentFundResponse:
    if payload.status is not None and payload.status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail="Недопустимый статус ФОС.")

    updated = update_assessment_fund_for_user(
        db,
        fund_id,
        current_user,
        title=payload.title,
        discipline_name=payload.discipline_name,
        status=payload.status,
        assessment_types=payload.assessment_types,
        sections=payload.sections,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="ФОС не найден или нет доступа.")
    return updated


@router.post("/{fund_id}/validate", response_model=AssessmentFundResponse)
def validate_fund(
    fund_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> AssessmentFundResponse:
    fund = revalidate_assessment_fund_for_user(db, fund_id, current_user)
    if fund is None:
        raise HTTPException(status_code=404, detail="ФОС не найден или нет доступа.")
    return fund
