# Railway deployment (two services + shared PostgreSQL)

Deploy **qadam-bot** and **qadam-admin** as separate Railway services. Both must use the **same** `DATABASE_URL` from one PostgreSQL plugin.

## Architecture

| Service       | Start command              | Public networking        |
|---------------|----------------------------|--------------------------|
| `qadam-bot`   | `python bot.py`            | Not required (polling)   |
| `qadam-admin` | `python admin_server.py`   | Public domain required   |

SQLite (`BOT_DB_PATH`) is for **local development only**. On Railway, set `DATABASE_URL` on both services.

Tables are created automatically on startup via `init_db()` in `db/database.py`.

---

## 1. PostgreSQL

1. In your Railway project, add **PostgreSQL**.
2. Copy the plugin’s `DATABASE_URL` (often `postgres://...`).
3. The app normalizes it to `postgresql+psycopg2://...` for sync SQLAlchemy.

---

## 2. Service: `qadam-bot`

**Settings**

- **Start command:** `python bot.py`
- **Public networking:** disabled (Telegram long polling does not need an HTTP port)

**Variables** (minimum)

| Variable | Notes |
|----------|--------|
| `BOT_TOKEN` | Telegram bot token |
| `WEBAPP_BASE_URL` | Your main web app URL (tests WebApp) |
| `ADMIN_TOKEN` | Same value as admin service |
| `ADMIN_CHAT_ID` | Telegram chat ID for bot admin commands |
| `DATABASE_URL` | Shared PostgreSQL URL from plugin |
| `TELEGRAM_BOT_USERNAME` | For campaign deep links in `/botstats` |

Optional: `BOT_ADMIN_BASE_URL` — public URL of the **admin** service (for “open dashboard” links in Telegram).

Do **not** set `BOT_DB_PATH` in production when using PostgreSQL.

---

## 3. Service: `qadam-admin`

**Settings**

- **Start command:** `python admin_server.py`
- **Public networking:** enabled → generate a domain (e.g. `qadam-admin.up.railway.app`)

**Variables** (minimum)

| Variable | Notes |
|----------|--------|
| `ADMIN_TOKEN` | Same as bot service |
| `DATABASE_URL` | **Same** PostgreSQL URL as `qadam-bot` |
| `BOT_ADMIN_BASE_URL` | `https://<your-admin-service-domain>` (no trailing slash) |
| `BOT_ADMIN_HOST` | `0.0.0.0` |
| `PORT` | Set automatically by Railway |

Railway sets `PORT`; `admin_server.py` uses it when present.

**Dashboard URL**

```
https://<admin-domain>/admin/bot-tracking?token=<ADMIN_TOKEN>
```

---

## 4. Local development

**SQLite (default)**

```env
BOT_DB_PATH=bot_tracking.db
# DATABASE_URL unset
```

**Optional: local PostgreSQL**

```env
DATABASE_URL=postgresql://user:pass@localhost:5432/qadam_bot
```

Run:

```bash
pip install -r requirements.txt
python bot.py
python admin_server.py
```

---

## 5. Verify after deploy

1. Send `/start` and tap a test button in Telegram.
2. Open the admin dashboard URL; confirm starts and test clicks appear.
3. Check logs for:
   - `Active database (PostgreSQL): postgresql (DATABASE_URL)`

---

## 6. Tests (local)

```bash
python scripts/test_bot_db_path.py
python scripts/test_database_config.py
python scripts/test_bot_tracking.py
```
