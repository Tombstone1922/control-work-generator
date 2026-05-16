from pydantic import BaseModel, Field
from typing import List, Optional


class ProgramAnalysis(BaseModel):
    program_id: str
    filename: str
    text_preview: str
    topics: List[str]
    competencies: List[str]
    learning_outcomes: List[str]


class GenerationRequest(BaseModel):
    program_id: str
    variants_count: int = Field(default=2, ge=1, le=20)
    questions_per_variant: int = Field(default=5, ge=1, le=50)
    difficulty: str = Field(default="medium", description="easy | medium | hard")
    question_types: List[str] = Field(default_factory=lambda: ["open"])


class Question(BaseModel):
    id: str
    topic: str
    text: str
    type: str
    difficulty: str


class ControlWorkVariant(BaseModel):
    variant_number: int
    questions: List[Question]


class QualityReport(BaseModel):
    topic_coverage: float
    duplicate_rate: float
    total_questions: int
    recommendations: List[str]


class GenerationResponse(BaseModel):
    session_id: str
    program_id: str
    variants: List[ControlWorkVariant]
    quality_report: QualityReport


class GenerationUpdateRequest(BaseModel):
    variants: List[ControlWorkVariant]


class ErrorResponse(BaseModel):
    detail: str
