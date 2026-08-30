"""Offline behavior tests for deterministic missing-fact detection."""

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
    FactKey,
    FactRequirement,
    IssueDefinition,
    IssueRegistry,
)
from vietnamese_labor_law_assistant.decision_support.issues import IssueCode
from vietnamese_labor_law_assistant.decision_support.missing_facts import (
    MissingFactDetectionError,
    MissingFactDetectionErrorCode,
    MissingFactDetector,
    RequirementGapReason,
    RequirementStatus,
)
from vietnamese_labor_law_assistant.decision_support.models import (
    CandidateIssue,
    CaseFact,
    SourceSpan,
)


def _fact(
    fact_key: FactKey | str,
    *,
    fact_id: str,
    assertion_mode: AssertionMode = AssertionMode.EXPLICIT,
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED,
    raw_value: str = "known-value",
) -> CaseFact:
    return CaseFact(
        fact_id=fact_id,
        fact_key=str(fact_key),
        fact_type="TEXT",
        raw_value=raw_value,
        normalized_value=raw_value,
        assertion_mode=assertion_mode,
        verification_status=verification_status,
        source_type=SourceType.USER_MESSAGE,
        source_ref="user_message:missing-facts",
        source_span=SourceSpan(
            start_offset=0,
            end_offset=len(raw_value),
            text=raw_value,
        ),
    )


def _candidate(issue_code: IssueCode) -> CandidateIssue:
    return CandidateIssue(issue_code=issue_code)


def _contract_registry(
    *,
    critical_facts: tuple[FactKey, ...] | None = None,
    first_requirement: FactRequirement | None = None,
) -> IssueRegistry:
    contract = ISSUE_REGISTRY.definitions[0]
    replacement = IssueDefinition(
        issue_code=contract.issue_code,
        required_facts=(
            first_requirement or contract.required_facts[0],
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


def test_candidate_issue_without_facts_reports_all_requirements_missing() -> None:
    result = MissingFactDetector().detect(
        known_facts=(),
        candidate_issues=(_candidate(IssueCode.CONTRACT_TERM),),
        registry=ISSUE_REGISTRY,
    )

    issue = result.issue_results[0]
    assert issue.issue_code is IssueCode.CONTRACT_TERM
    assert issue.satisfied_fields == ()
    assert issue.missing_fields == (FactKey.CONTRACT_TYPE,)
    assert issue.critical_missing_fields == issue.missing_fields
    assert issue.critical_missing is True
    assert result.critical_missing is True
    assert all(
        assessment.status is RequirementStatus.MISSING
        and assessment.gap_reasons == (RequirementGapReason.FACT_NOT_PROVIDED,)
        for assessment in issue.requirements
    )


def test_all_required_facts_satisfy_one_issue() -> None:
    facts = (
        _fact(FactKey.CONTRACT_TYPE, fact_id="CF-contract-type"),
        _fact(FactKey.CONTRACT_START_DATE, fact_id="CF-contract-start"),
        _fact(FactKey.CONTRACT_END_DATE, fact_id="CF-contract-end"),
    )

    result = MissingFactDetector().detect(
        known_facts=facts,
        candidate_issues=(_candidate(IssueCode.CONTRACT_TERM),),
        registry=ISSUE_REGISTRY,
    )

    issue = result.issue_results[0]
    assert issue.satisfied_fields == (FactKey.CONTRACT_TYPE,)
    assert issue.missing_fields == ()
    assert issue.critical_missing_fields == ()
    assert issue.critical_missing is False
    assert result.fields_needed == ()
    assert result.critical_missing is False


def test_missing_noncritical_fact_does_not_block_critical_gate() -> None:
    registry = _contract_registry(critical_facts=(FactKey.CONTRACT_TYPE,))
    facts = (
        _fact(FactKey.CONTRACT_TYPE, fact_id="CF-contract-type"),
        _fact(FactKey.CONTRACT_START_DATE, fact_id="CF-contract-start"),
    )

    result = MissingFactDetector().detect(
        known_facts=facts,
        candidate_issues=(_candidate(IssueCode.CONTRACT_TERM),),
        registry=registry,
    )

    assert result.issue_results[0].missing_fields == (FactKey.CONTRACT_END_DATE,)
    assert result.issue_results[0].critical_missing_fields == ()
    assert result.critical_missing is False


def test_missing_critical_fact_blocks_substantive_path() -> None:
    facts = (
        _fact(FactKey.CONTRACT_START_DATE, fact_id="CF-contract-start"),
        _fact(FactKey.CONTRACT_END_DATE, fact_id="CF-contract-end"),
    )

    result = MissingFactDetector().detect(
        known_facts=facts,
        candidate_issues=(_candidate(IssueCode.CONTRACT_TERM),),
        registry=ISSUE_REGISTRY,
    )

    assert result.issue_results[0].critical_missing_fields == (FactKey.CONTRACT_TYPE,)
    assert result.critical_missing is True


def test_multi_issue_shared_fact_is_deduplicated_with_traceability() -> None:
    result = MissingFactDetector().detect(
        known_facts=(),
        candidate_issues=(
            _candidate(IssueCode.EMPLOYEE_UNILATERAL_TERMINATION),
            _candidate(IssueCode.CONTRACT_TERM),
        ),
        registry=ISSUE_REGISTRY,
    )

    assert tuple(issue.issue_code for issue in result.issue_results) == tuple(IssueCode)
    assert tuple(need.fact_key for need in result.fields_needed) == (
        FactKey.CONTRACT_TYPE,
        FactKey.NOTICE_SPECIAL_CASE,
        FactKey.EMPLOYEE_ROLE,
    )
    shared = result.fields_needed[0]
    assert shared.required_by_issues == tuple(IssueCode)
    assert shared.critical_for_issues == tuple(IssueCode)


def test_duplicate_fact_representations_fail_closed() -> None:
    duplicate_facts = (
        _fact(FactKey.CONTRACT_TYPE, fact_id="CF-contract-type-1"),
        _fact(FactKey.CONTRACT_TYPE, fact_id="CF-contract-type-2"),
    )

    with pytest.raises(MissingFactDetectionError) as captured:
        MissingFactDetector().detect(
            known_facts=duplicate_facts,
            candidate_issues=(_candidate(IssueCode.CONTRACT_TERM),),
            registry=ISSUE_REGISTRY,
        )

    assert captured.value.code is MissingFactDetectionErrorCode.DUPLICATE_FACT_REPRESENTATION


def test_explicit_unverified_fact_satisfies_current_registry_policy() -> None:
    result = MissingFactDetector().detect(
        known_facts=(_fact(FactKey.CONTRACT_TYPE, fact_id="CF-contract-type"),),
        candidate_issues=(_candidate(IssueCode.CONTRACT_TERM),),
        registry=ISSUE_REGISTRY,
    )

    assessment = result.issue_results[0].requirements[0]
    assert assessment.status is RequirementStatus.SATISFIED
    assert assessment.matched_fact_ids == ("CF-contract-type",)
    assert assessment.gap_reasons == ()


def test_inferred_fact_fails_an_explicit_only_requirement_policy() -> None:
    contract = ISSUE_REGISTRY.definitions[0]
    explicit_only = FactRequirement(
        fact_key=FactKey.CONTRACT_TYPE,
        role=contract.required_facts[0].role,
        accepted_assertion_modes=(AssertionMode.EXPLICIT,),
        accepted_verification_statuses=(VerificationStatus.UNVERIFIED,),
    )
    registry = _contract_registry(first_requirement=explicit_only)

    result = MissingFactDetector().detect(
        known_facts=(
            _fact(
                FactKey.CONTRACT_TYPE,
                fact_id="CF-inferred-contract-type",
                assertion_mode=AssertionMode.INFERRED,
            ),
        ),
        candidate_issues=(_candidate(IssueCode.CONTRACT_TERM),),
        registry=registry,
    )

    assessment = result.issue_results[0].requirements[0]
    assert assessment.status is RequirementStatus.POLICY_REJECTED
    assert assessment.matched_fact_ids == ("CF-inferred-contract-type",)
    assert assessment.gap_reasons == (RequirementGapReason.ASSERTION_MODE_NOT_ACCEPTED,)
    assert result.critical_missing is True


def test_unknown_fact_key_does_not_satisfy_a_required_fact() -> None:
    result = MissingFactDetector().detect(
        known_facts=(_fact("MODEL_INVENTED_FACT", fact_id="CF-unknown"),),
        candidate_issues=(_candidate(IssueCode.CONTRACT_TERM),),
        registry=ISSUE_REGISTRY,
    )

    assert result.issue_results[0].satisfied_fields == ()
    assert result.issue_results[0].missing_fields == (FactKey.CONTRACT_TYPE,)
    assert result.critical_missing is True


def test_unsupported_candidate_issue_fails_safe() -> None:
    unsupported = CandidateIssue.model_construct(issue_code="UNKNOWN_ISSUE")

    with pytest.raises(MissingFactDetectionError) as captured:
        MissingFactDetector().detect(
            known_facts=(),
            candidate_issues=(unsupported,),
            registry=ISSUE_REGISTRY,
        )

    assert captured.value.code is MissingFactDetectionErrorCode.UNSUPPORTED_CANDIDATE_ISSUE


def test_no_candidate_issues_does_not_run_detection() -> None:
    with pytest.raises(MissingFactDetectionError) as captured:
        MissingFactDetector().detect(
            known_facts=(),
            candidate_issues=(),
            registry=ISSUE_REGISTRY,
        )

    assert captured.value.code is MissingFactDetectionErrorCode.NO_CANDIDATE_ISSUES


def test_duplicate_candidate_issue_fails_closed() -> None:
    candidate = _candidate(IssueCode.CONTRACT_TERM)

    with pytest.raises(MissingFactDetectionError) as captured:
        MissingFactDetector().detect(
            known_facts=(),
            candidate_issues=(candidate, candidate),
            registry=ISSUE_REGISTRY,
        )

    assert captured.value.code is MissingFactDetectionErrorCode.DUPLICATE_CANDIDATE_ISSUE


def test_ordering_and_output_are_deterministic_for_reordered_inputs() -> None:
    facts = (
        _fact(FactKey.EMPLOYEE_ROLE, fact_id="CF-role"),
        _fact(FactKey.CONTRACT_TYPE, fact_id="CF-contract-type"),
    )
    candidates = tuple(_candidate(issue_code) for issue_code in reversed(tuple(IssueCode)))
    detector = MissingFactDetector()

    first = detector.detect(facts, candidates, ISSUE_REGISTRY)
    second = detector.detect(tuple(reversed(facts)), tuple(reversed(candidates)), ISSUE_REGISTRY)

    assert first == second
    assert first.model_dump_json() == second.model_dump_json()


def test_detector_does_not_mutate_inputs_and_output_is_immutable() -> None:
    facts = [_fact(FactKey.CONTRACT_TYPE, fact_id="CF-contract-type")]
    candidates = [_candidate(IssueCode.CONTRACT_TERM)]
    facts_before = [fact.model_dump_json() for fact in facts]
    candidates_before = [candidate.model_dump_json() for candidate in candidates]

    result = MissingFactDetector().detect(facts, candidates, ISSUE_REGISTRY)

    assert [fact.model_dump_json() for fact in facts] == facts_before
    assert [candidate.model_dump_json() for candidate in candidates] == candidates_before
    with pytest.raises(ValidationError):
        result.critical_missing = False


def test_detector_module_is_pure_domain_logic() -> None:
    from vietnamese_labor_law_assistant.decision_support import missing_facts

    tree = ast.parse(inspect.getsource(missing_facts))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    prohibited_prefixes = (
        "openai",
        "vietnamese_labor_law_assistant.agent",
        "vietnamese_labor_law_assistant.calculator",
        "vietnamese_labor_law_assistant.mcp_clients",
        "vietnamese_labor_law_assistant.mcp_servers",
        "vietnamese_labor_law_assistant.retrieval",
    )
    assert not any(module.startswith(prohibited_prefixes) for module in imported_modules)


def test_indefinite_contract_type_does_not_require_contract_dates() -> None:
    result = MissingFactDetector().detect(
        known_facts=(
            _fact(
                FactKey.CONTRACT_TYPE,
                fact_id="CF-indefinite-type",
                raw_value="INDEFINITE",
            ),
        ),
        candidate_issues=(_candidate(IssueCode.CONTRACT_TERM),),
        registry=ISSUE_REGISTRY,
    )

    issue = result.issue_results[0]
    assert issue.missing_fields == ()
    assert issue.critical_missing_fields == ()


def test_explicit_24_month_duration_satisfies_contract_classification_scope() -> None:
    duration = CaseFact(
        fact_id="CF-duration-24",
        fact_key=FactKey.CONTRACT_DURATION.value,
        fact_type="DURATION",
        raw_value="24 tháng",
        normalized_value=24,
        assertion_mode=AssertionMode.EXPLICIT,
        verification_status=VerificationStatus.UNVERIFIED,
        source_type=SourceType.USER_MESSAGE,
        source_ref="user_message:missing-facts",
        source_span=SourceSpan(start_offset=0, end_offset=8, text="24 tháng"),
    )

    result = MissingFactDetector().detect(
        known_facts=(duration,),
        candidate_issues=(_candidate(IssueCode.CONTRACT_TERM),),
        registry=ISSUE_REGISTRY,
    )

    assessment = result.issue_results[0].requirements[0]
    assert assessment.status is RequirementStatus.SATISFIED
    assert assessment.matched_fact_ids == ("CF-duration-24",)
    assert result.fields_needed == ()


def test_unpaid_wage_signal_selects_wage_delay_clarification_branch() -> None:
    wage_problem = _fact(
        "WAGE_PAYMENT_PROBLEM",
        fact_id="CF-wage-problem",
        raw_value="WAGE_PAYMENT_PROBLEM_REPORTED",
    )

    result = MissingFactDetector().detect(
        known_facts=(wage_problem,),
        candidate_issues=(_candidate(IssueCode.EMPLOYEE_UNILATERAL_TERMINATION),),
        registry=ISSUE_REGISTRY,
    )

    assert tuple(field.fact_key.value for field in result.fields_needed) == (
        "WAGE_PAYMENT_DUE_DATE",
        "WAGE_PAYMENT_STATUS",
        "WAGE_DELAY_FORCE_MAJEURE",
    )
    assert all(
        field.fact_key not in {FactKey.CONTRACT_TYPE, FactKey.EMPLOYEE_ROLE}
        for field in result.fields_needed
    )
