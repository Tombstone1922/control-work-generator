from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.routers import (
    admin,
    assessment_funds,
    assessment_items,
    auth,
    context_module,
    export,
    generation,
    local_llm,
    narrow_generation,
    programs,
    qwen_training,
    reference_materials,
    training_examples,
)

app = FastAPI(title="Control Work Generator API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


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
app.include_router(export.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
