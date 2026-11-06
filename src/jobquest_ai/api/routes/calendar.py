import asyncio
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from jobquest_ai.api.schemas import CalendarConnectionResponse, CalendarEventResponse, CalendarEventsResponse
from jobquest_ai.auth.dependencies import get_current_user
from jobquest_ai.database.connection import get_db
from jobquest_ai.database.models.calendar_connection import CalendarConnection
from jobquest_ai.database.models.user import User
from jobquest_ai.mcp.client import list_calendar_events, list_calendar_events_rest

router = APIRouter(prefix="/calendar", tags=["Calendar"])
PROJECT_ROOT = Path(__file__).resolve().parents[4]
load_dotenv(PROJECT_ROOT / ".env")
_configured_client_file = Path(os.getenv("GOOGLE_OAUTH_CLIENT_FILE", "oauth-client.json")).expanduser()
CLIENT_FILE = _configured_client_file if _configured_client_file.is_absolute() else PROJECT_ROOT / _configured_client_file
REDIRECT_URI = os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:8000/calendar/oauth2callback")
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
_pending_flows: dict[str, tuple[int, Flow]] = {}


def _new_flow() -> Flow:
    if not CLIENT_FILE.is_file():
        raise HTTPException(status_code=503, detail="Google OAuth credentials are not configured.")
    return Flow.from_client_secrets_file(str(CLIENT_FILE), scopes=SCOPES, redirect_uri=REDIRECT_URI)


def _oauth_client_details() -> tuple[str, str]:
    config = json.loads(CLIENT_FILE.read_text(encoding="utf-8"))
    details = config.get("web") or config.get("installed") or {}
    return details.get("client_id"), details.get("client_secret")


@router.get("/status", response_model=CalendarConnectionResponse)
def calendar_status(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    connected = db.query(CalendarConnection).filter_by(user_id=current_user.id).first() is not None
    return CalendarConnectionResponse(connected=connected)


@router.post("/connect", response_model=CalendarConnectionResponse)
def connect_calendar(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    flow = _new_flow()
    state = secrets.token_urlsafe(32)
    auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent", state=state)
    _pending_flows[state] = (current_user.id, flow)
    return CalendarConnectionResponse(connected=False, authorization_url=auth_url)


@router.get("/oauth2callback", response_class=HTMLResponse, include_in_schema=False)
def calendar_callback(code: str | None = None, state: str | None = None, error: str | None = None, db: Session = Depends(get_db)):
    pending = _pending_flows.pop(state or "", None)
    if error or pending is None or not code:
        return HTMLResponse("Google Calendar connection was cancelled. You can close this tab.", status_code=400)
    user_id, flow = pending
    try:
        flow.fetch_token(code=code)
        credentials = flow.credentials
        connection = db.query(CalendarConnection).filter_by(user_id=user_id).first()
        if connection is None:
            connection = CalendarConnection(user_id=user_id)
            db.add(connection)
        connection.access_token = credentials.token
        connection.refresh_token = credentials.refresh_token
        connection.token_expiry = credentials.expiry
        db.commit()
    except Exception:
        db.rollback()
        return HTMLResponse("Google Calendar connection failed. You can close this tab and try again.", status_code=400)
    return HTMLResponse("Google Calendar connected. Return to JobQuest.Ai and refresh the Calendar page.")


def _event_time(value: dict) -> tuple[str, bool]:
    if value.get("date"):
        return value["date"], True
    return value.get("dateTime", ""), False


def _format_time(value: str, all_day: bool) -> tuple[str, str]:
    if all_day:
        return value[:10], "All day"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        day = parsed.strftime("%a, %b %d").replace(" 0", " ")
        return day, parsed.astimezone().strftime("%I:%M %p").lstrip("0")
    except ValueError:
        return value[:10], value


@router.get("/events", response_model=CalendarEventsResponse)
def calendar_events(days: int = Query(default=14, ge=1, le=60), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    connection = db.query(CalendarConnection).filter_by(user_id=current_user.id).first()
    time_zone = "Asia/Calcutta"
    if connection is None:
        return CalendarEventsResponse(connected=False, time_zone=time_zone, events=[])
    token_expiry = connection.token_expiry
    if token_expiry and token_expiry.tzinfo is None:
        # SQLite returns DateTime values without timezone information.
        token_expiry = token_expiry.replace(tzinfo=timezone.utc)
    if token_expiry and token_expiry <= datetime.now(timezone.utc) and connection.refresh_token:
        try:
            client_id, client_secret = _oauth_client_details()
            credentials = Credentials(token=connection.access_token, refresh_token=connection.refresh_token, token_uri="https://oauth2.googleapis.com/token", client_id=client_id, client_secret=client_secret, scopes=SCOPES)
            credentials.refresh(Request())
            connection.access_token = credentials.token
            connection.token_expiry = credentials.expiry
            db.commit()
        except Exception as exc:
            raise HTTPException(status_code=401, detail="Google Calendar authorization expired. Please reconnect.") from exc
    now = datetime.now(timezone.utc)
    try:
        payload = asyncio.run(list_calendar_events(connection.access_token, start_time=now.isoformat(), end_time=(now + timedelta(days=days)).isoformat(), time_zone=time_zone))
    except RuntimeError as exc:
        if "Developer Preview" not in str(exc):
            raise HTTPException(status_code=502, detail=f"Google Calendar could not be loaded: {exc}") from exc
        try:
            payload = asyncio.run(list_calendar_events_rest(connection.access_token, start_time=now.isoformat(), end_time=(now + timedelta(days=days)).isoformat(), time_zone=time_zone))
        except Exception as fallback_exc:
            raise HTTPException(status_code=502, detail=f"Google Calendar could not be loaded: {fallback_exc}") from fallback_exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Google Calendar could not be loaded: {exc}") from exc
    events = []
    for item in payload.get("events", []):
        start, all_day = _event_time(item.get("start") or {})
        end, _ = _event_time(item.get("end") or {})
        date_label, time_label = _format_time(start, all_day)
        events.append(CalendarEventResponse(id=str(item.get("id", secrets.token_urlsafe(6))), title=item.get("summary") or "Untitled event", start=start, end=end, date_label=date_label, time_label=time_label, location=item.get("location"), description=item.get("description"), link=item.get("htmlLink"), conference_url=item.get("conferenceUrl"), all_day=all_day))
    return CalendarEventsResponse(connected=True, time_zone=payload.get("timeZone", time_zone), calendar_name=payload.get("summary"), events=events)
