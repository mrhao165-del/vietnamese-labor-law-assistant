"""Offline behavior tests for deterministic refined-issue analysis state."""

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
from vietnamese_labor_law_assistant.decision_support.issue_registry import (
    ISSUE_REGISTRY,
    ApplicabilityScope,
    FactKey,
    FactRequirement,
    IssueDefinition,
    IssueRegistry,
)
from vietnamese_labor_law_assistant.decision_support.issues import (
    IssueCode,
    IssueRefinementReasonCode,
    RefinedIssueStatus,
)
from vietnamese_labor_law_assistant.decision_support.missing_facts import (
    MissingFactDetectionError,
    MissingFactDetectionErrorCode,
    MissingFactDetector,
    MissingFactResult,
)
from vietnamese_labor_law_assistant.decision_support.models import (
    CandidateIssue,
    CaseFact,
    SourceSpan,
)
from vietnamese_labor_law_assistant.decision_support.refined_issues import (
    RefinedIssue,
    RefinedIssueError,
    RefinedIssueErrorCode,
    RefinedIssueEvaluator,
    RefinedIssueResult,
)


def _fact(
    fact_key: FactKey | str,
    *,
    fact_id: str,
    assertion_mode: AssertionMode = AssertionMode.EXPLICIT,
) -> CaseFact:
    key = fact_key.value if isinstance(fact_key, FactKey) else fact_key
    raw_value = f"known-{key.lower()}"
    return CaseFact(
        fact_id=fact_id,
        fact_key=key,
        fact_type="TEXT",
        raw_value=raw_value,
        normalized_value=raw_value,
        assertion_mode=assertion_mode,
        verification_status=VerificationStatus.UNVERIFIED,
        source_type=SourceType.USER_MESSAGE,
        source_ref="user_message:refined-issues",
        source_span=SourceSpan(
            start_offset=0,
            end_offset=len(raw_value),
            text=raw_value,
        ),
    )


def _candidate(issue_code: IssueCode) -> CandidateIssue:
    return CandidateIssue(issue_code=issue_code)


def _contract_facts(
    *,
    contract_type_mode: AssertionMode = AssertionMode.EXPLICIT,
) -> tuple[CaseFact, ...]:
    return (
        _fact(
            FactKey.CONTRACT_TYPE,
            fact_id="CF-refined-contract-type",
            assertion_mode=contract_type_mode,
        ),
        _fact(FactKey.CONTRACT_START_DATE, fact_id="CF-refined-contract-start"),
        _fact(FactKey.CONTRACT_END_DATE, fact_id="CF-refined-contract-end"),
    )


def _contract_registry(
    *,
    critical_facts: tuple[FactKey, ...] | None = None,
    contract_type_modes: tuple[AssertionMode, ...] | None = None,
) -> IssueRegistry:
    contract = ISSUE_REGISTRY.definitions[0]
    first = contract.required_facts[0]
    contract_type = (
        first
        if contract_type_modes is None
        else FactRequirement(
            fact_key=first.fact_key,
            role=first.role,
            accepted_assertion_modes=contract_type_modes,
            accepted_verification_statuses=first.accepted_verification_statuses,
        )
    )
    replacement = IssueDefinition(
        issue_code=contract.issue_code,
        required_facts=(
            contract_type,
            FactRequirement(
                fact_key=FactKey.CONTRACT_START_DATE,
                role="Test-only optional interval start.",
            ),
            FactRequirement(
                fact_key=FactKey.CONTRACT_END_DATE,
                role="Test-only optional interval end.",
            ),
        ),
        critical_facts=critical_facts or contract.critical_facts,
        conditional_requirement_branches=contract.conditional_requirement_branches,
        context_fact_keys=contract.context_fact_keys,
        conflict_rules=contract.conflict_rules,
        evidence_needs=contract.evidence_needs,
        calculator_needs=contract.calculator_needs,
        applicability_scope=contract.applicability_scope,
    )
    return IssueRegistry(definitions=(replacement, ISSUE_REGISTRY.definitions[1]))


def _refine(
    facts: tuple[CaseFact, ...],
    issues: tuple[IssueCode, ...] = (IssueCode.CONTRACT_TERM,),
    *,
    registry: IssueRegistry = ISSUE_REGISTRY,
) -> RefinedIssueResult:
    candidates = tuple(_candidate(issue_code) for issue_code in issues)
    missing = MissingFactDetector().detect(facts, candidates, registry)
    return RefinedIssueEvaluator().refine(facts, candidates, missing, registry)


def test_refined_issue_status_and_reason_vocabularies_are_exact_and_stable() -> None:
    assert [status.value for status in RefinedIssueStatus] == [
        "ACTIVE",
        "POSSIBLE",
        "RESOLVED_OUT",
        "UNSUPPORTED_SCOPE",
    ]
    assert [reason.value for reason in IssueRefinementReasonCode] == [
        "REQUIREMENTS_SATISFIED",
        "CRITICAL_FACTS_MISSING",
        "REQUIRED_FACTS_MISSING",
        "CONFLICTING_FACTS",
        "DETERMINISTIC_EXCLUSION_ESTABLISHED",
        "APPLICABILITY_SCOPE_UNSUPPORTED",
    ]


def test_supported_candidate_with_sufficient_facts_becomes_active_analysis_state() -> None:
    candidate = _candidate(IssueCode.CONTRACT_TERM)
    facts = _contract_facts()
    missing = MissingFactDetector().detect(facts, (candidate,), ISSUE_REGISTRY)

    result = RefinedIssueEvaluator().refine(facts, (candidate,), missing, ISSUE_REGISTRY)

    assert result.critical_missing is False
    assert len(result.issues) == 1
    refined = result.issues[0]
    assert refined.issue_code is IssueCode.CONTRACT_TERM
    assert refined.candidate_issue == candidate
    assert refined.status is RefinedIssueStatus.ACTIVE
    assert refined.reason_code is IssueRefinementReasonCode.REQUIREMENTS_SATISFIED
    assert refined.applicability_scope is ApplicabilityScope.CONTRACT_TYPE_AND_DURATION
    assert refined.relevant_fact_keys == (
        FactKey.CONTRACT_TYPE,
        FactKey.CONTRACT_START_DATE,
        FactKey.CONTRACT_END_DATE,
    )
    assert tuple(fact.fact_id for fact in refined.relevant_facts) == (
        "CF-refined-contract-type",
        "CF-refined-contract-start",
        "CF-refined-contract-end",
    )
    assert refined.remaining_missing_fields == ()
    assert refined.critical_missing_fields == ()


def test_missing_critical_fact_keeps_supported_candidate_possible() -> None:
    result = _refine(_contract_facts()[1:])

    refined = result.issues[0]
    assert refined.status is RefinedIssueStatus.POSSIBLE
    assert refined.reason_code is IssueRefinementReasonCode.CRITICAL_FACTS_MISSING
    assert refined.remaining_missing_fields == (FactKey.CONTRACT_TYPE,)
    assert refined.critical_missing_fields == (FactKey.CONTRACT_TYPE,)
    assert result.critical_missing is True


def test_only_noncritical_gaps_keep_candidate_possible_without_critical_gate() -> None:
    registry = _contract_registry(critical_facts=(FactKey.CONTRACT_TYPE,))
    facts = (_contract_facts()[0],)

    result = _refine(facts, registry=registry)

    refined = result.issues[0]
    assert refined.status is RefinedIssueStatus.POSSIBLE
    assert refined.reason_code is IssueRefinementReasonCode.REQUIRED_FACTS_MISSING
    assert refined.remaining_missing_fields == (
        FactKey.CONTRACT_START_DATE,
        FactKey.CONTRACT_END_DATE,
    )
    assert refined.critical_missing_fields == ()
    assert result.critical_missing is False


def test_explicit_unverified_facts_remain_unverified_in_active_output() -> None:
    result = _refine(_contract_facts())

    assert result.issues[0].status is RefinedIssueStatus.ACTIVE
    assert all(
        fact.assertion_mode is AssertionMode.EXPLICIT
        and fact.verification_status is VerificationStatus.UNVERIFIED
        for fact in result.issues[0].relevant_facts
    )


def test_inferred_fact_is_preserved_and_never_upgraded() -> None:
    result = _refine(_contract_facts(contract_type_mode=AssertionMode.INFERRED))

    contract_type = result.issues[0].relevant_facts[0]
    assert result.issues[0].status is RefinedIssueStatus.ACTIVE
    assert contract_type.assertion_mode is AssertionMode.INFERRED
    assert contract_type.verification_status is VerificationStatus.UNVERIFIED


def test_inferred_fact_remains_missing_when_registry_requires_explicit() -> None:
    registry = _contract_registry(contract_type_modes=(AssertionMode.EXPLICIT,))

    result = _refine(
        _contract_facts(contract_type_mode=AssertionMode.INFERRED),
        registry=registry,
    )

    refined = result.issues[0]
    assert refined.status is RefinedIssueStatus.POSSIBLE
    assert refined.reason_code is IssueRefinementReasonCode.CRITICAL_FACTS_MISSING
    assert refined.remaining_missing_fields == (FactKey.CONTRACT_TYPE,)
    assert refined.relevant_facts[0].assertion_mode is AssertionMode.INFERRED


def test_unknown_fact_is_not_promoted_into_relevant_issue_state() -> None:
    unknown = _fact("MODEL_INVENTED_FACT", fact_id="CF-refined-unknown")

    result = _refine((unknown,))

    refined = result.issues[0]
    assert refined.status is RefinedIssueStatus.POSSIBLE
    assert refined.relevant_fact_keys == ()
    assert refined.relevant_facts == ()
    assert refined.remaining_missing_fields == (FactKey.CONTRACT_TYPE,)


def test_multi_issue_output_is_unique_and_follows_registry_order() -> None:
    result = _refine((), issues=tuple(reversed(tuple(IssueCode))))

    assert tuple(issue.issue_code for issue in result.issues) == tuple(IssueCode)
    assert len({issue.issue_code for issue in result.issues}) == len(result.issues)
    assert all(issue.status is RefinedIssueStatus.POSSIBLE for issue in result.issues)


def test_reordered_inputs_and_repeated_evaluation_are_deterministic() -> None:
    facts = (
        _fact(FactKey.EMPLOYEE_ROLE, fact_id="CF-refined-role"),
        _fact(FactKey.CONTRACT_TYPE, fact_id="CF-refined-type"),
    )
    first = _refine(facts, issues=tuple(reversed(tuple(IssueCode))))
    second = _refine(tuple(reversed(facts)), issues=tuple(IssueCode))
    third = _refine(facts, issues=tuple(reversed(tuple(IssueCode))))

    assert first == second == third
    assert first.model_dump_json() == second.model_dump_json() == third.model_dump_json()


def test_duplicate_candidate_does_not_create_duplicate_refined_issue() -> None:
    candidate = _candidate(IssueCode.CONTRACT_TERM)
    malformed_missing = MissingFactResult.model_construct(
        issue_results=(), fields_needed=(), critical_missing=True
    )

    with pytest.raises(MissingFactDetectionError) as captured:
        RefinedIssueEvaluator().refine(
            (),
            (candidate, candidate),
            malformed_missing,
            ISSUE_REGISTRY,
        )

    assert captured.value.code is MissingFactDetectionErrorCode.DUPLICATE_CANDIDATE_ISSUE


def test_unknown_candidate_fails_closed_instead_of_using_unsupported_as_error_bucket() -> None:
    unsupported = CandidateIssue.model_construct(issue_code="UNKNOWN_ISSUE")
    malformed_missing = MissingFactResult.model_construct(
        issue_results=(), fields_needed=(), critical_missing=True
    )

    with pytest.raises(MissingFactDetectionError) as captured:
        RefinedIssueEvaluator().refine((), (unsupported,), malformed_missing, ISSUE_REGISTRY)

    assert captured.value.code is MissingFactDetectionErrorCode.UNSUPPORTED_CANDIDATE_ISSUE


def test_inconsistent_missing_fact_result_fails_closed() -> None:
    facts = _contract_facts()
    candidates = (_candidate(IssueCode.CONTRACT_TERM),)
    missing = MissingFactDetector().detect(facts, candidates, ISSUE_REGISTRY)
    stale = missing.model_copy(update={"critical_missing": True})

    with pytest.raises(RefinedIssueError) as captured:
        RefinedIssueEvaluator().refine(facts, candidates, stale, ISSUE_REGISTRY)

    assert captured.value.code is RefinedIssueErrorCode.INCONSISTENT_MISSING_FACT_RESULT


def test_refinement_does_not_mutate_inputs_and_output_is_immutable() -> None:
    facts = list(_contract_facts())
    candidates = [_candidate(IssueCode.CONTRACT_TERM)]
    missing = MissingFactDetector().detect(facts, candidates, ISSUE_REGISTRY)
    facts_before = [fact.model_dump_json() for fact in facts]
    candidates_before = [candidate.model_dump_json() for candidate in candidates]
    missing_before = missing.model_dump_json()

    result = RefinedIssueEvaluator().refine(facts, candidates, missing, ISSUE_REGISTRY)

    assert [fact.model_dump_json() for fact in facts] == facts_before
    assert [candidate.model_dump_json() for candidate in candidates] == candidates_before
    assert missing.model_dump_json() == missing_before
    with pytest.raises(ValidationError):
        result.critical_missing = True
    with pytest.raises(ValidationError):
        result.issues[0].status = RefinedIssueStatus.RESOLVED_OUT


def test_refined_contract_rejects_duplicate_issues_and_inconsistent_status_reason() -> None:
    result = _refine(_contract_facts())
    refined = result.issues[0]

    with pytest.raises(ValidationError, match="refined issue codes must be unique"):
        RefinedIssueResult(issues=(refined, refined), critical_missing=False)

    payload = refined.model_dump(mode="python")
    payload["status"] = RefinedIssueStatus.RESOLVED_OUT
    with pytest.raises(ValidationError, match="status and reason code"):
        RefinedIssue.model_validate(payload)


def test_refinement_contract_has_no_legal_outcome_or_recommendation_text() -> None:
    result = _refine(_contract_facts())
    prohibited_fields = {
        "legal_outcome",
        "legal_conclusion",
        "recommendation",
        "decision_rule",
        "legal_application",
    }

    assert prohibited_fields.isdisjoint(RefinedIssue.model_fields)
    serialized = result.model_dump_json().casefold()
    assert "lawful" not in serialized
    assert "unlawful" not in serialized
    assert "should sue" not in serialized


def test_missing_information_never_becomes_resolved_out_or_active() -> None:
    result = _refine(())

    assert result.issues[0].status is RefinedIssueStatus.POSSIBLE
    assert result.issues[0].status not in {
        RefinedIssueStatus.ACTIVE,
        RefinedIssueStatus.RESOLVED_OUT,
        RefinedIssueStatus.UNSUPPORTED_SCOPE,
    }


def test_refined_issue_module_stays_in_pure_decision_support_boundary() -> None:
    from vietnamese_labor_law_assistant.decision_support import refined_issues

    tree = ast.parse(inspect.getsource(refined_issues))
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
