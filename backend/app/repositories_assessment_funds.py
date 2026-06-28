import json
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models
from app.repositories import user_can_access_program
from app.schemas import (
    AssessmentCompetencyCreateRequest,
    AssessmentCompetencyRead,
    AssessmentCompetencyUpdateRequest,
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


def _dt(value) -> str:
    return value.isoformat() if value else ""


def _user_name(user: models.User | None) -> str:
    return user.full_name if user else ""


def _user_email(user: models.User | None) -> str:
    return user.email if user else ""


def create_assessment_fund(
    db: Session,
    program: models.Program,
    draft: AssessmentFundDraft,
) -> AssessmentFundResponse:
    validation_payload = draft.validation.model_dump()
    validation_payload["created_by_name"] = _user_name(program.owner)
    validation_payload["created_by_email"] = _user_email(program.owner)
    entity = models.AssessmentFund(
        id=str(uuid4()),
        program_id=program.id,
        title=draft.title,
        discipline_name=draft.discipline_name,
        status="draft",
        assessment_types_json=_dump(draft.assessment_types),
        sections_json=_dump([section.model_dump() for section in draft.sections]),
        validation_json=_dump(validation_payload),
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
    persisted = _get_fund_entity(db, entity.id)
    if persisted is None:
        raise RuntimeError("Не удалось прочитать созданный ФОС из базы данных.")
    return fund_to_schema(persisted)


def fund_to_schema(entity: models.AssessmentFund) -> AssessmentFundResponse:
    competencies = [competency_to_schema(item) for item in entity.competencies]
    validation_payload = _load_dict(entity.validation_json)
    owner = entity.program.owner if entity.program else None
    return AssessmentFundResponse(
        fund_id=entity.id,
        program_id=entity.program_id,
        program_filename=entity.program.filename if entity.program else "",
        title=entity.title,
        discipline_name=entity.discipline_name,
        status=entity.status,
        assessment_types=_load_list(entity.assessment_types_json),
        sections=[AssessmentFundSection(**item) for item in _load_list(entity.sections_json)],
        competencies=competencies,
        validation=AssessmentFundValidation(**validation_payload),
        created_at=_dt(entity.created_at),
        updated_at=_dt(entity.updated_at),
        created_by_name=validation_payload.get("created_by_name") or _user_name(owner),
        created_by_email=validation_payload.get("created_by_email") or _user_email(owner),
        reviewed_by_name=validation_payload.get("reviewed_by_name", ""),
        reviewed_by_email=validation_payload.get("reviewed_by_email", ""),
        reviewed_at=validation_payload.get("reviewed_at", ""),
    )


def competency_to_schema(entity: models.AssessmentCompetency) -> AssessmentCompetencyRead:
    return AssessmentCompetencyRead(
        id=entity.id,
        code=entity.code,
        description=entity.description,
        indicators=_load_list(entity.indicators_json),
        levels=_load_list(entity.levels_json),
    )


def list_assessment_funds_for_user(db: Session, user: models.User) -> list[AssessmentFundResponse]:
    query = (
        select(models.AssessmentFund)
        .join(models.Program, models.AssessmentFund.program_id == models.Program.id)
        .options(
            selectinload(models.AssessmentFund.competencies),
            selectinload(models.AssessmentFund.program).selectinload(models.Program.owner),
        )
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
    _recalculate_validation(entity)
    if status in {"approved", "revision_required"}:
        _set_review_metadata(entity, user)

    db.commit()
    db.refresh(entity)
    return fund_to_schema(entity)


def revalidate_assessment_fund_for_user(db: Session, fund_id: str, user: models.User) -> AssessmentFundResponse | None:
    entity = _get_fund_entity(db, fund_id)
    if entity is None or not user_can_access_program(user, entity.program):
        return None

    _recalculate_validation(entity)
    db.commit()
    db.refresh(entity)
    return fund_to_schema(entity)


def create_competency_for_user(
    db: Session,
    fund_id: str,
    user: models.User,
    payload: AssessmentCompetencyCreateRequest,
) -> AssessmentFundResponse | None:
    fund = _get_fund_entity(db, fund_id)
    if fund is None or not user_can_access_program(user, fund.program):
        return None

    code = payload.code.strip()
    if any(item.code.lower() == code.lower() for item in fund.competencies):
        raise ValueError("Компетенция с таким кодом уже существует.")

    db.add(
        models.AssessmentCompetency(
            id=str(uuid4()),
            fund_id=fund.id,
            code=code,
            description=payload.description.strip(),
            indicators_json=_dump([item.strip() for item in payload.indicators if item.strip()]),
            levels_json=_dump([item.strip() for item in payload.levels if item.strip()]),
        )
    )
    db.flush()
    _recalculate_validation(fund)
    db.commit()
    return fund_to_schema(_get_fund_entity(db, fund.id))


def update_competency_for_user(
    db: Session,
    fund_id: str,
    competency_id: str,
    user: models.User,
    payload: AssessmentCompetencyUpdateRequest,
) -> AssessmentFundResponse | None:
    fund = _get_fund_entity(db, fund_id)
    if fund is None or not user_can_access_program(user, fund.program):
        return None
    competency = db.get(models.AssessmentCompetency, competency_id)
    if competency is None or competency.fund_id != fund.id:
        return None

    if payload.code is not None:
        new_code = payload.code.strip()
        if any(item.id != competency.id and item.code.lower() == new_code.lower() for item in fund.competencies):
            raise ValueError("Компетенция с таким кодом уже существует.")
        old_code = competency.code
        competency.code = new_code
        for item in fund.items:
            if item.competency_code == old_code:
                item.competency_code = new_code
    if payload.description is not None:
        competency.description = payload.description.strip()
    if payload.indicators is not None:
        competency.indicators_json = _dump([item.strip() for item in payload.indicators if item.strip()])
    if payload.levels is not None:
        competency.levels_json = _dump([item.strip() for item in payload.levels if item.strip()])

    _recalculate_validation(fund)
    db.commit()
    return fund_to_schema(_get_fund_entity(db, fund.id))


def delete_competency_for_user(
    db: Session,
    fund_id: str,
    competency_id: str,
    user: models.User,
) -> AssessmentFundResponse | None:
    fund = _get_fund_entity(db, fund_id)
    if fund is None or not user_can_access_program(user, fund.program):
        return None
    competency = db.get(models.AssessmentCompetency, competency_id)
    if competency is None or competency.fund_id != fund.id:
        return None

    deleted_code = competency.code
    db.delete(competency)
    for item in fund.items:
        if item.competency_code == deleted_code:
            item.competency_code = ""
            item.indicator = ""
    db.flush()
    _recalculate_validation(fund)
    db.commit()
    return fund_to_schema(_get_fund_entity(db, fund.id))


def _preserved_validation_metadata(entity: models.AssessmentFund) -> dict:
    current = _load_dict(entity.validation_json)
    keys = (
        "created_by_name",
        "created_by_email",
        "reviewed_by_name",
        "reviewed_by_email",
        "reviewed_at",
    )
    return {key: current.get(key, "") for key in keys if current.get(key)}


def _recalculate_validation(entity: models.AssessmentFund) -> None:
    metadata = _preserved_validation_metadata(entity)
    if "created_by_name" not in metadata and entity.program and entity.program.owner:
        metadata["created_by_name"] = entity.program.owner.full_name
        metadata["created_by_email"] = entity.program.owner.email
    sections = [AssessmentFundSection(**item) for item in _load_list(entity.sections_json)]
    competencies = [competency_to_schema(item) for item in entity.competencies]
    topics = json.loads(entity.program.topics_json or "[]")
    validation = validate_assessment_fund(sections, competencies, topics).model_dump()
    validation.update(metadata)
    entity.validation_json = _dump(validation)


def _set_review_metadata(entity: models.AssessmentFund, user: models.User) -> None:
    payload = _load_dict(entity.validation_json)
    payload["reviewed_by_name"] = user.full_name
    payload["reviewed_by_email"] = user.email
    payload["reviewed_at"] = datetime.utcnow().isoformat()
    entity.validation_json = _dump(payload)


def _get_fund_entity(db: Session, fund_id: str) -> models.AssessmentFund | None:
    return db.scalar(
        select(models.AssessmentFund)
        .where(models.AssessmentFund.id == fund_id)
        .options(
            selectinload(models.AssessmentFund.competencies),
            selectinload(models.AssessmentFund.items),
            selectinload(models.AssessmentFund.program).selectinload(models.Program.owner),
        )
    )
