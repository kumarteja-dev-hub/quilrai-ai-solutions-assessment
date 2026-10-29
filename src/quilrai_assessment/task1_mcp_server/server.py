from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any

from mcp import MCPError
from mcp.server import NotificationOptions, Server, ServerRequestContext
from mcp.server.stdio import stdio_server
from mcp.types import (
    INVALID_PARAMS,
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)
from pydantic import ValidationError

from .models import GetCustomerRecordInput, TriggerRefundInput
from .service import create_refund, get_customer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("quilrai.task1")

GET_CUSTOMER_TOOL = Tool(
    name="get_customer_record",
    description="Fetch a customer record by a strictly formatted CUST-XXXXX identifier.",
    input_schema=GetCustomerRecordInput.model_json_schema(),
)

TRIGGER_REFUND_TOOL = Tool(
    name="trigger_refund",
    description="Create a refund request after strict customer, amount, and reason validation.",
    input_schema=TriggerRefundInput.model_json_schema(),
)


def _validation_data(exc: ValidationError) -> dict[str, Any]:
    # Do not echo raw caller values in protocol errors. The location/message are enough
    # for a client to correct the request without leaking submitted content to logs/UI.
    return {
        "issues": [
            {"loc": list(error["loc"]), "type": error["type"], "msg": error["msg"]}
            for error in exc.errors(include_url=False)
        ]
    }


def _invalid_params(exc: ValidationError) -> MCPError:
    return MCPError(code=INVALID_PARAMS, message="Invalid params", data=_validation_data(exc))


async def list_tools(
    ctx: ServerRequestContext, params: PaginatedRequestParams | None
) -> ListToolsResult:
    del ctx, params
    return ListToolsResult(tools=[GET_CUSTOMER_TOOL, TRIGGER_REFUND_TOOL])


async def call_tool(ctx: ServerRequestContext, params: CallToolRequestParams) -> CallToolResult:
    del ctx
    arguments = params.arguments or {}

    if params.name == "get_customer_record":
        try:
            validated = GetCustomerRecordInput.model_validate(arguments)
        except ValidationError as exc:
            raise _invalid_params(exc) from exc
        payload = get_customer(validated.customer_id)
        logger.info("customer lookup completed customer_id=%s", validated.customer_id)

    elif params.name == "trigger_refund":
        try:
            validated = TriggerRefundInput.model_validate(arguments)
        except ValidationError as exc:
            raise _invalid_params(exc) from exc
        payload = create_refund(validated.customer_id, validated.amount, validated.reason)
        logger.info(
            "refund accepted customer_id=%s amount=%.2f",
            validated.customer_id,
            validated.amount,
        )
    else:
        raise MCPError(code=INVALID_PARAMS, message=f"Unknown tool: {params.name}")

    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payload, separators=(",", ":")))],
        structured_content=payload,
    )


server = Server(
    "quilrai-customer-tools",
    version="1.0.0",
    on_list_tools=list_tools,
    on_call_tool=call_tool,
)


async def main() -> None:
    # With stdio transport, stdout is the protocol wire. All diagnostics use logging,
    # which is explicitly configured for stderr above.
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(
                notification_options=NotificationOptions(tools_changed=False)
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
