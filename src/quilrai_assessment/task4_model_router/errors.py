from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class GatewayError(Exception):
    code: str
    message: str
    status_code: int = 502
    retry_after_seconds: float | None = None


class ProviderRateLimited(Exception):
    pass


class ProviderFailure(Exception):
    pass
