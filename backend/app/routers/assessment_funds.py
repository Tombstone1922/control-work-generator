from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models
from app.database import get_db
from app.repositories import get_program_entity_for_user, program_to_schema, user_can_access_program
from app.repositories_assessment_funds import (
    create_assessment_fund,
    create_competency_for_user,
    delete_competency_for_user,
    get_assessment_fund_for_user,
    list_assessment_funds_for_user,
    revalidate_assessment_fund_for_user,
    update_assessment_fund_for_user,
    update_competency_for_user,
)
from app.schemas import (
    AssessmentCompetencyCreateRequest,
    AssessmentCompetencyUpdateRequest,
    AssessmentFundCreateRequest,
    AssessmentFundResponse,
    AssessmentFundUpdateRequest,
)
from app.security import get_current_user
from app.services.assessment_fund_builder import build_assessment_fund
from app.services.document_parser import UnsupportedDocumentFormat, extract_text
from app.services.role_policy import (
    ensure_can_edit_fund_content,
    ensure_can_edit_program_content,
    is_admin,
    is_reviewer,
    is_teacher,
    require_teacher_or_admin,
    validate_fund_status_transition,
)

router = APIRouter(prefix="/api/assessment-funds", tags=["assessment-funds"])
ALLOWED_STATUSES = {"draft", "generated", "in_review", "revision_required", "approved"}
CONTENT_FIELDS = ("title", "discipline_name", "assessment_types", "sections")


@router.post("/", response_model=AssessmentFundResponse)
def create_fund(
    payload: AssessmentFundCreateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> AssessmentFundResponse:
    require_teacher_or_admin(current_user)
    program = get_program_entity_for_user(db, payload.program_id, current_user)
    if program is None:
        raise HTTPException(status_code=404, detail="РПД не найдена или нет доступа.")
    ensure_can_edit_program_content(current_user, program)

    try:
        source_text = extract_text(program.file_path)
    except (UnsupportedDocumentFormat, FileNotFoundError):
        source_text = program.text_preview

    draft = build_assessment_fund(
        program_to_schema(program),
        payload.discipline_name,
        source_text=source_text,
    )
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

    fund_entity = _get_fund_entity_for_route(db, fund_id, current_user)
    if fund_entity is None:
        raise HTTPException(status_code=404, detail="ФОС не найден или нет доступа.")

    content_changed = _payload_changes_content(payload)
    if is_admin(current_user):
        pass
    elif is_teacher(current_user):
        if payload.status in {"revision_required", "approved"}:
            raise HTTPException(status_code=403, detail="Преподаватель не может возвращать или утверждать ФОС.")
        if content_changed:
            ensure_can_edit_fund_content(current_user, fund_entity)
    elif is_reviewer(current_user):
        if content_changed:
            raise HTTPException(status_code=403, detail="Методист проверяет ФОС, но не редактирует структуру и задания преподавателя.")
        if payload.status is None:
            raise HTTPException(status_code=403, detail="Методист может менять только статус проверки ФОС.")
    else:
        raise HTTPException(status_code=403, detail="Недостаточно прав для изменения ФОС.")

    if payload.status is not None:
        validate_fund_status_transition(current_user, payload.status)

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


@router.post("/{fund_id}/competencies", response_model=AssessmentFundResponse)
def create_competency(
    fund_id: str,
    payload: AssessmentCompetencyCreateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> AssessmentFundResponse:
    fund_entity = _get_fund_entity_for_route(db, fund_id, current_user)
    if fund_entity is None:
        raise HTTPException(status_code=404, detail="ФОС не найден или нет доступа.")
    ensure_can_edit_fund_content(current_user, fund_entity)
    try:
        fund = create_competency_for_user(db, fund_id, current_user, payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if fund is None:
        raise HTTPException(status_code=404, detail="ФОС не найден или нет доступа.")
    return fund


@router.put("/{fund_id}/competencies/{competency_id}", response_model=AssessmentFundResponse)
def update_competency(
    fund_id: str,
    competency_id: str,
    payload: AssessmentCompetencyUpdateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> AssessmentFundResponse:
    fund_entity = _get_fund_entity_for_route(db, fund_id, current_user)
    if fund_entity is None:
        raise HTTPException(status_code=404, detail="ФОС не найден или нет доступа.")
    ensure_can_edit_fund_content(current_user, fund_entity)
    try:
        fund = update_competency_for_user(db, fund_id, competency_id, current_user, payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if fund is None:
        raise HTTPException(status_code=404, detail="Компетенция не найдена или нет доступа.")
    return fund


@router.delete("/{fund_id}/competencies/{competency_id}", response_model=AssessmentFundResponse)
def delete_competency(
    fund_id: str,
    competency_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> AssessmentFundResponse:
    fund_entity = _get_fund_entity_for_route(db, fund_id, current_user)
    if fund_entity is None:
        raise HTTPException(status_code=404, detail="ФОС не найден или нет доступа.")
    ensure_can_edit_fund_content(current_user, fund_entity)
    fund = delete_competency_for_user(db, fund_id, competency_id, current_user)
    if fund is None:
        raise HTTPException(status_code=404, detail="Компетенция не найдена или нет доступа.")
    return fund


def _payload_changes_content(payload: AssessmentFundUpdateRequest) -> bool:
    return any(getattr(payload, field_name) is not None for field_name in CONTENT_FIELDS)


def _get_fund_entity_for_route(
    db: Session,
    fund_id: str,
    current_user: models.User,
) -> models.AssessmentFund | None:
    fund = db.scalar(
        select(models.AssessmentFund)
        .where(models.AssessmentFund.id == fund_id)
        .options(selectinload(models.AssessmentFund.program))
    )
    if fund is None or not user_can_access_program(current_user, fund.program):
        return None
    return fund
