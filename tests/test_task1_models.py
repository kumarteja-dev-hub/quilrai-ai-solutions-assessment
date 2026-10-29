from __future__ import annotations

import pytest
from pydantic import ValidationError

from quilrai_assessment.task1_mcp_server.models import (
    GetCustomerRecordInput,
    TriggerRefundInput,
)


@pytest.mark.parametrize("customer_id", ["CUST-00001", "CUST-12345", "CUST-99999"])
def test_customer_id_valid(customer_id: str) -> None:
    assert GetCustomerRecordInput(customer_id=customer_id).customer_id == customer_id


@pytest.mark.parametrize(
    "customer_id",
    ["cust-12345", "CUST-1234", "CUST-123456", "CUST-ABCDE", " CUST-12345", ""],
)
def test_customer_id_rejects_malformed_values(customer_id: str) -> None:
    with pytest.raises(ValidationError):
        GetCustomerRecordInput(customer_id=customer_id)


@pytest.mark.parametrize("amount", [0.0, -1.0, float("inf"), float("-inf"), float("nan")])
def test_refund_rejects_non_positive_or_non_finite_amount(amount: float) -> None:
    with pytest.raises(ValidationError):
        TriggerRefundInput(customer_id="CUST-12345", amount=amount, reason="valid reason text")


def test_refund_rejects_short_reason_and_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        TriggerRefundInput(customer_id="CUST-12345", amount=10.0, reason="too short")
    with pytest.raises(ValidationError):
        TriggerRefundInput.model_validate(
            {"customer_id": "CUST-12345", "amount": 10.0, "reason": "long enough reason", "extra": True}
        )
