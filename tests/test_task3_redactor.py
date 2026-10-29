from __future__ import annotations

import pytest

from quilrai_assessment.task3_stream_guardrail.redactor import StreamingPIIRedactor


def run_chunks(chunks: list[str]) -> str:
    redactor = StreamingPIIRedactor()
    out = "".join(redactor.feed(chunk) for chunk in chunks)
    return out + redactor.flush()


@pytest.mark.parametrize(
    "pii",
    ["jane.doe@example.com", "123-45-6789", "4111 1111 1111 1111"],
)
def test_pii_is_redacted_across_every_two_chunk_split(pii: str) -> None:
    expected = "before [REDACTED] after"
    source = f"before {pii} after"
    for split in range(1, len(source)):
        assert run_chunks([source[:split], source[split:]]) == expected


def test_multiple_pii_values_survive_pathological_one_character_chunks() -> None:
    source = "Email a@b.co SSN 123-45-6789 card 4111-1111-1111-1111 end"
    result = run_chunks(list(source))
    assert result == "Email [REDACTED] SSN [REDACTED] card [REDACTED] end"


def test_invalid_luhn_number_is_not_redacted() -> None:
    source = "number 4111 1111 1111 1112 end"
    assert run_chunks([source]) == source


def test_pending_buffer_is_bounded_for_pathological_long_token() -> None:
    redactor = StreamingPIIRedactor()
    emitted = redactor.feed("a" * 10_000)
    assert emitted
    assert redactor.buffered_characters <= 384
