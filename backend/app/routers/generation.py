from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.repositories import (
    get_generation_entity_for_user,
    get_generation_for_user,
    get_program_entity_for_user,
    get_program_for_user,
    list_generations_for_user,
    program_to_schema,
    save_generation,
    update_generation_status,
    update_generation_variants,
)
from app.schemas import ControlWorkVariant, GenerationRequest, GenerationResponse
from app.security import get_current_user
from app.services.question_generator import generate_question, generate_variants
from app.services.quality_checker import build_quality_report
from app.services.role_policy import (
    ensure_can_edit_generation_content,
    ensure_can_edit_program_content,
    is_reviewer,
    require_teacher_or_admin,
)

router = APIRouter(prefix="/api/generation", tags=["generation"])
ALLOWED_STATUSES = {"generated", "in_review", "revision_required", "approved"}


class GenerationUpdateRequest(BaseModel):
    variants: list[ControlWorkVariant]


class GenerationStatusUpdateRequest(BaseModel):
    status: str
    review_comment: str = ""


@router.post("/run", response_model=GenerationResponse)
def run_generation(
    payload: GenerationRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> GenerationResponse:
    require_teacher_or_admin(current_user)
    program_entity = get_program_entity_for_user(db, payload.program_id, current_user)
    if program_entity is None:
        raise HTTPException(status_code=404, detail="РПД не найдена или нет доступа.")
    ensure_can_edit_program_content(current_user, program_entity)
    program = program_to_schema(program_entity)

    variants = generate_variants(
        topics=program.topics,
        variants_count=payload.variants_count,
        questions_per_variant=payload.questions_per_variant,
        difficulty=payload.difficulty,
        question_types=payload.question_types,
    )
    report = build_quality_report(variants, program.topics)

    response = GenerationResponse(
        session_id=str(uuid4()),
        program_id=payload.program_id,
        variants=variants,
        quality_report=report,
        status="generated",
    )
    save_generation(db, response)
    return response


@router.get("/", response_model=list[GenerationResponse])
def get_generations(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> list[GenerationResponse]:
    return list_generations_for_user(db, current_user)


@router.get("/{session_id}", response_model=GenerationResponse)
def get_generation(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> GenerationResponse:
    generation = get_generation_for_user(db, session_id, current_user)
    if generation is None:
        raise HTTPException(status_code=404, detail="Сеанс генерации не найден или нет доступа.")
    return generation


@router.put("/{session_id}", response_model=GenerationResponse)
def update_generation(
    session_id: str,
    payload: GenerationUpdateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> GenerationResponse:
    generation_entity = get_generation_entity_for_user(db, session_id, current_user)
    if generation_entity is None:
        raise HTTPException(status_code=404, detail="Сеанс генерации не найден или нет доступа.")

    program_entity = db.get(models.Program, generation_entity.program_id)
    if program_entity is None:
        raise HTTPException(status_code=404, detail="Связанная РПД не найдена или нет доступа.")
    ensure_can_edit_generation_content(current_user, generation_entity, program_entity)
    program = get_program_for_user(db, generation_entity.program_id, current_user)
    if program is None:
        raise HTTPException(status_code=404, detail="Связанная РПД не найдена или нет доступа.")

    report = build_quality_report(payload.variants, program.topics)
    updated = update_generation_variants(db, session_id, payload.variants, report)
    if updated is None:
        raise HTTPException(status_code=404, detail="Сеанс генерации не найден.")
    return updated


@router.patch("/{session_id}/status", response_model=GenerationResponse)
def update_status(
    session_id: str,
    payload: GenerationStatusUpdateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> GenerationResponse:
    generation = get_generation_for_user(db, session_id, current_user)
    if generation is None:
        raise HTTPException(status_code=404, detail="Сеанс генерации не найден или нет доступа.")
    if payload.status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail="Недопустимый статус.")

    if current_user.role == "teacher" and payload.status not in {"generated", "in_review"}:
        raise HTTPException(status_code=403, detail="Преподаватель может отправить работу только на проверку.")
    if is_reviewer(current_user) and payload.status not in {"revision_required", "approved", "in_review"}:
        raise HTTPException(status_code=403, detail="Недопустимое изменение статуса для проверяющего.")
    if current_user.role not in {"teacher", "methodist", "admin"}:
        raise HTTPException(status_code=403, detail="Недостаточно прав для изменения статуса.")

    reviewed_by = current_user.id if is_reviewer(current_user) else None
    updated = update_generation_status(db, session_id, payload.status, payload.review_comment, reviewed_by)
    if updated is None:
        raise HTTPException(status_code=404, detail="Сеанс генерации не найден.")
    return updated


@router.post("/{session_id}/regenerate-question/{question_id}", response_model=GenerationResponse)
def regenerate_question(
    session_id: str,
    question_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> GenerationResponse:
    generation_entity = get_generation_entity_for_user(db, session_id, current_user)
    if generation_entity is None:
        raise HTTPException(status_code=404, detail="Сеанс генерации не найден или нет доступа.")

    program_entity = db.get(models.Program, generation_entity.program_id)
    if program_entity is None:
        raise HTTPException(status_code=404, detail="Связанная РПД не найдена или нет доступа.")
    ensure_can_edit_generation_content(current_user, generation_entity, program_entity)

    generation = get_generation_for_user(db, session_id, current_user)
    program = get_program_for_user(db, generation_entity.program_id, current_user)
    if generation is None or program is None:
        raise HTTPException(status_code=404, detail="Связанная РПД или сеанс генерации не найдены.")

    question_found = False
    all_texts = [question.text for variant in generation.variants for question in variant.questions]
    updated_variants = []
    for variant in generation.variants:
        updated_questions = []
        for index, question in enumerate(variant.questions):
            if question.id == question_id:
                question_found = True
                new_question = generate_question(
                    topic=question.topic,
                    question_type=question.type,
                    difficulty=question.difficulty,
                    seed=len(all_texts) + index + variant.variant_number,
                    avoid_texts=all_texts,
                )
                updated_questions.append(new_question)
            else:
                updated_questions.append(question)
        updated_variants.append(type(variant)(variant_number=variant.variant_number, questions=updated_questions))

    if not question_found:
        raise HTTPException(status_code=404, detail="Задание не найдено в выбранном сеансе генерации.")

    report = build_quality_report(updated_variants, program.topics)
    updated = update_generation_variants(db, session_id, updated_variants, report)
    if updated is None:
        raise HTTPException(status_code=404, detail="Сеанс генерации не найден.")
    return updated
