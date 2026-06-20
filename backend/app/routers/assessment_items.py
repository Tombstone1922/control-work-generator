import json

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
from app.services.assessment_item_validator import validate_assessment_items
from app.services.example_based_generator import apply_example_based_generation
from app.services.narrow_llm_service import apply_narrow_llm_generation
from app.services.reference_library import find_om_examples_for_program, get_reference_library_path

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
    fund = get_fund_entity_for_user(db, fund_id, current_user)
    if fund is None:
        raise HTTPException(status_code=404, detail="ФОС не найден или нет доступа.")

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

    generated: list[AssessmentItemRead] = []
    target_codes: list[str] = []
    for section in selected_sections:
        target_codes.append(section.code)
        generated.extend(
            generate_items_for_section(
                ItemGenerationContext(
                    fund_id=fund.id,
                    section=section,
                    topics=topics,
                    competencies=competencies,
                    max_items=payload.max_items_per_section,
                )
            )
        )

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

    warnings = list(om_match.warnings) + list(generation_result.warnings)
    if uploaded_om_examples:
        warnings.insert(0, f"База загруженных OM добавила эталонных заданий: {len(uploaded_om_examples)}.")
    if om_match.examples:
        warnings.append(f"Папочная база OM добавила примеров: {len(om_match.examples)}. Папка: {get_reference_library_path()}")

    persisted = replace_items_for_sections(
        db,
        fund,
        target_codes,
        generation_result.items,
        payload.replace_existing,
    )
    return AssessmentItemsGenerateResponse(
        items=persisted,
        requested_mode=generation_result.requested_mode,
        used_mode=generation_result.used_mode,
        learned_generated_items=generation_result.learned_generated_items,
        narrow_llm_generated_items=getattr(generation_result, "narrow_llm_generated_items", 0),
        template_generated_items=generation_result.template_generated_items,
        model_version=getattr(generation_result, "model_version", ""),
        warnings=warnings,
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
    competencies = [item.code for item in fund.competencies]
    return validate_assessment_items(items, topics, competencies)


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
    if not delete_item_for_user(db, fund_id, item_id, current_user):
        raise HTTPException(status_code=404, detail="Задание не найдено или нет доступа.")
    return Response(status_code=204)
