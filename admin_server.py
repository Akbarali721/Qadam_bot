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

from api_schemas import RelationshipFunnelEventCreate, RelationshipPartnerCompletedPayload
from db.bot_tracking_service import get_bot_tracking_dashboard_stats
from db.database import get_db, init_db, log_active_database_path
from db.relationship_stats_service import get_relationship_funnel_stats
from relationship_api import (
    handle_partner_completed_api,
    handle_user1_result_opened_api,
    record_relationship_funnel_event_api,
)

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
ADMIN_TOKEN = (os.getenv("ADMIN_TOKEN") or "").strip()

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
        "relationship_funnel": get_relationship_funnel_stats(db=db),
    }
    template = templates.get_template("admin/bot_dashboard.html")
    return HTMLResponse(template.render(**context))


@app.post("/api/relationship/funnel-event")
def api_record_relationship_funnel_event(
    payload: RelationshipFunnelEventCreate,
    db: Session = Depends(get_db),
    _admin: None = Depends(verify_admin_token),
) -> dict[str, bool]:
    return record_relationship_funnel_event_api(db=db, payload=payload)


@app.post("/api/relationship/partner-completed")
def api_relationship_partner_completed(
    payload: RelationshipPartnerCompletedPayload,
    db: Session = Depends(get_db),
    _admin: None = Depends(verify_admin_token),
) -> dict[str, object]:
    return handle_partner_completed_api(db=db, payload=payload)


@app.post("/api/relationship/user1-result-opened")
def api_relationship_user1_result_opened(
    payload: RelationshipFunnelEventCreate,
    db: Session = Depends(get_db),
    _admin: None = Depends(verify_admin_token),
) -> dict[str, bool]:
    return handle_user1_result_opened_api(db=db, payload=payload)


def main() -> None:
    port = int(os.getenv("PORT", "8081"))
    log_active_database_path()
    init_db()
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    main()
