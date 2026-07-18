"""Finite, source-bound LangGraph service over the project's real MCP clients."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

from vietnamese_labor_law_assistant.common.settings import Settings, get_settings
from vietnamese_labor_law_assistant.guardrails.citation_parser import extract_legal_citations
from vietnamese_labor_law_assistant.guardrails.models import AtomicClaim, EvidenceContext
from vietnamese_labor_law_assistant.guardrails.policy import guarded_answer
from vietnamese_labor_law_assistant.guardrails.service import CitationGuardrailService
from vietnamese_labor_law_assistant.guardrails.source_registry import CanonicalSourceRegistry
from vietnamese_labor_law_assistant.mcp_clients.legal_calculator import LegalCalculatorMcpClient
from vietnamese_labor_law_assistant.mcp_clients.legal_retrieval import LegalRetrievalMcpClient

from .enums import AgentIntent, ToolName, WorkflowStatus
from .errors import (
    AgentError,
    AnswerGenerationError,
    IntentClassificationError,
    InvalidAgentInputError,
    ToolBudgetExceededError,
    ToolProtocolError,
    ToolResponseValidationError,
    ToolTimeoutError,
    WorkflowVerificationError,
)
from .graph import RouteName, build_agent_graph
from .mcp_gateways import CalculatorMcpGateway, RetrievalMcpGateway
from .models import AgentResult, AgentState, RouterOutput, ToolTrace
from .policies import AgentPolicy
from .protocols import AgentAnswerGenerator, IntentRouter, ToolGateway
from .routing import OpenAIStructuredAgentAnswerGenerator, OpenAIStructuredIntentRouter

DISCLAIMER = "Hệ thống chỉ hỗ trợ tra cứu, không thay thế tư vấn pháp lý chuyên nghiệp."


class AgentService:
    """A bounded graph: one classification and at most three allowlisted MCP calls."""

    def __init__(
        self,
        router: IntentRouter,
        answer_generator: AgentAnswerGenerator,
        retrieval_gateway: ToolGateway,
        calculator_gateway: ToolGateway,
        policy: AgentPolicy,
        guardrail_service: CitationGuardrailService | None = None,
    ) -> None:
        self.router = router
        self.answer_generator = answer_generator
        self.retrieval_gateway = retrieval_gateway
        self.calculator_gateway = calculator_gateway
        self.policy = policy
        self.guardrail_service = guardrail_service
        self.logger = structlog.get_logger(__name__)
        self.graph = build_agent_graph(self).compile()

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> AgentService:
        settings = settings or get_settings()
        policy = AgentPolicy(
            max_input_length=settings.agent_max_input_length,
            max_tool_calls=settings.agent_max_tool_calls,
            tool_timeout_seconds=settings.agent_tool_timeout_seconds,
            workflow_timeout_seconds=settings.agent_workflow_timeout_seconds,
            max_transport_retries=settings.agent_max_transport_retries,
            max_retrieval_top_k=settings.agent_max_retrieval_top_k,
            tool_output_max_chars=settings.agent_tool_output_max_chars,
        )
        return cls(
            router=OpenAIStructuredIntentRouter(settings),
            answer_generator=OpenAIStructuredAgentAnswerGenerator(settings),
            retrieval_gateway=RetrievalMcpGateway(
                LegalRetrievalMcpClient(timeout_seconds=policy.tool_timeout_seconds)
            ),
            calculator_gateway=CalculatorMcpGateway(
                LegalCalculatorMcpClient(timeout_seconds=policy.tool_timeout_seconds)
            ),
            policy=policy,
            guardrail_service=CitationGuardrailService(
                CanonicalSourceRegistry(settings.guardrail_canonical_source_path),
                lower_threshold=settings.guardrail_semantic_lower_threshold,
                high_threshold=settings.guardrail_semantic_high_threshold,
            ),
        )

    async def run(self, question: str, *, include_trace: bool = False) -> AgentResult:
        started = time.perf_counter()
        request_id = str(uuid.uuid4())
        state: AgentState = {
            "request_id": request_id,
            "question": question,
            "tool_calls_used": 0,
            "max_tool_calls": self.policy.max_tool_calls,
            "tool_trace": [],
            "errors": [],
            "citations": [],
            "stage_timings": {},
            "started_at": self._now(),
        }
        try:
            completed = await asyncio.wait_for(
                self.graph.ainvoke(state), timeout=self.policy.workflow_timeout_seconds
            )
        except TimeoutError:
            completed = {
                **state,
                "route_status": WorkflowStatus.TOOL_ERROR.value,
                "final_answer": "Yêu cầu đã quá thời hạn xử lý an toàn.",
                "errors": [self._error(ToolTimeoutError("workflow timeout"))],
                "workflow_verification": {"status": "FAIL", "reason": "WORKFLOW_TIMEOUT"},
            }
        latency_ms = (time.perf_counter() - started) * 1000
        return AgentResult(
            request_id=request_id,
            question=str(completed.get("normalized_question") or question).strip(),
            intent=completed.get("intent"),
            status=WorkflowStatus(
                completed.get("route_status") or WorkflowStatus.OUTPUT_INVALID.value
            ),
            answer=completed.get("final_answer") or "Không thể hoàn tất yêu cầu một cách an toàn.",
            disclaimer=DISCLAIMER,
            citations=completed.get("citations", []),
            clarification_question=completed.get("clarification_question"),
            errors=completed.get("errors", []),
            tool_trace=[ToolTrace.model_validate(item) for item in completed.get("tool_trace", [])]
            if include_trace
            else [],
            workflow_verification=completed.get(
                "workflow_verification", {"status": "FAIL", "reason": "MISSING"}
            ),
            verification=completed.get("verification"),
            latency_ms=latency_ms,
        )

    async def validate_input(self, state: AgentState) -> dict[str, Any]:
        started = time.perf_counter()
        question = str(state.get("question") or "")
        normalized = " ".join(question.strip().split())
        update: dict[str, Any] = {"normalized_question": normalized}
        if not normalized:
            update.update(self._terminal_error(InvalidAgentInputError("blank question")))
        elif len(normalized) > self.policy.max_input_length:
            update.update(self._terminal_error(InvalidAgentInputError("question too long")))
        self._timing(update, state, "validate_input", started)
        return update

    async def classify_intent(self, state: AgentState) -> dict[str, Any]:
        started = time.perf_counter()
        if state.get("route_status"):
            return {}
        try:
            normalized_question = str(state.get("normalized_question") or "")
            output = await self.router.classify(normalized_question)
            update: dict[str, Any] = {
                "intent": output.intent.value,
                "router_output": output.model_dump(mode="json"),
                "planned_tools": [tool.value for tool in output.planned_tools],
                "missing_parameters": output.missing_parameters,
                "clarification_question": output.clarification_question,
            }
            self.logger.info(
                "agent_intent_classified",
                request_id=str(state.get("request_id") or ""),
                intent=output.intent.value,
                planned_tools=update["planned_tools"],
                question_length=len(normalized_question),
            )
            if output.requires_clarification or output.missing_parameters:
                update.update(
                    {
                        "route_status": WorkflowStatus.CLARIFICATION_REQUIRED.value,
                        "clarification_question": output.clarification_question
                        or "Vui lòng cung cấp các tham số còn thiếu: "
                        + ", ".join(output.missing_parameters),
                    }
                )
            elif output.intent is AgentIntent.OUT_OF_SCOPE:
                update["route_status"] = WorkflowStatus.OUT_OF_SCOPE.value
            self._timing(update, state, "classify_intent", started)
            return update
        except (IntentClassificationError, ValueError):
            update = self._terminal_error(IntentClassificationError("classification failed"))
            self._timing(update, state, "classify_intent", started)
            return update

    def route_after_classification(self, state: AgentState) -> RouteName:
        if state.get("route_status"):
            return (
                "out_of_scope"
                if state.get("route_status") == WorkflowStatus.OUT_OF_SCOPE.value
                else "verify"
            )
        intent = state.get("intent")
        if intent == AgentIntent.RETRIEVAL_ONLY.value:
            return "retrieval"
        if intent == AgentIntent.CALCULATOR_ONLY.value:
            return "calculator"
        if intent == AgentIntent.RETRIEVAL_AND_CALCULATOR.value:
            return "combined"
        return "verify"

    async def retrieval_only(self, state: AgentState) -> dict[str, Any]:
        return await self._execute_matching_tools(state, "retrieval")

    async def calculator_only(self, state: AgentState) -> dict[str, Any]:
        return await self._execute_matching_tools(state, "calculator")

    async def _execute_matching_tools(self, state: AgentState, kind: str) -> dict[str, Any]:
        started = time.perf_counter()
        outputs: list[dict[str, Any]] = []
        updates: dict[str, Any] = {"tool_trace": list(state.get("tool_trace", []))}
        for raw_tool in state.get("planned_tools", []):
            tool = ToolName(raw_tool)
            is_retrieval = tool.value in {
                ToolName.SEARCH_LABOR_LAW.value,
                ToolName.GET_ARTICLE.value,
                ToolName.GET_CLAUSE.value,
                ToolName.GET_DOCUMENT_METADATA.value,
            }
            if (kind == "retrieval") != is_retrieval:
                continue
            arguments = self._arguments_for(tool, state)
            result, trace, error = await self._execute_tool(
                state,
                tool,
                arguments,
                self.retrieval_gateway if is_retrieval else self.calculator_gateway,
            )
            updates["tool_trace"].append(trace.model_dump(mode="json"))
            updates["tool_calls_used"] = state.get("tool_calls_used", 0) + len(outputs) + 1
            if error:
                updates["errors"] = [*state.get("errors", []), error]
                updates["route_status"] = WorkflowStatus.TOOL_ERROR.value
                break
            if result is not None:
                outputs.append(result)
        if kind == "retrieval":
            updates["retrieval_result"] = {"responses": outputs}
            if outputs and not self._retrieved_chunk_ids(updates["retrieval_result"]):
                updates["route_status"] = WorkflowStatus.INSUFFICIENT_CONTEXT.value
        else:
            updates["calculator_result"] = {"responses": outputs}
        self._timing(updates, state, f"{kind}_tools", started)
        return updates

    def _arguments_for(self, tool: ToolName, state: AgentState) -> dict[str, Any]:
        router = RouterOutput.model_validate(state.get("router_output") or {})
        if tool in {
            ToolName.SEARCH_LABOR_LAW,
            ToolName.GET_ARTICLE,
            ToolName.GET_CLAUSE,
            ToolName.GET_DOCUMENT_METADATA,
        }:
            if tool is ToolName.SEARCH_LABOR_LAW:
                return self.policy.bounded_retrieval_arguments(
                    router.retrieval_arguments, str(state.get("normalized_question") or "")
                )
            return router.retrieval_arguments
        return router.calculator_arguments

    async def _execute_tool(
        self, state: AgentState, tool: ToolName, arguments: dict[str, Any], gateway: ToolGateway
    ) -> tuple[dict[str, Any] | None, ToolTrace, dict[str, Any] | None]:
        try:
            self.policy.ensure_budget(state.get("tool_calls_used", 0))
        except ToolBudgetExceededError as exc:
            return (
                None,
                self._trace(state, tool, arguments, "blocked", 0, 0, exc.code),
                self._error(exc),
            )
        started_at, started = self._now(), time.perf_counter()
        retry_count = 0
        last_error: AgentError | None = None
        for attempt in range(self.policy.max_transport_retries + 1):
            try:
                response = await asyncio.wait_for(
                    gateway.execute(tool.value, arguments), timeout=self.policy.tool_timeout_seconds
                )
                self._validate_tool_response(response, tool)
                encoded = json.dumps(response, ensure_ascii=False)
                if len(encoded) > self.policy.tool_output_max_chars:
                    raise ToolResponseValidationError("tool output exceeded policy limit")
                trace = ToolTrace(
                    request_id=str(state.get("request_id") or ""),
                    sequence=state.get("tool_calls_used", 0) + 1,
                    server="legal-retrieval"
                    if tool.name.startswith(("SEARCH", "GET_"))
                    else "legal-calculator",
                    tool_name=tool,
                    sanitized_arguments=self.policy.sanitized_arguments(arguments),
                    started_at=started_at,
                    completed_at=self._now(),
                    latency_ms=(time.perf_counter() - started) * 1000,
                    status="ok" if response.get("ok") else "tool_error",
                    error_code=None
                    if response.get("ok")
                    else response.get("error", {}).get("code"),
                    retry_count=retry_count,
                )
                if not response.get("ok"):
                    error = AgentError("tool returned a public error")
                    error.code = str(response.get("error", {}).get("code", "TOOL_ERROR"))
                    return None, trace, self._error(error)
                return response, trace, None
            except TimeoutError:
                last_error = ToolTimeoutError("tool timeout")
            except (ToolProtocolError, ValueError, KeyError):
                last_error = ToolResponseValidationError("invalid tool response")
                break
            except Exception:
                last_error = AgentError("tool transport failed")
                last_error.code = "TOOL_TRANSPORT_ERROR"
                last_error.retryable = True
            if not last_error.retryable or attempt >= self.policy.max_transport_retries:
                break
            retry_count += 1
        error = last_error or AgentError("tool execution failed")
        return (
            None,
            self._trace(state, tool, arguments, "error", started, retry_count, error.code),
            self._error(error),
        )

    def _validate_tool_response(self, response: Any, tool: ToolName) -> None:
        if not isinstance(response, dict) or not isinstance(response.get("ok"), bool):
            raise ToolResponseValidationError("missing envelope")
        meta = response.get("meta")
        if (
            not isinstance(meta, dict)
            or meta.get("tool") != tool.value
            or meta.get("schema_version") != "1.0"
        ):
            raise ToolProtocolError("unexpected tool metadata")
        if response["ok"] and not isinstance(response.get("data"), dict):
            raise ToolResponseValidationError("success has no data")
        if not response["ok"] and not isinstance(response.get("error"), dict):
            raise ToolResponseValidationError("error has no public error")

    async def build_refusal(self, state: AgentState) -> dict[str, Any]:
        reason = (state.get("router_output") or {}).get(
            "out_of_scope_reason"
        ) or "ngoài snapshot pháp luật"
        return {"final_answer": f"Yêu cầu này nằm ngoài phạm vi hỗ trợ ({reason})."}

    async def generate_answer(self, state: AgentState) -> dict[str, Any]:
        if state.get("route_status") == WorkflowStatus.CLARIFICATION_REQUIRED.value:
            return {
                "final_answer": state.get("clarification_question")
                or "Vui lòng cung cấp thêm thông tin."
            }
        if state.get("route_status") == WorkflowStatus.INSUFFICIENT_CONTEXT.value:
            return {"final_answer": "Không tìm thấy context phù hợp để trả lời an toàn."}
        if state.get("route_status") == WorkflowStatus.TOOL_ERROR.value:
            return {"final_answer": "Không thể hoàn tất một công cụ bắt buộc một cách an toàn."}
        try:
            draft = await self.answer_generator.generate(
                str(state.get("normalized_question") or ""),
                state.get("retrieval_result"),
                state.get("calculator_result"),
            )
            known_ids = self._retrieved_chunk_ids(state.get("retrieval_result"))
            if any(chunk_id not in known_ids for chunk_id in draft.citation_chunk_ids):
                raise WorkflowVerificationError("unknown citation")
            return {
                "answer_draft": draft.model_dump(mode="json"),
                "final_answer": draft.answer,
                "citations": [{"chunk_id": chunk_id} for chunk_id in draft.citation_chunk_ids],
            }
        except (AnswerGenerationError, WorkflowVerificationError):
            return self._terminal_error(AnswerGenerationError("generation failed"))

    async def verify_workflow_output(self, state: AgentState) -> dict[str, Any]:
        try:
            traces = state.get("tool_trace", [])
            if len(traces) > self.policy.max_tool_calls:
                raise WorkflowVerificationError("tool budget exceeded")
            if any(
                trace.get("tool_name") not in {item.value for item in self.policy.allowlisted_tools}
                for trace in traces
            ):
                raise WorkflowVerificationError("tool not allowlisted")
            if state.get("intent") == AgentIntent.OUT_OF_SCOPE.value and traces:
                raise WorkflowVerificationError("out-of-scope called a tool")
            known_ids = self._retrieved_chunk_ids(state.get("retrieval_result"))
            if any(
                citation.get("chunk_id") not in known_ids for citation in state.get("citations", [])
            ):
                raise WorkflowVerificationError("citation not from retrieval")
            if state.get("calculator_result") and not any(
                trace.get("tool_name")
                in {
                    item.value
                    for item in {
                        ToolName.CALCULATE_NOTICE_PERIOD,
                        ToolName.CALCULATE_CONTRACT_DURATION,
                    }
                }
                for trace in traces
            ):
                raise WorkflowVerificationError("calculator result lacks a tool trace")
            status = state.get("route_status") or WorkflowStatus.WORKFLOW_VALID.value
            return {
                "route_status": status,
                "workflow_verification": {"status": "PASS", "checks": 5},
            }
        except WorkflowVerificationError as exc:
            return {
                **self._terminal_error(exc),
                "workflow_verification": {"status": "FAIL", "reason": exc.code},
            }

    async def apply_claim_guardrail(self, state: AgentState) -> dict[str, Any]:
        """Verify generated claims from MCP-produced evidence without another tool call."""
        if state.get("route_status") == WorkflowStatus.OUTPUT_INVALID.value:
            return {}
        settings = get_settings()
        if not settings.guardrail_enabled or self.guardrail_service is None:
            return {"verification": {"status": "DISABLED"}}
        if state.get("intent") == AgentIntent.OUT_OF_SCOPE.value:
            result = self.guardrail_service.verify([], [], out_of_scope_refusal=True)
            return {"verification": result.model_dump(mode="json")}
        evidence = self._guardrail_evidence(state)
        if not evidence:
            return {
                "final_answer": "INSUFFICIENT_VERIFIED_EVIDENCE",
                "citations": [],
                "verification": {"status": "INSUFFICIENT_CONTEXT", "reason": "NO_EVIDENCE"},
            }
        cited_ids = [
            item["chunk_id"]
            for item in state.get("citations", [])
            if isinstance(item.get("chunk_id"), str)
        ]
        if not cited_ids:
            cited_ids = [item.chunk_id for item in evidence if item.source_kind == "calculator"]
        claim = AtomicClaim(
            claim_id="AGENT-CLM-001",
            text=str(state.get("final_answer") or ""),
            cited_context_ids=cited_ids,
            legal_references=extract_legal_citations(str(state.get("final_answer") or "")),
        )
        try:
            result = self.guardrail_service.verify([claim], evidence)
            answer, warnings = guarded_answer(str(state.get("final_answer") or ""), result)
            update: dict[str, Any] = {
                "verification": result.model_dump(mode="json"),
                "final_answer": answer,
            }
            if warnings:
                update["guardrail_warnings"] = warnings
            if result.status.value in {"UNSUPPORTED", "INSUFFICIENT_CONTEXT"}:
                update["citations"] = []
            return update
        except Exception:
            return {
                "final_answer": "INSUFFICIENT_VERIFIED_EVIDENCE",
                "citations": [],
                "verification": {"status": "INSUFFICIENT_CONTEXT", "reason": "GUARDRAIL_FAILURE"},
            }

    def _guardrail_evidence(self, state: AgentState) -> list[EvidenceContext]:
        rows: list[EvidenceContext] = []
        for response in (state.get("retrieval_result") or {}).get("responses", []):
            data = response.get("data", {})
            for item in data.get("results", []) + data.get("clauses", []) + [data]:
                if isinstance(item, dict) and item.get("chunk_id") and item.get("content"):
                    rows.append(
                        EvidenceContext(
                            chunk_id=item["chunk_id"],
                            content=item["content"],
                            article_number=item["article_number"],
                            clause_number=item.get("clause_number"),
                            point_label=item.get("point_label"),
                        )
                    )
        registry = CanonicalSourceRegistry(get_settings().guardrail_canonical_source_path)
        for response in (state.get("calculator_result") or {}).get("responses", []):
            for basis in response.get("data", {}).get("legal_basis", []):
                chunk = registry.get(basis.get("source_chunk_id", ""))
                if chunk:
                    rows.append(
                        EvidenceContext(
                            chunk_id=chunk.chunk_id,
                            content=chunk.content,
                            article_number=chunk.article_number,
                            clause_number=chunk.clause_number,
                            point_label=chunk.point_label,
                            source_kind="calculator",
                        )
                    )
        return list({item.chunk_id: item for item in rows}.values())

    async def finalize(self, state: AgentState) -> dict[str, Any]:
        return {"completed_at": self._now()}

    def _retrieved_chunk_ids(self, result: dict[str, Any] | None) -> set[str]:
        identifiers: set[str] = set()
        for response in (result or {}).get("responses", []):
            data = response.get("data", {})
            for item in data.get("results", []) + data.get("clauses", []):
                if isinstance(item, dict) and isinstance(item.get("chunk_id"), str):
                    identifiers.add(item["chunk_id"])
            if isinstance(data.get("chunk_id"), str):
                identifiers.add(data["chunk_id"])
        return identifiers

    def _terminal_error(self, error: AgentError) -> dict[str, Any]:
        return {
            "route_status": WorkflowStatus.OUTPUT_INVALID.value,
            "final_answer": "Không thể hoàn tất yêu cầu một cách an toàn.",
            "errors": [self._error(error)],
        }

    def _error(self, error: AgentError) -> dict[str, Any]:
        return {
            "code": error.code,
            "message": "Yêu cầu không thể được xử lý an toàn.",
            "retryable": error.retryable,
        }

    def _trace(
        self,
        state: AgentState,
        tool: ToolName,
        arguments: dict[str, Any],
        status: str,
        started: float | int,
        retry_count: int,
        error_code: str | None,
    ) -> ToolTrace:
        return ToolTrace(
            request_id=str(state.get("request_id") or ""),
            sequence=state.get("tool_calls_used", 0) + 1,
            server="legal-retrieval"
            if tool.name.startswith(("SEARCH", "GET_"))
            else "legal-calculator",
            tool_name=tool,
            sanitized_arguments=self.policy.sanitized_arguments(arguments),
            started_at=self._now(),
            completed_at=self._now(),
            latency_ms=(time.perf_counter() - started) * 1000 if started else 0,
            status=status,
            error_code=error_code,
            retry_count=retry_count,
        )

    def _timing(self, update: dict[str, Any], state: AgentState, name: str, started: float) -> None:
        update["stage_timings"] = {
            **state.get("stage_timings", {}),
            name: (time.perf_counter() - started) * 1000,
        }

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()
