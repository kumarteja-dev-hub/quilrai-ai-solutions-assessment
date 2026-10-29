from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class CustomerRecord:
    customer_id: str
    name: str
    status: str
    lifetime_value: Decimal


CUSTOMERS: dict[str, CustomerRecord] = {
    "CUST-00001": CustomerRecord("CUST-00001", "Ada Lovelace", "active", Decimal("1250.50")),
    "CUST-00002": CustomerRecord("CUST-00002", "Grace Hopper", "active", Decimal("980.00")),
    "CUST-12345": CustomerRecord("CUST-12345", "Demo Customer", "review", Decimal("420.00")),
}


def get_customer(customer_id: str) -> dict[str, str]:
    record = CUSTOMERS.get(customer_id)
    if record is None:
        return {"customer_id": customer_id, "found": "false"}
    return {
        "customer_id": record.customer_id,
        "name": record.name,
        "status": record.status,
        "lifetime_value": str(record.lifetime_value),
        "found": "true",
    }


def create_refund(customer_id: str, amount: float, reason: str) -> dict[str, str | float]:
    return {
        "refund_id": f"rf_{uuid4().hex[:12]}",
        "customer_id": customer_id,
        "amount": round(amount, 2),
        "reason": reason,
        "status": "accepted",
    }
