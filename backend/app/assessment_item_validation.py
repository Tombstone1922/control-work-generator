from pydantic import BaseModel, Field


class AssessmentCoverageRow(BaseModel):
    topic: str
    total_items: int = 0
    section_counts: dict[str, int] = Field(default_factory=dict)
    competencies: list[str] = Field(default_factory=list)


class AssessmentDuplicateGroup(BaseModel):
    item_ids: list[str] = Field(default_factory=list)
    sample_text: str = ""
    similarity: float = 1.0


class AssessmentItemsValidation(BaseModel):
    total_items: int = 0
    topics_total: int = 0
    topics_covered: int = 0
    competencies_total: int = 0
    competencies_covered: int = 0
    topics_coverage_score: int = 0
    competencies_coverage_score: int = 0
    answers_readiness_score: int = 0
    criteria_readiness_score: int = 0
    duplicate_rate: float = 0.0
    empty_answer_item_ids: list[str] = Field(default_factory=list)
    placeholder_answer_item_ids: list[str] = Field(default_factory=list)
    empty_criteria_item_ids: list[str] = Field(default_factory=list)
    missing_topic_item_ids: list[str] = Field(default_factory=list)
    missing_competency_item_ids: list[str] = Field(default_factory=list)
    duplicate_groups: list[AssessmentDuplicateGroup] = Field(default_factory=list)
    coverage_rows: list[AssessmentCoverageRow] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
