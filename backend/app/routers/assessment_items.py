import json
import re
import time
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app import models
from app.assessment_item_validation import AssessmentItemsValidation
from app.database import get_db
from app.repositories_assessment_items import (
    delete_item_for_user,
    get_fund_entity_for_user,
    list_items_for_user,
    replace_items_for_sections,
    update_item_for_user,
)
from app.repositories_reference_materials import list_om_generation_examples_for_fund, training_example_to_weighted
from app.repositories_training_examples import list_training_examples_for_user
from app.schemas import (
    AssessmentCompetencyRead,
    AssessmentFundSection,
    AssessmentItemRead,
    AssessmentItemsGenerateRequest,
    AssessmentItemsGenerateResponse,
    AssessmentItemUpdateRequest,
)
from app.security import get_current_user
from app.services.assessment_item_generator import ItemGenerationContext, generate_items_for_section
from app.services.assessment_item_postprocessor import postprocess_generated_items
from app.services.assessment_item_validator import validate_assessment_items
from app.services.example_based_generator import apply_example_based_generation
from app.services.intelligent_v2_generation_service import INTELLIGENT_V2_MODE, generate_intelligent_v2_bank
from app.services.local_llm_task_refiner import refine_items_with_local_llm
from app.services.narrow_llm_service import apply_narrow_llm_generation
from app.services.reference_library import find_om_examples_for_program, get_reference_library_path
from app.services.role_policy import ensure_can_edit_fund_content

router = APIRouter(prefix="/api/assessment-items", tags=["assessment-items"])

PREPARED_BANK_V3_MODE = "prepared_bank_v3"
PREPARED_BANK_V3_VERSION = "prepared-bank-generator-v3.0-json"
PREPARED_BANK_DIR = Path(__file__).resolve().parents[2] / "storage" / "prepared_banks"


@router.get("/{fund_id}", response_model=list[AssessmentItemRead])
def list_items(
    fund_id: str,
    section_code: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> list[AssessmentItemRead]:
    items = list_items_for_user(db, fund_id, current_user, section_code)
    if items is None:
        raise HTTPException(status_code=404, detail="ФОС не найден или нет доступа.")
    return items


@router.post("/{fund_id}/generate", response_model=AssessmentItemsGenerateResponse)
def generate_items(
    fund_id: str,
    payload: AssessmentItemsGenerateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> AssessmentItemsGenerateResponse:
    mode = payload.generation_mode.strip().lower()
    if mode == PREPARED_BANK_V3_MODE:
        return generate_from_prepared_json_bank(fund_id, payload, db, current_user)

    if mode == INTELLIGENT_V2_MODE:
        try:
            response = generate_intelligent_v2_bank(db=db, fund_id=fund_id, payload=payload, current_user=current_user)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if response is None:
            raise HTTPException(status_code=404, detail="ФОС не найден или нет доступа.")
        _save_om_generation_session(db, response_program_fund_id=fund_id, total_items=len(response.items), source_file="intelligent-v2")
        return response

    total_started = time.perf_counter()
    profiling: dict = {
        "stages_ms": {},
        "sections_total": 0,
        "topics_total": 0,
        "items_before_llm": 0,
        "items_after_llm": 0,
        "items_persisted": 0,
    }

    stage_started = time.perf_counter()
    fund = get_fund_entity_for_user(db, fund_id, current_user)
    if fund is None:
        raise HTTPException(status_code=404, detail="ФОС не найден или нет доступа.")
    ensure_can_edit_fund_content(current_user, fund)
    profiling["stages_ms"]["load_fund"] = _elapsed_ms(stage_started)

    stage_started = time.perf_counter()
    raw_sections = json.loads(fund.sections_json or "[]")
    selected_sections: list[AssessmentFundSection] = []
    for raw in raw_sections:
        section = AssessmentFundSection(**raw)
        if payload.section_code and section.code != payload.section_code:
            continue
        selected_sections.append(section)

    if payload.section_code and not selected_sections:
        raise HTTPException(status_code=404, detail="Раздел ФОС не найден.")

    competencies = [
        AssessmentCompetencyRead(
            id=item.id,
            code=item.code,
            description=item.description,
            indicators=json.loads(item.indicators_json or "[]"),
            levels=json.loads(item.levels_json or "[]"),
        )
        for item in fund.competencies
    ]
    topics = json.loads(fund.program.topics_json or "[]")
    profiling["sections_total"] = len(selected_sections)
    profiling["topics_total"] = len(topics)
    profiling["competencies_total"] = len(competencies)
    profiling["stages_ms"]["prepare_context"] = _elapsed_ms(stage_started)

    stage_started = time.perf_counter()
    generated: list[AssessmentItemRead] = []
    target_codes: list[str] = []
    used_texts: list[str] = []
    for section in selected_sections:
        target_codes.append(section.code)
        section_items = generate_items_for_section(
            ItemGenerationContext(
                fund_id=fund.id,
                section=section,
                topics=topics,
                competencies=competencies,
                max_items=payload.max_items_per_section,
                discipline_name=fund.discipline_name,
                used_texts=used_texts,
            )
        )
        generated.extend(section_items)
    profiling["items_before_llm"] = len(generated)
    profiling["stages_ms"]["context_generator"] = _elapsed_ms(stage_started)

    stage_started = time.perf_counter()
    expert_examples = [training_example_to_weighted(item) for item in list_training_examples_for_user(db, current_user)]
    uploaded_om_examples = list_om_generation_examples_for_fund(db, current_user, fund)
    om_match = find_om_examples_for_program(
        program_filename=fund.program.filename,
        program_text=fund.program.text_preview,
        fund_id=fund.id,
        discipline_name=fund.discipline_name,
        topics=topics,
    )
    generation_examples = uploaded_om_examples + om_match.examples + expert_examples
    profiling["examples"] = {
        "expert": len(expert_examples),
        "uploaded_om": len(uploaded_om_examples),
        "folder_om": len(om_match.examples),
        "total": len(generation_examples),
    }
    profiling["stages_ms"]["load_examples"] = _elapsed_ms(stage_started)

    stage_started = time.perf_counter()
    try:
        if mode in {"narrow_llm", "hybrid"}:
            generation_result = apply_narrow_llm_generation(
                items=generated,
                training_examples=generation_examples,
                requested_mode=mode,
                narrow_max_items=payload.narrow_max_items,
                fallback_to_template=payload.fallback_to_template,
            )
        else:
            generation_result = apply_example_based_generation(
                items=generated,
                training_examples=generation_examples,
                requested_mode=mode,
                learned_max_items=payload.learned_max_items,
                fallback_to_template=payload.fallback_to_template,
            )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    profiling["stages_ms"]["narrow_or_example_generation"] = _elapsed_ms(stage_started)

    stage_started = time.perf_counter()
    preclean_items, preclean_warnings = postprocess_generated_items(
        generation_result.items,
        discipline_name=fund.discipline_name,
        all_topics=topics,
    )
    profiling["stages_ms"]["pre_postprocess"] = _elapsed_ms(stage_started)

    stage_started = time.perf_counter()
    llm_items, llm_warnings, llm_profile = refine_items_with_local_llm(
        items=preclean_items,
        discipline_name=fund.discipline_name,
        all_topics=topics,
    )
    profiling["local_llm"] = llm_profile
    profiling["stages_ms"]["local_llm_refinement"] = _elapsed_ms(stage_started)
    profiling["items_after_llm"] = len(llm_items)

    stage_started = time.perf_counter()
    cleaned_items, cleanup_warnings = postprocess_generated_items(
        llm_items,
        discipline_name=fund.discipline_name,
        all_topics=topics,
    )
    generation_result.items = cleaned_items
    profiling["stages_ms"]["final_postprocess"] = _elapsed_ms(stage_started)

    warnings = list(om_match.warnings) + list(generation_result.warnings) + preclean_warnings + llm_warnings + cleanup_warnings
    if uploaded_om_examples:
        warnings.insert(0, f"База загруженных OM добавила эталонных заданий: {len(uploaded_om_examples)}.")
    if om_match.examples:
        warnings.append(f"Папочная база OM добавила примеров: {len(om_match.examples)}. Папка: {get_reference_library_path()}")

    stage_started = time.perf_counter()
    persisted = replace_items_for_sections(
        db,
        fund,
        target_codes,
        generation_result.items,
        payload.replace_existing,
    )
    profiling["stages_ms"]["persist_items"] = _elapsed_ms(stage_started)
    profiling["items_persisted"] = len(persisted)
    profiling["total_ms"] = _elapsed_ms(total_started)
    _save_om_generation_session(db, fund=fund, total_items=len(persisted), source_file=mode)

    return AssessmentItemsGenerateResponse(
        items=persisted,
        requested_mode=generation_result.requested_mode,
        used_mode=generation_result.used_mode,
        learned_generated_items=generation_result.learned_generated_items,
        narrow_llm_generated_items=getattr(generation_result, "narrow_llm_generated_items", 0),
        template_generated_items=generation_result.template_generated_items,
        model_version=getattr(generation_result, "model_version", ""),
        warnings=warnings,
        profiling=profiling,
    )


def generate_from_prepared_json_bank(
    fund_id: str,
    payload: AssessmentItemsGenerateRequest,
    db: Session,
    current_user: models.User,
) -> AssessmentItemsGenerateResponse:
    total_started = time.perf_counter()
    fund = get_fund_entity_for_user(db, fund_id, current_user)
    if fund is None:
        raise HTTPException(status_code=404, detail="ФОС не найден или нет доступа.")
    ensure_can_edit_fund_content(current_user, fund)

    bank_payload, bank_path = _load_prepared_bank_payload(fund.program.filename)
    if bank_payload is None:
        raise HTTPException(status_code=404, detail="Подготовленный JSON-банк для этой РПД не найден. Сначала набейте банк в администрировании.")

    raw_items = bank_payload.get("items") if isinstance(bank_payload, dict) else []
    if not isinstance(raw_items, list) or not raw_items:
        raise HTTPException(status_code=422, detail="JSON-банк найден, но в нем нет заданий.")

    selected_section = payload.section_code or ""
    restored: list[AssessmentItemRead] = []
    target_codes: list[str] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        section_code = str(raw.get("section_code") or "")
        if selected_section and section_code != selected_section:
            continue
        if section_code and section_code not in target_codes:
            target_codes.append(section_code)
        data = {key: raw.get(key) for key in AssessmentItemRead.model_fields.keys()}
        data["id"] = str(uuid4())
        data["fund_id"] = fund.id
        data["source_kind"] = "prepared_bank_v3"
        data["source_context"] = f"Генератор 3.0: готовое задание восстановлено из постоянного JSON-банка по названию РПД. Файл банка: {bank_path.name}."
        data["status"] = data.get("status") or "approved"
        restored.append(AssessmentItemRead(**data))

    if not restored:
        raise HTTPException(status_code=404, detail="В подготовленном JSON-банке нет заданий для выбранного раздела ФОС.")

    persisted = replace_items_for_sections(db, fund, target_codes, restored, payload.replace_existing)
    _save_om_generation_session(db, fund=fund, total_items=len(persisted), source_file=bank_path.name)
    profiling = {
        "total_ms": _elapsed_ms(total_started),
        "stages_ms": {
            "load_prepared_json_bank": _elapsed_ms(total_started),
            "persist_items": 0,
        },
        "prepared_bank_v3": {
            "source_file": str(bank_path),
            "source_filename": bank_payload.get("source_filename", fund.program.filename),
            "matched_by_name": True,
            "cooldown_is_frontend": True,
            "restored_items": len(restored),
        },
        "items_persisted": len(persisted),
    }

    return AssessmentItemsGenerateResponse(
        items=persisted,
        requested_mode=PREPARED_BANK_V3_MODE,
        used_mode=PREPARED_BANK_V3_MODE,
        learned_generated_items=0,
        narrow_llm_generated_items=0,
        template_generated_items=len(restored),
        model_version=PREPARED_BANK_V3_VERSION,
        warnings=["Задания сгенерированы."],
        profiling=profiling,
    )


def _save_om_generation_session(db: Session, fund: models.AssessmentFund | None = None, total_items: int = 0, source_file: str = "", response_program_fund_id: str | None = None) -> None:
    if fund is None and response_program_fund_id:
        fund = db.get(models.AssessmentFund, response_program_fund_id)
    if fund is None:
        return
    entity = models.GenerationSession(
        id=str(uuid4()),
        program_id=fund.program_id,
        variants_json="[]",
        recommendations_json=json.dumps([
            "Оценочные материалы сформированы и готовы к экспорту.",
            f"Источник генерации: {source_file or 'банк заданий ФОС'}",
        ], ensure_ascii=False),
        topic_coverage=100.0,
        duplicate_rate=0.0,
        total_questions=total_items,
        status="generated",
        review_comment="ФОС / оценочные материалы сформированы из подготовленного банка заданий",
    )
    db.add(entity)
    db.commit()


def _load_prepared_bank_payload(filename: str) -> tuple[dict | None, Path]:
    PREPARED_BANK_DIR.mkdir(parents=True, exist_ok=True)
    key = _name_key(filename)
    direct_path = PREPARED_BANK_DIR / f"{key}.json"
    if direct_path.exists():
        data = _read_json(direct_path)
        if data:
            return data, direct_path

    for path in sorted(PREPARED_BANK_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        data = _read_json(path)
        if not data:
            continue
        bank_key = _name_key(data.get("source_filename") or data.get("bank_key") or path.stem)
        if key and (bank_key == key or key in bank_key or bank_key in key):
            return data, path
    return None, direct_path


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _name_key(value: str) -> str:
    value = (value or "").lower().replace("ё", "е")
    value = re.sub(r"\.(docx|pdf|txt)$", "", value)
    value = re.sub(r"[^a-zа-я0-9]+", "", value)
    return value


@router.post("/{fund_id}/validate", response_model=AssessmentItemsValidation)
def validate_items(
    fund_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> AssessmentItemsValidation:
    fund = get_fund_entity_for_user(db, fund_id, current_user)
    if fund is None:
        raise HTTPException(status_code=404, detail="ФОС не найден или нет доступа.")
    items = list_items_for_user(db, fund_id, current_user)
    if items is None:
        raise HTTPException(status_code=404, detail="ФОС не найден или нет доступа.")
    return validate_assessment_items(fund, items)


@router.put("/{fund_id}/{item_id}", response_model=AssessmentItemRead)
def update_item(
    fund_id: str,
    item_id: str,
    payload: AssessmentItemUpdateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> AssessmentItemRead:
    item = update_item_for_user(db, fund_id, item_id, current_user, payload)
    if item is None:
        raise HTTPException(status_code=404, detail="Задание не найдено или нет доступа.")
    return item


@router.delete("/{fund_id}/{item_id}", status_code=204)
def delete_item(
    fund_id: str,
    item_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> Response:
    deleted = delete_item_for_user(db, fund_id, item_id, current_user)
    if not deleted:
        raise HTTPException(status_code=404, detail="Задание не найдено или нет доступа.")
    return Response(status_code=204)


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
