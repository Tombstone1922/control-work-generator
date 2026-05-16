from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.services.docx_exporter import export_generation_to_docx
from app.state import GENERATIONS

router = APIRouter(prefix="/api/export", tags=["export"])


@router.get("/docx/{session_id}")
def export_docx(session_id: str) -> FileResponse:
    generation = GENERATIONS.get(session_id)
    if generation is None:
        raise HTTPException(status_code=404, detail="Сеанс генерации не найден.")

    file_path = export_generation_to_docx(generation)
    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
