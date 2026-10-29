from __future__ import annotations

from typing import Protocol

import httpx

from .errors import ProviderFailure, ProviderRateLimited
from .models import CompletionRequest, ProviderResult
from .rate_limiter import estimate_prompt_tokens


class ModelProvider(Protocol):
    name: str

    async def complete(self, request: CompletionRequest) -> ProviderResult: ...


class HTTPModelProvider:
    def __init__(self, name: str, url: str, client: httpx.AsyncClient) -> None:
        self.name = name
        self.url = url
        self.client = client

    async def complete(self, request: CompletionRequest) -> ProviderResult:
        try:
            response = await self.client.post(self.url, json=request.model_dump())
        except httpx.RequestError as exc:
            raise ProviderFailure("transport failure") from exc

        if response.status_code == 429:
            raise ProviderRateLimited("provider rate limited")
        if response.status_code >= 400:
            raise ProviderFailure(f"provider returned HTTP {response.status_code}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderFailure("provider returned invalid JSON") from exc

        text = payload.get("text")
        if not isinstance(text, str):
            raise ProviderFailure("provider response missing text")

        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        input_tokens = int(usage.get("input_tokens", estimate_prompt_tokens(request.prompt)))
        output_tokens = int(usage.get("output_tokens", max(1, len(text.encode("utf-8")) // 4)))
        return ProviderResult(
            text=text,
            input_tokens=max(0, input_tokens),
            output_tokens=max(0, output_tokens),
            model=str(payload.get("model", self.name)),
        )
