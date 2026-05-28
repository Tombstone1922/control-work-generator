from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.repositories import get_generation_for_user
from app.security import get_current_user
from app.services.docx_exporter import export_generation_to_docx

router = APIRouter(prefix="/api/export", tags=["export"])


@router.get("/docx/{session_id}")
def export_docx(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> FileResponse:
    generation = get_generation_for_user(db, session_id, current_user)
    if generation is None:
        raise HTTPException(status_code=404, detail="Сеанс генерации не найден или нет доступа.")

    file_path = export_generation_to_docx(generation)
    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
