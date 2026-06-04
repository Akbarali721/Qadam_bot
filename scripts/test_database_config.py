"""Verify DATABASE_URL and BOT_DB_PATH database configuration."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _reload_database_module():
    for name in list(sys.modules):
        if name == "db.database" or name.startswith("db."):
            del sys.modules[name]
    from db.database import (
        ACTIVE_DB_PATH,
        DATABASE_URL,
        POSTGRES_LOG_LABEL,
        database_backend,
        normalize_database_url,
        resolve_database_config,
    )

    return {
        "ACTIVE_DB_PATH": ACTIVE_DB_PATH,
        "DATABASE_URL": DATABASE_URL,
        "POSTGRES_LOG_LABEL": POSTGRES_LOG_LABEL,
        "database_backend": database_backend,
        "normalize_database_url": normalize_database_url,
        "resolve_database_config": resolve_database_config,
    }


def test_sqlite_default_when_database_url_unset() -> None:
    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("BOT_DB_PATH", None)
    cfg = _reload_database_module()
    expected = (ROOT / "bot_tracking.db").resolve()
    assert cfg["database_backend"]() == "sqlite"
    assert cfg["ACTIVE_DB_PATH"] == str(expected)
    assert cfg["DATABASE_URL"] == f"sqlite:///{expected.as_posix()}"


def test_database_url_postgres_normalized() -> None:
    os.environ["DATABASE_URL"] = "postgres://user:pass@host:5432/railway"
    os.environ["BOT_DB_PATH"] = "ignored.db"
    cfg = _reload_database_module()
    assert cfg["database_backend"]() == "postgresql"
    assert cfg["DATABASE_URL"] == "postgresql+psycopg2://user:pass@host:5432/railway"
    assert cfg["ACTIVE_DB_PATH"] == cfg["POSTGRES_LOG_LABEL"]


def test_database_url_postgresql_scheme_normalized() -> None:
    os.environ["DATABASE_URL"] = "postgresql://user:pass@host:5432/db"
    cfg = _reload_database_module()
    assert cfg["DATABASE_URL"] == "postgresql+psycopg2://user:pass@host:5432/db"


def test_database_url_sqlite_memory_for_tests() -> None:
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    cfg = _reload_database_module()
    assert cfg["database_backend"]() == "sqlite"
    assert cfg["DATABASE_URL"] == "sqlite:///:memory:"


def test_normalize_database_url_helper() -> None:
    os.environ.pop("DATABASE_URL", None)
    cfg = _reload_database_module()
    assert (
        cfg["normalize_database_url"]("postgres://x")
        == "postgresql+psycopg2://x"
    )
    assert (
        cfg["normalize_database_url"]("postgresql://x")
        == "postgresql+psycopg2://x"
    )
    assert cfg["normalize_database_url"]("sqlite:///local.db") == "sqlite:///local.db"


if __name__ == "__main__":
    test_sqlite_default_when_database_url_unset()
    test_database_url_postgres_normalized()
    test_database_url_postgresql_scheme_normalized()
    test_database_url_sqlite_memory_for_tests()
    test_normalize_database_url_helper()
    print("DATABASE_URL config tests passed")
