import json
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app import models
from app.repositories import user_can_access_program
from app.schemas import TrainingDatasetStats, TrainingExampleCreateRequest, TrainingExampleRead

TRAINING_DIR = Path(__file__).resolve().parent / "storage" / "training"
TRAINING_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_LABELS = {"good", "bad", "needs_revision"}
AUTO_GOOD_SOURCE = "auto_good_after_generation"


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _load_list(value: str) -> list:
    loaded = json.loads(value or "[]")
    return loaded if isinstance(loaded, list) else []


def training_example_to_schema(entity: models.TrainingExample) -> TrainingExampleRead:
    return TrainingExampleRead(
        id=entity.id,
        fund_id=entity.fund_id,
        item_id=entity.item_id,
        discipline_name=entity.discipline_name,
        topic=entity.topic,
        competency_code=entity.competency_code,
        indicator=entity.indicator,
        assessment_type=entity.assessment_type,
        item_type=entity.item_type,
        difficulty=entity.difficulty,
        text=entity.text,
        answer=entity.answer,
        criteria=_load_list(entity.criteria_json),
        quality_label=entity.quality_label,
        teacher_comment=entity.teacher_comment,
        source=entity.source,
        created_at=entity.created_at.isoformat(),
    )


def create_training_example_from_item(
    db: Session,
    fund_id: str,
    item_id: str,
    user: models.User,
    payload: TrainingExampleCreateRequest,
) -> TrainingExampleRead | None:
    label = payload.quality_label.strip()
    if label not in ALLOWED_LABELS:
        raise ValueError("Недопустимая метка качества. Используйте good, bad или needs_revision.")

    fund = _get_fund_for_user(db, fund_id, user)
    if fund is None:
        return None
    item = db.get(models.AssessmentItem, item_id)
    if item is None or item.fund_id != fund.id:
        return None

    entity = _build_training_entity_from_item(
        item=item,
        fund=fund,
        user=user,
        quality_label=label,
        teacher_comment=payload.teacher_comment.strip(),
        source="expert_feedback",
    )
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return training_example_to_schema(entity)


def sync_fund_items_as_good_examples(db: Session, fund_id: str, user: models.User) -> TrainingDatasetStats | None:
    fund = _get_fund_for_user(db, fund_id, user)
    if fund is None:
        return None

    db.execute(delete(models.TrainingExample).where(models.TrainingExample.fund_id == fund.id))
    items = db.scalars(
        select(models.AssessmentItem)
        .where(models.AssessmentItem.fund_id == fund.id)
        .order_by(models.AssessmentItem.created_at.asc())
    ).all()

    for item in items:
        item.status = "approved"
        db.add(_build_training_entity_from_item(
            item=item,
            fund=fund,
            user=user,
            quality_label="good",
            teacher_comment="Автоматически помечено как хороший пример после генерации банка ФОС.",
            source=AUTO_GOOD_SOURCE,
        ))
    db.commit()
    return get_training_dataset_stats(db, user, fund_id=fund.id)


def _build_training_entity_from_item(
    item: models.AssessmentItem,
    fund: models.AssessmentFund,
    user: models.User,
    quality_label: str,
    teacher_comment: str,
    source: str,
) -> models.TrainingExample:
    return models.TrainingExample(
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
        criteria_json=item.criteria_json,
        quality_label=quality_label,
        teacher_comment=teacher_comment,
        source=source,
    )


def list_training_examples_for_user(
    db: Session,
    user: models.User,
    fund_id: str | None = None,
    quality_label: str | None = None,
) -> list[TrainingExampleRead]:
    query = (
        select(models.TrainingExample)
        .join(models.AssessmentFund, models.TrainingExample.fund_id == models.AssessmentFund.id)
        .join(models.Program, models.AssessmentFund.program_id == models.Program.id)
        .options(selectinload(models.TrainingExample.fund))
        .order_by(models.TrainingExample.created_at.desc())
    )
    if user.role not in {"admin", "methodist"}:
        query = query.where((models.Program.owner_user_id == user.id) | (models.Program.owner_user_id.is_(None)))
    if fund_id:
        query = query.where(models.TrainingExample.fund_id == fund_id)
    if quality_label:
        query = query.where(models.TrainingExample.quality_label == quality_label)
    return [training_example_to_schema(entity) for entity in db.scalars(query).all()]


def get_training_dataset_stats(db: Session, user: models.User, fund_id: str | None = None) -> TrainingDatasetStats:
    examples = list_training_examples_for_user(db, user, fund_id=fund_id)
    topics = {item.topic for item in examples if item.topic}
    competencies = {item.competency_code for item in examples if item.competency_code}
    assessment_types = {item.assessment_type for item in examples if item.assessment_type}
    return TrainingDatasetStats(
        total_examples=len(examples),
        good_examples=sum(1 for item in examples if item.quality_label == "good"),
        bad_examples=sum(1 for item in examples if item.quality_label == "bad"),
        revision_examples=sum(1 for item in examples if item.quality_label == "needs_revision"),
        topics_count=len(topics),
        competencies_count=len(competencies),
        assessment_types_count=len(assessment_types),
    )


def export_training_dataset_jsonl(db: Session, user: models.User, fund_id: str | None = None) -> Path:
    examples = list_training_examples_for_user(db, user, fund_id=fund_id)
    suffix = fund_id[:8] if fund_id else "all"
    output_path = TRAINING_DIR / f"training_dataset_{suffix}.jsonl"
    with output_path.open("w", encoding="utf-8") as file:
        for item in examples:
            record = {
                "instruction": _build_instruction(item),
                "input": {
                    "discipline_name": item.discipline_name,
                    "topic": item.topic,
                    "competency_code": item.competency_code,
                    "indicator": item.indicator,
                    "assessment_type": item.assessment_type,
                    "item_type": item.item_type,
                    "difficulty": item.difficulty,
                },
                "output": {
                    "text": item.text,
                    "answer": item.answer,
                    "criteria": item.criteria,
                },
                "quality_label": item.quality_label,
                "teacher_comment": item.teacher_comment,
                "source": item.source,
            }
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
    return output_path


def delete_training_example_for_user(db: Session, example_id: str, user: models.User) -> bool:
    entity = db.scalar(
        select(models.TrainingExample)
        .where(models.TrainingExample.id == example_id)
        .options(selectinload(models.TrainingExample.fund).selectinload(models.AssessmentFund.program))
    )
    if entity is None or not user_can_access_program(user, entity.fund.program):
        return False
    db.delete(entity)
    db.commit()
    return True


def _get_fund_for_user(db: Session, fund_id: str, user: models.User) -> models.AssessmentFund | None:
    fund = db.scalar(
        select(models.AssessmentFund)
        .where(models.AssessmentFund.id == fund_id)
        .options(selectinload(models.AssessmentFund.program))
    )
    if fund is None or not user_can_access_program(user, fund.program):
        return None
    return fund


def _build_instruction(item: TrainingExampleRead) -> str:
    return (
        "Сформируй оценочное задание для фонда оценочных средств по дисциплине. "
        "Верни формулировку задания, эталонный ответ и критерии оценивания."
    )
