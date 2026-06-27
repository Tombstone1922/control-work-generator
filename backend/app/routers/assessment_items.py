import json
import time

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
    if payload.generation_mode.strip().lower() == INTELLIGENT_V2_MODE:
        try:
            response = generate_intelligent_v2_bank(db=db, fund_id=fund_id, payload=payload, current_user=current_user)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if response is None:
            raise HTTPException(status_code=404, detail="ФОС не найден или нет доступа.")
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
    mode = payload.generation_mode.strip().lower()
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

    topics = json.loads(fund.program.topics_json or "[]")
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
    return validate_assessment_items(items, topics, [competency.code for competency in competencies])


@router.put("/{fund_id}/{item_id}", response_model=AssessmentItemRead)
def update_item(
    fund_id: str,
    item_id: str,
    payload: AssessmentItemUpdateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> AssessmentItemRead:
    try:
        item = update_item_for_user(db, fund_id, item_id, current_user, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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
    if not delete_item_for_user(db, fund_id, item_id, current_user):
        raise HTTPException(status_code=404, detail="Задание не найдено или нет доступа.")
    return Response(status_code=204)


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
