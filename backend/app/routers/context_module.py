import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.repositories_assessment_items import get_fund_entity_for_user
from app.security import get_current_user
from app.services.assessment_item_smart_builder import normalize_topic
from app.services.discipline_knowledge_base import get_topic_knowledge_context

router = APIRouter(prefix="/api/context-module", tags=["context-module"])


@router.get("/{fund_id}/topic")
def get_topic_context(
    fund_id: str,
    topic: str = Query(default=""),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> dict:
    fund = get_fund_entity_for_user(db, fund_id, current_user)
    if fund is None:
        raise HTTPException(status_code=404, detail="ФОС не найден или нет доступа.")

    topics = json.loads(fund.program.topics_json or "[]")
    normalized_topic = normalize_topic(topic or (topics[0] if topics else ""))
    context = get_topic_knowledge_context(
        discipline_name=fund.discipline_name,
        topic=normalized_topic,
        all_topics=topics,
    )
    return {
        "discipline_name": context.discipline_name,
        "topic": context.topic,
        "profile_name": context.profile_name,
        "related_topics": context.related_topics,
        "learning_outcomes": context.learning_outcomes,
        "competencies": context.competencies,
        "key_terms": context.key_terms,
        "source": context.source,
        "runtime_topics_total": len(topics),
    }


@router.get("/{fund_id}/summary")
def get_context_summary(
    fund_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> dict:
    fund = get_fund_entity_for_user(db, fund_id, current_user)
    if fund is None:
        raise HTTPException(status_code=404, detail="ФОС не найден или нет доступа.")

    topics = json.loads(fund.program.topics_json or "[]")
    normalized_topics = [normalize_topic(value) for value in topics if str(value).strip()]
    sample_contexts = [
        get_topic_knowledge_context(
            discipline_name=fund.discipline_name,
            topic=topic,
            all_topics=topics,
        )
        for topic in normalized_topics[:5]
    ]
    sources = sorted({context.source for context in sample_contexts})
    key_terms = []
    for context in sample_contexts:
        for term in context.key_terms:
            if term not in key_terms:
                key_terms.append(term)
    return {
        "discipline_name": fund.discipline_name,
        "topics_total": len(normalized_topics),
        "sources": sources,
        "sample_topics": normalized_topics[:8],
        "key_terms": key_terms[:12],
    }
