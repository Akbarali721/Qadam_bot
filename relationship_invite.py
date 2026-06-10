"""Relationship test partner deep-link helpers and constants."""

from __future__ import annotations

from urllib.parse import quote, urlencode

REL_INVITE_PREFIX = "rel_invite_"
LEGACY_LOVE_PARTNER_PREFIX = "love_partner_"

REL_INVITE_CALLBACK_START_PREFIX = "rel_invite:start:"

RELATIONSHIP_FUNNEL_EVENTS: frozenset[str] = frozenset(
    {
        "invite_created",
        "partner_deeplink_opened",
        "partner_start_clicked",
        "partner_test_started",
        "partner_test_completed",
        "result_ready",
        "user1_result_opened",
    }
)

REL_INVITE_MESSAGE = (
    "Sizga Munosabat testi taklif qilindi 💞\n\n"
    "Testni yakunlasangiz, umumiy natija tayyorlanadi."
)

USER1_RESULT_READY_MESSAGE = (
    "Sherigingiz testni yakunladi ✅\n\n"
    "Endi umumiy natijani ko‘rishingiz mumkin."
)


def parse_relationship_invite_token(start_param: str | None) -> str | None:
    if not start_param:
        return None
    payload = start_param.strip()
    for prefix in (REL_INVITE_PREFIX, LEGACY_LOVE_PARTNER_PREFIX):
        if payload.startswith(prefix):
            token = payload.removeprefix(prefix).strip()
            return token or None
    return None


def build_partner_webapp_url(
    *,
    webapp_base_url: str,
    invite_token: str,
    partner_telegram_id: int,
) -> str:
    """Partner landing route used by the main WebApp: /start/{token}?partner_tg_id=..."""
    base = webapp_base_url.rstrip("/")
    query = urlencode({"partner_tg_id": str(partner_telegram_id)})
    return f"{base}/start/{quote(invite_token, safe='')}?{query}"


def build_result_webapp_url(*, webapp_base_url: str, invite_token: str) -> str:
    base = webapp_base_url.rstrip("/")
    return f"{base}/result/{quote(invite_token, safe='')}"


def parse_rel_invite_start_callback(callback_data: str | None) -> str | None:
    if not callback_data or not callback_data.startswith(REL_INVITE_CALLBACK_START_PREFIX):
        return None
    token = callback_data.removeprefix(REL_INVITE_CALLBACK_START_PREFIX).strip()
    return token or None
