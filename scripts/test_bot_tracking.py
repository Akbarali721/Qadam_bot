"""Local verification for bot start and test click tracking."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from sqlalchemy.orm import sessionmaker

from db import models  # noqa: F401
from db.crud import save_bot_start_event, save_bot_test_click_event
from db.database import Base, engine
from db.bot_tracking_service import get_bot_tracking_dashboard_stats


def run_tests() -> None:
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    event = save_bot_start_event(
        db=db,
        telegram_id=111,
        username="user1",
        first_name="Ali",
        last_name="Valiyev",
        language_code="uz",
        start_param=None,
    )
    assert event.source == "direct"

    event = save_bot_start_event(
        db=db,
        telegram_id=222,
        username="user2",
        first_name="Sara",
        last_name=None,
        language_code="uz",
        start_param="instagram_love_01",
    )
    assert event.source == "instagram_love_01"

    save_bot_start_event(
        db=db,
        telegram_id=111,
        username="user1",
        first_name="Ali",
        last_name="Valiyev",
        language_code="uz",
        start_param=None,
    )
    save_bot_start_event(
        db=db,
        telegram_id=111,
        username="user1",
        first_name="Ali",
        last_name="Valiyev",
        language_code="uz",
        start_param="instagram_love_01",
    )
    user = db.query(models.BotUser).filter_by(telegram_id=111).one()
    assert user.start_count == 3
    assert db.query(models.BotStartEvent).filter_by(telegram_id=111).count() == 3

    save_bot_start_event(
        db=db,
        telegram_id=111,
        username="user1",
        first_name="Ali",
        last_name="Valiyev",
        language_code="uz",
        start_param=None,
    )
    user = db.query(models.BotUser).filter_by(telegram_id=111).one()
    assert user.start_count == 4
    assert user.last_source == "instagram_love_01"

    love_click = save_bot_test_click_event(
        db=db,
        telegram_id=111,
        username="user1",
        first_name="Ali",
        selected_test="love",
    )
    assert love_click.source == "instagram_love_01"
    assert love_click.selected_test == "love"

    mbti_click = save_bot_test_click_event(
        db=db,
        telegram_id=222,
        username="user2",
        first_name="Sara",
        selected_test="mbti",
    )
    assert mbti_click.source == "instagram_love_01"

    direct_click = save_bot_test_click_event(
        db=db,
        telegram_id=333,
        username=None,
        first_name="Guest",
        selected_test="stress",
    )
    assert direct_click.source == "direct"

    assert db.query(models.BotTestClickEvent).count() == 3

    os.environ["TELEGRAM_BOT_USERNAME"] = "test_bot"
    stats = get_bot_tracking_dashboard_stats(db=db)
    assert stats["total_bot_users"] == 2
    assert stats["today_bot_starts"] == 5
    assert stats["total_test_clicks"] == 3
    assert stats["love_test_clicks"] == 1
    assert stats["mbti_test_clicks"] == 1
    assert stats["stress_test_clicks"] == 1
    assert len(stats["test_clicks_by_source"]) == 2
    assert len(stats["latest_test_click_events"]) == 3
    assert "instagram_love_01" in stats["campaign_link_examples"][0]

    try:
        save_bot_test_click_event(
            db=db,
            telegram_id=444,
            username=None,
            first_name="Bad",
            selected_test="invalid",
        )
        raise AssertionError("expected ValueError for invalid selected_test")
    except ValueError:
        pass

    db.close()
    print("All bot tracking tests passed")


if __name__ == "__main__":
    run_tests()
