import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from db import models

logger = logging.getLogger(__name__)

ALLOWED_SELECTED_TESTS: frozenset[str] = frozenset({"love", "mbti", "stress"})


def _utcnow() -> datetime:
    return datetime.utcnow()


def save_bot_start_event(
    db: Session,
    *,
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
    language_code: str | None,
    start_param: str | None,
) -> models.BotStartEvent:
    normalized_start_param = (start_param or "").strip() or None
    source = normalized_start_param if normalized_start_param else "direct"
    now = _utcnow()

    bot_user = db.execute(
        select(models.BotUser).where(models.BotUser.telegram_id == telegram_id),
    ).scalar_one_or_none()

    if bot_user is None:
        bot_user = models.BotUser(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language_code=language_code,
            last_start_param=normalized_start_param,
            last_source=source,
            first_seen_at=now,
            last_seen_at=now,
            start_count=1,
        )
        db.add(bot_user)
    else:
        bot_user.username = username
        bot_user.first_name = first_name
        bot_user.last_name = last_name
        bot_user.language_code = language_code
        bot_user.last_seen_at = now
        bot_user.start_count = int(bot_user.start_count) + 1
        if normalized_start_param:
            bot_user.last_start_param = normalized_start_param
            bot_user.last_source = source

    event = models.BotStartEvent(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        language_code=language_code,
        start_param=normalized_start_param,
        source=source,
        created_at=now,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    logger.info(
        "Saved bot start event telegram_id=%s source=%s event_id=%s start_count=%s",
        telegram_id,
        source,
        event.id,
        bot_user.start_count,
    )
    return event


def _resolve_user_source(db: Session, telegram_id: int) -> str:
    bot_user = db.execute(
        select(models.BotUser).where(models.BotUser.telegram_id == telegram_id),
    ).scalar_one_or_none()
    if bot_user is not None and bot_user.last_source:
        return bot_user.last_source
    return "direct"


def save_bot_test_click_event(
    db: Session,
    *,
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    selected_test: str,
) -> models.BotTestClickEvent:
    normalized_test = selected_test.strip().lower()
    if normalized_test not in ALLOWED_SELECTED_TESTS:
        raise ValueError(f"Invalid selected_test: {selected_test}")

    source = _resolve_user_source(db=db, telegram_id=telegram_id)
    now = _utcnow()

    event = models.BotTestClickEvent(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
        selected_test=normalized_test,
        source=source,
        created_at=now,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    logger.info(
        "Saved bot test click telegram_id=%s test=%s source=%s event_id=%s",
        telegram_id,
        normalized_test,
        source,
        event.id,
    )
    return event
