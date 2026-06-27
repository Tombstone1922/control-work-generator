from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.repositories import get_program_entity_for_user
from app.schemas import AssessmentItemRead
from app.security import get_current_user
from app.services.demo_task_bank_service import ensure_bank, get_bank
from app.services.role_policy import require_teacher_or_admin

router = APIRouter(prefix="/api/demo-bank", tags=["demo-bank"])


class DemoBankSection(BaseModel):
    code: str
    title: str
    assessment_type: str
    planned_items: int
    generated_items: int


class DemoBankResponse(BaseModel):
    ready: bool
    built_now: bool
    program_id: str
    filename: str
    fund_id: str
    mode: str
    model_version: str
    total_items: int
    planned_items: int
    sections: list[DemoBankSection]
    sample_items: list[AssessmentItemRead]
    llm: dict = Field(default_factory=dict)
    matched_by_name: bool = False


@router.post("/{program_id}/seed", response_model=DemoBankResponse)
def seed_bank(program_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)) -> DemoBankResponse:
    require_teacher_or_admin(current_user)
    program = get_program_entity_for_user(db, program_id, current_user)
    if program is None:
        raise HTTPException(status_code=404, detail="РПД не найдена или нет доступа.")
    return ensure_bank(db, program, rebuild=True)


@router.get("/{program_id}/work-mode", response_model=DemoBankResponse)
def work_mode(program_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)) -> DemoBankResponse:
    program = get_program_entity_for_user(db, program_id, current_user)
    if program is None:
        raise HTTPException(status_code=404, detail="РПД не найдена или нет доступа.")
    return get_bank(db, program, auto_build=False)
