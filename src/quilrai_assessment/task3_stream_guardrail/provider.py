from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Protocol

import httpx


class StreamingProvider(Protocol):
    def stream(self, prompt: str) -> AsyncIterator[str]: ...


class HTTPStreamingProvider:
    """Adapter for common SSE/NDJSON LLM streaming responses.

    Supported event shapes include OpenAI-style choices[0].delta.content plus
    simple {"delta": "..."} and {"text": "..."} mock-provider payloads.
    """

    def __init__(self, url: str, client: httpx.AsyncClient) -> None:
        self.url = url
        self.client = client

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        async with self.client.stream("POST", self.url, json={"prompt": prompt, "stream": True}) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                if line.startswith("data:"):
                    line = line[5:].strip()
                if line == "[DONE]":
                    break
                delta = self._extract_delta(line)
                if delta:
                    yield delta

    @staticmethod
    def _extract_delta(line: str) -> str:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return line

        if isinstance(payload.get("delta"), str):
            return payload["delta"]
        if isinstance(payload.get("text"), str):
            return payload["text"]
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            choice = choices[0]
            if isinstance(choice, dict):
                delta = choice.get("delta")
                if isinstance(delta, dict) and isinstance(delta.get("content"), str):
                    return delta["content"]
                if isinstance(choice.get("text"), str):
                    return choice["text"]
        return ""
