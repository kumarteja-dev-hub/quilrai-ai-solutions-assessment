from __future__ import annotations

import asyncio
import hashlib
import math
import os
import sqlite3
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class Reservation:
    reservation_id: str
    tenant_key: str
    reserved_tokens: int


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    reservation: Reservation | None = None
    retry_after_seconds: float | None = None
    remaining_tokens: int = 0


class SQLiteSlidingWindowRateLimiter:
    """Token-aware sliding-window limiter backed by an on-disk SQLite ledger.

    `BEGIN IMMEDIATE` makes the check-and-reserve operation atomic across concurrent
    tasks and processes that share the same database file. WAL improves reader/writer
    coexistence, and expired ledger rows are evicted on each mutation.
    """

    def __init__(
        self,
        db_path: str,
        limit_tokens: int = 50_000,
        window_seconds: float = 60.0,
        clock=time.time,
    ) -> None:
        self.db_path = db_path
        self.limit_tokens = limit_tokens
        self.window_seconds = window_seconds
        self.clock = clock
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS token_events (
                    reservation_id TEXT PRIMARY KEY,
                    tenant_key TEXT NOT NULL,
                    tokens INTEGER NOT NULL CHECK(tokens >= 0),
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_token_events_tenant_time
                    ON token_events(tenant_key, created_at);
                """
            )

    @staticmethod
    def _tenant_id(tenant_key: str) -> str:
        # The API key is a credential. Persist only a one-way identifier in SQLite.
        return hashlib.sha256(tenant_key.encode("utf-8")).hexdigest()

    async def reserve(self, tenant_key: str, tokens: int) -> RateLimitDecision:
        if tokens <= 0:
            raise ValueError("tokens must be positive")
        return await asyncio.to_thread(self._reserve_sync, self._tenant_id(tenant_key), tokens)

    def _reserve_sync(self, tenant_key: str, tokens: int) -> RateLimitDecision:
        now = float(self.clock())
        cutoff = now - self.window_seconds
        reservation_id = uuid4().hex
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM token_events WHERE created_at <= ?", (cutoff,))
            rows = conn.execute(
                "SELECT tokens, created_at FROM token_events "
                "WHERE tenant_key = ? ORDER BY created_at ASC",
                (tenant_key,),
            ).fetchall()
            used = sum(int(row["tokens"]) for row in rows)

            if used + tokens > self.limit_tokens:
                needed = used + tokens - self.limit_tokens
                released = 0
                retry_after = self.window_seconds
                for row in rows:
                    released += int(row["tokens"])
                    if released >= needed:
                        retry_after = max(
                            0.001,
                            float(row["created_at"]) + self.window_seconds - now,
                        )
                        break
                conn.execute("ROLLBACK")
                return RateLimitDecision(
                    allowed=False,
                    retry_after_seconds=retry_after,
                    remaining_tokens=max(0, self.limit_tokens - used),
                )

            conn.execute(
                "INSERT INTO token_events(reservation_id, tenant_key, tokens, created_at) "
                "VALUES (?, ?, ?, ?)",
                (reservation_id, tenant_key, tokens, now),
            )
            conn.execute("COMMIT")
            return RateLimitDecision(
                allowed=True,
                reservation=Reservation(reservation_id, tenant_key, tokens),
                remaining_tokens=max(0, self.limit_tokens - used - tokens),
            )
        except Exception:
            with suppress(sqlite3.Error):
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    async def reconcile(self, reservation: Reservation, actual_tokens: int) -> None:
        actual_tokens = max(0, actual_tokens)
        await asyncio.to_thread(self._reconcile_sync, reservation, actual_tokens)

    def _reconcile_sync(self, reservation: Reservation, actual_tokens: int) -> None:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "UPDATE token_events SET tokens = ? WHERE reservation_id = ?",
                (actual_tokens, reservation.reservation_id),
            )
            conn.execute("COMMIT")
        except Exception:
            with suppress(sqlite3.Error):
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    async def release(self, reservation: Reservation) -> None:
        await asyncio.to_thread(self._release_sync, reservation)

    def _release_sync(self, reservation: Reservation) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM token_events WHERE reservation_id = ?",
                (reservation.reservation_id,),
            )

    async def usage(self, tenant_key: str) -> int:
        return await asyncio.to_thread(self._usage_sync, self._tenant_id(tenant_key))

    def _usage_sync(self, tenant_key: str) -> int:
        now = float(self.clock())
        cutoff = now - self.window_seconds
        with self._connect() as conn:
            conn.execute("DELETE FROM token_events WHERE created_at <= ?", (cutoff,))
            row = conn.execute(
                "SELECT COALESCE(SUM(tokens), 0) AS used FROM token_events WHERE tenant_key = ?",
                (tenant_key,),
            ).fetchone()
            return int(row["used"])


def estimate_prompt_tokens(text: str) -> int:
    # Provider-independent conservative approximation. Production deployments can
    # replace this with the tokenizer for the selected model without changing the limiter.
    return max(1, math.ceil(len(text.encode("utf-8")) / 4))


def default_db_path() -> str:
    return os.getenv("RATE_LIMIT_DB", "./data/rate_limits.db")
