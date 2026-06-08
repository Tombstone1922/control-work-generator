import json

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app import models
from app.repositories import user_can_access_program
from app.schemas import AssessmentFundSection, AssessmentItemRead, AssessmentItemUpdateRequest


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _load_list(value: str) -> list:
    loaded = json.loads(value or "[]")
    return loaded if isinstance(loaded, list) else []


def item_to_schema(entity: models.AssessmentItem) -> AssessmentItemRead:
    return AssessmentItemRead(
        id=entity.id,
        fund_id=entity.fund_id,
        section_code=entity.section_code,
        assessment_type=entity.assessment_type,
        item_type=entity.item_type,
        topic=entity.topic,
        competency_code=entity.competency_code,
        indicator=entity.indicator,
        difficulty=entity.difficulty,
        text=entity.text,
        answer=entity.answer,
        criteria=_load_list(entity.criteria_json),
        source_context=entity.source_context,
        source_kind=entity.source_kind,
        status=entity.status,
    )


def get_fund_entity_for_user(db: Session, fund_id: str, user: models.User) -> models.AssessmentFund | None:
    entity = db.scalar(
        select(models.AssessmentFund)
        .where(models.AssessmentFund.id == fund_id)
        .options(
            selectinload(models.AssessmentFund.program),
            selectinload(models.AssessmentFund.competencies),
        )
    )
    if entity is None or not user_can_access_program(user, entity.program):
        return None
    return entity


def list_items_for_user(
    db: Session,
    fund_id: str,
    user: models.User,
    section_code: str | None = None,
) -> list[AssessmentItemRead] | None:
    fund = get_fund_entity_for_user(db, fund_id, user)
    if fund is None:
        return None

    query = select(models.AssessmentItem).where(models.AssessmentItem.fund_id == fund_id)
    if section_code:
        query = query.where(models.AssessmentItem.section_code == section_code)
    query = query.order_by(models.AssessmentItem.section_code, models.AssessmentItem.created_at)
    return [item_to_schema(entity) for entity in db.scalars(query).all()]


def replace_items_for_sections(
    db: Session,
    fund: models.AssessmentFund,
    section_codes: list[str],
    items: list[AssessmentItemRead],
    replace_existing: bool,
) -> list[AssessmentItemRead]:
    if replace_existing and section_codes:
        db.execute(
            delete(models.AssessmentItem).where(
                models.AssessmentItem.fund_id == fund.id,
                models.AssessmentItem.section_code.in_(section_codes),
            )
        )

    for item in items:
        db.add(
            models.AssessmentItem(
                id=item.id,
                fund_id=fund.id,
                section_code=item.section_code,
                assessment_type=item.assessment_type,
                item_type=item.item_type,
                topic=item.topic,
                competency_code=item.competency_code,
                indicator=item.indicator,
                difficulty=item.difficulty,
                text=item.text,
                answer=item.answer,
                criteria_json=_dump(item.criteria),
                source_context=item.source_context,
                source_kind=item.source_kind,
                status=item.status,
            )
        )

    fund.status = "generated"
    db.flush()
    _refresh_section_item_counts(db, fund)
    db.commit()
    return list_items_for_user(db, fund.id, fund.program.owner or models.User(role="admin")) or []


def update_item_for_user(
    db: Session,
    fund_id: str,
    item_id: str,
    user: models.User,
    payload: AssessmentItemUpdateRequest,
) -> AssessmentItemRead | None:
    fund = get_fund_entity_for_user(db, fund_id, user)
    if fund is None:
        return None
    entity = db.get(models.AssessmentItem, item_id)
    if entity is None or entity.fund_id != fund_id:
        return None

    for field in ("topic", "competency_code", "indicator", "difficulty", "text", "answer", "status"):
        value = getattr(payload, field)
        if value is not None:
            setattr(entity, field, value.strip() if isinstance(value, str) else value)
    if payload.criteria is not None:
        entity.criteria_json = _dump(payload.criteria)

    db.commit()
    db.refresh(entity)
    return item_to_schema(entity)


def delete_item_for_user(db: Session, fund_id: str, item_id: str, user: models.User) -> bool:
    fund = get_fund_entity_for_user(db, fund_id, user)
    if fund is None:
        return False
    entity = db.get(models.AssessmentItem, item_id)
    if entity is None or entity.fund_id != fund_id:
        return False

    db.delete(entity)
    db.flush()
    _refresh_section_item_counts(db, fund)
    db.commit()
    return True


def _refresh_section_item_counts(db: Session, fund: models.AssessmentFund) -> None:
    rows = db.execute(
        select(models.AssessmentItem.section_code, func.count(models.AssessmentItem.id))
        .where(models.AssessmentItem.fund_id == fund.id)
        .group_by(models.AssessmentItem.section_code)
    ).all()
    counts = {section_code: count for section_code, count in rows}
    sections = [AssessmentFundSection(**item) for item in _load_list(fund.sections_json)]
    for section in sections:
        section.generated_items = counts.get(section.code, 0)
    fund.sections_json = _dump([section.model_dump() for section in sections])
