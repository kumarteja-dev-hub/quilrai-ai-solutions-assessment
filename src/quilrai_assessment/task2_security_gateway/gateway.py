from __future__ import annotations

import logging
from typing import Any

import httpx
from pydantic import ValidationError

from .auth import Principal
from .models import JSONRPCRequest

logger = logging.getLogger("quilrai.task2")

UNAUTHORIZED_TOOL_CODE = -32001
INVALID_REQUEST_CODE = -32600


def jsonrpc_error(request_id: str | int | None, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "error": {"code": code, "message": message},
        "id": request_id,
    }


class SecurityGateway:
    def __init__(self, downstream_url: str, client: httpx.AsyncClient) -> None:
        self.downstream_url = downstream_url
        self.client = client

    async def handle(self, payload: dict[str, Any], principal: Principal) -> tuple[int, Any]:
        request_id = payload.get("id") if isinstance(payload, dict) else None
        try:
            request = JSONRPCRequest.model_validate(payload)
        except ValidationError:
            return 400, jsonrpc_error(request_id, INVALID_REQUEST_CODE, "Invalid Request")

        if request.method == "tools/call":
            params = request.params or {}
            tool_name = params.get("name")
            if not isinstance(tool_name, str):
                return 400, jsonrpc_error(request.id, -32602, "Invalid params")
            if tool_name.startswith("admin_") and principal.role != "admin":
                logger.warning(
                    "blocked unauthorized tool call subject=%s role=%s tool=%s",
                    principal.subject,
                    principal.role,
                    tool_name,
                )
                return 200, jsonrpc_error(
                    request.id,
                    UNAUTHORIZED_TOOL_CODE,
                    "Unauthorized Tool Call",
                )

        # tools/list and every non-blocked method are transparently forwarded.
        try:
            response = await self.client.post(self.downstream_url, json=payload)
        except httpx.RequestError:
            logger.exception("downstream MCP transport failure")
            return 502, jsonrpc_error(request.id, -32000, "Downstream MCP unavailable")

        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                return response.status_code, response.json()
            except ValueError:
                pass
        return response.status_code, response.text
