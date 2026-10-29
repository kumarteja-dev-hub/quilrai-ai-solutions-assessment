from __future__ import annotations

import sys

import pytest

mcp = pytest.importorskip("mcp")

from mcp import Client, MCPError, StdioServerParameters  # noqa: E402
from mcp.types import INVALID_PARAMS  # noqa: E402


@pytest.mark.asyncio
async def test_stdio_server_protocol_and_invalid_params_error() -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "quilrai_assessment.task1_mcp_server.server"],
    )
    async with Client(params) as client:
        tools = await client.list_tools()
        assert {tool.name for tool in tools.tools} == {"get_customer_record", "trigger_refund"}

        with pytest.raises(MCPError) as exc_info:
            await client.call_tool("get_customer_record", {"customer_id": "BAD-12345"})
        assert exc_info.value.code == INVALID_PARAMS
