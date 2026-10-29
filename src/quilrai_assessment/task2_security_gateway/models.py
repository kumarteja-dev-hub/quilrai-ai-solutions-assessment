from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JSONRPCRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    jsonrpc: str = Field(pattern=r"^2\.0$")
    method: str
    params: dict[str, Any] | None = None
    id: str | int | None = None


class JSONRPCErrorBody(BaseModel):
    code: int
    message: str


class JSONRPCErrorResponse(BaseModel):
    jsonrpc: str = "2.0"
    error: JSONRPCErrorBody
    id: str | int | None = None
