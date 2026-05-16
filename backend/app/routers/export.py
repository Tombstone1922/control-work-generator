from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories import get_generation
from app.services.docx_exporter import export_generation_to_docx

router = APIRouter(prefix="/api/export", tags=["export"])


@router.get("/docx/{session_id}")
def export_docx(session_id: str, db: Session = Depends(get_db)) -> FileResponse:
    generation = get_generation(db, session_id)
    if generation is None:
        raise HTTPException(status_code=404, detail="Сеанс генерации не найден.")

    file_path = export_generation_to_docx(generation)
    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
