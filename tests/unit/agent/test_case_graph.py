"""Offline behavior tests for the finite v1.1 Case Analysis graph."""

from __future__ import annotations

import inspect
from collections.abc import Sequence

import pytest
from pydantic import ValidationError

from vietnamese_labor_law_assistant.agent.case_graph import (
    CaseAnalysisErrorCode,
    CaseAnalysisResult,
    CaseAnalysisStatus,
    CaseGraph,
)
from vietnamese_labor_law_assistant.decision_support.enums import (
    AssertionMode,
    SourceType,
    VerificationStatus,
)
from vietnamese_labor_law_assistant.decision_support.intake import CaseIntakeError
from vietnamese_labor_law_assistant.decision_support.issue_registry import (
    ISSUE_REGISTRY,
    FactKey,
    IssueRegistry,
)
from vietnamese_labor_law_assistant.decision_support.issues import (
    IssueCode,
    RefinedIssueStatus,
)
from vietnamese_labor_law_assistant.decision_support.missing_facts import (
    MissingFactDetector,
    MissingFactResult,
)
from vietnamese_labor_law_assistant.decision_support.models import (
    CandidateIssue,
    CaseFact,
    CaseIntakeInput,
    CaseIntakeResult,
    SourceSpan,
)
from vietnamese_labor_law_assistant.decision_support.refined_issues import (
    RefinedIssueError,
    RefinedIssueErrorCode,
    RefinedIssueEvaluator,
    RefinedIssueResult,
)

_SOURCE_REF = "user_message:00000000-0000-0000-0000-000000000001"


class IntakeExtractorStub:
    def __init__(self, result: CaseIntakeResult | Exception) -> None:
        self.result = result
        self.calls: list[CaseIntakeInput] = []

    async def extract(self, case_input: CaseIntakeInput) -> CaseIntakeResult:
        self.calls.append(case_input)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FailingMissingFactDetector(MissingFactDetector):
    def detect(
        self,
        known_facts: Sequence[CaseFact],
        candidate_issues: Sequence[CandidateIssue],
        registry: IssueRegistry,
    ) -> MissingFactResult:
        del known_facts, candidate_issues, registry
        raise AssertionError("missing-fact detector must not run")


class FailingRefinedIssueEvaluator(RefinedIssueEvaluator):
    def refine(
        self,
        known_facts: Sequence[CaseFact],
        candidate_issues: Sequence[CandidateIssue],
        missing_facts: MissingFactResult,
        registry: IssueRegistry,
    ) -> RefinedIssueResult:
        del known_facts, candidate_issues, missing_facts, registry
        raise RefinedIssueError(RefinedIssueErrorCode.INCONSISTENT_MISSING_FACT_RESULT)


@pytest.fixture(autouse=True)
def fixed_request_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "vietnamese_labor_law_assistant.agent.case_graph.uuid.uuid4",
        lambda: "00000000-0000-0000-0000-000000000001",
    )


def _fact(
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
        verification_status=VerificationStatus.UNVERIFIED,
        source_type=SourceType.USER_MESSAGE,
        source_ref=_SOURCE_REF,
        source_span=SourceSpan(
            start_offset=start,
            end_offset=start + len(raw_value),
            text=raw_value,
        ),
    )


def _intake(
    *,
    facts: Sequence[CaseFact] = (),
    issues: Sequence[IssueCode] = (IssueCode.CONTRACT_TERM,),
) -> CaseIntakeResult:
    return CaseIntakeResult(
        facts=list(facts),
        candidate_issues=[CandidateIssue(issue_code=issue) for issue in issues],
    )


@pytest.mark.asyncio
async def test_missing_required_facts_terminate_with_bounded_clarification() -> None:
    extractor = IntakeExtractorStub(_intake())

    result = await CaseGraph(extractor).run("Analyze my fixed-term employment contract.")

    assert result.status is CaseAnalysisStatus.CLARIFICATION_REQUIRED
    assert result.error_code is None
    assert result.intake_result == extractor.result
    assert result.missing_facts is not None and result.missing_facts.critical_missing is True
    assert result.clarification is not None
    assert 1 <= len(result.clarification.questions) <= 3
    assert result.clarification.questions[0].fact_key is FactKey.CONTRACT_TYPE
    assert result.refined_issues is None
    assert result.evidence_request is None
    assert not hasattr(result, "answer")
    assert len(extractor.calls) == 1
    assert extractor.calls[0].source_ref == f"user_message:{result.request_id}"


@pytest.mark.asyncio
async def test_sufficient_facts_reach_refinement_and_evidence_request_metadata() -> None:
    question = "FIXED_TERM started 2026-01-01 and ended 2026-12-31."
    facts = (
        _fact(FactKey.CONTRACT_TYPE, "FIXED_TERM", question, fact_id="CF-contract-type"),
        _fact(
            FactKey.CONTRACT_START_DATE,
            "2026-01-01",
            question,
            fact_id="CF-contract-start",
        ),
        _fact(
            FactKey.CONTRACT_END_DATE,
            "2026-12-31",
            question,
            fact_id="CF-contract-end",
        ),
    )
    extractor = IntakeExtractorStub(_intake(facts=facts))

    result = await CaseGraph(extractor).run(question)

    assert result.status is CaseAnalysisStatus.EVIDENCE_REQUEST_READY
    assert result.missing_facts is not None
    assert result.missing_facts.fields_needed == ()
    assert result.clarification is None
    assert result.refined_issues is not None
    assert result.refined_issues.issues[0].status is RefinedIssueStatus.ACTIVE
    assert result.evidence_request is not None
    assert [(item.article, item.clause) for item in result.evidence_request.evidence_requests] == [
        (20, 1)
    ]
    assert [item.capability.value for item in result.evidence_request.calculator_requests] == [
        "CONTRACT_DURATION"
    ]
    assert result.evidence_request.substantive_analysis_blocked is False


@pytest.mark.asyncio
async def test_multi_issue_shared_missing_fact_is_asked_once() -> None:
    extractor = IntakeExtractorStub(_intake(issues=tuple(IssueCode)))

    result = await CaseGraph(extractor).run("Analyze my contract and resignation notice.")

    assert result.status is CaseAnalysisStatus.CLARIFICATION_REQUIRED
    assert result.missing_facts is not None
    contract_type = next(
        field
        for field in result.missing_facts.fields_needed
        if field.fact_key is FactKey.CONTRACT_TYPE
    )
    assert contract_type.required_by_issues == tuple(IssueCode)
    assert result.clarification is not None
    matching_questions = [
        question
        for question in result.clarification.questions
        if question.fact_key is FactKey.CONTRACT_TYPE
    ]
    assert len(matching_questions) == 1
    assert matching_questions[0].related_issue_codes == tuple(IssueCode)


@pytest.mark.asyncio
async def test_no_candidate_issues_terminate_as_unsupported_before_detection() -> None:
    extractor = IntakeExtractorStub(_intake(issues=()))

    result = await CaseGraph(
        extractor,
        missing_fact_detector=FailingMissingFactDetector(),
    ).run("This message contains no supported labor-law issue.")

    assert result.status is CaseAnalysisStatus.UNSUPPORTED_SCOPE
    assert result.intake_result == extractor.result
    assert result.missing_facts is None
    assert result.clarification is None
    assert result.refined_issues is None
    assert result.evidence_request is None


@pytest.mark.asyncio
async def test_provider_failure_maps_to_allowlisted_intake_error_without_raw_text() -> None:
    extractor = IntakeExtractorStub(CaseIntakeError("CASE_INTAKE_TIMEOUT"))

    result = await CaseGraph(extractor).run("Analyze this case. raw-provider-secret")

    assert result.status is CaseAnalysisStatus.CASE_INTAKE_FAILED
    assert result.error_code is CaseAnalysisErrorCode.CASE_INTAKE_TIMEOUT
    assert result.intake_result is None
    assert "raw-provider-secret" not in result.message
    assert "CASE_INTAKE_TIMEOUT" not in result.message


@pytest.mark.asyncio
async def test_malformed_intake_contract_fails_closed() -> None:
    malformed = CaseIntakeResult.model_construct(
        facts=[{"provider": "private-payload"}],
        candidate_issues=[{"issue_code": "MODEL_INVENTED"}],
    )

    result = await CaseGraph(IntakeExtractorStub(malformed)).run("Analyze this case.")

    assert result.status is CaseAnalysisStatus.CASE_INTAKE_FAILED
    assert result.error_code is CaseAnalysisErrorCode.CASE_INTAKE_SCHEMA_INVALID
    assert result.intake_result is None
    serialized = result.model_dump_json()
    assert "private-payload" not in serialized
    assert "MODEL_INVENTED" not in serialized


@pytest.mark.asyncio
async def test_refinement_contract_failure_maps_to_safe_analysis_error() -> None:
    question = "FIXED_TERM started 2026-01-01 and ended 2026-12-31."
    facts = (
        _fact(FactKey.CONTRACT_TYPE, "FIXED_TERM", question, fact_id="CF-type"),
        _fact(FactKey.CONTRACT_START_DATE, "2026-01-01", question, fact_id="CF-start"),
        _fact(FactKey.CONTRACT_END_DATE, "2026-12-31", question, fact_id="CF-end"),
    )

    result = await CaseGraph(
        IntakeExtractorStub(_intake(facts=facts)),
        refined_issue_evaluator=FailingRefinedIssueEvaluator(),
    ).run(question)

    assert result.status is CaseAnalysisStatus.CASE_ANALYSIS_FAILED
    assert result.error_code is CaseAnalysisErrorCode.CASE_DOMAIN_CONTRACT_INVALID
    assert result.refined_issues is None
    assert result.evidence_request is None
    assert "INCONSISTENT_MISSING_FACT_RESULT" not in result.model_dump_json()


def test_case_analysis_result_rejects_contradictory_terminal_payload() -> None:
    with pytest.raises(ValidationError, match="clarification terminal"):
        CaseAnalysisResult(
            request_id="request",
            status=CaseAnalysisStatus.CLARIFICATION_REQUIRED,
            message="Safe.",
        )


def test_case_graph_topology_is_finite_and_has_no_loop() -> None:
    graph = CaseGraph(IntakeExtractorStub(_intake())).graph.get_graph()
    edges = {(edge.source, edge.target) for edge in graph.edges}
    assert edges == {
        ("__start__", "case_intake"),
        ("case_intake", "detect_missing_facts"),
        ("case_intake", "__end__"),
        ("detect_missing_facts", "build_clarification"),
        ("detect_missing_facts", "refine_issues"),
        ("detect_missing_facts", "__end__"),
        ("build_clarification", "__end__"),
        ("refine_issues", "build_evidence_request"),
        ("refine_issues", "__end__"),
        ("build_evidence_request", "__end__"),
    }
    assert all(source != target for source, target in edges)
    assert all(target != "__start__" for _, target in edges)


def test_case_graph_constructor_exposes_no_tool_or_execution_gateway() -> None:
    parameters = set(inspect.signature(CaseGraph).parameters)

    assert not parameters & {
        "agent_service",
        "retrieval_gateway",
        "calculator_gateway",
        "mcp_client",
        "evidence_plan",
    }
    assert ISSUE_REGISTRY.supported_issue_codes == tuple(IssueCode)
