import asyncio
import logging
import os
import sys
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlparse, urlunparse

import httpx
from aiohttp.client_exceptions import ClientConnectorError
from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramNetworkError
from aiogram.filters import Command, CommandStart
from aiogram.filters.command import CommandObject
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    WebAppInfo,
)
from dotenv import load_dotenv

from config import WEBAPP_NOT_CONFIGURED_TEXT, is_webapp_configured
from db.bot_tracking_service import get_bot_tracking_dashboard_stats
from db.crud import save_bot_start_event, save_bot_test_click_event
from db.database import SessionLocal, init_db, log_active_database_path
from db.relationship_stats_service import get_relationship_funnel_stats
from handlers.relationship_invite_handlers import (
    handle_relationship_invite_deeplink,
    handle_relationship_invite_start_callback,
)
from relationship_invite import parse_relationship_invite_token

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# User notifications (partner completed, premium approved, PDF) live in the FastAPI
# backend: test_mvp/app/services/telegram_notify.py (notify_user1_test_completed,
# notify_love_user1_premium_unlocked, notify_admin_premium_request, etc.).
# This bot is the Qadam menu + admin command entry point only.

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_BASE_URL = os.getenv("WEBAPP_BASE_URL", "").rstrip("/")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0") or "0")
BOT_ADMIN_BASE_URL = os.getenv("BOT_ADMIN_BASE_URL", "").rstrip("/")
BOT_ADMIN_PORT = int(os.getenv("BOT_ADMIN_PORT", "8081") or "8081")

ADMIN_DENIED_TEXT = "Bu bo‘lim faqat admin uchun."
ERR_OFFLINE = "Web ilova hozir ishlamayapti. Keyinroq urinib ko‘ring."
ERR_UNAUTHORIZED = "Admin token noto‘g‘ri yoki ruxsat yo‘q."
ERR_INVALID_JSON = "Server noto‘g‘ri javob qaytardi."

SAFE_ANSWER_RETRY_DELAYS_SECONDS = (1, 2, 3)
RETRIABLE_ANSWER_ERRORS = (
    TelegramNetworkError,
    ClientConnectorError,
    asyncio.TimeoutError,
)

WELCOME_TEXT = (
    "Assalomu alaykum! 👋\n\n"
    "Qadam platformasiga xush kelibsiz.\n"
    "Bu yerda o‘zingizni va munosabatlaringizni yaxshiroq tushunishga "
    "yordam beradigan testlar bor.\n\n"
    "Quyidan testni tanlang:"
)

BTN_LOVE = "💞 Munosabat testi"
BTN_MBTI = "🧠 MBTI testi"
BTN_STRESS = "🌿 Stress testi"

STAT_LABELS: dict[str, str] = {
    "love_sessions_total": "❤️ Love — jami sessiyalar",
    "love_completed_pairs": "❤️ Love — tugallangan juftliklar",
    "love_premium_pending": "❤️ Love — premium kutilmoqda",
    "love_premium_approved": "❤️ Love — premium tasdiqlangan",
    "mbti_sessions_total": "🧠 MBTI — jami sessiyalar",
    "mbti_premium_pending": "🧠 MBTI — premium kutilmoqda",
    "mbti_premium_approved": "🧠 MBTI — premium tasdiqlangan",
    "stress_sessions_total": "😰 Stress — jami sessiyalar",
    "stress_premium_pending": "😰 Stress — premium kutilmoqda",
    "stress_premium_approved": "😰 Stress — premium tasdiqlangan",
}


@dataclass(frozen=True)
class TestProduct:
    reply_label: str
    path: str
    log_name: str
    explanation: str
    start_button: str


PRODUCTS: dict[str, TestProduct] = {
    BTN_LOVE: TestProduct(
        reply_label=BTN_LOVE,
        path="/",
        log_name="love",
        explanation=(
            "🧡 Munosabat testi\n\n"
            "Bu test siz va juftingiz bir-biringizni qayerda yaxshiroq "
            "tushunishingiz kerakligini ko‘rsatadi.\n"
            "Avval siz javob berasiz, keyin havolani juftingizga yuborasiz. "
            "Ikkalangiz javob bergach, umumiy natija chiqadi."
        ),
        start_button="🚀 Munosabat testini boshlash",
    ),
    BTN_MBTI: TestProduct(
        reply_label=BTN_MBTI,
        path="/mbti/start",
        log_name="mbti",
        explanation=(
            "🧠 MBTI testi\n\n"
            "Bu test shaxsiyatingiz, qaror qabul qilish uslubingiz va kuchli "
            "tomonlaringizni tushunishga yordam beradi.\n"
            "Qisqa savollarga javob bering va o‘zingizga yaqin shaxsiyat "
            "turini biling."
        ),
        start_button="🚀 MBTI testini boshlash",
    ),
    BTN_STRESS: TestProduct(
        reply_label=BTN_STRESS,
        path="/stress/start",
        log_name="stress",
        explanation=(
            "😰 Stress testi\n\n"
            "Bu test hozirgi ruhiy zo‘riqish darajangizni baholashga yordam beradi.\n"
            "Natijada stress darajangiz va oddiy tavsiyalarni ko‘rasiz."
        ),
        start_button="🚀 Stress testini boshlash",
    ),
}


def _is_retriable_answer_error(exc: BaseException) -> bool:
    if isinstance(exc, RETRIABLE_ANSWER_ERRORS):
        return True
    if isinstance(exc, TelegramNetworkError) and exc.__cause__ is not None:
        return isinstance(exc.__cause__, RETRIABLE_ANSWER_ERRORS)
    return False


async def safe_answer(
    message: Message,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | ReplyKeyboardMarkup | None = None,
    parse_mode: str | None = None,
    **kwargs: Any,
) -> bool:
    """
    Send message.answer with retries on temporary network failures.
    Returns True when sent, False when all attempts fail (bot keeps running).
    """
    max_attempts = len(SAFE_ANSWER_RETRY_DELAYS_SECONDS) + 1
    last_error: BaseException | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            await message.answer(
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                **kwargs,
            )
            return True
        except Exception as exc:
            if not _is_retriable_answer_error(exc):
                logger.exception(
                    "Non-retriable error sending message to chat_id=%s",
                    message.chat.id,
                )
                return False
            last_error = exc
            if attempt >= max_attempts:
                break
            delay = SAFE_ANSWER_RETRY_DELAYS_SECONDS[attempt - 1]
            logger.warning(
                "Telegram answer failed for chat_id=%s (attempt %s/%s): %s. "
                "Retrying in %ss...",
                message.chat.id,
                attempt,
                max_attempts,
                exc,
                delay,
            )
            await asyncio.sleep(delay)

    logger.error(
        "Failed to send Telegram answer to chat_id=%s after %s attempts: %s",
        message.chat.id,
        max_attempts,
        last_error,
        exc_info=last_error,
    )
    return False


def build_webapp_url(base_url: str, telegram_user_id: int) -> str:
    """Legacy helper: append tg_id to base URL path/query."""
    parsed = urlparse(base_url)
    path = parsed.path or "/"
    query = parse_qs(parsed.query)
    query["tg_id"] = [str(telegram_user_id)]
    return urlunparse(
        parsed._replace(path=path, query=urlencode(query, doseq=True))
    )


def build_test_webapp_url(path: str, telegram_user_id: int) -> str:
    """WEBAPP_BASE_URL + path + ?tg_id=... (preserves existing query params)."""
    normalized_path = path if path.startswith("/") else f"/{path}"
    full_url = f"{WEBAPP_BASE_URL}{normalized_path}"
    parsed = urlparse(full_url)
    query = parse_qs(parsed.query)
    query["tg_id"] = [str(telegram_user_id)]
    return urlunparse(
        parsed._replace(query=urlencode(query, doseq=True))
    )


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=BTN_LOVE),
                KeyboardButton(text=BTN_MBTI),
            ],
            [KeyboardButton(text=BTN_STRESS)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Testlardan birini tanlang...",
    )


def test_start_keyboard(product: TestProduct, telegram_user_id: int) -> InlineKeyboardMarkup:
    webapp_url = build_test_webapp_url(product.path, telegram_user_id)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=product.start_button,
                    web_app=WebAppInfo(url=webapp_url),
                )
            ]
        ]
    )


def build_admin_panel_url() -> str | None:
    if not is_webapp_configured(WEBAPP_BASE_URL):
        return None
    token = quote(ADMIN_TOKEN or "", safe="")
    return f"{WEBAPP_BASE_URL}/admin/dashboard?token={token}"


def build_bot_tracking_dashboard_url() -> str:
    token = quote(ADMIN_TOKEN or "", safe="")
    base = BOT_ADMIN_BASE_URL or f"http://127.0.0.1:{BOT_ADMIN_PORT}"
    return f"{base}/admin/bot-tracking?token={token}"


def is_admin_chat(chat_id: int) -> bool:
    return ADMIN_CHAT_ID > 0 and chat_id == ADMIN_CHAT_ID


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="📊 Statistika",
                callback_data="admin:stats",
            )
        ],
        [
            InlineKeyboardButton(
                text="💳 Premium so‘rovlar",
                callback_data="admin:pending",
            )
        ],
        [
            InlineKeyboardButton(
                text="📈 Bot /start tracking",
                callback_data="admin:bot_tracking",
            )
        ],
        [
            InlineKeyboardButton(
                text="🌐 Bot tracking panel",
                url=build_bot_tracking_dashboard_url(),
            )
        ],
    ]
    admin_panel_url = build_admin_panel_url()
    if admin_panel_url:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🌐 Web admin panel",
                    url=admin_panel_url,
                )
            ],
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def admin_api_get(path: str) -> tuple[object | None, str | None]:
    if not ADMIN_TOKEN:
        return None, "ADMIN_TOKEN sozlanmagan."
    if not is_webapp_configured(WEBAPP_BASE_URL):
        return None, WEBAPP_NOT_CONFIGURED_TEXT

    url = f"{WEBAPP_BASE_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, params={"token": ADMIN_TOKEN})
    except (httpx.RequestError, httpx.TimeoutException):
        logger.exception("Admin API unreachable: %s", path)
        return None, ERR_OFFLINE

    if response.status_code == 401:
        return None, ERR_UNAUTHORIZED
    if response.status_code >= 400:
        logger.warning("Admin API error %s for %s", response.status_code, path)
        return None, f"Server xatosi ({response.status_code})."

    try:
        return response.json(), None
    except ValueError:
        logger.exception("Admin API invalid JSON: %s", path)
        return None, ERR_INVALID_JSON


def _save_bot_start_sync(
    *,
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
    language_code: str | None,
    start_param: str | None,
) -> None:
    db = SessionLocal()
    try:
        save_bot_start_event(
            db=db,
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language_code=language_code,
            start_param=start_param,
        )
    finally:
        db.close()


async def record_bot_start(user, start_param: str | None) -> None:
    try:
        await asyncio.to_thread(
            _save_bot_start_sync,
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            language_code=user.language_code,
            start_param=start_param,
        )
    except Exception:
        logger.exception("Failed to record bot start for user %s", user.id)


def _save_bot_test_click_sync(
    *,
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    selected_test: str,
) -> None:
    db = SessionLocal()
    try:
        save_bot_test_click_event(
            db=db,
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            selected_test=selected_test,
        )
    finally:
        db.close()


async def record_bot_test_click(user, selected_test: str) -> None:
    try:
        await asyncio.to_thread(
            _save_bot_test_click_sync,
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            selected_test=selected_test,
        )
    except Exception:
        logger.exception(
            "Failed to record bot test click for user %s test=%s",
            user.id,
            selected_test,
        )


def _load_bot_tracking_stats():
    db = SessionLocal()
    try:
        return {
            "bot_tracking": get_bot_tracking_dashboard_stats(db=db),
            "relationship_funnel": get_relationship_funnel_stats(db=db),
        }
    finally:
        db.close()


def format_relationship_funnel_stats(stats: dict) -> str:
    lines = [
        "",
        "<b>Munosabat taklif voronkasi:</b>",
        f"• invite_created: <b>{stats.get('invite_created', 0)}</b>",
        f"• partner_deeplink_opened: <b>{stats.get('partner_deeplink_opened', 0)}</b>",
        f"• partner_start_clicked: <b>{stats.get('partner_start_clicked', 0)}</b>",
        f"• partner_test_started: <b>{stats.get('partner_test_started', 0)}</b>",
        f"• partner_test_completed: <b>{stats.get('partner_test_completed', 0)}</b>",
        f"• result_ready: <b>{stats.get('result_ready', 0)}</b>",
        f"• user1_result_opened: <b>{stats.get('user1_result_opened', 0)}</b>",
        f"• deeplink/invite: <b>{stats.get('conversion_deeplink_per_invite', 0)}%</b>",
        f"• start/deeplink: <b>{stats.get('conversion_start_per_deeplink', 0)}%</b>",
        f"• completed/started: <b>{stats.get('conversion_completed_per_started', 0)}%</b>",
    ]
    return "\n".join(lines)


def format_bot_tracking_stats(stats_bundle: dict) -> str:
    stats = stats_bundle.get("bot_tracking") or stats_bundle
    rel = stats_bundle.get("relationship_funnel") or {}
    lines = [
        "📈 <b>Bot /start tracking</b>\n",
        f"👥 Jami foydalanuvchilar: <b>{stats['total_bot_users']}</b>",
        f"📅 Bugun /start: <b>{stats['today_bot_starts']}</b>",
        f"🗓 So‘nggi 7 kun: <b>{stats['last_7_days_bot_starts']}</b>",
        "",
        "<b>Top manbalar:</b>",
    ]
    top_sources = stats.get("top_sources") or []
    if top_sources:
        for row in top_sources[:10]:
            lines.append(f"• <code>{row['source']}</code>: {row['count']}")
    else:
        lines.append("• hali yo‘q")

    lines.extend(["", "<b>So‘nggi 5 start:</b>"])
    latest = stats.get("latest_start_events") or []
    if latest:
        for event in latest[:5]:
            name = event.get("first_name") or "—"
            source = event.get("source") or "direct"
            count = event.get("start_count")
            count_text = f", starts={count}" if count is not None else ""
            lines.append(
                f"• {event['created_at'].strftime('%m-%d %H:%M')} "
                f"{name} / <code>{source}</code>{count_text}"
            )
    else:
        lines.append("• hali yo‘q")

    lines.extend(["", "<b>Kampaniya havolalari:</b>"])
    for link in stats.get("campaign_link_examples") or []:
        lines.append(f"• <code>{link}</code>")

    lines.extend(
        [
            "",
            "<b>Test tugma bosishlari:</b>",
            f"• Jami: <b>{stats.get('total_test_clicks', 0)}</b>",
            f"• Love: <b>{stats.get('love_test_clicks', 0)}</b>",
            f"• MBTI: <b>{stats.get('mbti_test_clicks', 0)}</b>",
            f"• Stress: <b>{stats.get('stress_test_clicks', 0)}</b>",
            "",
            f"🌐 To‘liq panel: {build_bot_tracking_dashboard_url()}",
        ]
    )
    if rel:
        lines.append(format_relationship_funnel_stats(rel))
    return "\n".join(lines)


async def send_bot_tracking(target: Message) -> None:
    try:
        stats = await asyncio.to_thread(_load_bot_tracking_stats)
    except Exception:
        logger.exception("Failed to load bot tracking stats")
        await target.answer("Bot tracking statistikasini yuklab bo‘lmadi.")
        return
    await target.answer(format_bot_tracking_stats(stats), parse_mode="HTML")


def format_stats(data: dict) -> str:
    lines = ["📊 <b>Qadam statistikasi</b>\n"]
    for key, label in STAT_LABELS.items():
        value = data.get(key, 0)
        lines.append(f"{label}: <b>{value}</b>")
    return "\n".join(lines)


def format_pending_item(index: int, item: dict) -> str:
    test_type = item.get("test_type") or "—"
    token = item.get("token") or "—"
    status = item.get("payment_status") or "—"
    creator_id = item.get("creator_telegram_id")
    creator_line = (
        f"\n👤 Telegram ID: <code>{creator_id}</code>" if creator_id else ""
    )
    return (
        f"<b>{index}.</b> {test_type}\n"
        f"🔑 Token: <code>{token}</code>\n"
        f"📌 Holat: {status}{creator_line}"
    )


def pending_keyboard(items: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for index, item in enumerate(items, start=1):
        dashboard_url = item.get("admin_dashboard_url")
        if dashboard_url:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"{index}. Admin panelda ochish",
                        url=dashboard_url,
                    )
                ]
            )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def send_stats(target: Message) -> None:
    data, error = await admin_api_get("/admin/api/stats")
    if error:
        await target.answer(error)
        return
    if not isinstance(data, dict):
        await target.answer(ERR_INVALID_JSON)
        return
    await target.answer(format_stats(data), parse_mode="HTML")


async def send_pending(target: Message) -> None:
    data, error = await admin_api_get("/admin/api/pending-payments")
    if error:
        await target.answer(error)
        return
    if not isinstance(data, list):
        await target.answer(ERR_INVALID_JSON)
        return
    if not data:
        await target.answer("Hozircha kutilayotgan premium so‘rovlar yo‘q.")
        return

    header = f"💳 <b>Kutilayotgan premium so‘rovlar</b> ({len(data)})\n"
    body = "\n\n".join(format_pending_item(i, item) for i, item in enumerate(data, 1))
    await target.answer(
        header + "\n" + body,
        parse_mode="HTML",
        reply_markup=pending_keyboard(data),
    )


async def cmd_start(message: Message, command: CommandObject) -> None:
    user = message.from_user
    start_param = (command.args or "").strip() or None
    invite_token = parse_relationship_invite_token(start_param)
    if invite_token:
        logger.info(
            "User %s opened relationship invite token=%s",
            user.id,
            invite_token,
        )
        await handle_relationship_invite_deeplink(
            message,
            invite_token,
            webapp_base_url=WEBAPP_BASE_URL,
            safe_answer=safe_answer,
        )
        return

    logger.info("User %s started bot start_param=%s", user.id, start_param or "direct")
    await record_bot_start(user, start_param)
    await safe_answer(message, WELCOME_TEXT, reply_markup=main_menu_keyboard())


async def on_product_selected(message: Message, product: TestProduct) -> None:
    user = message.from_user
    logger.info("User %s selected %s test", user.id, product.log_name)
    await record_bot_test_click(user, product.log_name)
    if not is_webapp_configured(WEBAPP_BASE_URL):
        await safe_answer(message, WEBAPP_NOT_CONFIGURED_TEXT)
        return
    await safe_answer(
        message,
        product.explanation,
        reply_markup=test_start_keyboard(product, user.id),
    )


async def on_love_selected(message: Message) -> None:
    await on_product_selected(message, PRODUCTS[BTN_LOVE])


async def on_mbti_selected(message: Message) -> None:
    await on_product_selected(message, PRODUCTS[BTN_MBTI])


async def on_stress_selected(message: Message) -> None:
    await on_product_selected(message, PRODUCTS[BTN_STRESS])


async def cmd_botstats(message: Message) -> None:
    if not is_admin_chat(message.chat.id):
        await message.answer(ADMIN_DENIED_TEXT)
        return
    await send_bot_tracking(message)


async def cmd_admin(message: Message) -> None:
    if not is_admin_chat(message.chat.id):
        await message.answer(ADMIN_DENIED_TEXT)
        return
    await message.answer(
        "🛠 <b>Admin panel</b>\nKerakli bo‘limni tanlang:",
        parse_mode="HTML",
        reply_markup=admin_menu_keyboard(),
    )


async def cmd_stats(message: Message) -> None:
    if not is_admin_chat(message.chat.id):
        await message.answer(ADMIN_DENIED_TEXT)
        return
    await send_stats(message)


async def cmd_pending(message: Message) -> None:
    if not is_admin_chat(message.chat.id):
        await message.answer(ADMIN_DENIED_TEXT)
        return
    await send_pending(message)


async def on_admin_callback(callback: CallbackQuery) -> None:
    if not is_admin_chat(callback.message.chat.id):
        await callback.answer(ADMIN_DENIED_TEXT, show_alert=True)
        return

    await callback.answer()
    if callback.data == "admin:stats":
        await send_stats(callback.message)
    elif callback.data == "admin:pending":
        await send_pending(callback.message)
    elif callback.data == "admin:bot_tracking":
        await send_bot_tracking(callback.message)


async def on_relationship_invite_start_callback(callback: CallbackQuery) -> None:
    await handle_relationship_invite_start_callback(
        callback,
        webapp_base_url=WEBAPP_BASE_URL,
        safe_answer=safe_answer,
    )


async def main() -> None:
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN must be set in .env")
        sys.exit(1)
    if not is_webapp_configured(WEBAPP_BASE_URL):
        logger.warning(
            "WEBAPP_BASE_URL is not set — bot will start, but test WebApp buttons are disabled",
        )
    if not ADMIN_TOKEN or not ADMIN_CHAT_ID:
        logger.warning("ADMIN_TOKEN or ADMIN_CHAT_ID not set — admin commands disabled")

    log_active_database_path()
    init_db()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.message.register(cmd_start, CommandStart())
    dp.message.register(on_love_selected, F.text == BTN_LOVE)
    dp.message.register(on_mbti_selected, F.text == BTN_MBTI)
    dp.message.register(on_stress_selected, F.text == BTN_STRESS)
    dp.message.register(cmd_admin, Command("admin"))
    dp.message.register(cmd_stats, Command("stats"))
    dp.message.register(cmd_pending, Command("pending"))
    dp.message.register(cmd_botstats, Command("botstats"))
    dp.callback_query.register(on_admin_callback, F.data.startswith("admin:"))
    dp.callback_query.register(
        on_relationship_invite_start_callback,
        F.data.startswith("rel_invite:start:"),
    )

    logger.info("Bot is starting (Qadam platform: love, mbti, stress)...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
