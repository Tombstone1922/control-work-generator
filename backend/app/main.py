from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app import models
from app.assessment_item_validation import AssessmentItemsValidation
from app.database import get_db, init_db
from app.repositories_assessment_items import get_fund_entity_for_user, list_items_for_user
from app.routers import (
    admin,
    assessment_funds,
    assessment_items,
    auth,
    context_module,
    demo_bank,
    export,
    generation,
    local_llm,
    narrow_generation,
    programs,
    qwen_training,
    reference_materials,
    training_examples,
)
from app.security import get_current_user
from app.services.assessment_item_validator import validate_assessment_items

app = FastAPI(title="Control Work Generator API", version="1.0.0")

DEV_FRONTEND_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=DEV_FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.post("/api/assessment-items/{fund_id}/validate", response_model=AssessmentItemsValidation)
def validate_items_without_blocking_generation(
    fund_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> AssessmentItemsValidation:
    try:
        fund = get_fund_entity_for_user(db, fund_id, current_user)
        items = list_items_for_user(db, fund_id, current_user)
        if fund is None or items is None:
            return AssessmentItemsValidation(warnings=["ФОС не найден или нет доступа."])
        return validate_assessment_items(fund, items)
    except Exception:
        return AssessmentItemsValidation(warnings=["Проверка банка заданий пропущена, генерация ФОС не прервана."])


app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(programs.router)
app.include_router(generation.router)
app.include_router(assessment_funds.router)
app.include_router(assessment_items.router)
app.include_router(narrow_generation.router)
app.include_router(qwen_training.router)
app.include_router(reference_materials.router)
app.include_router(training_examples.router)
app.include_router(context_module.router)
app.include_router(local_llm.router)
app.include_router(demo_bank.router)
app.include_router(export.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
