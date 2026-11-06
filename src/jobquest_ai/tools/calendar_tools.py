"""Calendar tools exposed to the authenticated career coach."""

import asyncio
import contextvars
import json
import logging
from datetime import datetime, timezone
from typing import Any

from langchain_core.tools import tool
from sqlalchemy.orm import Session

from jobquest_ai.database.models.calendar_connection import CalendarConnection
from jobquest_ai.mcp.client import (
    create_calendar_event_rest,
    delete_calendar_event_rest,
    list_calendar_events_rest,
    update_calendar_event_rest,
)

_calendar_context: contextvars.ContextVar[tuple[Session, int] | None] = contextvars.ContextVar(
    "jobquest_calendar_context", default=None
)
logger = logging.getLogger(__name__)


def set_calendar_context(db: Session, user_id: int):
    return _calendar_context.set((db, user_id))


def reset_calendar_context(token: contextvars.Token):
    _calendar_context.reset(token)


def _connection():
    context = _calendar_context.get()
    if context is None:
        return None
    db, user_id = context
    return db.query(CalendarConnection).filter_by(user_id=user_id).first()


@tool
def list_calendar_events_for_chat(query: str = "") -> str:
    """Find upcoming calendar events by optional title, location, or description.

    Use this before editing or deleting an event when the user gives a name
    instead of an event ID. Return the matching event IDs to the user.
    """
    logger.info("calendar_list_started query_length=%s", len(query))
    connection = _connection()
    if connection is None:
        return json.dumps({"success": False, "error": "Connect Google Calendar first."})
    now = datetime.now(timezone.utc)
    try:
        payload = asyncio.run(list_calendar_events_rest(connection.access_token, start_time=now.isoformat(), end_time=(now.replace(year=now.year + 1)).isoformat(), time_zone="Asia/Calcutta"))
        events = payload.get("events", [])
        terms = query.lower().split()
        if terms:
            events = [event for event in events if all(term in json.dumps(event).lower() for term in terms)]
        logger.info("calendar_list_completed event_count=%s", len(events))
        return json.dumps({"success": True, "events": [{"id": e.get("id"), "title": e.get("summary"), "start": e.get("start"), "end": e.get("end")} for e in events]}, default=str)
    except Exception as exc:
        logger.exception("calendar_list_failed")
        return json.dumps({"success": False, "error": str(exc)})


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

    Use ISO 8601 timestamps for start_time and end_time. The caller must pass
    the exact date, start time, end time, and timezone from the user's request;
    never use a default time. Ask a focused follow-up question if any required
    time detail is missing or ambiguous. Do not claim success unless this tool
    returns success=true.
    """
    logger.info("calendar_create_started title=%s", title)
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
    connection = _connection()
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
    logger.info("calendar_create_completed event_id=%s", result.get("id"))
    return json.dumps({
        "success": True,
        "event_id": result.get("id"),
        "title": result.get("summary", title.strip()),
        "start_time": result.get("start", {}).get("dateTime", start.isoformat()),
        "end_time": result.get("end", {}).get("dateTime", end.isoformat()),
        "calendar_link": result.get("htmlLink"),
    })


@tool
def update_calendar_event(
    event_id: str,
    title: str = "",
    start_time: str = "",
    end_time: str = "",
    description: str = "",
    location: str = "",
    confirmed: bool = False,
) -> str:
    """Edit a Google Calendar event after confirming the exact event and changes."""
    logger.info("calendar_update_started event_id=%s confirmed=%s", event_id, confirmed)
    connection = _connection()
    if connection is None:
        return json.dumps({"success": False, "error": "Connect Google Calendar first."})
    changes = {key: value for key, value in {"title": title, "start_time": start_time, "end_time": end_time, "description": description, "location": location}.items() if value}
    if not confirmed:
        return json.dumps({"success": False, "confirmation_required": True, "event_id": event_id, "changes": changes})
    try:
        result = asyncio.run(update_calendar_event_rest(connection.access_token, event_id=event_id, title=title or None, start_time=start_time or None, end_time=end_time or None, description=description or None, location=location or None))
        logger.info("calendar_update_completed event_id=%s", result.get("id"))
        return json.dumps({"success": True, "event_id": result.get("id"), "title": result.get("summary"), "calendar_link": result.get("htmlLink")})
    except Exception as exc:
        logger.exception("calendar_update_failed event_id=%s", event_id)
        logger.exception("calendar_create_failed")
        return json.dumps({"success": False, "error": str(exc)})


@tool
def delete_calendar_event(event_id: str, confirmed: bool = False) -> str:
    """Delete a Google Calendar event only after explicit user confirmation."""
    logger.info("calendar_delete_started event_id=%s confirmed=%s", event_id, confirmed)
    connection = _connection()
    if connection is None:
        return json.dumps({"success": False, "error": "Connect Google Calendar first."})
    if not confirmed:
        return json.dumps({"success": False, "confirmation_required": True, "event_id": event_id})
    try:
        asyncio.run(delete_calendar_event_rest(connection.access_token, event_id=event_id))
        logger.info("calendar_delete_completed event_id=%s", event_id)
        return json.dumps({"success": True, "event_id": event_id, "deleted": True})
    except Exception as exc:
        logger.exception("calendar_delete_failed event_id=%s", event_id)
        return json.dumps({"success": False, "error": str(exc)})


TOOLS = [list_calendar_events_for_chat, create_calendar_event, update_calendar_event, delete_calendar_event]
