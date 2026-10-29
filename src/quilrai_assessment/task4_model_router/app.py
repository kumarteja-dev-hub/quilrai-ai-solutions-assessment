from __future__ import annotations

import logging
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse

from .errors import GatewayError
from .models import CompletionRequest
from .provider import HTTPModelProvider, ModelProvider
from .rate_limiter import SQLiteSlidingWindowRateLimiter, default_db_path
from .router import ResilientModelRouter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stderr,
)


def create_app(
    primary: ModelProvider | None = None,
    secondary: ModelProvider | None = None,
    limiter: SQLiteSlidingWindowRateLimiter | None = None,
) -> FastAPI:
    client = httpx.AsyncClient(timeout=None) if primary is None or secondary is None else None
    active_primary = primary or HTTPModelProvider(
        "primary",
        os.getenv("PRIMARY_MODEL_URL", "http://127.0.0.1:9301/primary/completions"),
        client,  # type: ignore[arg-type]
    )
    active_secondary = secondary or HTTPModelProvider(
        "secondary",
        os.getenv("SECONDARY_MODEL_URL", "http://127.0.0.1:9301/secondary/completions"),
        client,  # type: ignore[arg-type]
    )
    active_limiter = limiter or SQLiteSlidingWindowRateLimiter(
        default_db_path(),
        limit_tokens=int(os.getenv("TOKEN_LIMIT_PER_MINUTE", "50000")),
    )
    router = ResilientModelRouter(
        active_primary,
        active_secondary,
        active_limiter,
        primary_timeout_seconds=float(os.getenv("PRIMARY_TIMEOUT_SECONDS", "3.0")),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if client is not None:
            await client.aclose()

    app = FastAPI(title="QuilrAI Resilient LLM Router", lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/completions")
    async def completions(
        body: CompletionRequest,
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    ) -> JSONResponse:
        request_id = uuid4().hex
        if not x_api_key:
            return JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "Missing tenant API key",
                        "request_id": request_id,
                    }
                },
            )
        try:
            result = await router.complete(x_api_key, body)
            return JSONResponse(
                status_code=200,
                content={"request_id": request_id, **result.model_dump()},
            )
        except GatewayError as exc:
            payload: dict[str, object] = {
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "request_id": request_id,
                }
            }
            headers: dict[str, str] = {}
            if exc.retry_after_seconds is not None:
                headers["Retry-After"] = str(max(1, int(exc.retry_after_seconds + 0.999)))
            return JSONResponse(status_code=exc.status_code, content=payload, headers=headers)

    return app


app = create_app()
