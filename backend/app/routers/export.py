import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.repositories import get_generation_for_user
from app.repositories_assessment_funds import get_assessment_fund_for_user
from app.repositories_assessment_items import get_fund_entity_for_user, list_items_for_user
from app.security import get_current_user
from app.services.assessment_fund_docx_exporter import export_assessment_fund_to_docx
from app.services.assessment_item_validator import validate_assessment_items
from app.services.docx_exporter import export_generation_to_docx

router = APIRouter(prefix="/api/export", tags=["export"])
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


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
        media_type=DOCX_MEDIA_TYPE,
    )


@router.get("/assessment-fund/{fund_id}/docx")
def export_assessment_fund_docx(
    fund_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> FileResponse:
    fund = get_assessment_fund_for_user(db, fund_id, current_user)
    fund_entity = get_fund_entity_for_user(db, fund_id, current_user)
    items = list_items_for_user(db, fund_id, current_user)
    if fund is None or fund_entity is None or items is None:
        raise HTTPException(status_code=404, detail="ФОС не найден или нет доступа.")

    topics = json.loads(fund_entity.program.topics_json or "[]")
    competencies = [item.code for item in fund_entity.competencies]
    validation = validate_assessment_items(items, topics, competencies)
    file_path = export_assessment_fund_to_docx(fund, items, validation)
    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type=DOCX_MEDIA_TYPE,
    )
