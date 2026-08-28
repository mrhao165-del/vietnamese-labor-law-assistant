"""Offline integration proof for the Week-2 to Week-3 domain contracts."""

from __future__ import annotations

from vietnamese_labor_law_assistant.decision_support.clarification import (
    ClarificationReasonCode,
    TargetedClarificationBuilder,
)
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
    MissingFactDetector,
    RequirementGapReason,
    RequirementStatus,
)
from vietnamese_labor_law_assistant.decision_support.models import (
    CandidateIssue,
    CaseFact,
    CaseIntakeResult,
    SourceSpan,
)


def _fact(
    fact_key: FactKey,
    *,
    fact_id: str,
    raw_value: str,
    assertion_mode: AssertionMode = AssertionMode.EXPLICIT,
) -> CaseFact:
    return CaseFact(
        fact_id=fact_id,
        fact_key=fact_key.value,
        fact_type="TEXT",
        raw_value=raw_value,
        normalized_value=raw_value,
        assertion_mode=assertion_mode,
        verification_status=VerificationStatus.UNVERIFIED,
        source_type=SourceType.USER_MESSAGE,
        source_ref="user_message:week3-domain-integration",
        source_span=SourceSpan(
            start_offset=0,
            end_offset=len(raw_value),
            text=raw_value,
        ),
    )


def _candidate(issue_code: IssueCode) -> CandidateIssue:
    return CandidateIssue(issue_code=issue_code)


def _run_domain_flow(
    intake: CaseIntakeResult,
    *,
    registry: IssueRegistry = ISSUE_REGISTRY,
    max_questions: int = 3,
):
    missing = MissingFactDetector().detect(
        known_facts=intake.facts,
        candidate_issues=intake.candidate_issues,
        registry=registry,
    )
    clarification = TargetedClarificationBuilder().build(
        missing,
        max_questions=max_questions,
    )
    return missing, clarification


def _explicit_contract_type_registry() -> IssueRegistry:
    contract = ISSUE_REGISTRY.definitions[0]
    contract_type = contract.required_facts[0]
    explicit_contract_type = FactRequirement(
        fact_key=contract_type.fact_key,
        role=contract_type.role,
        accepted_assertion_modes=(AssertionMode.EXPLICIT,),
        accepted_verification_statuses=contract_type.accepted_verification_statuses,
    )
    explicit_contract = IssueDefinition(
        issue_code=contract.issue_code,
        required_facts=(explicit_contract_type, *contract.required_facts[1:]),
        critical_facts=contract.critical_facts,
        evidence_needs=contract.evidence_needs,
        calculator_needs=contract.calculator_needs,
        applicability_scope=contract.applicability_scope,
    )
    return IssueRegistry(definitions=(explicit_contract, ISSUE_REGISTRY.definitions[1]))


def test_complete_typed_intake_produces_no_gap_or_clarification() -> None:
    intake = CaseIntakeResult(
        facts=[
            _fact(FactKey.CONTRACT_TYPE, fact_id="CF-flow-type", raw_value="INDEFINITE"),
            _fact(
                FactKey.CONTRACT_START_DATE,
                fact_id="CF-flow-start",
                raw_value="2026-01-01",
            ),
            _fact(
                FactKey.CONTRACT_END_DATE,
                fact_id="CF-flow-end",
                raw_value="2026-12-31",
            ),
        ],
        candidate_issues=[_candidate(IssueCode.CONTRACT_TERM)],
    )

    missing, clarification = _run_domain_flow(intake)

    assert missing.critical_missing is False
    assert missing.fields_needed == ()
    assert clarification.reason_code is ClarificationReasonCode.NO_MISSING_FACTS
    assert clarification.fields_needed == ()
    assert clarification.questions == ()


def test_critical_gap_from_typed_intake_produces_bounded_clarification() -> None:
    intake = CaseIntakeResult(
        facts=[
            _fact(
                FactKey.CONTRACT_START_DATE,
                fact_id="CF-critical-start",
                raw_value="2026-01-01",
            ),
            _fact(
                FactKey.CONTRACT_END_DATE,
                fact_id="CF-critical-end",
                raw_value="2026-12-31",
            ),
        ],
        candidate_issues=[_candidate(IssueCode.CONTRACT_TERM)],
    )

    missing, clarification = _run_domain_flow(intake, max_questions=1)

    assert missing.critical_missing is True
    assert tuple(field.fact_key for field in missing.fields_needed) == (FactKey.CONTRACT_TYPE,)
    assert clarification.reason_code is ClarificationReasonCode.CRITICAL_FACTS_MISSING
    assert len(clarification.questions) == 1
    assert clarification.questions[0].fact_key is FactKey.CONTRACT_TYPE
    assert clarification.questions[0].critical is True


def test_multi_issue_shared_gap_produces_one_semantic_question() -> None:
    intake = CaseIntakeResult(
        facts=[
            _fact(
                FactKey.CONTRACT_START_DATE,
                fact_id="CF-shared-start",
                raw_value="2026-01-01",
            ),
            _fact(
                FactKey.CONTRACT_END_DATE,
                fact_id="CF-shared-end",
                raw_value="2026-12-31",
            ),
            _fact(
                FactKey.NOTICE_SPECIAL_CASE,
                fact_id="CF-shared-special",
                raw_value="NONE",
            ),
            _fact(FactKey.EMPLOYEE_ROLE, fact_id="CF-shared-role", raw_value="STANDARD"),
        ],
        candidate_issues=[_candidate(issue_code) for issue_code in IssueCode],
    )

    missing, clarification = _run_domain_flow(intake)

    assert tuple(field.fact_key for field in missing.fields_needed) == (FactKey.CONTRACT_TYPE,)
    assert missing.fields_needed[0].required_by_issues == tuple(IssueCode)
    assert len(clarification.questions) == 1
    assert clarification.questions[0].fact_key is FactKey.CONTRACT_TYPE
    assert clarification.questions[0].related_issue_codes == tuple(IssueCode)


def test_inferred_fact_remains_missing_when_registry_requires_explicit_assertion() -> None:
    intake = CaseIntakeResult(
        facts=[
            _fact(
                FactKey.CONTRACT_TYPE,
                fact_id="CF-policy-type",
                raw_value="INDEFINITE",
                assertion_mode=AssertionMode.INFERRED,
            ),
            _fact(
                FactKey.CONTRACT_START_DATE,
                fact_id="CF-policy-start",
                raw_value="2026-01-01",
            ),
            _fact(
                FactKey.CONTRACT_END_DATE,
                fact_id="CF-policy-end",
                raw_value="2026-12-31",
            ),
        ],
        candidate_issues=[_candidate(IssueCode.CONTRACT_TERM)],
    )

    missing, clarification = _run_domain_flow(
        intake,
        registry=_explicit_contract_type_registry(),
    )

    assessment = missing.issue_results[0].requirements[0]
    assert assessment.status is RequirementStatus.POLICY_REJECTED
    assert assessment.gap_reasons == (RequirementGapReason.ASSERTION_MODE_NOT_ACCEPTED,)
    assert missing.critical_missing is True
    assert clarification.reason_code is ClarificationReasonCode.CRITICAL_FACTS_MISSING
    assert tuple(question.fact_key for question in clarification.questions) == (
        FactKey.CONTRACT_TYPE,
    )
