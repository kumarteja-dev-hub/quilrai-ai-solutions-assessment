from __future__ import annotations

import asyncio

import pytest

from quilrai_assessment.task4_model_router.rate_limiter import SQLiteSlidingWindowRateLimiter


class FakeClock:
    def __init__(self, value: float = 1_000.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


@pytest.mark.asyncio
async def test_sliding_window_evicts_expired_tokens(tmp_path) -> None:
    clock = FakeClock()
    limiter = SQLiteSlidingWindowRateLimiter(str(tmp_path / "limits.db"), 100, 60, clock=clock)
    first = await limiter.reserve("tenant-a", 80)
    assert first.allowed
    blocked = await limiter.reserve("tenant-a", 30)
    assert not blocked.allowed
    assert blocked.retry_after_seconds == pytest.approx(60.0)

    clock.value += 60.001
    allowed = await limiter.reserve("tenant-a", 30)
    assert allowed.allowed
    assert await limiter.usage("tenant-a") == 30


@pytest.mark.asyncio
async def test_concurrent_reservations_cannot_overshoot_limit(tmp_path) -> None:
    limiter = SQLiteSlidingWindowRateLimiter(str(tmp_path / "limits.db"), 100, 60)
    decisions = await asyncio.gather(*(limiter.reserve("tenant-a", 10) for _ in range(20)))
    assert sum(decision.allowed for decision in decisions) == 10
    assert await limiter.usage("tenant-a") == 100
