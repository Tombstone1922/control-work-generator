import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.repositories import get_generation_for_user, get_program_for_user
from app.repositories_assessment_funds import get_assessment_fund_for_user
from app.repositories_assessment_items import get_fund_entity_for_user, list_items_for_user, replace_items_for_sections
from app.repositories_training_examples import list_training_examples_for_user
from app.schemas import AssessmentCompetencyRead, AssessmentFundSection, AssessmentItemRead
from app.security import get_current_user
from app.services.assessment_fund_docx_exporter import export_assessment_fund_to_docx
from app.services.assessment_item_generator import ItemGenerationContext, generate_items_for_section
from app.services.assessment_item_validator import validate_assessment_items
from app.services.docx_exporter import export_generation_to_docx
from app.services.example_based_generator import apply_example_based_generation
from app.services.reference_library import find_om_examples_for_program
from app.services.role_policy import ensure_can_edit_fund_content

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

    program = get_program_for_user(db, generation.program_id, current_user)
    file_path = export_generation_to_docx(generation, program)
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

    if not items:
        try:
            ensure_can_edit_fund_content(current_user, fund_entity)
        except HTTPException as exc:
            raise HTTPException(
                status_code=422,
                detail="В ФОС еще нет заданий. Попросите преподавателя сформировать банк заданий перед экспортом.",
            ) from exc
        items = _generate_missing_items_for_export(db, fund_entity, current_user)
        fund = get_assessment_fund_for_user(db, fund_id, current_user)
        if fund is None:
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


def _generate_missing_items_for_export(
    db: Session,
    fund: models.AssessmentFund,
    current_user: models.User,
) -> list[AssessmentItemRead]:
    raw_sections = json.loads(fund.sections_json or "[]")
    selected_sections = [
        AssessmentFundSection(**raw)
        for raw in raw_sections
        if raw.get("enabled") and raw.get("assessment_type") not in {"competency_matrix", "grading_rubric"}
    ]
    if not selected_sections:
        return []

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
                    max_items=40,
                )
            )
        )

    training_examples = list_training_examples_for_user(db, current_user)
    om_match = find_om_examples_for_program(
        program_filename=fund.program.filename,
        program_text=fund.program.text_preview,
        fund_id=fund.id,
        discipline_name=fund.discipline_name,
        topics=topics,
    )
    training_examples = om_match.examples + training_examples

    generation_result = apply_example_based_generation(
        items=generated,
        training_examples=training_examples,
        requested_mode="learned",
        learned_max_items=len(generated),
        fallback_to_template=True,
    )
    return replace_items_for_sections(
        db,
        fund,
        target_codes,
        generation_result.items,
        replace_existing=True,
    )
