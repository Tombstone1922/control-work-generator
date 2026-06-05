import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models
from app.repositories import user_can_access_program
from app.schemas import (
    AssessmentCompetencyRead,
    AssessmentFundResponse,
    AssessmentFundSection,
    AssessmentFundValidation,
)
from app.services.assessment_fund_builder import AssessmentFundDraft, validate_assessment_fund


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _load_list(value: str) -> list:
    loaded = json.loads(value or "[]")
    return loaded if isinstance(loaded, list) else []


def _load_dict(value: str) -> dict:
    loaded = json.loads(value or "{}")
    return loaded if isinstance(loaded, dict) else {}


def create_assessment_fund(
    db: Session,
    program: models.Program,
    draft: AssessmentFundDraft,
) -> AssessmentFundResponse:
    entity = models.AssessmentFund(
        id=str(uuid4()),
        program_id=program.id,
        title=draft.title,
        discipline_name=draft.discipline_name,
        status="draft",
        assessment_types_json=_dump(draft.assessment_types),
        sections_json=_dump([section.model_dump() for section in draft.sections]),
        validation_json=_dump(draft.validation.model_dump()),
    )
    db.add(entity)
    db.flush()

    for competency in draft.competencies:
        db.add(
            models.AssessmentCompetency(
                id=competency.id,
                fund_id=entity.id,
                code=competency.code,
                description=competency.description,
                indicators_json=_dump(competency.indicators),
                levels_json=_dump(competency.levels),
            )
        )

    db.commit()
    return get_assessment_fund_for_user(db, entity.id, program.owner) if program.owner else fund_to_schema(_get_fund_entity(db, entity.id))


def fund_to_schema(entity: models.AssessmentFund) -> AssessmentFundResponse:
    competencies = [
        AssessmentCompetencyRead(
            id=item.id,
            code=item.code,
            description=item.description,
            indicators=_load_list(item.indicators_json),
            levels=_load_list(item.levels_json),
        )
        for item in entity.competencies
    ]
    return AssessmentFundResponse(
        fund_id=entity.id,
        program_id=entity.program_id,
        title=entity.title,
        discipline_name=entity.discipline_name,
        status=entity.status,
        assessment_types=_load_list(entity.assessment_types_json),
        sections=[AssessmentFundSection(**item) for item in _load_list(entity.sections_json)],
        competencies=competencies,
        validation=AssessmentFundValidation(**_load_dict(entity.validation_json)),
    )


def list_assessment_funds_for_user(db: Session, user: models.User) -> list[AssessmentFundResponse]:
    query = (
        select(models.AssessmentFund)
        .join(models.Program, models.AssessmentFund.program_id == models.Program.id)
        .options(selectinload(models.AssessmentFund.competencies))
        .order_by(models.AssessmentFund.updated_at.desc())
    )
    if user.role not in {"admin", "methodist"}:
        query = query.where((models.Program.owner_user_id == user.id) | (models.Program.owner_user_id.is_(None)))
    return [fund_to_schema(entity) for entity in db.scalars(query).all()]


def get_assessment_fund_for_user(db: Session, fund_id: str, user: models.User) -> AssessmentFundResponse | None:
    entity = _get_fund_entity(db, fund_id)
    if entity is None or not user_can_access_program(user, entity.program):
        return None
    return fund_to_schema(entity)


def update_assessment_fund_for_user(
    db: Session,
    fund_id: str,
    user: models.User,
    *,
    title: str | None = None,
    discipline_name: str | None = None,
    status: str | None = None,
    assessment_types: list[str] | None = None,
    sections: list[AssessmentFundSection] | None = None,
) -> AssessmentFundResponse | None:
    entity = _get_fund_entity(db, fund_id)
    if entity is None or not user_can_access_program(user, entity.program):
        return None

    if title is not None:
        entity.title = title.strip()
    if discipline_name is not None:
        entity.discipline_name = discipline_name.strip()
    if status is not None:
        entity.status = status
    if assessment_types is not None:
        entity.assessment_types_json = _dump(assessment_types)
    if sections is not None:
        entity.sections_json = _dump([section.model_dump() for section in sections])
        validation = validate_assessment_fund(
            sections,
            [
                AssessmentCompetencyRead(
                    id=item.id,
                    code=item.code,
                    description=item.description,
                    indicators=_load_list(item.indicators_json),
                    levels=_load_list(item.levels_json),
                )
                for item in entity.competencies
            ],
            entity.program and json.loads(entity.program.topics_json or "[]") or [],
        )
        entity.validation_json = _dump(validation.model_dump())

    db.commit()
    db.refresh(entity)
    return fund_to_schema(entity)


def revalidate_assessment_fund_for_user(db: Session, fund_id: str, user: models.User) -> AssessmentFundResponse | None:
    entity = _get_fund_entity(db, fund_id)
    if entity is None or not user_can_access_program(user, entity.program):
        return None

    sections = [AssessmentFundSection(**item) for item in _load_list(entity.sections_json)]
    competencies = [
        AssessmentCompetencyRead(
            id=item.id,
            code=item.code,
            description=item.description,
            indicators=_load_list(item.indicators_json),
            levels=_load_list(item.levels_json),
        )
        for item in entity.competencies
    ]
    topics = json.loads(entity.program.topics_json or "[]")
    entity.validation_json = _dump(validate_assessment_fund(sections, competencies, topics).model_dump())
    db.commit()
    db.refresh(entity)
    return fund_to_schema(entity)


def _get_fund_entity(db: Session, fund_id: str) -> models.AssessmentFund | None:
    return db.scalar(
        select(models.AssessmentFund)
        .where(models.AssessmentFund.id == fund_id)
        .options(
            selectinload(models.AssessmentFund.competencies),
            selectinload(models.AssessmentFund.program).selectinload(models.Program.owner),
        )
    )
