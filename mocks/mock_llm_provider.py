from __future__ import annotations

import asyncio
import json

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI(title="Mock LLM providers")


@app.post("/v1/stream")
async def stream(request: Request) -> StreamingResponse:
    body = await request.json()
    prompt = str(body.get("prompt", ""))
    text = (
        "Safe intro. Contact jane.doe@example.com, SSN 123-45-6789, "
        "card 4111 1111 1111 1111. End."
        if "pii" in prompt.lower()
        else f"Echo: {prompt}"
    )

    async def events():
        # Awkward boundaries intentionally split PII values.
        remaining = text
        for width in (7, 3, 11, 2, 5):
            if not remaining:
                break
            chunk, remaining = remaining[:width], remaining[width:]
            yield f"data: {json.dumps({'delta': chunk})}\n\n"
            await asyncio.sleep(0.005)
        if remaining:
            yield f"data: {json.dumps({'delta': remaining})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


async def _completion(request: Request, provider: str) -> JSONResponse:
    body = await request.json()
    prompt = str(body.get("prompt", ""))
    if provider == "primary" and "trigger-429" in prompt:
        return JSONResponse({"error": "rate limited"}, status_code=429)
    if provider == "primary" and "trigger-timeout" in prompt:
        await asyncio.sleep(3.5)
    if "trigger-500" in prompt:
        return JSONResponse({"internal": "sensitive stack trace"}, status_code=500)
    text = f"{provider} response to: {prompt}"
    return JSONResponse(
        {
            "text": text,
            "model": f"mock-{provider}",
            "usage": {"input_tokens": max(1, len(prompt) // 4), "output_tokens": max(1, len(text) // 4)},
        }
    )


@app.post("/primary/completions")
async def primary(request: Request) -> JSONResponse:
    return await _completion(request, "primary")


@app.post("/secondary/completions")
async def secondary(request: Request) -> JSONResponse:
    return await _completion(request, "secondary")
