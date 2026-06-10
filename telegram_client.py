"""Minimal Telegram Bot API client for admin service notifications."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def send_telegram_message(
    *,
    chat_id: int,
    text: str,
    reply_markup: dict[str, Any] | None = None,
) -> bool:
    bot_token = (os.getenv("BOT_TOKEN") or "").strip()
    if not bot_token:
        logger.error("BOT_TOKEN is not configured — cannot send Telegram message")
        return False

    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(url, json=payload)
            body = response.json()
    except Exception:
        logger.exception("Telegram sendMessage failed chat_id=%s", chat_id)
        return False

    if not body.get("ok"):
        logger.warning(
            "Telegram sendMessage rejected chat_id=%s detail=%s",
            chat_id,
            body.get("description"),
        )
        return False
    return True
