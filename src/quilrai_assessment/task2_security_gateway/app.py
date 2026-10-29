from __future__ import annotations

import logging
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from .auth import JWTAuthenticator
from .gateway import SecurityGateway, jsonrpc_error

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stderr,
)


def create_app(
    downstream_url: str | None = None,
    authenticator: JWTAuthenticator | None = None,
    downstream_client: httpx.AsyncClient | None = None,
) -> FastAPI:
    owns_client = downstream_client is None
    client = downstream_client or httpx.AsyncClient(timeout=httpx.Timeout(10.0))
    auth = authenticator or JWTAuthenticator.from_env()
    gateway = SecurityGateway(
        downstream_url or os.getenv("MCP_DOWNSTREAM_URL", "http://127.0.0.1:9102/mcp"),
        client,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if owns_client:
            await client.aclose()

    app = FastAPI(title="QuilrAI MCP Security Gateway", lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/mcp")
    async def proxy(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> Response:
        try:
            payload = await request.json()
        except ValueError:
            return JSONResponse(
                status_code=400,
                content=jsonrpc_error(None, -32700, "Parse error"),
            )

        if not isinstance(payload, dict):
            return JSONResponse(
                status_code=400,
                content=jsonrpc_error(None, -32600, "Invalid Request"),
            )

        try:
            principal = auth.authenticate_header(authorization)
        except HTTPException as exc:
            # Convert authentication failures into JSON-RPC shaped errors so MCP clients
            # never receive an unrelated framework error schema.
            status = exc.status_code
            return JSONResponse(
                status_code=status,
                content=jsonrpc_error(payload.get("id"), -32001, "Unauthorized Tool Call"),
            )

        status, body = await gateway.handle(payload, principal)
        if isinstance(body, dict | list):
            return JSONResponse(status_code=status, content=body)
        return Response(status_code=status, content=str(body))

    return app


app = create_app()
