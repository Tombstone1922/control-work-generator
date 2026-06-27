import re
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.repositories import get_program_entity_for_user
from app.schemas import AssessmentItemRead
from app.security import get_current_user
from app.services.demo_task_bank_service import ensure_bank, get_bank
from app.services.role_policy import require_teacher_or_admin

router = APIRouter(prefix="/api/demo-bank", tags=["demo-bank"])

BACKEND_DIR = Path(__file__).resolve().parents[2]
PREPARED_BANK_DIR = BACKEND_DIR / "storage" / "prepared_banks"
PREPARED_BANK_EXPORT_DIR = BACKEND_DIR / "storage" / "exports"
JSON_MEDIA_TYPE = "application/json"
ZIP_MEDIA_TYPE = "application/zip"


class DemoBankSection(BaseModel):
    code: str
    title: str
    assessment_type: str
    planned_items: int
    generated_items: int


class DemoBankResponse(BaseModel):
    ready: bool
    built_now: bool
    program_id: str
    filename: str
    fund_id: str
    mode: str
    model_version: str
    total_items: int
    planned_items: int
    sections: list[DemoBankSection]
    sample_items: list[AssessmentItemRead]
    llm: dict = Field(default_factory=dict)
    system: dict = Field(default_factory=dict)
    matched_by_name: bool = False
    restored_from_file: bool = False
    persistent: bool = False
    persistent_path: str = ""


@router.post("/{program_id}/seed", response_model=DemoBankResponse)
def seed_bank(program_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)) -> DemoBankResponse:
    require_teacher_or_admin(current_user)
    program = get_program_entity_for_user(db, program_id, current_user)
    if program is None:
        raise HTTPException(status_code=404, detail="РПД не найдена или нет доступа.")
    return ensure_bank(db, program, rebuild=True)


@router.get("/{program_id}/work-mode", response_model=DemoBankResponse)
def work_mode(program_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)) -> DemoBankResponse:
    program = get_program_entity_for_user(db, program_id, current_user)
    if program is None:
        raise HTTPException(status_code=404, detail="РПД не найдена или нет доступа.")
    return get_bank(db, program, auto_build=False)


@router.get("/{program_id}/download-current")
def download_current_bank(program_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)) -> FileResponse:
    program = get_program_entity_for_user(db, program_id, current_user)
    if program is None:
        raise HTTPException(status_code=404, detail="РПД не найдена или нет доступа.")
    bank_path = _find_bank_file_for_filename(program.filename)
    if bank_path is None:
        raise HTTPException(status_code=404, detail="JSON-банк для текущей РПД не найден. Сначала нажмите “Набить банк заданий”.")
    return FileResponse(path=str(bank_path), filename=f"bank_{_name_key(program.filename)}.json", media_type=JSON_MEDIA_TYPE)


@router.get("/download/all")
def download_all_banks(current_user: models.User = Depends(get_current_user)) -> FileResponse:
    require_teacher_or_admin(current_user)
    PREPARED_BANK_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(PREPARED_BANK_DIR.glob("*.json"), key=lambda item: item.name.lower())
    if not files:
        raise HTTPException(status_code=404, detail="Подготовленные JSON-банки пока не найдены.")
    PREPARED_BANK_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = PREPARED_BANK_EXPORT_DIR / f"prepared_banks_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, arcname=path.name)
    return FileResponse(path=str(archive_path), filename=archive_path.name, media_type=ZIP_MEDIA_TYPE)


def _find_bank_file_for_filename(filename: str) -> Path | None:
    PREPARED_BANK_DIR.mkdir(parents=True, exist_ok=True)
    key = _name_key(filename)
    direct = PREPARED_BANK_DIR / f"{key}.json"
    if direct.exists():
        return direct
    for path in sorted(PREPARED_BANK_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        path_key = _name_key(path.stem)
        if key and (path_key == key or key in path_key or path_key in key):
            return path
    return None


def _name_key(value: str) -> str:
    value = (value or "").lower().replace("ё", "е")
    value = re.sub(r"\.(docx|pdf|txt)$", "", value)
    value = re.sub(r"[^a-zа-я0-9]+", "", value)
    return value or "prepared_bank"
