from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.repositories import save_program
from app.routers.programs import _analyze_program_text, _build_program_schema
from app.security import get_current_user
from app.services import demo_task_bank_service as bank_service
from app.services.bulk_bank_fast_mode import bulk_fast_mode
from app.services.document_parser import UnsupportedDocumentFormat, extract_text

router = APIRouter(prefix="/api/demo-bank-bulk", tags=["demo-bank-bulk"])

BACKEND_DIR = Path(__file__).resolve().parents[2]
UPLOAD_DIR = BACKEND_DIR / "storage" / "uploads"

BANK_600_SECTIONS = [
    ("current_oral", "2.1 Вопросы для устного опроса", "oral", 160),
    ("current_practice", "2.1 Практические задания текущего контроля", "practice", 120),
    ("intermediate_credit", "2.2 Вопросы к зачету", "credit", 120),
    ("intermediate_credit_practice", "2.2 Практические задания к зачету", "credit_practice", 80),
    ("diagnostic", "2.3 Итоговая диагностическая работа", "diagnostic", 120),
]
BANK_600_TOTAL = sum(section[3] for section in BANK_600_SECTIONS)


class BulkBankItem(BaseModel):
    filename: str
    program_id: str = ""
    status: str
    total_items: int = 0
    planned_items: int = BANK_600_TOTAL
    error: str = ""
    persistent_path: str = ""


class BulkBankResponse(BaseModel):
    total_files: int
    processed: int
    ready: int
    failed: int
    total_items: int
    planned_items_per_rpd: int = BANK_600_TOTAL
    items: list[BulkBankItem]


@router.post("/upload-seed", response_model=BulkBankResponse)
async def bulk_upload_seed(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> BulkBankResponse:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Массовое наполнение подготовленного банка доступно только администратору.")
    if not files:
        raise HTTPException(status_code=400, detail="Выберите файлы РПД для массовой загрузки.")

    _activate_600_bank_profile()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    items: list[BulkBankItem] = []
    ready = 0
    total_items = 0

    with bulk_fast_mode():
        for file in files:
            original_name = file.filename or "program"
            try:
                program = await _upload_program_from_file(db, file, current_user.id)
                summary = bank_service.ensure_bank(db, program, rebuild=True)
                item = BulkBankItem(
                    filename=original_name,
                    program_id=program.id,
                    status="ready" if summary.get("ready") else "partial",
                    total_items=int(summary.get("total_items") or 0),
                    planned_items=int(summary.get("planned_items") or BANK_600_TOTAL),
                    persistent_path=str(summary.get("persistent_path") or ""),
                )
                if summary.get("ready"):
                    ready += 1
                total_items += item.total_items
                items.append(item)
            except Exception as exc:
                items.append(BulkBankItem(filename=original_name, status="error", error=str(exc)))

    failed = len([item for item in items if item.status == "error"])
    return BulkBankResponse(
        total_files=len(files),
        processed=len(items),
        ready=ready,
        failed=failed,
        total_items=total_items,
        items=items,
    )


def _activate_600_bank_profile() -> None:
    bank_service.SECTIONS = BANK_600_SECTIONS
    bank_service.TOTAL = BANK_600_TOTAL
    bank_service.MODEL_VERSION = "prepared-system-bank-v4.0-600-fast"
    bank_service.QWEN_BATCH_SIZE = max(getattr(bank_service, "QWEN_BATCH_SIZE", 5), 10)


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
