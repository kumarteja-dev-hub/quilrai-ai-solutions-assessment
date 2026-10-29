from __future__ import annotations

import httpx
import pytest

from quilrai_assessment.task2_security_gateway.app import create_app
from quilrai_assessment.task2_security_gateway.auth import JWTAuthenticator, issue_demo_token

SECRET = "0123456789abcdef0123456789abcdef"


async def _client(role: str, downstream_handler):
    downstream = httpx.AsyncClient(transport=httpx.MockTransport(downstream_handler))
    app = create_app(
        downstream_url="http://downstream.test/mcp",
        authenticator=JWTAuthenticator(SECRET),
        downstream_client=downstream,
    )
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://gateway.test",
    )
    token = issue_demo_token(f"demo-{role}", role, SECRET)  # type: ignore[arg-type]
    return client, downstream, token


@pytest.mark.asyncio
async def test_tools_list_is_forwarded_transparently() -> None:
    calls = 0

    def downstream(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 7, "result": {"tools": []}})

    client, downstream_client, token = await _client("viewer", downstream)
    try:
        response = await client.post(
            "/mcp",
            headers={"Authorization": f"Bearer {token}"},
            json={"jsonrpc": "2.0", "id": 7, "method": "tools/list", "params": {}},
        )
        assert response.status_code == 200
        assert response.json()["id"] == 7
        assert calls == 1
    finally:
        await client.aclose()
        await downstream_client.aclose()


@pytest.mark.asyncio
async def test_viewer_admin_tool_is_blocked_without_downstream_call() -> None:
    calls = 0

    def downstream(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"unexpected": True})

    client, downstream_client, token = await _client("viewer", downstream)
    try:
        response = await client.post(
            "/mcp",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "jsonrpc": "2.0",
                "id": "abc-123",
                "method": "tools/call",
                "params": {"name": "admin_reset_key", "arguments": {}},
            },
        )
        body = response.json()
        assert response.status_code == 200
        assert body["id"] == "abc-123"
        assert body["error"] == {"code": -32001, "message": "Unauthorized Tool Call"}
        assert calls == 0
    finally:
        await client.aclose()
        await downstream_client.aclose()


@pytest.mark.asyncio
async def test_admin_tool_is_forwarded() -> None:
    calls = 0

    def downstream(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 3, "result": {"ok": True}})

    client, downstream_client, token = await _client("admin", downstream)
    try:
        response = await client.post(
            "/mcp",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "admin_reset_key", "arguments": {}},
            },
        )
        assert response.json()["result"] == {"ok": True}
        assert calls == 1
    finally:
        await client.aclose()
        await downstream_client.aclose()


@pytest.mark.asyncio
async def test_invalid_bearer_token_returns_jsonrpc_auth_error_without_forwarding() -> None:
    calls = 0

    def downstream(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"unexpected": True})

    downstream_client = httpx.AsyncClient(transport=httpx.MockTransport(downstream))
    app = create_app(
        downstream_url="http://downstream.test/mcp",
        authenticator=JWTAuthenticator(SECRET),
        downstream_client=downstream_client,
    )
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://gateway.test",
    )
    try:
        response = await client.post(
            "/mcp",
            headers={"Authorization": "Bearer definitely-not-a-jwt"},
            json={"jsonrpc": "2.0", "id": 99, "method": "tools/list", "params": {}},
        )
        assert response.status_code == 401
        assert response.json() == {
            "jsonrpc": "2.0",
            "error": {"code": -32001, "message": "Unauthorized Tool Call"},
            "id": 99,
        }
        assert calls == 0
    finally:
        await client.aclose()
        await downstream_client.aclose()
