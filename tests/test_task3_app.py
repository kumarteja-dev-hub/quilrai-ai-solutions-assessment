from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from quilrai_assessment.task3_stream_guardrail.app import create_app


class ScriptedProvider:
    async def stream(self, prompt: str) -> AsyncIterator[str]:
        del prompt
        for chunk in ["Contact jane.do", "e@example.", "com SSN 123-", "45-6789 done"]:
            yield chunk


@pytest.mark.asyncio
async def test_gateway_stream_never_contains_raw_pii() -> None:
    app = create_app(ScriptedProvider())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/generate", json={"prompt": "demo"})
    assert response.status_code == 200
    assert "jane.doe@example.com" not in response.text
    assert "123-45-6789" not in response.text
    assert response.text.count("[REDACTED]") == 2
