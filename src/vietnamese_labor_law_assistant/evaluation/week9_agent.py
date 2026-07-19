"""Deterministic Week 9 dataset validation, metrics and offline contract benchmark."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from vietnamese_labor_law_assistant.agent.enums import AgentIntent, ToolName
from vietnamese_labor_law_assistant.agent.models import (
    AgentAnswerDraft,
    AgentAtomicClaim,
    RouterOutput,
)
from vietnamese_labor_law_assistant.agent.policies import AgentPolicy
from vietnamese_labor_law_assistant.agent.service import AgentService


class Week9AgentCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(pattern=r"^w9-\d{3}$")
    question: str = Field(min_length=1, max_length=4000)
    expected_intent: AgentIntent
    expected_tools: list[str] = Field(default_factory=list, max_length=3)
    expected_parameters: dict[str, Any] = Field(default_factory=dict)
    should_call_tool: bool
    should_refuse: bool
    requires_clarification: bool
    difficulty: str
    notes: str

    @field_validator("expected_tools")
    @classmethod
    def unique_tools(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("expected_tools must be unique")
        return value


def load_week9_cases(path: Path) -> list[Week9AgentCase]:
    cases = [
        Week9AgentCase.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    identifiers = [case.case_id for case in cases]
    if len(cases) < 40 or len(identifiers) != len(set(identifiers)):
        raise ValueError("Week 9 dataset must contain at least 40 unique cases")
    distribution = {
        intent: sum(case.expected_intent is intent for case in cases) for intent in AgentIntent
    }
    if any(count < 10 for count in distribution.values()):
        raise ValueError("Week 9 dataset must contain at least 10 cases per intent")
    return cases


@dataclass(frozen=True)
class Week9Prediction:
    case_id: str
    intent: str | None
    tools: list[str]
    parameters: dict[str, Any]
    status: str
    latency_ms: float
    errors: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "intent": self.intent,
            "tools": self.tools,
            "parameters": self.parameters,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "errors": self.errors,
        }


def week9_metrics(
    cases: list[Week9AgentCase], predictions: list[Week9Prediction]
) -> dict[str, float]:
    by_id = {prediction.case_id: prediction for prediction in predictions}
    if set(by_id) != {case.case_id for case in cases}:
        raise ValueError("predictions must contain exactly one row for every case")
    total = len(cases)
    intent = tool_set = tool_sequence = parameter = out_of_scope = clarification = 0
    successes = tool_successes = error_successes = tool_calls = 0
    latencies: list[float] = []
    for case in cases:
        prediction = by_id[case.case_id]
        latencies.append(prediction.latency_ms)
        intent += prediction.intent == case.expected_intent.value
        tool_set += set(prediction.tools) == set(case.expected_tools)
        tool_sequence += prediction.tools == case.expected_tools
        parameter += all(
            prediction.parameters.get(key) == value
            for key, value in case.expected_parameters.items()
        )
        out_of_scope += (prediction.status == "OUT_OF_SCOPE") == case.should_refuse
        clarification += (
            prediction.status == "CLARIFICATION_REQUIRED"
        ) == case.requires_clarification
        expected_error = "error" in case.notes.casefold() or "unsupported" in case.notes.casefold()
        error_successes += bool(prediction.errors) == expected_error
        if case.should_call_tool:
            tool_successes += bool(prediction.tools) and not prediction.errors
        else:
            tool_successes += not prediction.tools
        successes += prediction.status in {
            "WORKFLOW_VALID",
            "OUT_OF_SCOPE",
            "CLARIFICATION_REQUIRED",
        }
        tool_calls += len(prediction.tools)
    ordered = sorted(latencies)
    p95_index = min(len(ordered) - 1, max(0, int(len(ordered) * 0.95) - 1))
    return {
        "intent_accuracy": intent / total,
        "tool_selection_accuracy": tool_set / total,
        "tool_sequence_accuracy": tool_sequence / total,
        "parameter_exact_match": parameter / total,
        "parameter_field_accuracy": parameter / total,
        "tool_call_success_rate": tool_successes / total,
        "out_of_scope_accuracy": out_of_scope / total,
        "clarification_accuracy": clarification / total,
        "workflow_success_rate": successes / total,
        "error_handling_success_rate": error_successes / total,
        "average_tool_calls": tool_calls / total,
        "mean_latency_ms": mean(latencies),
        "p95_latency_ms": ordered[p95_index],
    }


def write_jsonl_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    temporary.replace(path)


class _CaseRouter:
    def __init__(self, case: Week9AgentCase) -> None:
        self.case = case

    async def classify(self, question: str) -> RouterOutput:
        del question
        if self.case.requires_clarification:
            return RouterOutput(
                intent=self.case.expected_intent,
                confidence=1,
                rationale_code="DATASET_CLARIFICATION",
                requested_operation="clarify",
                requires_clarification=True,
                clarification_question="Vui lòng bổ sung tham số bắt buộc.",
            )
        if self.case.should_refuse:
            return RouterOutput(
                intent=AgentIntent.OUT_OF_SCOPE,
                confidence=1,
                rationale_code="DATASET_OUT_OF_SCOPE",
                requested_operation="refuse",
                out_of_scope_reason="outside_snapshot",
            )
        retrieval_keys = {
            "top_k",
            "article_number",
            "clause_number",
            "chapter_number",
            "document_id",
        }
        retrieval_arguments = {
            key: value
            for key, value in self.case.expected_parameters.items()
            if key in retrieval_keys
        }
        calculator_arguments = {
            key: value
            for key, value in self.case.expected_parameters.items()
            if key not in retrieval_keys
        }
        return RouterOutput(
            intent=self.case.expected_intent,
            confidence=1,
            rationale_code="DATASET_ROUTE",
            requested_operation="dataset",
            planned_tools=[ToolName(tool) for tool in self.case.expected_tools],
            retrieval_arguments=retrieval_arguments,
            calculator_arguments=calculator_arguments,
        )


class _CaseGateway:
    def __init__(self, case: Week9AgentCase) -> None:
        self.case = case

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        error_case = "error-oriented" in self.case.notes
        is_retrieval = tool_name.startswith("get_") or tool_name == "search_labor_law"
        if error_case:
            return {
                "ok": False,
                "data": None,
                "error": {"code": "DATASET_EXPECTED_ERROR", "message": "safe", "retryable": False},
                "meta": {
                    "tool": tool_name,
                    "schema_version": "1.0",
                    "request_id": self.case.case_id,
                },
            }
        data = (
            {"results": [{"chunk_id": f"{self.case.case_id}-chunk"}]}
            if is_retrieval
            else {"value": 1}
        )
        if tool_name == "get_article":
            data = {"clauses": [{"chunk_id": f"{self.case.case_id}-chunk"}]}
        if tool_name == "get_clause":
            data = {"chunk_id": f"{self.case.case_id}-chunk"}
        return {
            "ok": True,
            "data": data,
            "error": None,
            "meta": {"tool": tool_name, "schema_version": "1.0", "request_id": self.case.case_id},
        }


class _CaseGenerator:
    async def generate(
        self,
        question: str,
        retrieval_result: dict[str, Any] | None,
        calculator_result: dict[str, Any] | None,
    ) -> AgentAnswerDraft:
        del question, calculator_result
        chunk_ids: list[str] = []
        for response in (retrieval_result or {}).get("responses", []):
            data = response.get("data", {})
            rows = data.get("results") or data.get("clauses") or [data]
            chunk_ids.extend(
                row["chunk_id"] for row in rows if isinstance(row, dict) and "chunk_id" in row
            )
        return AgentAnswerDraft(
            answer="Kết quả workflow đã xác minh.",
            citation_chunk_ids=chunk_ids[:1],
            claims=[
                AgentAtomicClaim(
                    claim_id="AGENT-CLM-001",
                    text="Kết quả workflow đã xác minh.",
                    citation_chunk_ids=chunk_ids[:1],
                )
            ],
        )


def run_offline_contract_evaluation(cases: list[Week9AgentCase]) -> list[Week9Prediction]:
    """Exercise the real StateGraph deterministically without a provider or MCP subprocess."""
    predictions: list[Week9Prediction] = []
    for case in cases:
        gateway = _CaseGateway(case)
        service = AgentService(
            _CaseRouter(case),
            _CaseGenerator(),
            gateway,
            gateway,
            AgentPolicy(max_tool_calls=3),
        )
        result = asyncio.run(service.run(case.question, include_trace=True))
        arguments: dict[str, Any] = {}
        for trace in result.tool_trace:
            arguments.update(trace.sanitized_arguments)
        predictions.append(
            Week9Prediction(
                case_id=case.case_id,
                intent=result.intent.value if result.intent else None,
                tools=[trace.tool_name.value for trace in result.tool_trace],
                parameters=arguments,
                status=result.status.value,
                latency_ms=result.latency_ms,
                errors=result.errors,
            )
        )
    return predictions
