import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.repositories import save_program
from app.routers.programs import _analyze_program_text, _build_program_schema
from app.security import get_current_user
from app.services.document_parser import UnsupportedDocumentFormat, extract_text
from app.services.question_generator import generate_question

router = APIRouter(prefix="/api/control-bank", tags=["control-bank"])

BACKEND_DIR = Path(__file__).resolve().parents[2]
UPLOAD_DIR = BACKEND_DIR / "storage" / "uploads"
CONTROL_BANK_DIR = BACKEND_DIR / "storage" / "control_work_banks"
EXPORT_DIR = BACKEND_DIR / "storage" / "exports"
CONTROL_BANK_TOTAL = 50
CONTROL_TYPES = ["open"] * 20 + ["practice"] * 20 + ["test"] * 10


class ControlBankItem(BaseModel):
    filename: str
    program_id: str = ""
    status: str
    total_items: int = 0
    planned_items: int = CONTROL_BANK_TOTAL
    error: str = ""
    persistent_path: str = ""


class ControlBankBulkResponse(BaseModel):
    total_files: int
    processed: int
    ready: int
    failed: int
    total_items: int
    planned_items_per_rpd: int = CONTROL_BANK_TOTAL
    items: list[ControlBankItem]


@router.post("/bulk-upload-seed", response_model=ControlBankBulkResponse)
async def bulk_upload_seed(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> ControlBankBulkResponse:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Массовое наполнение банка контрольных работ доступно только администратору.")
    if not files:
        raise HTTPException(status_code=400, detail="Выберите файлы РПД для массовой загрузки.")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    CONTROL_BANK_DIR.mkdir(parents=True, exist_ok=True)
    items: list[ControlBankItem] = []
    ready = 0
    total_items = 0

    for file in files:
        original_name = file.filename or "program"
        try:
            program = await _upload_program_from_file(db, file, current_user.id)
            payload = _build_control_bank(program)
            bank_path = CONTROL_BANK_DIR / f"{_name_key(program.filename)}.json"
            bank_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            count = len(payload["items"])
            status_value = "ready" if count >= CONTROL_BANK_TOTAL else "partial"
            if status_value == "ready":
                ready += 1
            total_items += count
            items.append(ControlBankItem(
                filename=original_name,
                program_id=program.id,
                status=status_value,
                total_items=count,
                persistent_path=str(bank_path),
            ))
        except Exception as exc:
            items.append(ControlBankItem(filename=original_name, status="error", error=str(exc)))

    failed = len([item for item in items if item.status == "error"])
    return ControlBankBulkResponse(
        total_files=len(files),
        processed=len(items),
        ready=ready,
        failed=failed,
        total_items=total_items,
        items=items,
    )


@router.get("/download/all")
def download_all_control_banks(current_user: models.User = Depends(get_current_user)) -> FileResponse:
    if current_user.role not in {"admin", "methodist", "teacher"}:
        raise HTTPException(status_code=403, detail="Недостаточно прав для скачивания банка.")
    CONTROL_BANK_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(CONTROL_BANK_DIR.glob("*.json"), key=lambda item: item.name.lower())
    if not files:
        raise HTTPException(status_code=404, detail="Банки контрольных работ пока не найдены.")
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = EXPORT_DIR / f"control_work_banks_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, arcname=path.name)
    return FileResponse(path=str(archive_path), filename=archive_path.name, media_type="application/zip")


def _build_control_bank(program: models.Program) -> dict:
    topics = [str(item).strip() for item in json.loads(program.topics_json or "[]") if str(item).strip()] or ["Общие положения дисциплины"]
    items = []
    used_texts: list[str] = []
    for index in range(CONTROL_BANK_TOTAL):
        question_type = CONTROL_TYPES[index % len(CONTROL_TYPES)]
        topic = topics[index % len(topics)]
        question = generate_question(
            topic=topic,
            question_type=question_type,
            difficulty="medium",
            seed=index,
            avoid_texts=used_texts,
        )
        used_texts.append(question.text)
        items.append({
            "id": question.id,
            "topic": question.topic,
            "text": question.text,
            "type": question.type,
            "assessment_type": question.type,
            "item_type": "single_choice" if question.type == "test" else question.type,
            "difficulty": question.difficulty,
            "answer": question.answer,
            "criteria": question.criteria,
            "source_kind": "control_work_bank_50",
            "source_context": f"Банк контрольных работ: 50 заданий по РПД {program.filename}.",
            "status": "approved",
        })
    return {
        "schema_version": 1,
        "bank_type": "control_work_50",
        "model_version": "control-work-bank-v1.0-50",
        "source_filename": program.filename,
        "bank_key": _name_key(program.filename),
        "program_id": program.id,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "planned_items": CONTROL_BANK_TOTAL,
        "items": items,
    }


async def _upload_program_from_file(db: Session, file: UploadFile, owner_user_id: str) -> models.Program:
    program_id = str(uuid4())
    original_name = file.filename or "program"
    extension = Path(original_name).suffix.lower()
    storage_path = UPLOAD_DIR / f"{program_id}{extension}"
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail=f"Файл {original_name} пуст.")
    storage_path.write_bytes(content)

    try:
        text = extract_text(storage_path)
    except UnsupportedDocumentFormat as exc:
        storage_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"{original_name}: {exc}") from exc

    if not text.strip():
        raise HTTPException(status_code=422, detail=f"{original_name}: не удалось извлечь текст из документа.")

    result = _build_program_schema(program_id, original_name, text, _analyze_program_text(original_name, text))
    return save_program(db, result, str(storage_path), owner_user_id=owner_user_id)


def _name_key(value: str) -> str:
    value = (value or "").lower().replace("ё", "е")
    value = re.sub(r"\.(docx|pdf|txt)$", "", value)
    value = re.sub(r"[^a-zа-я0-9]+", "", value)
    return value or "control_work_bank"
