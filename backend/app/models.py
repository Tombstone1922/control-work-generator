from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(500), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="teacher")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    programs: Mapped[list["Program"]] = relationship(back_populates="owner")


class Program(Base):
    __tablename__ = "programs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    text_preview: Mapped[str] = mapped_column(Text, nullable=False, default="")
    topics_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    competencies_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    learning_outcomes_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    analysis_report_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    owner: Mapped[User | None] = relationship(back_populates="programs")
    generations: Mapped[list["GenerationSession"]] = relationship(
        back_populates="program",
        cascade="all, delete-orphan",
    )
    assessment_funds: Mapped[list["AssessmentFund"]] = relationship(
        back_populates="program",
        cascade="all, delete-orphan",
    )


class GenerationSession(Base):
    __tablename__ = "generation_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    program_id: Mapped[str] = mapped_column(ForeignKey("programs.id"), nullable=False)
    variants_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    recommendations_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    topic_coverage: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    duplicate_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="generated")
    review_comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reviewed_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    program: Mapped[Program] = relationship(back_populates="generations")


class AssessmentFund(Base):
    __tablename__ = "assessment_funds"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    program_id: Mapped[str] = mapped_column(ForeignKey("programs.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    discipline_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    assessment_types_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    sections_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    validation_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    program: Mapped[Program] = relationship(back_populates="assessment_funds")
    competencies: Mapped[list["AssessmentCompetency"]] = relationship(
        back_populates="fund",
        cascade="all, delete-orphan",
    )
    items: Mapped[list["AssessmentItem"]] = relationship(
        back_populates="fund",
        cascade="all, delete-orphan",
    )
    training_examples: Mapped[list["TrainingExample"]] = relationship(
        back_populates="fund",
        cascade="all, delete-orphan",
    )


class AssessmentCompetency(Base):
    __tablename__ = "assessment_competencies"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    fund_id: Mapped[str] = mapped_column(ForeignKey("assessment_funds.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    indicators_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    levels_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    fund: Mapped[AssessmentFund] = relationship(back_populates="competencies")


class AssessmentItem(Base):
    __tablename__ = "assessment_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    fund_id: Mapped[str] = mapped_column(ForeignKey("assessment_funds.id"), nullable=False, index=True)
    section_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    assessment_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    item_type: Mapped[str] = mapped_column(String(64), nullable=False, default="open")
    topic: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    competency_code: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    indicator: Mapped[str] = mapped_column(Text, nullable=False, default="")
    difficulty: Mapped[str] = mapped_column(String(32), nullable=False, default="medium")
    text: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    criteria_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    source_context: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_kind: Mapped[str] = mapped_column(String(64), nullable=False, default="template")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    fund: Mapped[AssessmentFund] = relationship(back_populates="items")


class TrainingExample(Base):
    __tablename__ = "training_examples"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    fund_id: Mapped[str] = mapped_column(ForeignKey("assessment_funds.id"), nullable=False, index=True)
    item_id: Mapped[str | None] = mapped_column(ForeignKey("assessment_items.id"), nullable=True, index=True)
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    discipline_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    topic: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    competency_code: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    indicator: Mapped[str] = mapped_column(Text, nullable=False, default="")
    assessment_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    item_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    difficulty: Mapped[str] = mapped_column(String(32), nullable=False, default="medium")
    text: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    criteria_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    quality_label: Mapped[str] = mapped_column(String(32), nullable=False, default="good")
    teacher_comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="expert_feedback")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    fund: Mapped[AssessmentFund] = relationship(back_populates="training_examples")


class ReferenceDocument(Base):
    __tablename__ = "reference_documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    document_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    discipline_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    parsed_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    om_items: Mapped[list["OmAssessmentItem"]] = relationship(
        back_populates="om_document",
        cascade="all, delete-orphan",
    )


class RpOmPair(Base):
    __tablename__ = "rp_om_pairs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    rp_document_id: Mapped[str] = mapped_column(ForeignKey("reference_documents.id"), nullable=False, index=True)
    om_document_id: Mapped[str] = mapped_column(ForeignKey("reference_documents.id"), nullable=False, index=True)
    discipline_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    pairing_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class OmAssessmentItem(Base):
    __tablename__ = "om_assessment_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pair_id: Mapped[str | None] = mapped_column(ForeignKey("rp_om_pairs.id"), nullable=True, index=True)
    om_document_id: Mapped[str] = mapped_column(ForeignKey("reference_documents.id"), nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    competency_code: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    indicator: Mapped[str] = mapped_column(Text, nullable=False, default="")
    assessment_type: Mapped[str] = mapped_column(String(64), nullable=False, default="oral")
    item_type: Mapped[str] = mapped_column(String(64), nullable=False, default="open")
    difficulty: Mapped[str] = mapped_column(String(32), nullable=False, default="medium")
    text: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    criteria_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    source_section: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sample_weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    om_document: Mapped[ReferenceDocument] = relationship(back_populates="om_items")
