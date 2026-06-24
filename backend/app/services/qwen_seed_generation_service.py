import json
import time
from uuid import uuid4

from sqlalchemy.orm import Session

from app import models
from app.repositories_assessment_items import get_fund_entity_for_user, replace_items_for_sections
from app.schemas import (
    AssessmentCompetencyRead,
    AssessmentFundSection,
    AssessmentItemRead,
    AssessmentItemsGenerateRequest,
    AssessmentItemsGenerateResponse,
)
from app.services.assessment_item_generator import ItemGenerationContext, generate_items_for_section
from app.services.assessment_item_postprocessor import postprocess_generated_items
from app.services.fast_local_llm_task_refiner import refine_items_with_local_llm
from app.services.role_policy import ensure_can_edit_fund_content


def generate_qwen_seed_bank(
    *,
    db: Session,
    fund_id: str,
    payload: AssessmentItemsGenerateRequest,
    current_user: models.User,
) -> AssessmentItemsGenerateResponse | None:
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
        return None
    ensure_can_edit_fund_content(current_user, fund)
    profiling["stages_ms"]["load_fund"] = _elapsed_ms(stage_started)

    stage_started = time.perf_counter()
    sections = _selected_sections(fund.sections_json, payload.section_code)
    if payload.section_code and not sections:
        raise ValueError("Раздел ФОС не найден.")
    topics = json.loads(fund.program.topics_json or "[]")
    competencies = _competencies(fund)
    profiling["sections_total"] = len(sections)
    profiling["topics_total"] = len(topics)
    profiling["competencies_total"] = len(competencies)
    profiling["stages_ms"]["prepare_context"] = _elapsed_ms(stage_started)

    stage_started = time.perf_counter()
    generated: list[AssessmentItemRead] = []
    target_codes: list[str] = []
    used_texts: list[str] = []
    for section in sections:
        target_codes.append(section.code)
        generated.extend(
            generate_items_for_section(
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
        )
    profiling["items_before_llm"] = len(generated)
    profiling["stages_ms"]["context_generator"] = _elapsed_ms(stage_started)

    stage_started = time.perf_counter()
    preclean_items, preclean_warnings = postprocess_generated_items(generated, discipline_name=fund.discipline_name, all_topics=topics)
    profiling["stages_ms"]["pre_postprocess"] = _elapsed_ms(stage_started)

    stage_started = time.perf_counter()
    qwen_items, qwen_warnings, llm_profile = refine_items_with_local_llm(
        items=preclean_items,
        discipline_name=fund.discipline_name,
        all_topics=topics,
        mode_override="batch",
        skip_types_override=set(),
        force_rewrite_override=True,
        max_items_override=len(preclean_items),
    )
    profiling["local_llm"] = llm_profile
    profiling["stages_ms"]["local_llm_refinement"] = _elapsed_ms(stage_started)
    profiling["items_after_llm"] = len(qwen_items)

    stage_started = time.perf_counter()
    cleaned_items, cleanup_warnings = postprocess_generated_items(qwen_items, discipline_name=fund.discipline_name, all_topics=topics)
    qwen_good_items = [
        item.model_copy(update={
            "source_kind": "qwen_seed_good" if item.source_kind == "local_llm_qwen3" else item.source_kind,
            "status": "approved",
            "source_context": f"Qwen-only seed generation; auto-good training example. {item.source_context}",
        })
        for item in cleaned_items
    ]
    generated_ids = {item.id for item in qwen_good_items}
    profiling["stages_ms"]["final_postprocess"] = _elapsed_ms(stage_started)

    stage_started = time.perf_counter()
    persisted = replace_items_for_sections(db, fund, target_codes, qwen_good_items, payload.replace_existing)
    profiling["stages_ms"]["persist_items"] = _elapsed_ms(stage_started)
    profiling["items_persisted"] = len([item for item in persisted if item.id in generated_ids])

    stage_started = time.perf_counter()
    seed_items = [item for item in persisted if item.id in generated_ids]
    examples_count = _create_auto_good_examples(db=db, fund=fund, user=current_user, items=seed_items)
    profiling["stages_ms"]["save_good_training_examples"] = _elapsed_ms(stage_started)
    profiling["auto_good_examples"] = examples_count
    profiling["total_ms"] = _elapsed_ms(total_started)

    warnings = [
        "Qwen-only режим: задания сформированы через контекстный каркас и улучшены локальной Qwen-моделью.",
        f"Автоматически добавлено хороших обучающих примеров: {examples_count}.",
    ] + preclean_warnings + qwen_warnings + cleanup_warnings

    return AssessmentItemsGenerateResponse(
        items=persisted,
        requested_mode="qwen_seed_good",
        used_mode="qwen_seed_good",
        learned_generated_items=examples_count,
        narrow_llm_generated_items=0,
        template_generated_items=max(0, len(seed_items) - examples_count),
        model_version="qwen-seed-good-v0.1",
        warnings=warnings,
        profiling=profiling,
    )


def _create_auto_good_examples(*, db: Session, fund: models.AssessmentFund, user: models.User, items: list[AssessmentItemRead]) -> int:
    created = 0
    for item in items:
        if item.fund_id != fund.id:
            continue
        entity = models.TrainingExample(
            id=str(uuid4()),
            fund_id=fund.id,
            item_id=item.id,
            created_by_user_id=user.id,
            discipline_name=fund.discipline_name,
            topic=item.topic,
            competency_code=item.competency_code,
            indicator=item.indicator,
            assessment_type=item.assessment_type,
            item_type=item.item_type,
            difficulty=item.difficulty,
            text=item.text,
            answer=item.answer,
            criteria_json=json.dumps(item.criteria, ensure_ascii=False),
            quality_label="good",
            teacher_comment="Автоматически подтверждено режимом Qwen-only для наполнения обучающей выборки.",
            source="qwen_seed_good",
        )
        db.add(entity)
        created += 1
    db.commit()
    return created


def _selected_sections(sections_json: str, section_code: str | None) -> list[AssessmentFundSection]:
    result = []
    for raw in json.loads(sections_json or "[]"):
        section = AssessmentFundSection(**raw)
        if section_code and section.code != section_code:
            continue
        if not section.enabled or section.assessment_type in {"competency_matrix", "grading_rubric"}:
            continue
        result.append(section)
    return result


def _competencies(fund: models.AssessmentFund) -> list[AssessmentCompetencyRead]:
    return [
        AssessmentCompetencyRead(
            id=item.id,
            code=item.code,
            description=item.description,
            indicators=json.loads(item.indicators_json or "[]"),
            levels=json.loads(item.levels_json or "[]"),
        )
        for item in fund.competencies
    ]


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
