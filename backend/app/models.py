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
