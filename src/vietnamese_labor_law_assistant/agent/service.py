"""Finite, source-bound LangGraph service over the project's real MCP clients."""

from __future__ import annotations

import asyncio
import copy
import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

from vietnamese_labor_law_assistant.common.settings import Settings, get_settings
from vietnamese_labor_law_assistant.guardrails.citation_parser import extract_numeric_tokens
from vietnamese_labor_law_assistant.guardrails.judge import OpenAIStructuredClaimJudge
from vietnamese_labor_law_assistant.guardrails.models import (
    AtomicClaim,
    EvidenceContext,
    VerificationResult,
)
from vietnamese_labor_law_assistant.guardrails.policy import guarded_answer
from vietnamese_labor_law_assistant.guardrails.service import CitationGuardrailService
from vietnamese_labor_law_assistant.guardrails.source_registry import CanonicalSourceRegistry
from vietnamese_labor_law_assistant.mcp_clients.legal_calculator import LegalCalculatorMcpClient
from vietnamese_labor_law_assistant.mcp_clients.legal_retrieval import LegalRetrievalMcpClient

from .clarifications import (
    ARTICLE_LIMIT_OPERATION,
    NOTICE_FRAMEWORK_OVERVIEW_OPERATION,
    article_limit_clarification,
    clarification_for,
    referenced_article_numbers,
)
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
from .models import (
    AgentAnswerDraft,
    AgentAtomicClaim,
    AgentResult,
    AgentState,
    PlannedToolCall,
    RouterOutput,
    ToolTrace,
)
from .policies import AgentPolicy
from .protocols import AgentAnswerGenerator, IntentRouter, ToolGateway
from .routing import OpenAIStructuredAgentAnswerGenerator, OpenAIStructuredIntentRouter

DISCLAIMER = "Hệ thống chỉ hỗ trợ tra cứu, không thay thế tư vấn pháp lý chuyên nghiệp."


def out_of_scope_answer(reason: str | None = None) -> str:
    """Return the established direct-agent refusal wording for outer reuse."""

    return f"Yêu cầu này nằm ngoài phạm vi hỗ trợ ({reason or 'ngoài snapshot pháp luật'})."


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
    def from_settings(
        cls,
        settings: Settings | None = None,
        *,
        guardrail_service: CitationGuardrailService | None = None,
    ) -> AgentService:
        settings = settings or get_settings()
        policy = AgentPolicy(
            max_input_length=settings.agent_max_input_length,
            max_tool_calls=settings.agent_max_tool_calls,
            max_articles_per_request=settings.agent_max_articles_per_request,
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
            guardrail_service=guardrail_service
            or CitationGuardrailService(
                CanonicalSourceRegistry(settings.guardrail_canonical_source_path),
                judge=OpenAIStructuredClaimJudge(settings)
                if settings.guardrail_llm_judge_enabled
                else None,
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
            router_decision=completed.get("router_decision"),
            planned_tools=[ToolName(item) for item in completed.get("planned_tools", [])],
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
            explicit_articles = referenced_article_numbers(normalized_question)
            output = self._align_explicit_article_plan(output, explicit_articles)
            update: dict[str, Any] = {
                "intent": output.intent.value,
                "router_output": output.model_dump(mode="json"),
                "router_decision": output.requested_operation,
                "tool_plan": [call.model_dump(mode="json") for call in output.tool_plan],
                "planned_tools": [tool.value for tool in output.planned_tools],
                "missing_parameters": output.missing_parameters,
                "clarification_question": output.clarification_question,
            }
            self.logger.info(
                "agent_intent_classified",
                request_id=str(state.get("request_id") or ""),
                intent=output.intent.value,
                planned_tools=update["planned_tools"],
                tool_plan=[
                    {
                        "call_id": call.call_id,
                        "tool_name": call.tool_name.value,
                        "arguments": self.policy.sanitized_arguments(call.arguments),
                        "sequence": call.sequence,
                    }
                    for call in output.tool_plan
                ],
                question_length=len(normalized_question),
            )
            article_count = sum(call.tool_name is ToolName.GET_ARTICLE for call in output.tool_plan)
            plan_exceeds_budget = len(output.tool_plan) > self.policy.max_tool_calls
            if (
                self.policy.article_limit_exceeded(article_count)
                or self.policy.article_limit_exceeded(len(explicit_articles))
                or plan_exceeds_budget
            ):
                clarification = article_limit_clarification(
                    max(article_count, len(explicit_articles)),
                    self.policy.max_articles_per_request,
                )
                update.update(
                    {
                        "route_status": WorkflowStatus.CLARIFICATION_REQUIRED.value,
                        "router_output": {
                            **(update.get("router_output") or {}),
                            "requested_operation": ARTICLE_LIMIT_OPERATION,
                            "requires_clarification": True,
                            "clarification_question": clarification,
                        },
                        "router_decision": ARTICLE_LIMIT_OPERATION,
                        "tool_plan": [],
                        "planned_tools": [],
                        "clarification_question": clarification,
                        "final_answer": clarification,
                    }
                )
            elif output.requires_clarification or output.missing_parameters:
                clarification = clarification_for(output)
                update.update(
                    {
                        "route_status": WorkflowStatus.CLARIFICATION_REQUIRED.value,
                        "clarification_question": clarification,
                        "final_answer": clarification,
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
        missing_targets: list[dict[str, Any]] = []
        updates: dict[str, Any] = {"tool_trace": list(state.get("tool_trace", []))}
        used = state.get("tool_calls_used", 0)
        for raw_call in state.get("tool_plan", []):
            call = PlannedToolCall.model_validate(raw_call)
            tool = call.tool_name
            is_retrieval = tool.value in {
                ToolName.SEARCH_LABOR_LAW.value,
                ToolName.GET_ARTICLE.value,
                ToolName.GET_CLAUSE.value,
                ToolName.GET_DOCUMENT_METADATA.value,
            }
            if (kind == "retrieval") != is_retrieval:
                continue
            arguments = self._arguments_for(call, state)
            result, trace, error = await self._execute_tool(
                state,
                call,
                arguments,
                self.retrieval_gateway if is_retrieval else self.calculator_gateway,
                used,
            )
            updates["tool_trace"].append(trace.model_dump(mode="json"))
            used += 1
            updates["tool_calls_used"] = used
            if error:
                updates["errors"] = [*updates.get("errors", state.get("errors", [])), error]
                if tool is ToolName.GET_ARTICLE and error.get("code") == "ARTICLE_NOT_FOUND":
                    missing_targets.append(
                        {
                            "call_id": call.call_id,
                            "tool_name": tool.value,
                            "article_number": arguments["article_number"],
                            "error_code": "ARTICLE_NOT_FOUND",
                        }
                    )
                    continue
                updates["route_status"] = WorkflowStatus.TOOL_ERROR.value
                break
            if result is not None:
                outputs.append(
                    {
                        **result,
                        "agent_call": {
                            "call_id": call.call_id,
                            "tool_name": tool.value,
                            "sequence": call.sequence,
                            "target_article_number": arguments.get("article_number"),
                        },
                    }
                )
        if kind == "retrieval":
            updates["retrieval_result"] = {
                "responses": outputs,
                "missing_targets": missing_targets,
            }
            if outputs and not self._retrieved_chunk_ids(updates["retrieval_result"]):
                updates["route_status"] = WorkflowStatus.INSUFFICIENT_CONTEXT.value
            elif missing_targets and not outputs:
                updates["route_status"] = WorkflowStatus.INSUFFICIENT_CONTEXT.value
        else:
            updates["calculator_result"] = {"responses": outputs}
        self._timing(updates, state, f"{kind}_tools", started)
        return updates

    def _arguments_for(self, call: PlannedToolCall, state: AgentState) -> dict[str, Any]:
        if call.tool_name in {
            ToolName.SEARCH_LABOR_LAW,
            ToolName.GET_ARTICLE,
            ToolName.GET_CLAUSE,
            ToolName.GET_DOCUMENT_METADATA,
        }:
            if call.tool_name is ToolName.SEARCH_LABOR_LAW:
                return self.policy.bounded_retrieval_arguments(
                    call.arguments, str(state.get("normalized_question") or "")
                )
        return call.arguments

    async def _execute_tool(
        self,
        state: AgentState,
        call: PlannedToolCall,
        arguments: dict[str, Any],
        gateway: ToolGateway,
        used: int,
    ) -> tuple[dict[str, Any] | None, ToolTrace, dict[str, Any] | None]:
        tool = call.tool_name
        try:
            self.policy.ensure_budget(used)
        except ToolBudgetExceededError as exc:
            return (
                None,
                self._trace(state, call, arguments, "blocked", 0, 0, exc.code, used),
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
                    call_id=call.call_id,
                    sequence=used + 1,
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
            self._trace(state, call, arguments, "error", started, retry_count, error.code, used),
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
        return {"final_answer": out_of_scope_answer(reason)}

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
        if self._requires_complete_source_overview(state):
            overview = self._article_lookup_fallback(state)
            if overview is not None:
                return {
                    "answer_draft": overview.model_dump(mode="json"),
                    "final_answer": overview.answer,
                    "citations": [
                        {"chunk_id": chunk_id} for chunk_id in overview.citation_chunk_ids
                    ],
                }
        try:
            draft = await self.answer_generator.generate(
                str(state.get("normalized_question") or ""),
                self._project_retrieval_result(state),
                state.get("calculator_result"),
            )
            draft = self._enrich_numeric_claim_citations(draft, self._guardrail_evidence(state))
            known_ids = self._retrieved_chunk_ids(state.get("retrieval_result"))
            known_ids.update(item.chunk_id for item in self._guardrail_evidence(state))
            calculator_ids = {
                item.chunk_id
                for item in self._guardrail_evidence(state)
                if item.source_kind == "calculator"
            }
            allowed_ids = known_ids | calculator_ids
            claim_ids = {
                chunk_id for claim in draft.claims for chunk_id in claim.citation_chunk_ids
            }
            if self._is_complete_article_lookup(state) and not known_ids.issubset(claim_ids):
                fallback = self._article_lookup_fallback(state)
                if fallback is not None:
                    draft = fallback
                    claim_ids = {
                        chunk_id for claim in draft.claims for chunk_id in claim.citation_chunk_ids
                    }
            self._validate_claim_article_associations(draft, self._guardrail_evidence(state), state)
            if any(
                chunk_id not in allowed_ids for chunk_id in draft.citation_chunk_ids
            ) or not claim_ids.issubset(allowed_ids):
                raise WorkflowVerificationError("unknown citation")
            return {
                "answer_draft": draft.model_dump(mode="json"),
                "final_answer": draft.answer,
                "citations": [{"chunk_id": chunk_id} for chunk_id in draft.citation_chunk_ids],
            }
        except (AnswerGenerationError, WorkflowVerificationError):
            fallback = self._article_lookup_fallback(state)
            if fallback is not None:
                return {
                    "answer_draft": fallback.model_dump(mode="json"),
                    "final_answer": fallback.answer,
                    "citations": [
                        {"chunk_id": chunk_id} for chunk_id in fallback.citation_chunk_ids
                    ],
                }
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
            known_ids.update(item.chunk_id for item in self._guardrail_evidence(state))
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
        if state.get("route_status") == WorkflowStatus.CLARIFICATION_REQUIRED.value:
            return {
                "verification": {
                    "status": "CLARIFICATION_REQUIRED",
                    "reason": "CLARIFICATION_REQUIRED",
                    "warnings": [],
                    "claims": [],
                }
            }
        if state.get("route_status") == WorkflowStatus.INSUFFICIENT_CONTEXT.value:
            reason = (
                "ARTICLE_NOT_FOUND"
                if (state.get("retrieval_result") or {}).get("missing_targets")
                else "INSUFFICIENT_CONTEXT"
            )
            return {"verification": {"status": "INSUFFICIENT_CONTEXT", "reason": reason}}
        settings = get_settings()
        if not settings.guardrail_enabled or self.guardrail_service is None:
            return {"verification": {"status": "DISABLED"}}
        if state.get("intent") == AgentIntent.OUT_OF_SCOPE.value:
            result = self.guardrail_service.verify([], [], out_of_scope_refusal=True)
            return {"verification": result.model_dump(mode="json")}
        draft = state.get("answer_draft") or {}
        raw_claims = draft.get("claims") if isinstance(draft, dict) else None
        if not isinstance(raw_claims, list) or not raw_claims:
            return {
                "final_answer": "INSUFFICIENT_VERIFIED_EVIDENCE",
                "citations": [],
                "verification": {
                    "status": "INSUFFICIENT_CONTEXT",
                    "reason": "INVALID_CLAIM_CONTRACT",
                },
            }
        evidence = self._guardrail_evidence(state)
        if not evidence:
            return {
                "final_answer": "INSUFFICIENT_VERIFIED_EVIDENCE",
                "citations": [],
                "verification": {"status": "INSUFFICIENT_CONTEXT", "reason": "NO_EVIDENCE"},
            }
        claims = [
            AtomicClaim(
                claim_id=str(item["claim_id"]),
                text=str(item["text"]),
                cited_context_ids=list(item.get("citation_chunk_ids", [])),
                parse_inline_references=False,
                target_article_number=item.get("target_article_number"),
            )
            for item in raw_claims
            if isinstance(item, dict)
        ]
        try:
            # The singleton has already warmed during API startup.  This bounded worker call
            # protects the event loop and returns a fail-closed result on an abnormal scorer.
            result = await asyncio.wait_for(
                asyncio.to_thread(self.guardrail_service.verify, claims, evidence),
                timeout=settings.guardrail_semantic_timeout_seconds,
            )
            fallback = self._article_lookup_fallback(state)
            fallback_used = False
            fallback_citation_ids: list[str] | None = None
            if (
                result.status.value in {"UNSUPPORTED", "INSUFFICIENT_CONTEXT"}
                and fallback is not None
            ):
                fallback_state: AgentState = {
                    **state,
                    "answer_draft": fallback.model_dump(mode="json"),
                    "final_answer": fallback.answer,
                }
                fallback_evidence = self._guardrail_evidence(fallback_state)
                fallback_claims = [
                    AtomicClaim(
                        claim_id=claim.claim_id,
                        text=claim.text,
                        cited_context_ids=claim.citation_chunk_ids,
                        parse_inline_references=False,
                        target_article_number=claim.target_article_number,
                    )
                    for claim in fallback.claims
                ]
                fallback_result = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.guardrail_service.verify, fallback_claims, fallback_evidence
                    ),
                    timeout=settings.guardrail_semantic_timeout_seconds,
                )
                if fallback_result.status.value in {"SUPPORTED", "PARTIALLY_SUPPORTED"}:
                    self.logger.info(
                        "article_lookup_guardrail_fallback_used",
                        claim_count=len(fallback_claims),
                        evidence_count=len(fallback_evidence),
                        status=fallback_result.status.value,
                    )
                    result = fallback_result
                    claims = fallback_claims
                    state = fallback_state
                    fallback_used = True
                    fallback_citation_ids = fallback.citation_chunk_ids
            missing_warnings = self._missing_article_warnings(state)
            if missing_warnings:
                result = result.model_copy(
                    update={"warnings": [*result.warnings, *missing_warnings]}
                )
            answer, warnings = guarded_answer(str(state.get("final_answer") or ""), result, claims)
            answer = self._structured_multi_article_answer(answer, result, claims, state)
            update: dict[str, Any] = {
                "verification": result.model_dump(mode="json"),
                "final_answer": answer,
            }
            if warnings:
                update["guardrail_warnings"] = warnings
            if result.status.value in {"UNSUPPORTED", "INSUFFICIENT_CONTEXT"}:
                update["citations"] = []
            elif (
                fallback_used
                and fallback_citation_ids is not None
                and result.status.value
                in {
                    "SUPPORTED",
                    "PARTIALLY_SUPPORTED",
                }
            ):
                update["citations"] = [{"chunk_id": chunk_id} for chunk_id in fallback_citation_ids]
            return update
        except TimeoutError:
            self.logger.warning(
                "guardrail_semantic_timeout",
                timeout_seconds=settings.guardrail_semantic_timeout_seconds,
                claim_count=len(claims),
                evidence_count=len(evidence),
            )
            return {
                "final_answer": "INSUFFICIENT_VERIFIED_EVIDENCE",
                "citations": [],
                "verification": {"status": "INSUFFICIENT_CONTEXT", "reason": "GUARDRAIL_TIMEOUT"},
            }
        except Exception as exc:
            self.logger.warning(
                "guardrail_semantic_failure",
                exception_type=type(exc).__name__,
                claim_count=len(claims),
                evidence_count=len(evidence),
            )
            return {
                "final_answer": "INSUFFICIENT_VERIFIED_EVIDENCE",
                "citations": [],
                "verification": {"status": "INSUFFICIENT_CONTEXT", "reason": "GUARDRAIL_FAILURE"},
            }

    def _guardrail_evidence(self, state: AgentState) -> list[EvidenceContext]:
        rows: list[EvidenceContext] = []
        retrieval_ids: list[str] = []
        calculator_ids: list[str] = []
        for response in (state.get("retrieval_result") or {}).get("responses", []):
            data = response.get("data", {})
            call = response.get("agent_call", {})
            call_id = call.get("call_id")
            tool_name = call.get("tool_name")
            target_article = call.get("target_article_number")
            for item in data.get("results", []) + data.get("clauses", []) + [data]:
                if isinstance(item, dict) and item.get("chunk_id") and item.get("content"):
                    rows.append(
                        EvidenceContext(
                            chunk_id=item["chunk_id"],
                            content=item["content"],
                            article_number=item["article_number"],
                            clause_number=item.get("clause_number"),
                            point_label=item.get("point_label"),
                            point_labels=item.get("point_labels", []),
                            origin_call_ids=[call_id] if isinstance(call_id, str) else [],
                            origin_tool_names=[tool_name] if isinstance(tool_name, str) else [],
                            target_article_numbers=(
                                [target_article] if isinstance(target_article, int) else []
                            ),
                        )
                    )
                    retrieval_ids.append(str(item["chunk_id"]))
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
                            point_labels=chunk.point_labels,
                            source_kind="calculator",
                        )
                    )
                    calculator_ids.append(chunk.chunk_id)
        merged_by_id: dict[str, EvidenceContext] = {}
        for item in rows:
            existing = merged_by_id.get(item.chunk_id)
            if existing is None:
                merged_by_id[item.chunk_id] = item
                continue
            merged_by_id[item.chunk_id] = existing.model_copy(
                update={
                    "origin_call_ids": list(
                        dict.fromkeys([*existing.origin_call_ids, *item.origin_call_ids])
                    ),
                    "origin_tool_names": list(
                        dict.fromkeys([*existing.origin_tool_names, *item.origin_tool_names])
                    ),
                    "target_article_numbers": list(
                        dict.fromkeys(
                            [
                                *existing.target_article_numbers,
                                *item.target_article_numbers,
                            ]
                        )
                    ),
                }
            )
        merged = list(merged_by_id.values())
        draft = state.get("answer_draft") or {}
        raw_claims = draft.get("claims") or [] if isinstance(draft, dict) else []
        cited_ids = list(
            dict.fromkeys(
                str(chunk_id)
                for claim in raw_claims
                if isinstance(claim, dict)
                for chunk_id in claim.get("citation_chunk_ids", [])
                if isinstance(chunk_id, str)
            )
        )
        max_contexts = get_settings().guardrail_semantic_max_contexts
        retained = self._fair_context_projection(
            merged,
            cited_ids,
            self._requested_article_numbers(state),
            max_contexts,
        )
        retained_ids = {item.chunk_id for item in retained}
        dropped = [item.chunk_id for item in merged if item.chunk_id not in retained_ids]
        self.logger.info(
            "guardrail_evidence_merged",
            retrieval_evidence_ids=retrieval_ids,
            calculator_evidence_ids=calculator_ids,
            cited_context_ids=cited_ids,
            retained_context_ids=[item.chunk_id for item in retained],
            retained_context_origins=[
                {
                    "chunk_id": item.chunk_id,
                    "article_number": item.article_number,
                    "call_ids": item.origin_call_ids,
                    "tool_names": item.origin_tool_names,
                    "target_articles": item.target_article_numbers,
                }
                for item in retained
            ],
            dropped_context_ids=dropped,
            max_contexts=max_contexts,
        )
        return retained

    @staticmethod
    def _fair_context_projection(
        evidence: list[EvidenceContext],
        cited_ids: list[str],
        target_articles: list[int],
        max_contexts: int,
    ) -> list[EvidenceContext]:
        by_id = {item.chunk_id: item for item in evidence}
        cited = {chunk_id for chunk_id in cited_ids if chunk_id in by_id}
        ordered_targets = list(
            dict.fromkeys([*target_articles, *(item.article_number for item in evidence)])
        )
        selected: list[EvidenceContext] = []
        selected_ids: set[str] = set()

        def add(item: EvidenceContext) -> None:
            if item.chunk_id not in selected_ids and len(selected) < max_contexts:
                selected.append(item)
                selected_ids.add(item.chunk_id)

        # Reserve one context per target first; prefer a cited context for that target.
        for article_number in ordered_targets:
            candidates = [item for item in evidence if item.article_number == article_number]
            seed = next(
                (
                    by_id[chunk_id]
                    for chunk_id in cited_ids
                    if chunk_id in cited and by_id[chunk_id].article_number == article_number
                ),
                None,
            )
            if seed is None and candidates:
                seed = candidates[0]
            if seed is not None:
                add(seed)
        # All remaining cited contexts precede uncited global fill.
        for chunk_id in cited_ids:
            if chunk_id in by_id:
                add(by_id[chunk_id])
        for item in evidence:
            add(item)
        return selected

    def _project_retrieval_result(self, state: AgentState) -> dict[str, Any] | None:
        result = state.get("retrieval_result")
        if not result:
            return None
        retained_ids = {item.chunk_id for item in self._guardrail_evidence(state)}
        projected = copy.deepcopy(result)
        for response in projected.get("responses", []):
            data = response.get("data", {})
            for key in ("results", "clauses"):
                if isinstance(data.get(key), list):
                    data[key] = [
                        item
                        for item in data[key]
                        if isinstance(item, dict) and item.get("chunk_id") in retained_ids
                    ]
            if isinstance(data.get("chunk_id"), str) and data["chunk_id"] not in retained_ids:
                response["data"] = {}
        return projected

    def _requested_article_numbers(self, state: AgentState) -> list[int]:
        return [
            int(call["arguments"]["article_number"])
            for call in state.get("tool_plan", [])
            if call.get("tool_name") == ToolName.GET_ARTICLE.value
            and isinstance(call.get("arguments"), dict)
            and isinstance(call["arguments"].get("article_number"), int)
        ]

    def _validate_claim_article_associations(
        self,
        draft: AgentAnswerDraft,
        evidence: list[EvidenceContext],
        state: AgentState,
    ) -> None:
        targets = self._requested_article_numbers(state)
        if not targets:
            return
        by_id = {item.chunk_id: item for item in evidence}
        multi_article = len(targets) > 1
        for claim in draft.claims:
            target = claim.target_article_number
            if multi_article and target is None:
                raise WorkflowVerificationError("multi-article claim lacks target article")
            if target is not None and target not in targets:
                raise WorkflowVerificationError("claim target not in requested articles")
            if target is not None and any(
                by_id[chunk_id].article_number != target
                for chunk_id in claim.citation_chunk_ids
                if chunk_id in by_id
            ):
                raise WorkflowVerificationError("cross-article citation mismatch")

    def _missing_article_warnings(self, state: AgentState) -> list[str]:
        return [
            f"ARTICLE_NOT_FOUND:{item['article_number']}"
            for item in (state.get("retrieval_result") or {}).get("missing_targets", [])
            if isinstance(item, dict) and isinstance(item.get("article_number"), int)
        ]

    def _structured_multi_article_answer(
        self,
        answer: str,
        result: VerificationResult,
        claims: list[AtomicClaim],
        state: AgentState,
    ) -> str:
        targets = self._requested_article_numbers(state)
        if result.status.value != "SUPPORTED" or len(targets) < 2:
            return answer
        grouped: dict[int, list[str]] = {article_number: [] for article_number in targets}
        for claim in claims:
            if claim.target_article_number in grouped:
                grouped[claim.target_article_number].append(claim.text)
        sections = [
            f"Điều {article_number}:\n"
            + "\n".join(f"- {claim_text}" for claim_text in grouped[article_number])
            for article_number in targets
            if grouped[article_number]
        ]
        return "\n\n".join(sections) or answer

    def _enrich_numeric_claim_citations(
        self, draft: AgentAnswerDraft, evidence: list[EvidenceContext]
    ) -> AgentAnswerDraft:
        """Attach retrieved source chunks that contain an omitted literal number.

        This is deliberately narrow: it never invents a chunk ID, changes a claim,
        or treats lexical overlap as legal support. It only completes a structured
        citation with already retrieved canonical evidence. The final semantic
        guardrail still verifies every claim against the resulting evidence set.
        """

        by_chunk_id = {item.chunk_id: item for item in evidence}
        enriched_claims: list[AgentAtomicClaim] = []
        additions: dict[str, list[str]] = {}
        for claim in draft.claims:
            cited = list(dict.fromkeys(claim.citation_chunk_ids))
            cited_contexts = [
                by_chunk_id[chunk_id] for chunk_id in cited if chunk_id in by_chunk_id
            ]
            supported_numbers = (
                set().union(*(extract_numeric_tokens(item.content) for item in cited_contexts))
                if cited_contexts
                else set()
            )
            supported_numbers.update(str(item.article_number) for item in cited_contexts)
            supported_numbers.update(
                str(item.clause_number) for item in cited_contexts if item.clause_number is not None
            )
            missing_numbers = extract_numeric_tokens(claim.text) - supported_numbers
            candidates: list[str] = []
            for item in evidence:
                if item.chunk_id in cited:
                    continue
                if (
                    claim.target_article_number is not None
                    and item.article_number != claim.target_article_number
                ):
                    continue
                item_numbers = extract_numeric_tokens(item.content)
                item_numbers.add(str(item.article_number))
                if item.clause_number is not None:
                    item_numbers.add(str(item.clause_number))
                if missing_numbers.intersection(item_numbers):
                    candidates.append(item.chunk_id)
            added = candidates[: max(0, 20 - len(cited))]
            if added:
                additions[claim.claim_id] = added
                cited.extend(added)
            enriched_claims.append(claim.model_copy(update={"citation_chunk_ids": cited}))
        all_citations = list(
            dict.fromkeys(
                chunk_id for claim in enriched_claims for chunk_id in claim.citation_chunk_ids
            )
        )
        if not additions or len(all_citations) > 20:
            return draft
        self.logger.info(
            "agent_claim_citations_enriched",
            claim_ids=sorted(additions),
            added_context_ids=additions,
        )
        return draft.model_copy(
            update={"claims": enriched_claims, "citation_chunk_ids": all_citations}
        )

    def _article_lookup_fallback(self, state: AgentState) -> AgentAnswerDraft | None:
        """Build a bounded, verbatim source projection for a generic article lookup.

        It is available only after an LLM draft fails closed. The projection uses
        the existing MCP response, does not infer a rule, and is verified by the
        same claim guardrail before it can become public output.
        """

        planned_tools = state.get("planned_tools", [])
        if (
            state.get("intent") != AgentIntent.RETRIEVAL_ONLY.value
            or not planned_tools
            or any(tool != ToolName.GET_ARTICLE.value for tool in planned_tools)
        ):
            return None
        source_state: AgentState = {**state, "answer_draft": None}
        available = self._guardrail_evidence(source_state)
        max_contexts = get_settings().guardrail_semantic_max_contexts
        requested_articles = self._requested_article_numbers(state)
        article_order = list(
            dict.fromkeys([*requested_articles, *(item.article_number for item in available)])
        )
        multi_article = len(article_order) > 1
        grouped_parts: dict[int, list[str]] = {article: [] for article in article_order}
        claims: list[AgentAtomicClaim] = []
        answer_length = 0
        for item in available[:max_contexts]:
            if len(item.content) > 1200:
                continue
            heading_length = (
                len(f"Điều {item.article_number}:\n")
                if multi_article and not grouped_parts[item.article_number]
                else 0
            )
            separator_length = 2 if grouped_parts[item.article_number] else 0
            if answer_length + heading_length + separator_length + len(item.content) > 6000:
                break
            grouped_parts[item.article_number].append(item.content)
            answer_length += heading_length + separator_length + len(item.content)
            claims.append(
                AgentAtomicClaim(
                    claim_id=f"AGENT-CLM-SOURCE-{len(claims) + 1:02d}",
                    text=item.content,
                    citation_chunk_ids=[item.chunk_id],
                    target_article_number=item.article_number,
                )
            )
        if not claims:
            return None
        answer_parts = []
        for article_number in article_order:
            contents = grouped_parts[article_number]
            if not contents:
                continue
            article_text = "\n\n".join(contents)
            answer_parts.append(
                f"Điều {article_number}:\n{article_text}" if multi_article else article_text
            )
        chunk_ids = [claim.citation_chunk_ids[0] for claim in claims]
        return AgentAnswerDraft(
            answer="\n\n".join(answer_parts), citation_chunk_ids=chunk_ids, claims=claims
        )

    @staticmethod
    def _is_complete_article_lookup(state: AgentState) -> bool:
        planned_tools = state.get("planned_tools", [])
        return bool(planned_tools) and all(
            tool == ToolName.GET_ARTICLE.value for tool in planned_tools
        )

    @staticmethod
    def _align_explicit_article_plan(
        output: RouterOutput, explicit_articles: list[int]
    ) -> RouterOutput:
        """Prefer exact article tools when the question explicitly names legal articles."""

        if not explicit_articles or output.requires_clarification:
            return output
        replace_search = output.intent is AgentIntent.RETRIEVAL_AND_CALCULATOR and any(
            call.tool_name is ToolName.SEARCH_LABOR_LAW for call in output.tool_plan
        )
        if output.intent is not AgentIntent.OUT_OF_SCOPE and not replace_search:
            return output
        retained = [
            call for call in output.tool_plan if call.tool_name is not ToolName.SEARCH_LABOR_LAW
        ]
        for article_number in explicit_articles:
            retained.append(
                PlannedToolCall(
                    call_id=f"explicit-article-{article_number}",
                    tool_name=ToolName.GET_ARTICLE,
                    arguments={"article_number": article_number},
                    sequence=len(retained) + 1,
                    purpose="retrieve explicitly requested legal article",
                )
            )
        intent = (
            AgentIntent.RETRIEVAL_AND_CALCULATOR
            if any(call.tool_name is ToolName.CALCULATE_NOTICE_PERIOD for call in retained)
            else AgentIntent.RETRIEVAL_ONLY
        )
        data = output.model_dump(mode="python")
        data.update(
            {
                "intent": intent,
                "rationale_code": "EXPLICIT_ARTICLE_REFERENCE",
                "requested_operation": "GET_EXPLICIT_ARTICLES",
                "tool_plan": [call.model_dump(mode="python") for call in retained],
                "planned_tools": [],
                "out_of_scope_reason": None,
            }
        )
        return RouterOutput.model_validate(data)

    @staticmethod
    def _requires_complete_source_overview(state: AgentState) -> bool:
        router_output = state.get("router_output") or {}
        return (
            router_output.get("requested_operation") == NOTICE_FRAMEWORK_OVERVIEW_OPERATION
            and state.get("intent") == AgentIntent.RETRIEVAL_ONLY.value
            and AgentService._is_complete_article_lookup(state)
        )

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
        call: PlannedToolCall,
        arguments: dict[str, Any],
        status: str,
        started: float | int,
        retry_count: int,
        error_code: str | None,
        used: int,
    ) -> ToolTrace:
        tool = call.tool_name
        return ToolTrace(
            request_id=str(state.get("request_id") or ""),
            call_id=call.call_id,
            sequence=used + 1,
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
