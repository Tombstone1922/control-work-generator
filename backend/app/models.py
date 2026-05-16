from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Program(Base):
    __tablename__ = "programs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    text_preview: Mapped[str] = mapped_column(Text, nullable=False, default="")
    topics_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    competencies_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    learning_outcomes_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    program: Mapped[Program] = relationship(back_populates="generations")
