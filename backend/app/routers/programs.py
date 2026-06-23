from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.repositories import (
    get_program_entity_for_user,
    get_program_for_user,
    list_programs_for_user,
    save_program,
    update_program_analysis,
)
from app.schemas import ProgramAnalysis, RpdAnalysisReport, RpdDiagnostics
from app.security import get_current_user
from app.services.discipline_catalog import enrich_analysis_with_catalog
from app.services.discipline_profile import DOMAIN_PROFILES, detect_discipline_profile, enrich_analysis_with_discipline_profile
from app.services.document_parser import UnsupportedDocumentFormat, extract_text
from app.services.role_policy import ensure_can_edit_program_content, require_teacher_or_admin
from app.services.rpd_analyzer import RpdAnalysisResult, analyze_rpd_text
from app.services.rpd_topic_sanitizer import sanitize_rpd_topics

router = APIRouter(prefix="/api/programs", tags=["programs"])
UPLOAD_DIR = Path(__file__).resolve().parents[1] / "storage" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _analyze_program_text(filename: str, text: str) -> RpdAnalysisResult:
    analysis = analyze_rpd_text(text)
    analysis = enrich_analysis_with_discipline_profile(filename, text, analysis)
    analysis = enrich_analysis_with_catalog(filename, text, analysis)
    return _sanitize_analysis_topics(analysis, filename=filename, text=text)


def _sanitize_analysis_topics(analysis: RpdAnalysisResult, *, filename: str, text: str) -> RpdAnalysisResult:
    raw_count = len(analysis.topics)
    cleaned_topics = sanitize_rpd_topics(analysis.topics)
    removed_count = max(raw_count - len(cleaned_topics), 0)
    if removed_count:
        analysis.diagnostics.warnings.append(f"Очистка тем РПД удалила служебные фрагменты таблиц и вопросы ФОС: {removed_count}.")

    recovered_topics = _recover_missing_topics(
        filename=filename,
        text=text,
        current_topics=cleaned_topics,
    )
    if recovered_topics:
        cleaned_topics = _merge_unique_topics(cleaned_topics, recovered_topics)
        analysis.diagnostics.warnings.append(
            f"После очистки нормальных тем было недостаточно; восстановлены темы по предметному профилю: {len(recovered_topics)}."
        )

    analysis.topics = cleaned_topics
    analysis.topic_sources = list(cleaned_topics)
    analysis.diagnostics.topics_count = len(cleaned_topics)
    analysis.diagnostics.quality_score = min(
        100,
        min(len(cleaned_topics) * 5, 45)
        + min(len(analysis.competencies) * 5, 20)
        + min(len(analysis.learning_outcomes) * 4, 24)
        + min(len(analysis.detected_sections) * 3, 11),
    )
    return analysis


def _recover_missing_topics(*, filename: str, text: str, current_topics: list[str]) -> list[str]:
    if len(current_topics) >= 5:
        return []
    profile_key, confidence = detect_discipline_profile(filename, text, current_topics)
    if not profile_key or confidence < 1.0:
        return []
    profile_topics = DOMAIN_PROFILES.get(profile_key, {}).get("topics", [])
    candidates = sanitize_rpd_topics(profile_topics)
    missing = []
    existing = {_norm_topic(topic) for topic in current_topics}
    for topic in candidates:
        key = _norm_topic(topic)
        if key in existing:
            continue
        existing.add(key)
        missing.append(topic)
        if len(current_topics) + len(missing) >= 8:
            break
    return missing


def _merge_unique_topics(primary: list[str], fallback: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for topic in [*primary, *fallback]:
        key = _norm_topic(topic)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(topic)
    return result[:40]


def _norm_topic(value: str) -> str:
    return " ".join((value or "").lower().replace("ё", "е").split())


def _build_program_schema(program_id: str, filename: str, text: str, analysis: RpdAnalysisResult) -> ProgramAnalysis:
    diagnostics = RpdDiagnostics(
        source_lines=analysis.diagnostics.source_lines,
        analyzed_lines=analysis.diagnostics.analyzed_lines,
        ignored_lines=analysis.diagnostics.ignored_lines,
        topics_count=analysis.diagnostics.topics_count,
        competencies_count=analysis.diagnostics.competencies_count,
        learning_outcomes_count=analysis.diagnostics.learning_outcomes_count,
        detected_sections_count=analysis.diagnostics.detected_sections_count,
        quality_score=analysis.diagnostics.quality_score,
        extraction_strategy=analysis.diagnostics.extraction_strategy,
        warnings=analysis.diagnostics.warnings,
    )
    report = RpdAnalysisReport(
        detected_sections=analysis.detected_sections,
        topic_sources=analysis.topic_sources,
        competency_sources=analysis.competency_sources,
        outcome_sources=analysis.outcome_sources,
        diagnostics=diagnostics,
    )
    return ProgramAnalysis(
        program_id=program_id,
        filename=filename,
        text_preview=text[:1000],
        topics=analysis.topics,
        competencies=analysis.competencies,
        learning_outcomes=analysis.learning_outcomes,
        analysis_report=report,
    )


@router.post("/upload", response_model=ProgramAnalysis)
async def upload_program(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> ProgramAnalysis:
    require_teacher_or_admin(current_user)
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

    result = _build_program_schema(program_id, original_name, text, _analyze_program_text(original_name, text))
    save_program(db, result, str(storage_path), owner_user_id=current_user.id)
    return result


@router.post("/{program_id}/reanalyze", response_model=ProgramAnalysis)
def reanalyze_program(
    program_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> ProgramAnalysis:
    entity = get_program_entity_for_user(db, program_id, current_user)
    if entity is None:
        raise HTTPException(status_code=404, detail="РПД не найдена или нет доступа.")
    ensure_can_edit_program_content(current_user, entity)

    try:
        text = extract_text(entity.file_path)
    except (UnsupportedDocumentFormat, FileNotFoundError) as exc:
        raise HTTPException(status_code=422, detail="Не удалось повторно прочитать исходный файл РПД.") from exc

    result = _build_program_schema(entity.id, entity.filename, text, _analyze_program_text(entity.filename, text))
    update_program_analysis(db, entity, result)
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
