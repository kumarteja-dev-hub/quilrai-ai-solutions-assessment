from __future__ import annotations

import json
import logging
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .provider import HTTPStreamingProvider, StreamingProvider
from .redactor import StreamingPIIRedactor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("quilrai.task3")


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=100_000)


def _sse(delta: str) -> bytes:
    return f"data: {json.dumps({'delta': delta}, separators=(',', ':'))}\n\n".encode()


def create_app(provider: StreamingProvider | None = None) -> FastAPI:
    client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=300.0)) if provider is None else None
    active_provider = provider or HTTPStreamingProvider(
        os.getenv("LLM_STREAM_URL", "http://127.0.0.1:9301/v1/stream"),
        client,  # type: ignore[arg-type]
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if client is not None:
            await client.aclose()

    app = FastAPI(title="QuilrAI Streaming PII Guardrail", lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/generate")
    async def generate(body: GenerateRequest) -> StreamingResponse:
        async def guarded_stream() -> AsyncIterator[bytes]:
            redactor = StreamingPIIRedactor()
            try:
                async for chunk in active_provider.stream(body.prompt):
                    safe = redactor.feed(chunk)
                    if safe:
                        yield _sse(safe)
                tail = redactor.flush()
                if tail:
                    yield _sse(tail)
                yield b"data: [DONE]\n\n"
            except Exception:
                logger.exception("streaming provider failed")
                # Do not serialize raw provider exceptions into the user-visible stream.
                yield _sse("[UPSTREAM_ERROR]")
                yield b"data: [DONE]\n\n"

        return StreamingResponse(guarded_stream(), media_type="text/event-stream")

    return app


app = create_app()
