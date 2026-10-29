from __future__ import annotations

from pydantic import BaseModel, Field


class CompletionRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=100_000)
    max_tokens: int = Field(default=512, ge=1, le=8192)


class ProviderResult(BaseModel):
    text: str
    input_tokens: int
    output_tokens: int
    model: str

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class CompletionResponse(BaseModel):
    text: str
    model: str
    provider: str
    usage: dict[str, int]
