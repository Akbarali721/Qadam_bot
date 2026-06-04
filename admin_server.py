"""Local admin dashboard for bot /start tracking (runs inside test_MVP_Bot only)."""

import hmac
import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

from db.bot_tracking_service import get_bot_tracking_dashboard_stats
from db.database import get_db, init_db, log_active_database_path

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
ADMIN_TOKEN = (os.getenv("ADMIN_TOKEN") or "").strip()
BOT_ADMIN_HOST = os.getenv(
    "BOT_ADMIN_HOST",
    "0.0.0.0" if os.getenv("PORT") else "127.0.0.1",
)
BOT_ADMIN_PORT = int(os.getenv("PORT") or os.getenv("BOT_ADMIN_PORT", "8081") or "8081")

templates = Environment(
    loader=FileSystemLoader(str(BASE_DIR / "templates")),
    autoescape=select_autoescape(["html", "xml"]),
)

app = FastAPI(title="Qadam Bot Admin")


def verify_admin_token(
    token: str | None = Query(default=None),
) -> None:
    if not ADMIN_TOKEN:
        raise HTTPException(status_code=503, detail="ADMIN_TOKEN is not configured")
    if not token or not hmac.compare_digest(token, ADMIN_TOKEN):
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.on_event("startup")
def on_startup() -> None:
    log_active_database_path()
    init_db()


@app.get("/admin/bot-tracking", response_class=HTMLResponse)
def bot_tracking_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    _admin: None = Depends(verify_admin_token),
):
    context = {
        "request": request,
        "bot_tracking": get_bot_tracking_dashboard_stats(db=db),
    }
    template = templates.get_template("admin/bot_dashboard.html")
    return HTMLResponse(template.render(**context))


def main() -> None:
    log_active_database_path()
    init_db()
    uvicorn.run(
        "admin_server:app",
        host=BOT_ADMIN_HOST,
        port=BOT_ADMIN_PORT,
        reload=False,
    )


if __name__ == "__main__":
    main()
