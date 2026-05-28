import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.schemas import (
    ControlWorkVariant,
    GenerationResponse,
    ProgramAnalysis,
    QualityReport,
)


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _load(value: str):
    return json.loads(value or "[]")


def save_program(
    db: Session,
    program: ProgramAnalysis,
    file_path: str,
    owner_user_id: str | None = None,
) -> models.Program:
    entity = models.Program(
        id=program.program_id,
        filename=program.filename,
        file_path=file_path,
        text_preview=program.text_preview,
        topics_json=_dump(program.topics),
        competencies_json=_dump(program.competencies),
        learning_outcomes_json=_dump(program.learning_outcomes),
        owner_user_id=owner_user_id,
    )
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return entity


def program_to_schema(program: models.Program) -> ProgramAnalysis:
    return ProgramAnalysis(
        program_id=program.id,
        filename=program.filename,
        text_preview=program.text_preview,
        topics=_load(program.topics_json),
        competencies=_load(program.competencies_json),
        learning_outcomes=_load(program.learning_outcomes_json),
    )


def user_can_access_program(user: models.User, program: models.Program | None) -> bool:
    if program is None:
        return False
    if user.role in {"admin", "methodist"}:
        return True
    return program.owner_user_id in {None, user.id}


def get_program(db: Session, program_id: str) -> ProgramAnalysis | None:
    entity = db.get(models.Program, program_id)
    return program_to_schema(entity) if entity else None


def get_program_for_user(db: Session, program_id: str, user: models.User) -> ProgramAnalysis | None:
    entity = db.get(models.Program, program_id)
    if not user_can_access_program(user, entity):
        return None
    return program_to_schema(entity)


def get_program_entity_for_user(db: Session, program_id: str, user: models.User) -> models.Program | None:
    entity = db.get(models.Program, program_id)
    if not user_can_access_program(user, entity):
        return None
    return entity


def list_programs(db: Session) -> list[ProgramAnalysis]:
    entities = db.scalars(select(models.Program).order_by(models.Program.created_at.desc())).all()
    return [program_to_schema(entity) for entity in entities]


def list_programs_for_user(db: Session, user: models.User) -> list[ProgramAnalysis]:
    query = select(models.Program).order_by(models.Program.created_at.desc())
    if user.role not in {"admin", "methodist"}:
        query = query.where((models.Program.owner_user_id == user.id) | (models.Program.owner_user_id.is_(None)))
    entities = db.scalars(query).all()
    return [program_to_schema(entity) for entity in entities]


def save_generation(db: Session, generation: GenerationResponse) -> models.GenerationSession:
    entity = models.GenerationSession(
        id=generation.session_id,
        program_id=generation.program_id,
        variants_json=_dump([variant.model_dump() for variant in generation.variants]),
        recommendations_json=_dump(generation.quality_report.recommendations),
        topic_coverage=generation.quality_report.topic_coverage,
        duplicate_rate=generation.quality_report.duplicate_rate,
        total_questions=generation.quality_report.total_questions,
    )
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return entity


def generation_to_schema(entity: models.GenerationSession) -> GenerationResponse:
    variants = [ControlWorkVariant(**item) for item in _load(entity.variants_json)]
    report = QualityReport(
        topic_coverage=entity.topic_coverage,
        duplicate_rate=entity.duplicate_rate,
        total_questions=entity.total_questions,
        recommendations=_load(entity.recommendations_json),
    )
    return GenerationResponse(
        session_id=entity.id,
        program_id=entity.program_id,
        variants=variants,
        quality_report=report,
    )


def get_generation(db: Session, session_id: str) -> GenerationResponse | None:
    entity = db.get(models.GenerationSession, session_id)
    return generation_to_schema(entity) if entity else None


def get_generation_for_user(db: Session, session_id: str, user: models.User) -> GenerationResponse | None:
    entity = db.get(models.GenerationSession, session_id)
    if entity is None:
        return None
    program = db.get(models.Program, entity.program_id)
    if not user_can_access_program(user, program):
        return None
    return generation_to_schema(entity)


def list_generations(db: Session) -> list[GenerationResponse]:
    entities = db.scalars(select(models.GenerationSession).order_by(models.GenerationSession.created_at.desc())).all()
    return [generation_to_schema(entity) for entity in entities]


def list_generations_for_user(db: Session, user: models.User) -> list[GenerationResponse]:
    query = (
        select(models.GenerationSession)
        .join(models.Program, models.GenerationSession.program_id == models.Program.id)
        .order_by(models.GenerationSession.created_at.desc())
    )
    if user.role not in {"admin", "methodist"}:
        query = query.where((models.Program.owner_user_id == user.id) | (models.Program.owner_user_id.is_(None)))
    entities = db.scalars(query).all()
    return [generation_to_schema(entity) for entity in entities]


def update_generation_variants(
    db: Session,
    session_id: str,
    variants: list[ControlWorkVariant],
    report: QualityReport,
) -> GenerationResponse | None:
    entity = db.get(models.GenerationSession, session_id)
    if entity is None:
        return None

    entity.variants_json = _dump([variant.model_dump() for variant in variants])
    entity.recommendations_json = _dump(report.recommendations)
    entity.topic_coverage = report.topic_coverage
    entity.duplicate_rate = report.duplicate_rate
    entity.total_questions = report.total_questions
    db.commit()
    db.refresh(entity)
    return generation_to_schema(entity)
