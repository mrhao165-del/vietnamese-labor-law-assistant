"""Stable public response envelopes for the Legal Calculator MCP tools."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0"


class ToolMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str
    schema_version: str = SCHEMA_VERSION
    request_id: str


class ToolError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    retryable: bool
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


DataT = TypeVar("DataT", bound=BaseModel)


class ToolResponse(BaseModel, Generic[DataT]):
    """Exactly one of ``data`` and ``error`` is populated in the public contract."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    data: DataT | None = None
    error: ToolError | None = None
    meta: ToolMeta
