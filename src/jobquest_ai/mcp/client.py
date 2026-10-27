
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
