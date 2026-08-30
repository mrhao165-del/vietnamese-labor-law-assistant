"""Offline contract tests for the Week-4 evidence-request skeleton."""

from __future__ import annotations

import ast
import inspect

import pytest
from pydantic import ValidationError

from vietnamese_labor_law_assistant.decision_support.enums import (
    AssertionMode,
    SourceType,
    VerificationStatus,
)
from vietnamese_labor_law_assistant.decision_support.evidence_requests import (
    EvidenceRequestSkeleton,
    EvidenceRequestSkeletonBuilder,
)
from vietnamese_labor_law_assistant.decision_support.issue_registry import (
    ISSUE_REGISTRY,
    CalculatorNeed,
    EvidenceNeed,
    FactKey,
    IssueDefinition,
    IssueRegistry,
)
from vietnamese_labor_law_assistant.decision_support.issues import (
    IssueCode,
    IssueRefinementReasonCode,
    RefinedIssueStatus,
)
from vietnamese_labor_law_assistant.decision_support.missing_facts import MissingFactDetector
from vietnamese_labor_law_assistant.decision_support.models import (
    CandidateIssue,
    CaseFact,
    SourceSpan,
)
from vietnamese_labor_law_assistant.decision_support.refined_issues import (
    RefinedIssue,
    RefinedIssueEvaluator,
    RefinedIssueResult,
)


def _fact(fact_key: FactKey, *, fact_id: str) -> CaseFact:
    raw_value = f"known-{fact_key.value.lower()}"
    return CaseFact(
        fact_id=fact_id,
        fact_key=fact_key.value,
        fact_type="TEXT",
        raw_value=raw_value,
        normalized_value=raw_value,
        assertion_mode=AssertionMode.EXPLICIT,
        verification_status=VerificationStatus.UNVERIFIED,
        source_type=SourceType.USER_MESSAGE,
        source_ref="user_message:evidence-request-skeleton",
        source_span=SourceSpan(
            start_offset=0,
            end_offset=len(raw_value),
            text=raw_value,
        ),
    )


def _facts_for(*fact_keys: FactKey) -> tuple[CaseFact, ...]:
    return tuple(
        _fact(fact_key, fact_id=f"CF-evidence-{index:02d}")
        for index, fact_key in enumerate(fact_keys, start=1)
    )


def _refine(
    facts: tuple[CaseFact, ...],
    issue_codes: tuple[IssueCode, ...],
    *,
    registry: IssueRegistry = ISSUE_REGISTRY,
) -> RefinedIssueResult:
    candidates = tuple(CandidateIssue(issue_code=issue_code) for issue_code in issue_codes)
    missing = MissingFactDetector().detect(facts, candidates, registry)
    return RefinedIssueEvaluator().refine(facts, candidates, missing, registry)


def _contract_facts() -> tuple[CaseFact, ...]:
    return _facts_for(
        FactKey.CONTRACT_TYPE,
        FactKey.CONTRACT_START_DATE,
        FactKey.CONTRACT_END_DATE,
    )


def _all_issue_facts() -> tuple[CaseFact, ...]:
    return _facts_for(
        FactKey.CONTRACT_TYPE,
        FactKey.CONTRACT_START_DATE,
        FactKey.CONTRACT_END_DATE,
        FactKey.NOTICE_SPECIAL_CASE,
        FactKey.EMPLOYEE_ROLE,
    )


def _shared_requirement_registry() -> IssueRegistry:
    contract = ISSUE_REGISTRY.definitions[0]
    termination = ISSUE_REGISTRY.definitions[1]
    contract_evidence = contract.evidence_needs[0]
    contract_calculator = contract.calculator_needs[0]
    shared_termination = IssueDefinition(
        issue_code=termination.issue_code,
        required_facts=contract.required_facts,
        critical_facts=contract.critical_facts,
        context_fact_keys=contract.context_fact_keys,
        evidence_needs=(
            EvidenceNeed(
                document_id=contract_evidence.document_id,
                article=contract_evidence.article,
                clause=contract_evidence.clause,
                source_chunk_id=contract_evidence.source_chunk_id,
                role="Use the same registry source for the second issue.",
            ),
        ),
        calculator_needs=(
            CalculatorNeed(
                capability=contract_calculator.capability,
                input_fact_keys=tuple(reversed(contract_calculator.input_fact_keys)),
                role="Use the same calculator dependency set for the second issue.",
            ),
        ),
        applicability_scope=termination.applicability_scope,
    )
    return IssueRegistry(definitions=(contract, shared_termination))


def _terminal_result(status: RefinedIssueStatus) -> RefinedIssueResult:
    active = _refine(_contract_facts(), (IssueCode.CONTRACT_TERM,)).issues[0]
    reason = {
        RefinedIssueStatus.RESOLVED_OUT: (
            IssueRefinementReasonCode.DETERMINISTIC_EXCLUSION_ESTABLISHED
        ),
        RefinedIssueStatus.UNSUPPORTED_SCOPE: (
            IssueRefinementReasonCode.APPLICABILITY_SCOPE_UNSUPPORTED
        ),
    }[status]
    payload = active.model_dump(mode="python")
    payload.update(status=status, reason_code=reason)
    terminal = RefinedIssue.model_validate(payload)
    return RefinedIssueResult(issues=(terminal,), critical_missing=False)


def test_one_active_refined_issue_materializes_registry_metadata_only() -> None:
    refined = _refine(_contract_facts(), (IssueCode.CONTRACT_TERM,))

    result = EvidenceRequestSkeletonBuilder().build(refined, ISSUE_REGISTRY)

    assert result.substantive_analysis_blocked is False
    assert len(result.issue_states) == 1
    assert result.issue_states[0].issue_code is IssueCode.CONTRACT_TERM
    assert result.issue_states[0].status is RefinedIssueStatus.ACTIVE
    assert result.issue_states[0].contributes_requirements is True
    assert len(result.evidence_requests) == 1
    assert (
        result.evidence_requests[0].document_id,
        result.evidence_requests[0].article,
        result.evidence_requests[0].clause,
    ) == ("labor_law", 20, 1)
    assert len(result.calculator_requests) == 1
    assert result.calculator_requests[0].input_fact_keys == (
        FactKey.CONTRACT_TYPE,
        FactKey.CONTRACT_START_DATE,
        FactKey.CONTRACT_END_DATE,
    )


def test_multiple_refined_issues_follow_registry_order() -> None:
    refined = _refine(
        _all_issue_facts(),
        tuple(reversed(tuple(IssueCode))),
    )

    result = EvidenceRequestSkeletonBuilder().build(refined, ISSUE_REGISTRY)

    assert tuple(state.issue_code for state in result.issue_states) == tuple(IssueCode)
    assert [(request.article, request.clause) for request in result.evidence_requests] == [
        (20, 1),
        (35, 1),
        (35, 2),
        (97, 4),
    ]
    assert [request.capability.value for request in result.calculator_requests] == [
        "CONTRACT_DURATION",
        "NOTICE_PERIOD",
    ]


def test_shared_registry_requirements_are_deduplicated_with_issue_traceability() -> None:
    registry = _shared_requirement_registry()
    refined = _refine(_contract_facts(), tuple(IssueCode), registry=registry)

    result = EvidenceRequestSkeletonBuilder().build(refined, registry)

    assert len(result.evidence_requests) == 1
    assert tuple(trace.issue_code for trace in result.evidence_requests[0].issue_traces) == tuple(
        IssueCode
    )
    assert len(result.calculator_requests) == 1
    assert tuple(trace.issue_code for trace in result.calculator_requests[0].issue_traces) == tuple(
        IssueCode
    )
    assert result.calculator_requests[0].input_fact_keys == (
        FactKey.CONTRACT_TYPE,
        FactKey.CONTRACT_START_DATE,
        FactKey.CONTRACT_END_DATE,
    )


def test_repeated_builds_are_deterministic() -> None:
    refined = _refine(_all_issue_facts(), tuple(IssueCode))
    builder = EvidenceRequestSkeletonBuilder()

    first = builder.build(refined, ISSUE_REGISTRY)
    second = builder.build(refined, ISSUE_REGISTRY)

    assert first == second
    assert first.model_dump_json() == second.model_dump_json()


@pytest.mark.parametrize(
    "status",
    (RefinedIssueStatus.RESOLVED_OUT, RefinedIssueStatus.UNSUPPORTED_SCOPE),
)
def test_terminal_refined_statuses_do_not_contribute_requirements(
    status: RefinedIssueStatus,
) -> None:
    refined = _terminal_result(status)

    result = EvidenceRequestSkeletonBuilder().build(refined, ISSUE_REGISTRY)

    assert result.issue_states[0].status is status
    assert result.issue_states[0].contributes_requirements is False
    assert result.evidence_requests == ()
    assert result.calculator_requests == ()
    assert result.substantive_analysis_blocked is False


def test_possible_issue_with_critical_gaps_remains_blocked_without_status_upgrade() -> None:
    refined = _refine((), (IssueCode.CONTRACT_TERM,))

    result = EvidenceRequestSkeletonBuilder().build(refined, ISSUE_REGISTRY)

    assert refined.issues[0].status is RefinedIssueStatus.POSSIBLE
    assert result.issue_states[0].status is RefinedIssueStatus.POSSIBLE
    assert result.issue_states[0].contributes_requirements is True
    assert result.issue_states[0].critical_missing_fields == (FactKey.CONTRACT_TYPE,)
    assert result.substantive_analysis_blocked is True
    assert result.evidence_requests
    assert result.calculator_requests


def test_builder_is_idempotent_does_not_mutate_inputs_and_returns_frozen_contracts() -> None:
    refined = _refine(_contract_facts(), (IssueCode.CONTRACT_TERM,))
    refined_before = refined.model_dump_json()
    registry_before = ISSUE_REGISTRY.model_dump_json()
    builder = EvidenceRequestSkeletonBuilder()

    first = builder.build(refined, ISSUE_REGISTRY)
    second = builder.build(refined, ISSUE_REGISTRY)

    assert first == second
    assert refined.model_dump_json() == refined_before
    assert ISSUE_REGISTRY.model_dump_json() == registry_before
    with pytest.raises(ValidationError):
        first.substantive_analysis_blocked = True
    with pytest.raises(ValidationError):
        first.evidence_requests[0].article = 35


def test_skeleton_contract_contains_no_plan_query_budget_or_legal_outcome_fields() -> None:
    prohibited_fields = {
        "evidence_plan",
        "retrieval_query",
        "search_text",
        "top_k",
        "tool_budget",
        "evidence_score",
        "legal_outcome",
        "recommendation",
    }

    assert prohibited_fields.isdisjoint(EvidenceRequestSkeleton.model_fields)


def test_evidence_request_module_is_pure_and_cannot_execute_tools() -> None:
    from vietnamese_labor_law_assistant.decision_support import evidence_requests

    tree = ast.parse(inspect.getsource(evidence_requests))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    prohibited_prefixes = (
        "openai",
        "vietnamese_labor_law_assistant.agent",
        "vietnamese_labor_law_assistant.api",
        "vietnamese_labor_law_assistant.calculator",
        "vietnamese_labor_law_assistant.mcp_clients",
        "vietnamese_labor_law_assistant.mcp_servers",
        "vietnamese_labor_law_assistant.retrieval",
    )
    assert not any(module.startswith(prohibited_prefixes) for module in imported_modules)
    assert not any(isinstance(node, (ast.AsyncFunctionDef, ast.Await)) for node in ast.walk(tree))
