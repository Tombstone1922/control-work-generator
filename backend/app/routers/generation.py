from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories import get_generation as repo_get_generation
from app.repositories import get_program as repo_get_program
from app.repositories import list_generations, save_generation
from app.schemas import GenerationRequest, GenerationResponse
from app.services.question_generator import generate_variants
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
