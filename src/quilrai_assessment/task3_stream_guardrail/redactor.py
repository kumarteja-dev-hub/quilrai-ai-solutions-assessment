from __future__ import annotations

import re

REDACTED = "[REDACTED]"

_EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+\-])"
    r"[A-Za-z0-9._%+\-]{1,64}@"
    r"[A-Za-z0-9.-]{1,255}\."
    r"[A-Za-z]{2,63}"
    r"(?![A-Za-z0-9.-])"
)
_SSN_RE = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
_CARD_CANDIDATE_RE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")

# Anything matching these suffixes might become PII after the next upstream chunk.
# We hold only the unresolved tail, not the whole generated response.
_EMAILISH_TAIL_RE = re.compile(r"[A-Za-z0-9._%+@\-]{1,384}$")
_NUMERIC_TAIL_RE = re.compile(r"(?:\d[ -]?){1,24}$")
_MAX_CARRY = 384


def _luhn_valid(candidate: str) -> bool:
    digits = [int(ch) for ch in candidate if ch.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        value = digit
        if index % 2 == parity:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def redact_complete_text(text: str) -> str:
    text = _EMAIL_RE.sub(REDACTED, text)
    text = _SSN_RE.sub(REDACTED, text)

    def replace_card(match: re.Match[str]) -> str:
        value = match.group(0).rstrip(" -")
        suffix = match.group(0)[len(value) :]
        return (REDACTED if _luhn_valid(value) else value) + suffix

    return _CARD_CANDIDATE_RE.sub(replace_card, text)


class StreamingPIIRedactor:
    """Incremental redactor with bounded carry state.

    The key safety property is that a suffix which could still become an email,
    SSN, or card number is never emitted until a later character proves it safe,
    or the upstream stream ends and `flush()` performs a final full match.
    """

    def __init__(self) -> None:
        self._pending = ""

    @property
    def buffered_characters(self) -> int:
        return len(self._pending)

    def feed(self, chunk: str) -> str:
        if not chunk:
            return ""
        self._pending += chunk
        cut = self._safe_cut(self._pending)
        if cut <= 0:
            # Keep memory bounded even for pathological giant tokens. Values beyond
            # the maximum valid email/card shape cannot later become a supported PII match.
            if len(self._pending) > _MAX_CARRY:
                cut = len(self._pending) - _MAX_CARRY
            else:
                return ""

        safe = self._pending[:cut]
        self._pending = self._pending[cut:]
        return redact_complete_text(safe)

    def flush(self) -> str:
        final = redact_complete_text(self._pending)
        self._pending = ""
        return final

    @staticmethod
    def _safe_cut(text: str) -> int:
        starts: list[int] = []
        emailish = _EMAILISH_TAIL_RE.search(text)
        if emailish:
            starts.append(emailish.start())
        numeric = _NUMERIC_TAIL_RE.search(text)
        if numeric:
            starts.append(numeric.start())
        if not starts:
            return len(text)
        return min(starts)
