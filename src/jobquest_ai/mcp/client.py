
import json
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

CALENDAR_MCP_URL = (
    "https://calendarmcp.googleapis.com/mcp/v1"
)


async def inspect_calendar_server(access_token: str):
    """Connect with an existing OAuth access token and list tools."""

    async with streamablehttp_client(
        CALENDAR_MCP_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
        },
    ) as (read_stream, write_stream, _):
        async with ClientSession(
            read_stream, write_stream
        ) as session:
            await session.initialize()

            result = await session.list_tools()

            return [
                {
                    "name": tool.name,
                    "description": tool.description or "",
                }
                for tool in result.tools
            ]


async def list_calendar_events(
    access_token: str,
    *,
    start_time: str,
    end_time: str,
    time_zone: str = "Asia/Calcutta",
    page_size: int = 50,
):
    """Read upcoming events from Google's hosted Calendar MCP server."""
    async with streamablehttp_client(
        CALENDAR_MCP_URL,
        headers={"Authorization": f"Bearer {access_token}"},
    ) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(
                "list_events",
                arguments={
                    "startTime": start_time,
                    "endTime": end_time,
                    "timeZone": time_zone,
                    "orderBy": "startTime",
                    "pageSize": page_size,
                },
            )

    if getattr(result, "isError", False):
        details = []
        for item in getattr(result, "content", []):
            text = getattr(item, "text", None)
            if isinstance(text, str) and text.strip():
                details.append(text.strip())
        message = " ".join(details) or "Google Calendar MCP returned an error."
        raise RuntimeError(message)
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured
    for item in getattr(result, "content", []):
        text = getattr(item, "text", None)
        if isinstance(text, str):
            try:
                decoded = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(decoded, dict):
                return decoded
    raise RuntimeError("Google Calendar MCP returned an unreadable response.")


async def list_calendar_events_rest(
    access_token: str,
    *,
    start_time: str,
    end_time: str,
    time_zone: str = "Asia/Calcutta",
    page_size: int = 50,
):
    """Fallback reader using the stable Calendar REST API.

    Google's hosted Calendar MCP is currently limited to Workspace Developer
    Preview projects. The same read-only OAuth scope can read events through
    this endpoint while MCP access is pending.
    """
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "timeMin": start_time,
                "timeMax": end_time,
                "timeZone": time_zone,
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": page_size,
            },
        )
    if response.is_error:
        raise RuntimeError(
            f"Google Calendar REST returned HTTP {response.status_code}."
        )
    payload = response.json()
    return {
        "summary": payload.get("summary"),
        "timeZone": payload.get("timeZone", time_zone),
        "events": payload.get("items", []),
    }


async def create_calendar_event_rest(
    access_token: str,
    *,
    title: str,
    start_time: str,
    end_time: str,
    description: str = "",
    location: str = "",
    time_zone: str = "Asia/Calcutta",
):
    """Create an event through Google Calendar's events.insert endpoint."""
    body: dict[str, Any] = {
        "summary": title,
        "start": {"dateTime": start_time, "timeZone": time_zone},
        "end": {"dateTime": end_time, "timeZone": time_zone},
    }
    if description:
        body["description"] = description
    if location:
        body["location"] = location
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"sendUpdates": "all"},
            json=body,
        )
    if response.is_error:
        if response.status_code in {401, 403}:
            raise RuntimeError("Calendar write access is not authorized. Reconnect Google Calendar and approve event creation.")
        raise RuntimeError(f"Google Calendar returned HTTP {response.status_code}.")
    return response.json()
