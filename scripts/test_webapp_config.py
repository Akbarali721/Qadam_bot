"""Tests for optional WEBAPP_BASE_URL behavior."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import WEBAPP_NOT_CONFIGURED_TEXT, is_webapp_configured


def test_is_webapp_configured() -> None:
    assert is_webapp_configured("https://example.com") is True
    assert is_webapp_configured("https://example.com/") is True
    assert is_webapp_configured("") is False
    assert is_webapp_configured(None) is False
    assert is_webapp_configured("   ") is False


def test_not_configured_message() -> None:
    assert WEBAPP_NOT_CONFIGURED_TEXT == "WebApp URL is not configured yet."


if __name__ == "__main__":
    test_is_webapp_configured()
    test_not_configured_message()
    print("WEBAPP config tests passed")
