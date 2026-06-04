import os
from datetime import datetime, timedelta
from typing import TypedDict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db import models


class BotStartEventRow(TypedDict):
    id: int
    created_at: datetime
    first_name: str | None
    username: str | None
    telegram_id: int
    source: str | None
    start_param: str | None
    start_count: int | None


class BotSourceStat(TypedDict):
    source: str
    count: int


class BotUserRow(TypedDict):
    first_name: str | None
    username: str | None
    telegram_id: int
    last_source: str | None
    last_seen_at: datetime
    start_count: int


class BotTestClickEventRow(TypedDict):
    id: int
    created_at: datetime
    first_name: str | None
    username: str | None
    telegram_id: int
    selected_test: str
    source: str | None


class BotTrackingDashboardStats(TypedDict):
    total_bot_users: int
    today_bot_starts: int
    last_7_days_bot_starts: int
    top_sources: list[BotSourceStat]
    latest_start_events: list[BotStartEventRow]
    recent_bot_users: list[BotUserRow]
    campaign_link_examples: list[str]
    total_test_clicks: int
    love_test_clicks: int
    mbti_test_clicks: int
    stress_test_clicks: int
    test_clicks_by_source: list[BotSourceStat]
    latest_test_click_events: list[BotTestClickEventRow]


def bot_username() -> str:
    return (
        os.getenv("TELEGRAM_BOT_USERNAME")
        or os.getenv("BOT_USERNAME")
        or ""
    ).lstrip("@")


def _utcnow() -> datetime:
    return datetime.utcnow()


def _today_start() -> datetime:
    now = _utcnow()
    return datetime(now.year, now.month, now.day)


def get_bot_tracking_dashboard_stats(db: Session) -> BotTrackingDashboardStats:
    today_start = _today_start()
    seven_days_ago = _utcnow() - timedelta(days=7)

    total_bot_users = db.execute(select(func.count(models.BotUser.id))).scalar_one() or 0
    today_bot_starts = (
        db.execute(
            select(func.count(models.BotStartEvent.id)).where(
                models.BotStartEvent.created_at >= today_start,
            ),
        ).scalar_one()
        or 0
    )
    last_7_days_bot_starts = (
        db.execute(
            select(func.count(models.BotStartEvent.id)).where(
                models.BotStartEvent.created_at >= seven_days_ago,
            ),
        ).scalar_one()
        or 0
    )

    top_source_rows = db.execute(
        select(models.BotStartEvent.source, func.count(models.BotStartEvent.id))
        .group_by(models.BotStartEvent.source)
        .order_by(func.count(models.BotStartEvent.id).desc())
        .limit(10),
    ).all()
    top_sources: list[BotSourceStat] = [
        {"source": (source or "direct"), "count": int(count)}
        for source, count in top_source_rows
    ]

    latest_events = db.execute(
        select(models.BotStartEvent)
        .order_by(models.BotStartEvent.created_at.desc(), models.BotStartEvent.id.desc())
        .limit(30),
    ).scalars().all()

    telegram_ids = {event.telegram_id for event in latest_events}
    start_counts_by_telegram_id: dict[int, int] = {}
    if telegram_ids:
        user_rows = db.execute(
            select(models.BotUser.telegram_id, models.BotUser.start_count).where(
                models.BotUser.telegram_id.in_(telegram_ids),
            ),
        ).all()
        start_counts_by_telegram_id = {
            int(telegram_id): int(start_count) for telegram_id, start_count in user_rows
        }

    latest_start_events: list[BotStartEventRow] = [
        {
            "id": event.id,
            "created_at": event.created_at,
            "first_name": event.first_name,
            "username": event.username,
            "telegram_id": int(event.telegram_id),
            "source": event.source,
            "start_param": event.start_param,
            "start_count": start_counts_by_telegram_id.get(int(event.telegram_id)),
        }
        for event in latest_events
    ]

    recent_users = db.execute(
        select(models.BotUser)
        .order_by(models.BotUser.last_seen_at.desc(), models.BotUser.id.desc())
        .limit(30),
    ).scalars().all()
    recent_bot_users: list[BotUserRow] = [
        {
            "first_name": user.first_name,
            "username": user.username,
            "telegram_id": int(user.telegram_id),
            "last_source": user.last_source,
            "last_seen_at": user.last_seen_at,
            "start_count": int(user.start_count),
        }
        for user in recent_users
    ]

    username = bot_username() or "YOUR_BOT_USERNAME"
    campaign_params = ("instagram_love_01", "instagram_mbti_01", "youtube_stress_01")
    campaign_link_examples = [
        f"https://t.me/{username}?start={param}" for param in campaign_params
    ]

    total_test_clicks = (
        db.execute(select(func.count(models.BotTestClickEvent.id))).scalar_one() or 0
    )
    love_test_clicks = (
        db.execute(
            select(func.count(models.BotTestClickEvent.id)).where(
                models.BotTestClickEvent.selected_test == "love",
            ),
        ).scalar_one()
        or 0
    )
    mbti_test_clicks = (
        db.execute(
            select(func.count(models.BotTestClickEvent.id)).where(
                models.BotTestClickEvent.selected_test == "mbti",
            ),
        ).scalar_one()
        or 0
    )
    stress_test_clicks = (
        db.execute(
            select(func.count(models.BotTestClickEvent.id)).where(
                models.BotTestClickEvent.selected_test == "stress",
            ),
        ).scalar_one()
        or 0
    )

    test_click_source_rows = db.execute(
        select(models.BotTestClickEvent.source, func.count(models.BotTestClickEvent.id))
        .group_by(models.BotTestClickEvent.source)
        .order_by(func.count(models.BotTestClickEvent.id).desc())
        .limit(10),
    ).all()
    test_clicks_by_source: list[BotSourceStat] = [
        {"source": (source or "direct"), "count": int(count)}
        for source, count in test_click_source_rows
    ]

    latest_test_clicks = db.execute(
        select(models.BotTestClickEvent)
        .order_by(
            models.BotTestClickEvent.created_at.desc(),
            models.BotTestClickEvent.id.desc(),
        )
        .limit(30),
    ).scalars().all()
    latest_test_click_events: list[BotTestClickEventRow] = [
        {
            "id": event.id,
            "created_at": event.created_at,
            "first_name": event.first_name,
            "username": event.username,
            "telegram_id": int(event.telegram_id),
            "selected_test": event.selected_test,
            "source": event.source,
        }
        for event in latest_test_clicks
    ]

    return {
        "total_bot_users": int(total_bot_users),
        "today_bot_starts": int(today_bot_starts),
        "last_7_days_bot_starts": int(last_7_days_bot_starts),
        "top_sources": top_sources,
        "latest_start_events": latest_start_events,
        "recent_bot_users": recent_bot_users,
        "campaign_link_examples": campaign_link_examples,
        "total_test_clicks": int(total_test_clicks),
        "love_test_clicks": int(love_test_clicks),
        "mbti_test_clicks": int(mbti_test_clicks),
        "stress_test_clicks": int(stress_test_clicks),
        "test_clicks_by_source": test_clicks_by_source,
        "latest_test_click_events": latest_test_click_events,
    }
