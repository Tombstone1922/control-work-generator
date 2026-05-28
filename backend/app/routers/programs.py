from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.repositories import get_program_for_user, list_programs_for_user, save_program
from app.schemas import ProgramAnalysis
from app.security import get_current_user
from app.services.document_parser import UnsupportedDocumentFormat, extract_text
from app.services.rpd_analyzer import analyze_rpd_text

router = APIRouter(prefix="/api/programs", tags=["programs"])
UPLOAD_DIR = Path(__file__).resolve().parents[1] / "storage" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/upload", response_model=ProgramAnalysis)
async def upload_program(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> ProgramAnalysis:
    program_id = str(uuid4())
    original_name = file.filename or "program"
    extension = Path(original_name).suffix.lower()
    storage_path = UPLOAD_DIR / f"{program_id}{extension}"

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Загруженный файл пуст.")

    storage_path.write_bytes(content)

    try:
        text = extract_text(storage_path)
    except UnsupportedDocumentFormat as exc:
        storage_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not text.strip():
        raise HTTPException(
            status_code=422,
            detail="Не удалось извлечь текст из документа. Проверьте, что файл содержит текстовый слой.",
        )

    analysis = analyze_rpd_text(text)
    result = ProgramAnalysis(
        program_id=program_id,
        filename=original_name,
        text_preview=text[:1000],
        topics=analysis.topics,
        competencies=analysis.competencies,
        learning_outcomes=analysis.learning_outcomes,
    )
    save_program(db, result, str(storage_path), owner_user_id=current_user.id)
    return result


@router.get("/", response_model=list[ProgramAnalysis])
def get_programs(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> list[ProgramAnalysis]:
    return list_programs_for_user(db, current_user)


@router.get("/{program_id}", response_model=ProgramAnalysis)
def get_program(
    program_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> ProgramAnalysis:
    program = get_program_for_user(db, program_id, current_user)
    if program is None:
        raise HTTPException(status_code=404, detail="РПД не найдена или нет доступа.")
    return program
