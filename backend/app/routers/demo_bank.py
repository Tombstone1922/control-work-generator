from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.repositories import get_program_entity_for_user, user_can_access_program
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


class SeedAllResponse(BaseModel):
    programs_processed: int
    total_items: int
    planned_items_per_program: int


@router.post("/{program_id}/seed", response_model=DemoBankResponse)
def seed_bank(
    program_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> DemoBankResponse:
    require_teacher_or_admin(current_user)
    program = get_program_entity_for_user(db, program_id, current_user)
    if program is None:
        raise HTTPException(status_code=404, detail="РПД не найдена или нет доступа.")
    return ensure_bank(db, program, rebuild=True)


@get_bank_route := router.get("/{program_id}/work-mode", response_model=DemoBankResponse)
def work_mode(
    program_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> DemoBankResponse:
    program = get_program_entity_for_user(db, program_id, current_user)
    if program is None:
        raise HTTPException(status_code=404, detail="РПД не найдена или нет доступа.")
    return get_bank(db, program, auto_build=False)


@router.post("/seed-all", response_model=SeedAllResponse)
def seed_all(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> SeedAllResponse:
    require_teacher_or_admin(current_user)
    query = select(models.Program).order_by(models.Program.created_at.desc())
    if current_user.role not in {"admin", "methodist"}:
        query = query.where((models.Program.owner_user_id == current_user.id) | (models.Program.owner_user_id.is_(None)))
    programs = [program for program in db.scalars(query).all() if user_can_access_program(current_user, program)]
    total_items = 0
    for program in programs:
        summary = ensure_bank(db, program, rebuild=True)
        total_items += summary["total_items"]
    return SeedAllResponse(programs_processed=len(programs), total_items=total_items, planned_items_per_program=145)
