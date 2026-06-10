"""Aiogram handlers for relationship partner deep-link invites."""

from __future__ import annotations

import asyncio
import logging

from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from config import WEBAPP_NOT_CONFIGURED_TEXT, is_webapp_configured
from db.database import SessionLocal
from db.relationship_crud import save_relationship_funnel_event
from relationship_invite import (
    REL_INVITE_CALLBACK_START_PREFIX,
    REL_INVITE_MESSAGE,
    build_partner_webapp_url,
    parse_rel_invite_start_callback,
)

logger = logging.getLogger(__name__)


def _record_funnel_event_sync(
    *,
    invite_token: str,
    event_name: str,
    telegram_id: int | None,
    role: str | None = None,
    metadata: dict | None = None,
) -> None:
    db = SessionLocal()
    try:
        save_relationship_funnel_event(
            db=db,
            invite_token=invite_token,
            event_name=event_name,
            telegram_id=telegram_id,
            role=role,
            metadata=metadata,
        )
    finally:
        db.close()


async def record_funnel_event(
    *,
    invite_token: str,
    event_name: str,
    telegram_id: int | None,
    role: str | None = None,
    metadata: dict | None = None,
) -> None:
    try:
        await asyncio.to_thread(
            _record_funnel_event_sync,
            invite_token=invite_token,
            event_name=event_name,
            telegram_id=telegram_id,
            role=role,
            metadata=metadata,
        )
    except Exception:
        logger.exception(
            "Failed to record relationship funnel event token=%s event=%s",
            invite_token,
            event_name,
        )


def rel_invite_start_callback_data(invite_token: str) -> str:
    return f"{REL_INVITE_CALLBACK_START_PREFIX}{invite_token}"


def rel_invite_start_keyboard(invite_token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📝 Testni boshlash",
                    callback_data=rel_invite_start_callback_data(invite_token),
                ),
            ],
        ],
    )


def rel_invite_webapp_keyboard(
    *,
    webapp_base_url: str,
    invite_token: str,
    partner_telegram_id: int,
) -> InlineKeyboardMarkup:
    webapp_url = build_partner_webapp_url(
        webapp_base_url=webapp_base_url,
        invite_token=invite_token,
        partner_telegram_id=partner_telegram_id,
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📝 Testni boshlash",
                    web_app=WebAppInfo(url=webapp_url),
                ),
            ],
        ],
    )


async def handle_relationship_invite_deeplink(
    message: Message,
    invite_token: str,
    *,
    webapp_base_url: str,
    safe_answer,
) -> None:
    user = message.from_user
    await record_funnel_event(
        invite_token=invite_token,
        event_name="partner_deeplink_opened",
        telegram_id=user.id,
        role="user2",
        metadata={
            "username": user.username,
            "first_name": user.first_name,
        },
    )

    if not is_webapp_configured(webapp_base_url):
        await safe_answer(message, WEBAPP_NOT_CONFIGURED_TEXT)
        return

    await safe_answer(
        message,
        REL_INVITE_MESSAGE,
        reply_markup=rel_invite_start_keyboard(invite_token),
    )


async def handle_relationship_invite_start_callback(
    callback: CallbackQuery,
    *,
    webapp_base_url: str,
    safe_answer,
) -> None:
    invite_token = parse_rel_invite_start_callback(callback.data)
    if not invite_token:
        await callback.answer("Taklif topilmadi.", show_alert=True)
        return

    user = callback.from_user
    await record_funnel_event(
        invite_token=invite_token,
        event_name="partner_start_clicked",
        telegram_id=user.id,
        role="user2",
    )

    if not is_webapp_configured(webapp_base_url):
        await callback.answer(WEBAPP_NOT_CONFIGURED_TEXT, show_alert=True)
        return

    await callback.answer()
    await safe_answer(
        callback.message,
        "Testni boshlash uchun tugmani bosing 👇",
        reply_markup=rel_invite_webapp_keyboard(
            webapp_base_url=webapp_base_url,
            invite_token=invite_token,
            partner_telegram_id=user.id,
        ),
    )
