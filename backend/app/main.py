from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import export, generation, programs

app = FastAPI(title="Control Work Generator API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(programs.router)
app.include_router(generation.router)
app.include_router(export.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
