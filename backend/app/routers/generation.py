from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.schemas import GenerationRequest, GenerationResponse
from app.services.question_generator import generate_variants
from app.services.quality_checker import build_quality_report
from app.state import GENERATIONS, PROGRAMS

router = APIRouter(prefix="/api/generation", tags=["generation"])


@router.post("/run", response_model=GenerationResponse)
def run_generation(payload: GenerationRequest) -> GenerationResponse:
    program = PROGRAMS.get(payload.program_id)
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
    GENERATIONS[response.session_id] = response
    return response


@router.get("/{session_id}", response_model=GenerationResponse)
def get_generation(session_id: str) -> GenerationResponse:
    generation = GENERATIONS.get(session_id)
    if generation is None:
        raise HTTPException(status_code=404, detail="Сеанс генерации не найден.")
    return generation
