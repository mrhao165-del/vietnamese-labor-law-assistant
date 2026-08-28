"""Offline routing tests for the additive AssistantService facade."""

from __future__ import annotations

from typing import Any

import pytest

from vietnamese_labor_law_assistant.agent.assistant_service import (
    AssistantResult,
    AssistantService,
)
from vietnamese_labor_law_assistant.agent.case_graph import (
    CaseAnalysisErrorCode,
    CaseAnalysisResult,
    CaseAnalysisStatus,
)
from vietnamese_labor_law_assistant.agent.enums import AgentIntent, WorkflowStatus
from vietnamese_labor_law_assistant.agent.errors import RequestModeRoutingError
from vietnamese_labor_law_assistant.agent.mode_routing import RequestMode
from vietnamese_labor_law_assistant.agent.models import AgentResult
from vietnamese_labor_law_assistant.decision_support.clarification import (
    TargetedClarificationBuilder,
)
from vietnamese_labor_law_assistant.decision_support.enums import (
    AssertionMode,
    SourceType,
)
from vietnamese_labor_law_assistant.decision_support.enums import (
    VerificationStatus as FactVerificationStatus,
)
from vietnamese_labor_law_assistant.decision_support.evidence_requests import (
    EvidenceRequestSkeletonBuilder,
)
from vietnamese_labor_law_assistant.decision_support.issue_registry import (
    ISSUE_REGISTRY,
    FactKey,
)
from vietnamese_labor_law_assistant.decision_support.issues import IssueCode
from vietnamese_labor_law_assistant.decision_support.missing_facts import MissingFactDetector
from vietnamese_labor_law_assistant.decision_support.models import (
    CandidateIssue,
    CaseFact,
    CaseIntakeResult,
    SourceSpan,
)
from vietnamese_labor_law_assistant.decision_support.refined_issues import (
    RefinedIssueEvaluator,
)
from vietnamese_labor_law_assistant.guardrails.enums import (
    ReasonCode,
    VerificationStatus,
)
from vietnamese_labor_law_assistant.guardrails.models import VerificationResult


class ModeRouter:
    def __init__(self, outcome: RequestMode | Exception) -> None:
        self.outcome = outcome
        self.calls: list[str] = []

    async def route(self, question: str) -> RequestMode:
        self.calls.append(question)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class DirectService:
    def __init__(self, result: AgentResult) -> None:
        self.result = result
        self.calls: list[tuple[str, bool]] = []

    async def run(self, question: str, *, include_trace: bool = False) -> AgentResult:
        self.calls.append((question, include_trace))
        return self.result


class CaseRunner:
    def __init__(self, result: CaseAnalysisResult) -> None:
        self.result = result
        self.calls: list[str] = []

    async def run(self, question: str) -> CaseAnalysisResult:
        self.calls.append(question)
        return self.result


def direct_result(**updates: Any) -> AgentResult:
    result = AgentResult(
        request_id="direct-request",
        question="question",
        intent=AgentIntent.RETRIEVAL_ONLY,
        status=WorkflowStatus.WORKFLOW_VALID,
        answer="verified answer",
        disclaimer="disclaimer",
        citations=[],
        tool_trace=[],
        workflow_verification={"status": "PASS"},
        verification={"status": "SUPPORTED", "claims": [], "warnings": []},
        latency_ms=1,
    )
    return result.model_copy(update=updates)


def refusal_verification() -> VerificationResult:
    return VerificationResult(
        status=VerificationStatus.INSUFFICIENT_CONTEXT,
        warnings=[ReasonCode.OUT_OF_SCOPE_REFUSAL.value],
    )


def _contract_fact(
    fact_key: FactKey,
    raw_value: str,
    source_text: str,
    *,
    fact_id: str,
) -> CaseFact:
    start = source_text.index(raw_value)
    return CaseFact(
        fact_id=fact_id,
        fact_key=fact_key.value,
        fact_type="TEXT",
        raw_value=raw_value,
        normalized_value=raw_value,
        assertion_mode=AssertionMode.EXPLICIT,
        verification_status=FactVerificationStatus.UNVERIFIED,
        source_type=SourceType.USER_MESSAGE,
        source_ref="user_message:case-request",
        source_span=SourceSpan(
            start_offset=start,
            end_offset=start + len(raw_value),
            text=raw_value,
        ),
    )


def case_result(status: CaseAnalysisStatus) -> CaseAnalysisResult:
    candidate = CandidateIssue(issue_code=IssueCode.CONTRACT_TERM)
    if status is CaseAnalysisStatus.CLARIFICATION_REQUIRED:
        intake = CaseIntakeResult(facts=[], candidate_issues=[candidate])
        missing = MissingFactDetector().detect([], [candidate], ISSUE_REGISTRY)
        clarification = TargetedClarificationBuilder().build(missing)
        return CaseAnalysisResult(
            request_id="case-request",
            status=status,
            message="Safe clarification terminal.",
            intake_result=intake,
            missing_facts=missing,
            clarification=clarification,
        )
    if status is CaseAnalysisStatus.EVIDENCE_REQUEST_READY:
        source = "FIXED_TERM from 2026-01-01 until 2026-12-31"
        facts = [
            _contract_fact(FactKey.CONTRACT_TYPE, "FIXED_TERM", source, fact_id="CF-type"),
            _contract_fact(
                FactKey.CONTRACT_START_DATE,
                "2026-01-01",
                source,
                fact_id="CF-start",
            ),
            _contract_fact(
                FactKey.CONTRACT_END_DATE,
                "2026-12-31",
                source,
                fact_id="CF-end",
            ),
        ]
        intake = CaseIntakeResult(facts=facts, candidate_issues=[candidate])
        missing = MissingFactDetector().detect(facts, [candidate], ISSUE_REGISTRY)
        refined = RefinedIssueEvaluator().refine(
            facts,
            [candidate],
            missing,
            ISSUE_REGISTRY,
        )
        evidence = EvidenceRequestSkeletonBuilder().build(refined, ISSUE_REGISTRY)
        return CaseAnalysisResult(
            request_id="case-request",
            status=status,
            message="Safe evidence metadata terminal.",
            intake_result=intake,
            missing_facts=missing,
            refined_issues=refined,
            evidence_request=evidence,
        )
    if status is CaseAnalysisStatus.UNSUPPORTED_SCOPE:
        return CaseAnalysisResult(
            request_id="case-request",
            status=status,
            message="Safe unsupported terminal.",
            intake_result=CaseIntakeResult(),
        )
    return CaseAnalysisResult(
        request_id="case-request",
        status=status,
        message="Safe failure terminal.",
        error_code=(
            CaseAnalysisErrorCode.CASE_INTAKE_TIMEOUT
            if status is CaseAnalysisStatus.CASE_INTAKE_FAILED
            else CaseAnalysisErrorCode.CASE_DOMAIN_CONTRACT_INVALID
        ),
    )


@pytest.mark.asyncio
async def test_direct_qa_delegates_and_preserves_exact_agent_result() -> None:
    expected = direct_result()
    direct = DirectService(expected)
    case = CaseRunner(case_result(CaseAnalysisStatus.UNSUPPORTED_SCOPE))
    service = AssistantService(
        ModeRouter(RequestMode.DIRECT_QA), direct, case, refusal_verification
    )

    result = await service.run("Điều 35 quy định gì?", include_trace=True)

    assert isinstance(result, AssistantResult)
    assert result.request_mode is RequestMode.DIRECT_QA
    assert result.agent_result is expected
    assert result.case_analysis is None
    assert direct.calls == [("Điều 35 quy định gì?", True)]
    assert case.calls == []


@pytest.mark.asyncio
async def test_case_clarification_preserves_neutral_domain_questions() -> None:
    expected = case_result(CaseAnalysisStatus.CLARIFICATION_REQUIRED)
    direct = DirectService(direct_result())
    case = CaseRunner(expected)
    service = AssistantService(
        ModeRouter(RequestMode.CASE_ANALYSIS), direct, case, refusal_verification
    )

    result = await service.run("Phân tích tranh chấp của tôi.", include_trace=True)

    assert result.request_mode is RequestMode.CASE_ANALYSIS
    assert result.case_analysis is expected
    assert result.agent_result.status is WorkflowStatus.CLARIFICATION_REQUIRED
    assert expected.clarification is not None
    assert result.agent_result.answer == "\n".join(
        question.question for question in expected.clarification.questions
    )
    assert result.agent_result.router_decision == "CLARIFICATION_REQUIRED"
    assert result.agent_result.verification == {
        "status": "CLARIFICATION_REQUIRED",
        "reason": "CLARIFICATION_REQUIRED",
        "claims": [],
        "warnings": [],
    }
    assert result.agent_result.citations == [] and result.agent_result.tool_trace == []
    assert direct.calls == []
    assert case.calls == ["Phân tích tranh chấp của tôi."]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case_status", "workflow_status"),
    [
        (CaseAnalysisStatus.EVIDENCE_REQUEST_READY, WorkflowStatus.INSUFFICIENT_CONTEXT),
        (CaseAnalysisStatus.UNSUPPORTED_SCOPE, WorkflowStatus.INSUFFICIENT_CONTEXT),
        (CaseAnalysisStatus.CASE_INTAKE_FAILED, WorkflowStatus.OUTPUT_INVALID),
        (CaseAnalysisStatus.CASE_ANALYSIS_FAILED, WorkflowStatus.OUTPUT_INVALID),
    ],
)
async def test_case_terminals_map_without_legal_answer_or_raw_error(
    case_status: CaseAnalysisStatus,
    workflow_status: WorkflowStatus,
) -> None:
    expected = case_result(case_status)
    service = AssistantService(
        ModeRouter(RequestMode.CASE_ANALYSIS),
        DirectService(direct_result()),
        CaseRunner(expected),
        refusal_verification,
    )

    result = await service.run("Analyze this case.")

    assert result.case_analysis is expected
    assert result.agent_result.status is workflow_status
    assert result.agent_result.answer == "INSUFFICIENT_VERIFIED_EVIDENCE"
    assert result.agent_result.router_decision == case_status.value
    assert result.agent_result.workflow_verification == {
        "status": "PASS",
        "reason": case_status.value,
    }
    serialized = result.agent_result.model_dump_json(exclude={"question"})
    assert "lawful" not in serialized and "unlawful" not in serialized
    assert result.agent_result.citations == [] and result.agent_result.tool_trace == []


@pytest.mark.asyncio
async def test_outer_out_of_scope_reuses_refusal_semantics_without_direct_execution() -> None:
    direct = DirectService(direct_result())
    case = CaseRunner(case_result(CaseAnalysisStatus.UNSUPPORTED_SCOPE))
    service = AssistantService(
        ModeRouter(RequestMode.OUT_OF_SCOPE), direct, case, refusal_verification
    )

    result = await service.run("Tư vấn ly hôn.")

    assert result.request_mode is RequestMode.OUT_OF_SCOPE
    assert result.case_analysis is None
    assert result.agent_result.intent is AgentIntent.OUT_OF_SCOPE
    assert result.agent_result.status is WorkflowStatus.OUT_OF_SCOPE
    assert result.agent_result.answer == (
        "Yêu cầu này nằm ngoài phạm vi hỗ trợ (ngoài snapshot pháp luật)."
    )
    assert result.agent_result.verification == {
        "status": "INSUFFICIENT_CONTEXT",
        "claims": [],
        "warnings": ["OUT_OF_SCOPE_REFUSAL"],
    }
    assert direct.calls == [] and case.calls == []


@pytest.mark.asyncio
async def test_typed_mode_router_failure_is_fail_closed_and_calls_no_branch() -> None:
    direct = DirectService(direct_result())
    case = CaseRunner(case_result(CaseAnalysisStatus.UNSUPPORTED_SCOPE))
    router = ModeRouter(RequestModeRoutingError("REQUEST_MODE_SCHEMA_INVALID"))
    service = AssistantService(router, direct, case, refusal_verification)

    result = await service.run("ambiguous request")

    assert result.request_mode is None
    assert result.case_analysis is None
    assert result.agent_result.status is WorkflowStatus.ROUTING_ERROR
    assert result.agent_result.workflow_verification == {
        "status": "FAIL",
        "reason": "REQUEST_MODE_ROUTING_ERROR",
    }
    assert direct.calls == [] and case.calls == []
