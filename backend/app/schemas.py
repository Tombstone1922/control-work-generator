from pydantic import BaseModel, EmailStr, Field
from typing import List


class UserCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    role: str = Field(default="teacher", description="teacher | methodist | admin")


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserRead(BaseModel):
    id: str
    full_name: str
    email: EmailStr
    role: str
    is_active: bool


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


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
