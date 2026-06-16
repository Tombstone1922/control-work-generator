from pydantic import BaseModel, EmailStr, Field
from typing import List


class UserCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserRead(BaseModel):
    id: str
    full_name: str
    email: EmailStr
    role: str
    is_active: bool


class UserRoleUpdate(BaseModel):
    role: str


class UserActiveUpdate(BaseModel):
    is_active: bool


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class RpdDiagnostics(BaseModel):
    source_lines: int = 0
    analyzed_lines: int = 0
    ignored_lines: int = 0
    topics_count: int = 0
    competencies_count: int = 0
    learning_outcomes_count: int = 0
    detected_sections_count: int = 0
    quality_score: int = 0
    extraction_strategy: str = "rules"
    warnings: List[str] = Field(default_factory=list)


class RpdAnalysisReport(BaseModel):
    detected_sections: List[str] = Field(default_factory=list)
    topic_sources: List[str] = Field(default_factory=list)
    competency_sources: List[str] = Field(default_factory=list)
    outcome_sources: List[str] = Field(default_factory=list)
    diagnostics: RpdDiagnostics = Field(default_factory=RpdDiagnostics)


class ProgramAnalysis(BaseModel):
    program_id: str
    filename: str
    text_preview: str
    topics: List[str]
    competencies: List[str]
    learning_outcomes: List[str]
    analysis_report: RpdAnalysisReport = Field(default_factory=RpdAnalysisReport)


class AssessmentFundSection(BaseModel):
    code: str
    title: str
    description: str
    assessment_type: str
    enabled: bool = True
    topics: List[str] = Field(default_factory=list)
    planned_items: int = 0
    generated_items: int = 0


class AssessmentCompetencyRead(BaseModel):
    id: str
    code: str
    description: str = ""
    indicators: List[str] = Field(default_factory=list)
    levels: List[str] = Field(default_factory=list)


class AssessmentCompetencyCreateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    description: str = ""
    indicators: List[str] = Field(default_factory=list)
    levels: List[str] = Field(default_factory=lambda: [
        "Продвинутый уровень",
        "Повышенный уровень",
        "Пороговый уровень",
    ])


class AssessmentCompetencyUpdateRequest(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = None
    indicators: List[str] | None = None
    levels: List[str] | None = None


class AssessmentFundValidation(BaseModel):
    completeness_score: int = 0
    topics_coverage_score: int = 0
    competencies_coverage_score: int = 0
    missing_sections: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class AssessmentFundCreateRequest(BaseModel):
    program_id: str
    discipline_name: str | None = None


class AssessmentFundUpdateRequest(BaseModel):
    title: str | None = None
    discipline_name: str | None = None
    status: str | None = None
    assessment_types: List[str] | None = None
    sections: List[AssessmentFundSection] | None = None


class AssessmentFundResponse(BaseModel):
    fund_id: str
    program_id: str
    title: str
    discipline_name: str
    status: str
    assessment_types: List[str]
    sections: List[AssessmentFundSection]
    competencies: List[AssessmentCompetencyRead]
    validation: AssessmentFundValidation


class AssessmentItemRead(BaseModel):
    id: str
    fund_id: str
    section_code: str
    assessment_type: str
    item_type: str
    topic: str
    competency_code: str = ""
    indicator: str = ""
    difficulty: str
    text: str
    answer: str = ""
    criteria: List[str] = Field(default_factory=list)
    source_context: str = ""
    source_kind: str = "template"
    status: str = "draft"


class AssessmentItemUpdateRequest(BaseModel):
    topic: str | None = None
    competency_code: str | None = None
    indicator: str | None = None
    difficulty: str | None = None
    text: str | None = None
    answer: str | None = None
    criteria: List[str] | None = None
    status: str | None = None


class AssessmentItemsGenerateRequest(BaseModel):
    section_code: str | None = None
    replace_existing: bool = False
    max_items_per_section: int = Field(default=40, ge=1, le=200)
    generation_mode: str = Field(default="template", description="template | hybrid | ollama")
    ollama_model: str | None = None
    ollama_max_items: int = Field(default=12, ge=1, le=50)
    fallback_to_template: bool = True


class AssessmentItemsGenerateResponse(BaseModel):
    items: List[AssessmentItemRead]
    requested_mode: str
    used_mode: str
    ollama_model: str = ""
    ollama_generated_items: int = 0
    template_generated_items: int = 0
    warnings: List[str] = Field(default_factory=list)


class LocalModelStatusResponse(BaseModel):
    available: bool
    base_url: str
    models: List[str] = Field(default_factory=list)
    default_model: str = ""
    error: str = ""


class TrainingExampleCreateRequest(BaseModel):
    quality_label: str = Field(default="good", description="good | bad | needs_revision")
    teacher_comment: str = ""


class TrainingExampleRead(BaseModel):
    id: str
    fund_id: str
    item_id: str | None = None
    discipline_name: str
    topic: str
    competency_code: str = ""
    indicator: str = ""
    assessment_type: str
    item_type: str
    difficulty: str
    text: str
    answer: str = ""
    criteria: List[str] = Field(default_factory=list)
    quality_label: str
    teacher_comment: str = ""
    source: str = "expert_feedback"
    created_at: str


class TrainingDatasetStats(BaseModel):
    total_examples: int = 0
    good_examples: int = 0
    bad_examples: int = 0
    revision_examples: int = 0
    topics_count: int = 0
    competencies_count: int = 0
    assessment_types_count: int = 0


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
    status: str = "generated"
    review_comment: str = ""
    reviewed_by_user_id: str | None = None


class GenerationUpdateRequest(BaseModel):
    variants: List[ControlWorkVariant]


class GenerationStatusUpdateRequest(BaseModel):
    status: str
    review_comment: str = ""


class ErrorResponse(BaseModel):
    detail: str
