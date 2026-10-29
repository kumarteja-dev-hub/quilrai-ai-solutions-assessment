from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

CustomerId = Annotated[str, StringConstraints(pattern=r"^CUST-\d{5}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class GetCustomerRecordInput(StrictModel):
    customer_id: CustomerId


class TriggerRefundInput(StrictModel):
    customer_id: CustomerId
    amount: float = Field(gt=0, allow_inf_nan=False)
    reason: str = Field(min_length=10, max_length=500)
