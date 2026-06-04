"""Verify BOT_DB_PATH resolution."""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _reload_database_module():
    for name in list(sys.modules):
        if name == "db.database" or name.startswith("db."):
            del sys.modules[name]
    from db.database import ACTIVE_DB_PATH, DATABASE_URL, resolve_database_config

    return ACTIVE_DB_PATH, DATABASE_URL, resolve_database_config


def test_default_path() -> None:
    os.environ.pop("BOT_DB_PATH", None)
    os.environ.pop("DATABASE_URL", None)
    active_path, database_url, _ = _reload_database_module()
    expected = (ROOT / "bot_tracking.db").resolve()
    assert active_path == str(expected)
    assert database_url == f"sqlite:///{expected.as_posix()}"
    assert expected.parent.exists()


def test_custom_relative_path() -> None:
    os.environ.pop("DATABASE_URL", None)
    os.environ["BOT_DB_PATH"] = "custom_tracking.db"
    active_path, _, _ = _reload_database_module()
    expected = (ROOT / "custom_tracking.db").resolve()
    assert active_path == str(expected)
    if expected.exists():
        expected.unlink()


def test_volume_style_absolute_path() -> None:
    os.environ.pop("DATABASE_URL", None)
    with tempfile.TemporaryDirectory() as tmp:
        db_file = Path(tmp) / "data" / "bot_tracking.db"
        os.environ["BOT_DB_PATH"] = str(db_file)
        active_path, database_url, _ = _reload_database_module()
        assert active_path == str(db_file.resolve())
        assert db_file.parent.exists()
        assert database_url == f"sqlite:///{db_file.resolve().as_posix()}"


if __name__ == "__main__":
    test_default_path()
    test_custom_relative_path()
    test_volume_style_absolute_path()
    print("BOT_DB_PATH tests passed")
