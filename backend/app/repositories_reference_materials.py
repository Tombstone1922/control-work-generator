import json
from difflib import SequenceMatcher
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.reference_materials_schemas import (
    OmAssessmentItemRead,
    ReferenceDocumentRead,
    ReferenceLibraryStats,
    RpOmPairRead,
)
from app.repositories import user_can_access_program
from app.schemas import TrainingExampleRead
from app.services.reference_material_parser import ParsedReferenceDocument, score_rp_om_pair

PAIR_THRESHOLD = 0.42


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _load_dict(value: str) -> dict:
    loaded = json.loads(value or "{}")
    return loaded if isinstance(loaded, dict) else {}


def _load_list(value: str) -> list:
    loaded = json.loads(value or "[]")
    return loaded if isinstance(loaded, list) else []


def document_to_schema(entity: models.ReferenceDocument) -> ReferenceDocumentRead:
    parsed = _load_dict(entity.parsed_json)
    return ReferenceDocumentRead(
        id=entity.id,
        document_type=entity.document_type,
        discipline_name=entity.discipline_name,
        filename=entity.filename,
        text_hash=entity.text_hash,
        parsed_summary=parsed.get("summary", parsed),
        created_at=entity.created_at.isoformat(),
    )


def pair_to_schema(entity: models.RpOmPair) -> RpOmPairRead:
    return RpOmPairRead(
        id=entity.id,
        rp_document_id=entity.rp_document_id,
        om_document_id=entity.om_document_id,
        discipline_name=entity.discipline_name,
        pairing_confidence=entity.pairing_confidence,
        created_at=entity.created_at.isoformat(),
    )


def om_item_to_schema(entity: models.OmAssessmentItem) -> OmAssessmentItemRead:
    return OmAssessmentItemRead(
        id=entity.id,
        pair_id=entity.pair_id,
        om_document_id=entity.om_document_id,
        topic=entity.topic,
        competency_code=entity.competency_code,
        indicator=entity.indicator,
        assessment_type=entity.assessment_type,
        item_type=entity.item_type,
        difficulty=entity.difficulty,
        text=entity.text,
        answer=entity.answer,
        criteria=_load_list(entity.criteria_json),
        source_section=entity.source_section,
        sample_weight=entity.sample_weight,
    )


def save_reference_document(
    db: Session,
    user: models.User,
    *,
    document_type: str,
    filename: str,
    file_path: str | Path,
    parsed: ParsedReferenceDocument,
) -> tuple[ReferenceDocumentRead, int, int]:
    if document_type not in {"rp", "om"}:
        raise ValueError("Тип документа должен быть rp или om.")

    existing = db.scalar(
        select(models.ReferenceDocument).where(
            models.ReferenceDocument.owner_user_id == user.id,
            models.ReferenceDocument.text_hash == parsed.text_hash,
            models.ReferenceDocument.document_type == document_type,
        )
    )
    if existing is not None:
        paired = _auto_pair_document(db, existing)
        db.commit()
        return document_to_schema(existing), len(existing.om_items) if document_type == "om" else 0, paired

    entity = models.ReferenceDocument(
        id=str(uuid4()),
        owner_user_id=user.id,
        document_type=document_type,
        discipline_name=parsed.discipline_name,
        filename=filename,
        file_path=str(file_path),
        text_hash=parsed.text_hash,
        parsed_json=_dump({"summary": parsed.summary, "warnings": parsed.warnings}),
    )
    db.add(entity)
    db.flush()

    items_count = 0
    if document_type == "om":
        for raw_item in parsed.om_items:
            db.add(
                models.OmAssessmentItem(
                    id=str(uuid4()),
                    om_document_id=entity.id,
                    topic=raw_item.get("topic", ""),
                    competency_code=raw_item.get("competency_code", ""),
                    indicator=raw_item.get("indicator", ""),
                    assessment_type=raw_item.get("assessment_type", "oral"),
                    item_type=raw_item.get("item_type", "open"),
                    difficulty=raw_item.get("difficulty", "medium"),
                    text=raw_item.get("text", ""),
                    answer=raw_item.get("answer", ""),
                    criteria_json=_dump(raw_item.get("criteria", [])),
                    source_section=raw_item.get("source_section", ""),
                    sample_weight=float(raw_item.get("sample_weight", 1.0)),
                )
            )
            items_count += 1

    db.flush()
    paired_count = _auto_pair_document(db, entity)
    db.commit()
    db.refresh(entity)
    return document_to_schema(entity), items_count, paired_count


def list_reference_documents(db: Session, user: models.User, document_type: str | None = None) -> list[ReferenceDocumentRead]:
    query = select(models.ReferenceDocument).where(models.ReferenceDocument.owner_user_id == user.id)
    if document_type:
        query = query.where(models.ReferenceDocument.document_type == document_type)
    query = query.order_by(models.ReferenceDocument.created_at.desc())
    return [document_to_schema(entity) for entity in db.scalars(query).all()]


def list_pairs(db: Session, user: models.User) -> list[RpOmPairRead]:
    document_ids = select(models.ReferenceDocument.id).where(models.ReferenceDocument.owner_user_id == user.id)
    query = (
        select(models.RpOmPair)
        .where(models.RpOmPair.rp_document_id.in_(document_ids))
        .order_by(models.RpOmPair.pairing_confidence.desc(), models.RpOmPair.created_at.desc())
    )
    return [pair_to_schema(entity) for entity in db.scalars(query).all()]


def list_om_items(db: Session, user: models.User, om_document_id: str | None = None, pair_id: str | None = None) -> list[OmAssessmentItemRead]:
    document_ids = select(models.ReferenceDocument.id).where(models.ReferenceDocument.owner_user_id == user.id)
    query = select(models.OmAssessmentItem).where(models.OmAssessmentItem.om_document_id.in_(document_ids))
    if om_document_id:
        query = query.where(models.OmAssessmentItem.om_document_id == om_document_id)
    if pair_id:
        query = query.where(models.OmAssessmentItem.pair_id == pair_id)
    query = query.order_by(models.OmAssessmentItem.created_at.desc())
    return [om_item_to_schema(entity) for entity in db.scalars(query).all()]


def get_reference_stats(db: Session, user: models.User) -> ReferenceLibraryStats:
    document_query = select(models.ReferenceDocument).where(models.ReferenceDocument.owner_user_id == user.id)
    docs = db.scalars(document_query).all()
    doc_ids = [doc.id for doc in docs]
    pair_query = select(models.RpOmPair).where(models.RpOmPair.rp_document_id.in_(doc_ids)) if doc_ids else select(models.RpOmPair).where(False)
    pairs = db.scalars(pair_query).all()
    om_items = 0
    if doc_ids:
        om_items = db.scalar(select(func.count(models.OmAssessmentItem.id)).where(models.OmAssessmentItem.om_document_id.in_(doc_ids))) or 0
    avg_conf = round(sum(pair.pairing_confidence for pair in pairs) / len(pairs), 3) if pairs else 0.0
    return ReferenceLibraryStats(
        rp_documents=sum(1 for doc in docs if doc.document_type == "rp"),
        om_documents=sum(1 for doc in docs if doc.document_type == "om"),
        rp_om_pairs=len(pairs),
        om_items=om_items,
        average_pairing_confidence=avg_conf,
    )


def list_om_generation_examples_for_fund(db: Session, user: models.User, fund: models.AssessmentFund) -> list:
    if not user_can_access_program(user, fund.program):
        return []
    target_name = (fund.discipline_name or "").lower()
    docs = db.scalars(
        select(models.ReferenceDocument).where(
            models.ReferenceDocument.owner_user_id == user.id,
            models.ReferenceDocument.document_type == "om",
        )
    ).all()
    if not docs:
        return []

    result = []
    for doc in docs:
        similarity = _discipline_similarity(target_name, doc.discipline_name.lower())
        if similarity < 0.35:
            continue
        source = "om_direct" if similarity >= 0.86 else "om_related"
        doc_weight = 1.45 if source == "om_direct" else 0.75 + 0.35 * similarity
        for item in doc.om_items:
            result.append(
                SimpleNamespace(
                    id=f"om:{item.id}",
                    fund_id=fund.id,
                    item_id=None,
                    discipline_name=doc.discipline_name,
                    topic=item.topic,
                    competency_code=item.competency_code,
                    indicator=item.indicator,
                    assessment_type=item.assessment_type,
                    item_type=item.item_type,
                    difficulty=item.difficulty,
                    text=item.text,
                    answer=item.answer,
                    criteria=_load_list(item.criteria_json),
                    quality_label="good",
                    teacher_comment=f"OM reference, discipline similarity={round(similarity, 3)}",
                    source=source,
                    sample_weight=round(item.sample_weight * doc_weight, 3),
                    created_at=item.created_at.isoformat(),
                )
            )
    return result


def training_example_to_weighted(example: TrainingExampleRead):
    source_weight = 1.2 if example.quality_label == "good" else 0.4
    return SimpleNamespace(**example.model_dump(), sample_weight=source_weight)


def _auto_pair_document(db: Session, document: models.ReferenceDocument) -> int:
    opposite_type = "om" if document.document_type == "rp" else "rp"
    candidates = db.scalars(
        select(models.ReferenceDocument).where(
            models.ReferenceDocument.owner_user_id == document.owner_user_id,
            models.ReferenceDocument.document_type == opposite_type,
        )
    ).all()
    created = 0
    current_summary = (_load_dict(document.parsed_json).get("summary") or {}) | {"discipline_name": document.discipline_name}
    for candidate in candidates:
        candidate_summary = (_load_dict(candidate.parsed_json).get("summary") or {}) | {"discipline_name": candidate.discipline_name}
        confidence = score_rp_om_pair(current_summary, candidate_summary)
        if confidence < PAIR_THRESHOLD:
            continue
        rp_id = document.id if document.document_type == "rp" else candidate.id
        om_id = candidate.id if document.document_type == "rp" else document.id
        exists = db.scalar(
            select(models.RpOmPair).where(
                models.RpOmPair.rp_document_id == rp_id,
                models.RpOmPair.om_document_id == om_id,
            )
        )
        if exists:
            continue
        pair = models.RpOmPair(
            id=str(uuid4()),
            rp_document_id=rp_id,
            om_document_id=om_id,
            discipline_name=document.discipline_name or candidate.discipline_name,
            pairing_confidence=confidence,
        )
        db.add(pair)
        db.flush()
        db.execute(
            models.OmAssessmentItem.__table__.update()
            .where(models.OmAssessmentItem.om_document_id == om_id)
            .values(pair_id=pair.id)
        )
        created += 1
    return created


def _discipline_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()
