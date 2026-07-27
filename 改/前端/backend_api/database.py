from __future__ import annotations

import os
from pathlib import Path
from typing import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker


BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_SQLITE_PATH = BACKEND_DIR / "smartagribrain.db"

load_dotenv(BACKEND_DIR / ".env")
load_dotenv(BACKEND_DIR / ".env.mqtt.local", override=True)


def normalize_database_url(raw_url: str) -> str:
    url = raw_url.strip()
    if not url:
        return f"sqlite:///{DEFAULT_SQLITE_PATH.as_posix()}"
    if url.startswith("sqlite:///"):
        sqlite_path = url.removeprefix("sqlite:///")
        normalized_path = sqlite_path[2:] if sqlite_path.startswith("./") else sqlite_path
        path = Path(normalized_path)
        if normalized_path and not path.is_absolute():
            return f"sqlite:///{(BACKEND_DIR / normalized_path).as_posix()}"
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


DATABASE_URL = normalize_database_url(os.getenv("DATABASE_URL", ""))

engine_kwargs = {"future": True}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_database() -> None:
    import agri_source_models  # noqa: F401
    import app_state_models  # noqa: F401
    import device_models  # noqa: F401
    import kb_models  # noqa: F401
    import monitoring_models  # noqa: F401
    import photo_models  # noqa: F401
    import site_models  # noqa: F401
    from agri_source_service import seed_agri_source_settings
    from app_state_service import seed_default_camera_position
    from kb_service import seed_initial_knowledge, seed_reference_tomato_knowledge

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_default_camera_position(db)
        seed_agri_source_settings(db)
        seed_initial_knowledge(db)
        seed_reference_tomato_knowledge(db)
