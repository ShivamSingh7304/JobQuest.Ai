"""Calendar tools exposed to the authenticated career coach."""

import asyncio
import contextvars
import json
from datetime import datetime, timezone
from typing import Any

from langchain_core.tools import tool
from sqlalchemy.orm import Session

from jobquest_ai.database.models.calendar_connection import CalendarConnection
from jobquest_ai.mcp.client import create_calendar_event_rest

_calendar_context: contextvars.ContextVar[tuple[Session, int] | None] = contextvars.ContextVar(
    "jobquest_calendar_context", default=None
)


def set_calendar_context(db: Session, user_id: int):
    return _calendar_context.set((db, user_id))


def reset_calendar_context(token: contextvars.Token):
    _calendar_context.reset(token)


@tool
def create_calendar_event(
    title: str,
    start_time: str,
    end_time: str,
    description: str = "",
    location: str = "",
    time_zone: str = "Asia/Calcutta",
) -> str:
    """Create a Google Calendar event after the user clearly requests scheduling it.

    Use ISO 8601 timestamps for start_time and end_time. Ask a focused
    follow-up question if the date, start time, or duration is missing. Do not
    claim success unless this tool returns success=true.
    """
    context = _calendar_context.get()
    if context is None:
        return json.dumps({"success": False, "error": "Calendar context is unavailable."})
    if not title.strip() or not start_time.strip() or not end_time.strip():
        return json.dumps({"success": False, "error": "title, start_time, and end_time are required."})
    try:
        start = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
    except ValueError:
        return json.dumps({"success": False, "error": "Use ISO 8601 timestamps for the event times."})
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    if end <= start:
        return json.dumps({"success": False, "error": "end_time must be after start_time."})

    db, user_id = context
    connection = db.query(CalendarConnection).filter_by(user_id=user_id).first()
    if connection is None:
        return json.dumps({"success": False, "error": "Connect Google Calendar before scheduling an event."})
    try:
        result = asyncio.run(create_calendar_event_rest(
            connection.access_token,
            title=title.strip(),
            start_time=start.isoformat(),
            end_time=end.isoformat(),
            description=description.strip(),
            location=location.strip(),
            time_zone=time_zone,
        ))
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)})
    return json.dumps({
        "success": True,
        "event_id": result.get("id"),
        "title": result.get("summary", title.strip()),
        "start_time": result.get("start", {}).get("dateTime", start.isoformat()),
        "end_time": result.get("end", {}).get("dateTime", end.isoformat()),
        "calendar_link": result.get("htmlLink"),
    })


TOOLS = [create_calendar_event]
