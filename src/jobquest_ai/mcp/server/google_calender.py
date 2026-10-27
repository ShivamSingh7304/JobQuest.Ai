import asyncio
import json
import os
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from google_auth_oauthlib.flow import Flow
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

PROJECT_ROOT = Path(__file__).resolve().parents[4]
CLIENT_FILE = Path(
    os.environ.get(
        "GOOGLE_OAUTH_CLIENT_FILE",
        str(PROJECT_ROOT / "oauth-client.json"),
    )
).expanduser()

REDIRECT_URI = "http://localhost:8080/oauth2callback"
MCP_URL = "https://calendarmcp.googleapis.com/mcp/v1"
OAUTH_TIMEOUT_SECONDS = 180

SCOPES = [
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    "https://www.googleapis.com/auth/calendar.events.freebusy",
    "https://www.googleapis.com/auth/calendar.events.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]

callback_result: dict[str, str | None] = {}
callback_received = threading.Event()


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != "/oauth2callback":
            self.send_error(404)
            return

        params = parse_qs(parsed.query)
        callback_result["code"] = params.get("code", [None])[0]
        callback_result["state"] = params.get("state", [None])[0]
        callback_result["error"] = params.get("error", [None])[0]

        self.send_response(400 if callback_result["error"] else 200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            b"Google authorization failed."
            if callback_result["error"]
            else b"Google sign-in complete. Return to JobQuest.Ai."
        )
        callback_received.set()

    def log_message(self, format, *args):
        pass


def authorize():
    if not CLIENT_FILE.is_file():
        raise FileNotFoundError(
            "OAuth credentials not found. Set GOOGLE_OAUTH_CLIENT_FILE "
            "or place oauth-client.json in the project root."
        )

    config = json.loads(CLIENT_FILE.read_text(encoding="utf-8"))
    if "web" not in config:
        raise ValueError(
            "Expected a Web application OAuth JSON with a top-level 'web' object."
        )

    flow = Flow.from_client_secrets_file(
        str(CLIENT_FILE),
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    auth_url, expected_state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
    )

    callback_result.clear()
    callback_received.clear()
    try:
        server = HTTPServer(("localhost", 8080), OAuthCallbackHandler)
    except OSError as exc:
        raise RuntimeError(
            "Could not start the OAuth callback server on localhost:8080. "
            "Close the process using that port and try again."
        ) from exc

    server.timeout = 1
    try:
        print("Opening Google sign-in...")
        if not webbrowser.open(auth_url):
            print(f"Open this URL in your browser to continue:\n{auth_url}")

        deadline = time.monotonic() + OAUTH_TIMEOUT_SECONDS
        while not callback_received.is_set() and time.monotonic() < deadline:
            server.handle_request()
    finally:
        server.server_close()

    if not callback_received.is_set():
        raise TimeoutError(
            "Google sign-in timed out. Run the command again and complete "
            "authorization within three minutes."
        )

    if callback_result.get("error"):
        raise RuntimeError(
            f"Google authorization failed: {callback_result['error']}"
        )
    if callback_result.get("state") != expected_state:
        raise RuntimeError(
            "OAuth state validation failed. Restart the sign-in flow."
        )

    code = callback_result.get("code")
    if not code:
        raise RuntimeError("Google did not return an authorization code.")

    flow.fetch_token(code=code)
    print("OAuth authorization succeeded.")
    return flow.credentials


async def test_mcp(access_token: str):
    if not access_token:
        raise ValueError("Google OAuth returned an empty access token.")

    print("Connecting to Google Calendar MCP...")
    async with streamablehttp_client(
        MCP_URL,
        headers={"Authorization": f"Bearer {access_token}"},
    ) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.list_tools()

    print("\nSUCCESS: MCP handshake completed.")
    print("Available Calendar tools:")
    for tool in result.tools:
        print(f"- {tool.name}: {tool.description or ''}")
    return result.tools


def main():
    print("1. Starting Google OAuth...")
    credentials = authorize()
    print("2. Access token obtained.")
    print("3. Testing MCP connection...")
    asyncio.run(test_mcp(credentials.token))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nTEST FAILED ({type(exc).__name__}): {exc}")
        raise SystemExit(1) from exc
