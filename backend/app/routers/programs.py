from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.schemas import ProgramAnalysis
from app.services.document_parser import UnsupportedDocumentFormat, extract_text
from app.services.rpd_analyzer import analyze_rpd_text
from app.state import PROGRAMS

router = APIRouter(prefix="/api/programs", tags=["programs"])
UPLOAD_DIR = Path(__file__).resolve().parents[1] / "storage" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/upload", response_model=ProgramAnalysis)
async def upload_program(file: UploadFile = File(...)) -> ProgramAnalysis:
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
    PROGRAMS[program_id] = result
    return result


@router.get("/{program_id}", response_model=ProgramAnalysis)
def get_program(program_id: str) -> ProgramAnalysis:
    program = PROGRAMS.get(program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="РПД не найдена. Для MVP данные хранятся в памяти процесса.")
    return program
