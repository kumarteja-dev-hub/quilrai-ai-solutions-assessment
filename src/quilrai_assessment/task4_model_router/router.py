from __future__ import annotations

import asyncio
import logging

from .errors import GatewayError, ProviderFailure, ProviderRateLimited
from .models import CompletionRequest, CompletionResponse, ProviderResult
from .provider import ModelProvider
from .rate_limiter import SQLiteSlidingWindowRateLimiter, estimate_prompt_tokens

logger = logging.getLogger("quilrai.task4")


class ResilientModelRouter:
    def __init__(
        self,
        primary: ModelProvider,
        secondary: ModelProvider,
        limiter: SQLiteSlidingWindowRateLimiter,
        primary_timeout_seconds: float = 3.0,
    ) -> None:
        self.primary = primary
        self.secondary = secondary
        self.limiter = limiter
        self.primary_timeout_seconds = primary_timeout_seconds

    async def complete(self, tenant_key: str, request: CompletionRequest) -> CompletionResponse:
        # Reserve worst-case capacity up front so concurrent requests cannot all pass
        # based only on current usage and later overshoot the tenant's minute budget.
        reserve_tokens = estimate_prompt_tokens(request.prompt) + request.max_tokens
        decision = await self.limiter.reserve(tenant_key, reserve_tokens)
        if not decision.allowed or decision.reservation is None:
            raise GatewayError(
                code="RATE_LIMIT_EXCEEDED",
                message="Tenant token rate limit exceeded",
                status_code=429,
                retry_after_seconds=decision.retry_after_seconds,
            )
        reservation = decision.reservation

        try:
            result, provider_name = await self._call_with_fallback(request)
            await self.limiter.reconcile(reservation, result.total_tokens)
            return CompletionResponse(
                text=result.text,
                model=result.model,
                provider=provider_name,
                usage={
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "total_tokens": result.total_tokens,
                },
            )
        except GatewayError:
            await self.limiter.release(reservation)
            raise
        except Exception as exc:
            await self.limiter.release(reservation)
            logger.exception("unexpected router failure")
            raise GatewayError(
                code="GATEWAY_INTERNAL_ERROR",
                message="Model gateway could not complete the request",
                status_code=502,
            ) from exc

    async def _call_with_fallback(
        self, request: CompletionRequest
    ) -> tuple[ProviderResult, str]:
        try:
            # wait_for cancels the primary coroutine when the timeout expires and waits
            # for cancellation to propagate before this method starts the backup call.
            result = await asyncio.wait_for(
                self.primary.complete(request),
                timeout=self.primary_timeout_seconds,
            )
            return result, self.primary.name
        except (TimeoutError, ProviderRateLimited) as exc:
            reason = "timeout" if isinstance(exc, TimeoutError) else "rate_limit"
            logger.warning("primary provider fallback reason=%s", reason)
            try:
                return await self.secondary.complete(request), self.secondary.name
            except (ProviderRateLimited, ProviderFailure) as backup_exc:
                raise GatewayError(
                    code="UPSTREAM_UNAVAILABLE",
                    message="Model service is temporarily unavailable",
                    status_code=503,
                ) from backup_exc
        except ProviderFailure as exc:
            # The prompt can be invalid or the primary can fail in a way that retrying
            # elsewhere would duplicate a bad request. The requirement names only 429
            # and 3000 ms timeout as automatic failover triggers.
            raise GatewayError(
                code="UPSTREAM_ERROR",
                message="Primary model request failed",
                status_code=502,
            ) from exc
