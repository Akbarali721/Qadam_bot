import logging
import os
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_FILENAME = "bot_tracking.db"
POSTGRES_LOG_LABEL = "postgresql (DATABASE_URL)"


def _resolve_sqlite_path() -> Path:
    raw_path = (os.getenv("BOT_DB_PATH") or "").strip()
    if raw_path:
        path = Path(raw_path)
        if not path.is_absolute():
            path = BASE_DIR / path
    else:
        path = BASE_DIR / DEFAULT_SQLITE_FILENAME
    return path.resolve()


def _build_sqlite_database_url(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path.as_posix()}"


def normalize_database_url(database_url: str) -> str:
    """Normalize Railway/Heroku-style URLs for sync SQLAlchemy + psycopg2."""
    url = database_url.strip()
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://") and "+psycopg2" not in url:
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def resolve_database_config() -> tuple[str, str]:
    """
    Returns (sqlalchemy_database_url, label_for_logging).

    Priority:
    1. DATABASE_URL if set (PostgreSQL in production, or sqlite:// for tests)
    2. SQLite file from BOT_DB_PATH, defaulting to bot_tracking.db
    """
    database_url = (os.getenv("DATABASE_URL") or "").strip()
    if database_url:
        normalized = normalize_database_url(database_url)
        if normalized.startswith("sqlite"):
            if normalized.startswith("sqlite:///"):
                return normalized, normalized.removeprefix("sqlite:///")
            return normalized, normalized
        return normalized, POSTGRES_LOG_LABEL

    sqlite_path = _resolve_sqlite_path()
    return _build_sqlite_database_url(sqlite_path), str(sqlite_path)


DATABASE_URL, ACTIVE_DB_PATH = resolve_database_config()


def database_backend() -> str:
    if DATABASE_URL.startswith("sqlite"):
        return "sqlite"
    if DATABASE_URL.startswith("postgresql"):
        return "postgresql"
    return "other"


connect_args: dict[str, object] = {}
engine_kwargs: dict[str, object] = {}
if database_backend() == "sqlite":
    connect_args["check_same_thread"] = False
    engine_kwargs["connect_args"] = connect_args
elif database_backend() == "postgresql":
    engine_kwargs["pool_pre_ping"] = True

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def log_active_database_path() -> None:
    backend = database_backend()
    if backend == "sqlite":
        logger.info("Active database (SQLite): %s", ACTIVE_DB_PATH)
    elif backend == "postgresql":
        logger.info("Active database (PostgreSQL): %s", ACTIVE_DB_PATH)
    else:
        logger.info("Active database: %s", ACTIVE_DB_PATH)


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
