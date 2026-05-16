from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories import get_generation as repo_get_generation
from app.repositories import get_program as repo_get_program
from app.repositories import list_generations, save_generation, update_generation_variants
from app.schemas import GenerationRequest, GenerationResponse, GenerationUpdateRequest
from app.services.question_generator import generate_question, generate_variants
from app.services.quality_checker import build_quality_report

router = APIRouter(prefix="/api/generation", tags=["generation"])


@router.post("/run", response_model=GenerationResponse)
def run_generation(payload: GenerationRequest, db: Session = Depends(get_db)) -> GenerationResponse:
    program = repo_get_program(db, payload.program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="РПД не найдена. Сначала загрузите документ.")

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
    )
    save_generation(db, response)
    return response


@router.get("/", response_model=list[GenerationResponse])
def get_generations(db: Session = Depends(get_db)) -> list[GenerationResponse]:
    return list_generations(db)


@router.get("/{session_id}", response_model=GenerationResponse)
def get_generation(session_id: str, db: Session = Depends(get_db)) -> GenerationResponse:
    generation = repo_get_generation(db, session_id)
    if generation is None:
        raise HTTPException(status_code=404, detail="Сеанс генерации не найден.")
    return generation


@router.put("/{session_id}", response_model=GenerationResponse)
def update_generation(
    session_id: str,
    payload: GenerationUpdateRequest,
    db: Session = Depends(get_db),
) -> GenerationResponse:
    generation = repo_get_generation(db, session_id)
    if generation is None:
        raise HTTPException(status_code=404, detail="Сеанс генерации не найден.")

    program = repo_get_program(db, generation.program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="Связанная РПД не найдена.")

    report = build_quality_report(payload.variants, program.topics)
    updated = update_generation_variants(db, session_id, payload.variants, report)
    if updated is None:
        raise HTTPException(status_code=404, detail="Сеанс генерации не найден.")
    return updated


@router.post("/{session_id}/regenerate-question/{question_id}", response_model=GenerationResponse)
def regenerate_question(
    session_id: str,
    question_id: str,
    db: Session = Depends(get_db),
) -> GenerationResponse:
    generation = repo_get_generation(db, session_id)
    if generation is None:
        raise HTTPException(status_code=404, detail="Сеанс генерации не найден.")

    program = repo_get_program(db, generation.program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="Связанная РПД не найдена.")

    question_found = False
    all_texts = [
        question.text
        for variant in generation.variants
        for question in variant.questions
    ]

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
