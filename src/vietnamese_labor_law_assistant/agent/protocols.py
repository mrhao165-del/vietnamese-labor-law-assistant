"""Ports that keep production MCP transport replaceable by offline test fakes."""

from __future__ import annotations

from typing import Any, Protocol

from .models import AgentAnswerDraft, RouterOutput


class IntentRouter(Protocol):
    async def classify(self, question: str) -> RouterOutput: ...


class AgentAnswerGenerator(Protocol):
    async def generate(
        self,
        question: str,
        retrieval_result: dict[str, Any] | None,
        calculator_result: dict[str, Any] | None,
    ) -> AgentAnswerDraft: ...


class ToolGateway(Protocol):
    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...
