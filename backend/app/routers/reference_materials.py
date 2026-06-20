import shutil
import tempfile
import zipfile
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.reference_materials_schemas import (
    OmAssessmentItemRead,
    ReferenceDocumentRead,
    ReferenceLibraryStats,
    ReferenceUploadResponse,
    RpOmPairRead,
)
from app.repositories_reference_materials import (
    get_reference_stats,
    list_om_items,
    list_pairs,
    list_reference_documents,
    save_reference_document,
)
from app.security import get_current_user
from app.services.document_parser import UnsupportedDocumentFormat, extract_text
from app.services.reference_material_parser import parse_reference_document

router = APIRouter(prefix="/api/reference-materials", tags=["reference-materials"])

REFERENCE_DIR = Path(__file__).resolve().parents[1] / "storage" / "reference_materials"
REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
SUPPORTED_UPLOAD_EXTENSIONS = {".docx", ".pdf", ".txt"}


@router.post("/upload", response_model=ReferenceUploadResponse)
async def upload_reference_document(
    document_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> ReferenceUploadResponse:
    document_type = _normalize_document_type(document_type)
    original_name = file.filename or "reference_document"
    extension = Path(original_name).suffix.lower()
    if extension not in SUPPORTED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Поддерживаются только DOCX, PDF и TXT документы.")

    storage_path = REFERENCE_DIR / f"{uuid4()}{extension}"
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Файл пуст.")
    storage_path.write_bytes(content)

    return _save_uploaded_reference(db, current_user, document_type, original_name, storage_path)


@router.post("/upload-archive", response_model=list[ReferenceUploadResponse])
async def upload_reference_archive(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> list[ReferenceUploadResponse]:
    original_name = file.filename or "reference_archive.zip"
    if Path(original_name).suffix.lower() != ".zip":
        raise HTTPException(status_code=400, detail="Архив должен быть в формате ZIP.")

    archive_bytes = await file.read()
    if not archive_bytes:
        raise HTTPException(status_code=400, detail="Архив пуст.")

    results: list[ReferenceUploadResponse] = []
    with tempfile.TemporaryDirectory() as temp_dir:
        archive_path = Path(temp_dir) / "archive.zip"
        archive_path.write_bytes(archive_bytes)
        try:
            with zipfile.ZipFile(archive_path) as archive:
                archive.extractall(temp_dir)
        except zipfile.BadZipFile as exc:
            raise HTTPException(status_code=400, detail="Не удалось прочитать ZIP-архив.") from exc

        extracted_files = [path for path in Path(temp_dir).rglob("*") if path.is_file() and path.suffix.lower() in SUPPORTED_UPLOAD_EXTENSIONS]
        if not extracted_files:
            raise HTTPException(status_code=422, detail="В архиве не найдено DOCX, PDF или TXT файлов RP/OM.")

        for source_path in extracted_files:
            document_type = _infer_document_type(source_path.name)
            storage_path = REFERENCE_DIR / f"{uuid4()}{source_path.suffix.lower()}"
            shutil.copyfile(source_path, storage_path)
            results.append(_save_uploaded_reference(db, current_user, document_type, source_path.name, storage_path))

    return results


@router.get("/", response_model=list[ReferenceDocumentRead])
def get_reference_documents(
    document_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> list[ReferenceDocumentRead]:
    if document_type:
        document_type = _normalize_document_type(document_type)
    return list_reference_documents(db, current_user, document_type=document_type)


@router.get("/pairs", response_model=list[RpOmPairRead])
def get_pairs(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> list[RpOmPairRead]:
    return list_pairs(db, current_user)


@router.get("/om-items", response_model=list[OmAssessmentItemRead])
def get_om_items(
    om_document_id: str | None = Query(default=None),
    pair_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> list[OmAssessmentItemRead]:
    return list_om_items(db, current_user, om_document_id=om_document_id, pair_id=pair_id)


@router.get("/stats", response_model=ReferenceLibraryStats)
def get_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> ReferenceLibraryStats:
    return get_reference_stats(db, current_user)


def _save_uploaded_reference(
    db: Session,
    user: models.User,
    document_type: str,
    original_name: str,
    storage_path: Path,
) -> ReferenceUploadResponse:
    try:
        text = extract_text(storage_path)
    except UnsupportedDocumentFormat as exc:
        storage_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not text.strip():
        storage_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=f"Не удалось извлечь текст из файла {original_name}.")

    parsed = parse_reference_document(text, original_name, document_type)
    try:
        document, items_count, paired_count = save_reference_document(
            db,
            user,
            document_type=document_type,
            filename=original_name,
            file_path=storage_path,
            parsed=parsed,
        )
    except ValueError as exc:
        storage_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ReferenceUploadResponse(
        document=document,
        parsed_items_count=items_count,
        paired_count=paired_count,
        warnings=parsed.warnings,
    )


def _normalize_document_type(value: str) -> str:
    lowered = (value or "").strip().lower()
    if lowered in {"rp", "рп", "rpd", "рпд", "program"}:
        return "rp"
    if lowered in {"om", "ом", "fos", "фос", "assessment", "оценочные"}:
        return "om"
    raise HTTPException(status_code=400, detail="Тип документа должен быть RP или OM.")


def _infer_document_type(filename: str) -> str:
    lowered = filename.lower()
    if any(marker in lowered for marker in ("om", "ом", "фос", "оценоч", "assessment")):
        return "om"
    if any(marker in lowered for marker in ("rp", "рп", "rpd", "рпд", "рабоч", "program")):
        return "rp"
    return "om" if "оцен" in lowered else "rp"
