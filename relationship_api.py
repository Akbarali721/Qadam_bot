"""Admin API helpers for relationship funnel events and user1 notifications."""

from __future__ import annotations

import logging
import os

from sqlalchemy.orm import Session

from api_schemas import RelationshipFunnelEventCreate, RelationshipPartnerCompletedPayload
from db.relationship_crud import save_relationship_funnel_event
from relationship_invite import USER1_RESULT_READY_MESSAGE, build_result_webapp_url
from telegram_client import send_telegram_message

logger = logging.getLogger(__name__)


def record_relationship_funnel_event_api(
    db: Session,
    payload: RelationshipFunnelEventCreate,
) -> dict[str, bool]:
    save_relationship_funnel_event(
        db=db,
        invite_token=payload.invite_token,
        event_name=payload.event_name,
        telegram_id=payload.telegram_id,
        role=payload.role,
        metadata=payload.metadata,
    )
    return {"ok": True}


def handle_partner_completed_api(
    db: Session,
    payload: RelationshipPartnerCompletedPayload,
) -> dict[str, bool]:
    save_relationship_funnel_event(
        db=db,
        invite_token=payload.invite_token,
        event_name="partner_test_completed",
        telegram_id=payload.partner_telegram_id,
        role="user2",
    )
    save_relationship_funnel_event(
        db=db,
        invite_token=payload.invite_token,
        event_name="result_ready",
        telegram_id=payload.user1_telegram_id,
        role="user1",
    )

    webapp_base_url = (os.getenv("WEBAPP_BASE_URL") or "").rstrip("/")
    if not webapp_base_url:
        logger.warning(
            "WEBAPP_BASE_URL missing — user1 notified without WebApp button token=%s",
            payload.invite_token,
        )
        send_telegram_message(
            chat_id=payload.user1_telegram_id,
            text=USER1_RESULT_READY_MESSAGE,
        )
        return {"ok": True, "notified": True}

    result_url = build_result_webapp_url(
        webapp_base_url=webapp_base_url,
        invite_token=payload.invite_token,
    )
    notified = send_telegram_message(
        chat_id=payload.user1_telegram_id,
        text=USER1_RESULT_READY_MESSAGE,
        reply_markup={
            "inline_keyboard": [
                [
                    {
                        "text": "📊 Natijani ko‘rish",
                        "web_app": {"url": result_url},
                    },
                ],
            ],
        },
    )
    return {"ok": True, "notified": notified}


def handle_user1_result_opened_api(
    db: Session,
    payload: RelationshipFunnelEventCreate,
) -> dict[str, bool]:
    save_relationship_funnel_event(
        db=db,
        invite_token=payload.invite_token,
        event_name="user1_result_opened",
        telegram_id=payload.telegram_id,
        role="user1",
        metadata=payload.metadata,
    )
    return {"ok": True}
