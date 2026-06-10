import json
import logging
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db import models
from relationship_invite import RELATIONSHIP_FUNNEL_EVENTS

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.utcnow()


def save_relationship_funnel_event(
    db: Session,
    *,
    invite_token: str,
    event_name: str,
    telegram_id: int | None = None,
    role: str | None = None,
    metadata: dict | None = None,
) -> models.RelationshipFunnelEvent:
    normalized_token = invite_token.strip()
    normalized_event = event_name.strip()
    if not normalized_token:
        raise ValueError("invite_token is required")
    if normalized_event not in RELATIONSHIP_FUNNEL_EVENTS:
        raise ValueError(f"Invalid event_name: {event_name}")

    event = models.RelationshipFunnelEvent(
        invite_token=normalized_token,
        event_name=normalized_event,
        telegram_id=telegram_id,
        role=role,
        metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
        created_at=_utcnow(),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    logger.info(
        "Saved relationship funnel event token=%s event=%s telegram_id=%s role=%s id=%s",
        normalized_token,
        normalized_event,
        telegram_id,
        role,
        event.id,
    )
    return event


def count_relationship_funnel_event(db: Session, event_name: str) -> int:
    return int(
        db.execute(
            select(func.count(models.RelationshipFunnelEvent.id)).where(
                models.RelationshipFunnelEvent.event_name == event_name,
            ),
        ).scalar_one()
        or 0,
    )
