import asyncio
import logging
import os
import sys
from dataclasses import dataclass
from urllib.parse import parse_qs, quote, urlencode, urlparse, urlunparse

import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
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

ADMIN_DENIED_TEXT = "Bu bo‘lim faqat admin uchun."
ERR_OFFLINE = "Web ilova hozir ishlamayapti. Keyinroq urinib ko‘ring."
ERR_UNAUTHORIZED = "Admin token noto‘g‘ri yoki ruxsat yo‘q."
ERR_INVALID_JSON = "Server noto‘g‘ri javob qaytardi."

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


def build_admin_panel_url() -> str:
    token = quote(ADMIN_TOKEN or "", safe="")
    return f"{WEBAPP_BASE_URL}/admin/dashboard?token={token}"


def is_admin_chat(chat_id: int) -> bool:
    return ADMIN_CHAT_ID > 0 and chat_id == ADMIN_CHAT_ID


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
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
                    text="🌐 Web admin panel",
                    url=build_admin_panel_url(),
                )
            ],
        ]
    )


async def admin_api_get(path: str) -> tuple[object | None, str | None]:
    if not ADMIN_TOKEN:
        return None, "ADMIN_TOKEN sozlanmagan."

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


async def cmd_start(message: Message) -> None:
    user_id = message.from_user.id
    logger.info("User %s started bot", user_id)
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_keyboard())


async def on_product_selected(message: Message, product: TestProduct) -> None:
    user_id = message.from_user.id
    logger.info("User %s selected %s test", user_id, product.log_name)
    await message.answer(
        product.explanation,
        reply_markup=test_start_keyboard(product, user_id),
    )


async def on_love_selected(message: Message) -> None:
    await on_product_selected(message, PRODUCTS[BTN_LOVE])


async def on_mbti_selected(message: Message) -> None:
    await on_product_selected(message, PRODUCTS[BTN_MBTI])


async def on_stress_selected(message: Message) -> None:
    await on_product_selected(message, PRODUCTS[BTN_STRESS])


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


async def main() -> None:
    if not BOT_TOKEN or not WEBAPP_BASE_URL:
        logger.error("BOT_TOKEN and WEBAPP_BASE_URL must be set in .env")
        sys.exit(1)
    if not ADMIN_TOKEN or not ADMIN_CHAT_ID:
        logger.warning("ADMIN_TOKEN or ADMIN_CHAT_ID not set — admin commands disabled")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.message.register(cmd_start, CommandStart())
    dp.message.register(on_love_selected, F.text == BTN_LOVE)
    dp.message.register(on_mbti_selected, F.text == BTN_MBTI)
    dp.message.register(on_stress_selected, F.text == BTN_STRESS)
    dp.message.register(cmd_admin, Command("admin"))
    dp.message.register(cmd_stats, Command("stats"))
    dp.message.register(cmd_pending, Command("pending"))
    dp.callback_query.register(on_admin_callback, F.data.startswith("admin:"))

    logger.info("Bot is starting (Qadam platform: love, mbti, stress)...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
