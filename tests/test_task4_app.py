from __future__ import annotations

import httpx
import pytest

from quilrai_assessment.task4_model_router.app import create_app
from quilrai_assessment.task4_model_router.errors import ProviderFailure
from quilrai_assessment.task4_model_router.models import CompletionRequest, ProviderResult
from quilrai_assessment.task4_model_router.rate_limiter import SQLiteSlidingWindowRateLimiter


class FailingProvider:
    name = "primary"

    async def complete(self, request: CompletionRequest) -> ProviderResult:
        del request
        raise ProviderFailure("SECRET_TOKEN=/private/path traceback")


class BackupProvider:
    name = "secondary"

    async def complete(self, request: CompletionRequest) -> ProviderResult:
        del request
        return ProviderResult(text="backup", input_tokens=1, output_tokens=1, model="secondary")


@pytest.mark.asyncio
async def test_http_error_payload_is_standardized_and_sanitized(tmp_path) -> None:
    limiter = SQLiteSlidingWindowRateLimiter(str(tmp_path / "limits.db"))
    app = create_app(FailingProvider(), BackupProvider(), limiter)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/completions",
            headers={"X-API-Key": "tenant-a"},
            json={"prompt": "hello", "max_tokens": 20},
        )
    body = response.json()
    assert response.status_code == 502
    assert body["error"]["code"] == "UPSTREAM_ERROR"
    assert "SECRET_TOKEN" not in response.text
    assert "/private/path" not in response.text
    assert body["error"]["request_id"]
