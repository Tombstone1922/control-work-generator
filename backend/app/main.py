from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.routers import admin, auth, export, generation, programs

app = FastAPI(title="Control Work Generator API", version="0.4.0")

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
app.include_router(export.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
