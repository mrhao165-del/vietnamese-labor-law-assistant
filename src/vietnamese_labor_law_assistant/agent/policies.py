"""Centralized allowlist, limits, sanitization and bounded-retry policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .enums import ToolName
from .errors import ToolBudgetExceededError
from .models import CALCULATOR_TOOLS, RETRIEVAL_TOOLS


@dataclass(frozen=True)
class AgentPolicy:
    max_input_length: int = 4000
    max_tool_calls: int = 3
    tool_timeout_seconds: float = 30.0
    workflow_timeout_seconds: float = 90.0
    max_transport_retries: int = 1
    max_retrieval_top_k: int = 5
    tool_output_max_chars: int = 12000

    @property
    def allowlisted_tools(self) -> frozenset[ToolName]:
        return RETRIEVAL_TOOLS | CALCULATOR_TOOLS

    def ensure_budget(self, used: int) -> None:
        if used >= self.max_tool_calls:
            raise ToolBudgetExceededError("tool-call budget exhausted")

    def bounded_retrieval_arguments(
        self, arguments: dict[str, Any], question: str
    ) -> dict[str, Any]:
        allowed = {
            "query",
            "top_k",
            "article_number",
            "clause_number",
            "chapter_number",
            "document_id",
        }
        result = {key: value for key, value in arguments.items() if key in allowed}
        result["query"] = str(result.get("query") or question)
        top_k = result.get("top_k", self.max_retrieval_top_k)
        try:
            result["top_k"] = min(max(int(top_k), 1), self.max_retrieval_top_k)
        except (TypeError, ValueError):
            result["top_k"] = self.max_retrieval_top_k
        return result

    def sanitized_arguments(self, arguments: dict[str, Any]) -> dict[str, Any]:
        safe: dict[str, Any] = {}
        for key, value in arguments.items():
            if key.casefold() in {"api_key", "authorization", "token", "secret"}:
                safe[key] = "<redacted>"
            elif isinstance(value, str):
                safe[key] = value[:240]
            elif isinstance(value, (int, float, bool)) or value is None:
                safe[key] = value
            else:
                safe[key] = "<non-scalar>"
        return safe
