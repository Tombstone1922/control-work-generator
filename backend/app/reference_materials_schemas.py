from pydantic import BaseModel, Field


class ReferenceDocumentRead(BaseModel):
    id: str
    document_type: str
    discipline_name: str
    filename: str
    text_hash: str
    parsed_summary: dict = Field(default_factory=dict)
    created_at: str


class RpOmPairRead(BaseModel):
    id: str
    rp_document_id: str
    om_document_id: str
    discipline_name: str
    pairing_confidence: float
    created_at: str


class OmAssessmentItemRead(BaseModel):
    id: str
    pair_id: str | None = None
    om_document_id: str
    topic: str
    competency_code: str = ""
    indicator: str = ""
    assessment_type: str
    item_type: str
    difficulty: str
    text: str
    answer: str = ""
    criteria: list[str] = Field(default_factory=list)
    source_section: str = ""
    sample_weight: float = 1.0


class ReferenceUploadResponse(BaseModel):
    document: ReferenceDocumentRead
    parsed_items_count: int = 0
    paired_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class ReferenceLibraryStats(BaseModel):
    rp_documents: int = 0
    om_documents: int = 0
    rp_om_pairs: int = 0
    om_items: int = 0
    average_pairing_confidence: float = 0.0
