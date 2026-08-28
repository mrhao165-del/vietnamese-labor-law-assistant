"""Outer facade that preserves the existing direct-QA service boundary."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from vietnamese_labor_law_assistant.guardrails.models import VerificationResult

from .case_graph import CaseAnalysisResult, CaseAnalysisStatus
from .enums import AgentIntent, WorkflowStatus
from .errors import RequestModeRoutingError
from .mode_routing import RequestMode
from .models import AgentResult
from .service import DISCLAIMER, out_of_scope_answer

_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_VERIFIED_EVIDENCE"


class RequestModeRouter(Protocol):
    async def route(self, question: str) -> RequestMode: ...


class DirectQaService(Protocol):
    async def run(self, question: str, *, include_trace: bool = False) -> AgentResult: ...


class CaseAnalysisRunner(Protocol):
    async def run(self, question: str) -> CaseAnalysisResult: ...


class AssistantResult(BaseModel):
    """Typed outer result while retaining the established ``AgentResult`` contract."""

    model_config = ConfigDict(extra="forbid")

    request_mode: RequestMode | None
    agent_result: AgentResult
    case_analysis: CaseAnalysisResult | None = None


class AssistantService:
    """Route once, then delegate to exactly one bounded execution path."""

    def __init__(
        self,
        mode_router: RequestModeRouter,
        direct_qa_service: DirectQaService,
        case_graph: CaseAnalysisRunner,
        out_of_scope_verifier: Callable[[], VerificationResult],
    ) -> None:
        self.mode_router = mode_router
        self.direct_qa_service = direct_qa_service
        self.case_graph = case_graph
        self.out_of_scope_verifier = out_of_scope_verifier

    async def run(self, question: str, *, include_trace: bool = False) -> AssistantResult:
        """Return a typed fail-closed result without reimplementing direct-QA behavior."""

        started = time.perf_counter()
        try:
            mode = await self.mode_router.route(question)
        except RequestModeRoutingError:
            return AssistantResult(
                request_mode=None,
                agent_result=self._routing_failure(question, started),
            )

        if mode is RequestMode.DIRECT_QA:
            result = await self.direct_qa_service.run(question, include_trace=include_trace)
            return AssistantResult(request_mode=mode, agent_result=result)
        if mode is RequestMode.CASE_ANALYSIS:
            case_result = await self.case_graph.run(question)
            return AssistantResult(
                request_mode=mode,
                agent_result=self._case_result(question, case_result, started),
                case_analysis=case_result,
            )
        return AssistantResult(
            request_mode=RequestMode.OUT_OF_SCOPE,
            agent_result=self._out_of_scope(
                question,
                self.out_of_scope_verifier(),
                started,
            ),
        )

    @staticmethod
    def _case_result(question: str, case_result: CaseAnalysisResult, started: float) -> AgentResult:
        reason = case_result.status.value
        if case_result.status is CaseAnalysisStatus.CLARIFICATION_REQUIRED:
            status = WorkflowStatus.CLARIFICATION_REQUIRED
            verification_status = WorkflowStatus.CLARIFICATION_REQUIRED.value
            clarification = case_result.clarification
            assert clarification is not None
            answer = "\n".join(question.question for question in clarification.questions)
        elif case_result.status in {
            CaseAnalysisStatus.EVIDENCE_REQUEST_READY,
            CaseAnalysisStatus.UNSUPPORTED_SCOPE,
        }:
            status = WorkflowStatus.INSUFFICIENT_CONTEXT
            verification_status = WorkflowStatus.INSUFFICIENT_CONTEXT.value
            answer = _INSUFFICIENT_EVIDENCE
        else:
            status = WorkflowStatus.OUTPUT_INVALID
            verification_status = WorkflowStatus.OUTPUT_INVALID.value
            answer = _INSUFFICIENT_EVIDENCE
        return AgentResult(
            request_id=case_result.request_id,
            question=question.strip(),
            router_decision=reason,
            status=status,
            answer=answer,
            disclaimer=DISCLAIMER,
            citations=[],
            errors=[],
            tool_trace=[],
            workflow_verification={"status": "PASS", "reason": reason},
            verification={
                "status": verification_status,
                "reason": reason,
                "claims": [],
                "warnings": [],
            },
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    @staticmethod
    def _out_of_scope(
        question: str, verification: VerificationResult, started: float
    ) -> AgentResult:
        return AgentResult(
            request_id=str(uuid.uuid4()),
            question=question.strip(),
            intent=AgentIntent.OUT_OF_SCOPE,
            router_decision="OUT_OF_SCOPE",
            status=WorkflowStatus.OUT_OF_SCOPE,
            answer=out_of_scope_answer(),
            disclaimer=DISCLAIMER,
            citations=[],
            errors=[],
            tool_trace=[],
            workflow_verification={"status": "PASS", "reason": "OUT_OF_SCOPE"},
            verification=verification.model_dump(mode="json"),
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    @staticmethod
    def _routing_failure(question: str, started: float) -> AgentResult:
        return AgentResult(
            request_id=str(uuid.uuid4()),
            question=question.strip(),
            router_decision=RequestModeRoutingError.code,
            status=WorkflowStatus.ROUTING_ERROR,
            answer="Không thể phân loại yêu cầu một cách an toàn.",
            disclaimer=DISCLAIMER,
            citations=[],
            errors=[
                {
                    "code": RequestModeRoutingError.code,
                    "message": "Request-mode routing failed.",
                    "retryable": False,
                }
            ],
            tool_trace=[],
            workflow_verification={
                "status": "FAIL",
                "reason": RequestModeRoutingError.code,
            },
            verification={
                "status": "INSUFFICIENT_CONTEXT",
                "reason": RequestModeRoutingError.code,
                "claims": [],
                "warnings": [],
            },
            latency_ms=(time.perf_counter() - started) * 1000,
        )
