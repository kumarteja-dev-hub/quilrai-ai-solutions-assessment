from __future__ import annotations

import asyncio

import pytest

from quilrai_assessment.task4_model_router.errors import GatewayError, ProviderFailure, ProviderRateLimited
from quilrai_assessment.task4_model_router.models import CompletionRequest, ProviderResult
from quilrai_assessment.task4_model_router.rate_limiter import SQLiteSlidingWindowRateLimiter
from quilrai_assessment.task4_model_router.router import ResilientModelRouter


class Provider:
    def __init__(self, name: str, behavior: str = "ok") -> None:
        self.name = name
        self.behavior = behavior
        self.calls = 0
        self.cancelled = False

    async def complete(self, request: CompletionRequest) -> ProviderResult:
        self.calls += 1
        if self.behavior == "429":
            raise ProviderRateLimited("429")
        if self.behavior == "failure":
            raise ProviderFailure("raw secret stack trace")
        if self.behavior == "slow":
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                self.cancelled = True
                raise
        return ProviderResult(text="ok", input_tokens=3, output_tokens=4, model=self.name)


def router(tmp_path, primary: Provider, secondary: Provider, timeout: float = 0.05) -> ResilientModelRouter:
    limiter = SQLiteSlidingWindowRateLimiter(str(tmp_path / "limits.db"), 50_000, 60)
    return ResilientModelRouter(primary, secondary, limiter, timeout)


@pytest.mark.asyncio
async def test_primary_429_falls_back_to_secondary(tmp_path) -> None:
    primary = Provider("primary", "429")
    secondary = Provider("secondary")
    result = await router(tmp_path, primary, secondary).complete(
        "tenant-a", CompletionRequest(prompt="hello", max_tokens=10)
    )
    assert result.provider == "secondary"
    assert primary.calls == 1 and secondary.calls == 1


@pytest.mark.asyncio
async def test_primary_timeout_is_cancelled_before_fallback(tmp_path) -> None:
    primary = Provider("primary", "slow")
    secondary = Provider("secondary")
    result = await router(tmp_path, primary, secondary, timeout=0.01).complete(
        "tenant-a", CompletionRequest(prompt="hello", max_tokens=10)
    )
    assert result.provider == "secondary"
    assert primary.cancelled is True
    assert secondary.calls == 1


@pytest.mark.asyncio
async def test_non_429_primary_failure_does_not_fallback_or_leak_detail(tmp_path) -> None:
    primary = Provider("primary", "failure")
    secondary = Provider("secondary")
    with pytest.raises(GatewayError) as exc_info:
        await router(tmp_path, primary, secondary).complete(
            "tenant-a", CompletionRequest(prompt="hello", max_tokens=10)
        )
    assert exc_info.value.code == "UPSTREAM_ERROR"
    assert "secret" not in exc_info.value.message
    assert secondary.calls == 0


@pytest.mark.asyncio
async def test_reservation_is_reconciled_to_actual_usage(tmp_path) -> None:
    primary = Provider("primary")
    secondary = Provider("secondary")
    instance = router(tmp_path, primary, secondary)
    await instance.complete("tenant-a", CompletionRequest(prompt="hello", max_tokens=100))
    assert await instance.limiter.usage("tenant-a") == 7
