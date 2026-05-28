from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{STORAGE_DIR / 'app.db'}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _apply_sqlite_migrations()


def _apply_sqlite_migrations() -> None:
    inspector = inspect(engine)
    if "programs" not in inspector.get_table_names():
        return

    program_columns = {column["name"] for column in inspector.get_columns("programs")}
    with engine.begin() as connection:
        if "owner_user_id" not in program_columns:
            connection.execute(text("ALTER TABLE programs ADD COLUMN owner_user_id VARCHAR(64)"))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
