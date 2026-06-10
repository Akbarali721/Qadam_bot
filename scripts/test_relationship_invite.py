"""Tests for relationship invite deep-link flow."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from sqlalchemy.orm import sessionmaker

from db import models  # noqa: F401
from db.database import Base, engine
from db.relationship_crud import save_relationship_funnel_event
from db.relationship_stats_service import get_relationship_funnel_stats
from relationship_invite import (
    build_partner_webapp_url,
    build_result_webapp_url,
    parse_relationship_invite_token,
    parse_rel_invite_start_callback,
)


def run_tests() -> None:
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    assert parse_relationship_invite_token("rel_invite_abc123") == "abc123"
    assert parse_relationship_invite_token("love_partner_abc123") == "abc123"
    assert parse_relationship_invite_token("instagram_love_01") is None

    assert parse_rel_invite_start_callback("rel_invite:start:abc123") == "abc123"

    partner_url = build_partner_webapp_url(
        webapp_base_url="https://app.example.com",
        invite_token="abc123",
        partner_telegram_id=999,
    )
    assert partner_url.startswith("https://app.example.com/start/abc123?")
    assert "partner_tg_id=999" in partner_url

    result_url = build_result_webapp_url(
        webapp_base_url="https://app.example.com",
        invite_token="abc123",
    )
    assert result_url == "https://app.example.com/result/abc123"

    save_relationship_funnel_event(
        db=db,
        invite_token="abc123",
        event_name="invite_created",
        telegram_id=111,
        role="user1",
    )
    save_relationship_funnel_event(
        db=db,
        invite_token="abc123",
        event_name="partner_deeplink_opened",
        telegram_id=222,
        role="user2",
    )
    save_relationship_funnel_event(
        db=db,
        invite_token="abc123",
        event_name="partner_start_clicked",
        telegram_id=222,
        role="user2",
    )
    save_relationship_funnel_event(
        db=db,
        invite_token="abc123",
        event_name="partner_test_started",
        telegram_id=222,
        role="user2",
    )
    save_relationship_funnel_event(
        db=db,
        invite_token="abc123",
        event_name="partner_test_completed",
        telegram_id=222,
        role="user2",
    )

    stats = get_relationship_funnel_stats(db=db)
    assert stats["invite_created"] == 1
    assert stats["partner_deeplink_opened"] == 1
    assert stats["partner_start_clicked"] == 1
    assert stats["partner_test_started"] == 1
    assert stats["partner_test_completed"] == 1
    assert stats["conversion_deeplink_per_invite"] == 100.0
    assert stats["conversion_start_per_deeplink"] == 100.0
    assert stats["conversion_completed_per_started"] == 100.0

    db.close()
    print("Relationship invite tests passed")


if __name__ == "__main__":
    run_tests()
