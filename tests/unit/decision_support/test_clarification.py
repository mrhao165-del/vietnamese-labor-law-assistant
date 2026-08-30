"""Offline behavior tests for bounded targeted clarification."""

from __future__ import annotations

import ast
import inspect

import pytest
from pydantic import ValidationError

from vietnamese_labor_law_assistant.decision_support.clarification import (
    ClarificationError,
    ClarificationErrorCode,
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
    MissingFactResult,
    RequirementGapReason,
)
from vietnamese_labor_law_assistant.decision_support.models import (
    CandidateIssue,
    CaseFact,
    SourceSpan,
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
        source_ref="user_message:clarification-tests",
        source_span=SourceSpan(
            start_offset=0,
            end_offset=len(raw_value),
            text=raw_value,
        ),
    )


def _candidate(issue_code: IssueCode) -> CandidateIssue:
    return CandidateIssue(issue_code=issue_code)


def _detect(
    *,
    facts: tuple[CaseFact, ...] = (),
    issues: tuple[IssueCode, ...] = (IssueCode.CONTRACT_TERM,),
    registry: IssueRegistry = ISSUE_REGISTRY,
) -> MissingFactResult:
    return MissingFactDetector().detect(
        known_facts=facts,
        candidate_issues=tuple(_candidate(issue_code) for issue_code in issues),
        registry=registry,
    )


def _registry_with_contract_critical_facts(
    critical_facts: tuple[FactKey, ...],
) -> IssueRegistry:
    contract = ISSUE_REGISTRY.definitions[0]
    replacement = IssueDefinition(
        issue_code=contract.issue_code,
        required_facts=(
            contract.required_facts[0],
            FactRequirement(
                fact_key=FactKey.CONTRACT_START_DATE,
                role="Test-only optional interval start.",
            ),
            FactRequirement(
                fact_key=FactKey.CONTRACT_END_DATE,
                role="Test-only optional interval end.",
            ),
        ),
        critical_facts=critical_facts,
        conditional_requirement_branches=contract.conditional_requirement_branches,
        context_fact_keys=contract.context_fact_keys,
        conflict_rules=contract.conflict_rules,
        evidence_needs=contract.evidence_needs,
        calculator_needs=contract.calculator_needs,
        applicability_scope=contract.applicability_scope,
    )
    return IssueRegistry(definitions=(replacement, ISSUE_REGISTRY.definitions[1]))


def test_critical_field_is_prioritized_ahead_of_earlier_noncritical_fields() -> None:
    registry = _registry_with_contract_critical_facts((FactKey.CONTRACT_START_DATE,))

    result = TargetedClarificationBuilder().build(
        _detect(registry=registry),
        max_questions=1,
    )

    assert result.reason_code is ClarificationReasonCode.CRITICAL_FACTS_MISSING
    assert tuple(question.fact_key for question in result.questions) == (
        FactKey.CONTRACT_START_DATE,
    )
    assert result.questions[0].critical is True
    assert result.questions[0].priority == 1


def test_shared_field_is_asked_once_with_all_issue_dependencies() -> None:
    result = TargetedClarificationBuilder().build(
        _detect(issues=tuple(reversed(tuple(IssueCode)))),
        max_questions=5,
    )

    contract_type_questions = tuple(
        question for question in result.questions if question.fact_key is FactKey.CONTRACT_TYPE
    )
    assert len(contract_type_questions) == 1
    assert contract_type_questions[0].related_issue_codes == tuple(IssueCode)
    assert result.questions[0] == contract_type_questions[0]


def test_satisfied_fact_is_never_asked() -> None:
    missing = _detect(
        facts=(_fact(FactKey.CONTRACT_TYPE, fact_id="CF-contract-type"),),
    )

    result = TargetedClarificationBuilder().build(missing, max_questions=3)

    assert result.fields_needed == ()
    assert all(question.fact_key is not FactKey.CONTRACT_TYPE for question in result.questions)


def test_previously_requested_field_is_not_repeated_but_remains_an_unresolved_gap() -> None:
    result = TargetedClarificationBuilder().build(
        _detect(),
        previously_requested_fields=(FactKey.CONTRACT_TYPE,),
        max_questions=1,
    )

    assert result.fields_needed[0].fact_key is FactKey.CONTRACT_TYPE
    assert result.questions == ()


def test_explicit_question_budget_is_respected() -> None:
    result = TargetedClarificationBuilder().build(_detect(issues=tuple(IssueCode)), max_questions=2)

    assert len(result.questions) == 2
    assert tuple(question.priority for question in result.questions) == (1, 2)


def test_default_question_budget_bounds_a_round_to_three_questions() -> None:
    result = TargetedClarificationBuilder().build(
        _detect(issues=tuple(IssueCode)),
    )

    assert len(result.questions) == 3


def test_ordering_is_deterministic_for_reordered_inputs_and_history() -> None:
    detector = MissingFactDetector()
    first_missing = detector.detect(
        known_facts=(),
        candidate_issues=tuple(_candidate(code) for code in reversed(tuple(IssueCode))),
        registry=ISSUE_REGISTRY,
    )
    second_missing = detector.detect(
        known_facts=(),
        candidate_issues=tuple(_candidate(code) for code in IssueCode),
        registry=ISSUE_REGISTRY,
    )
    builder = TargetedClarificationBuilder()

    first = builder.build(
        first_missing,
        previously_requested_fields=(FactKey.EMPLOYEE_ROLE, FactKey.CONTRACT_END_DATE),
    )
    second = builder.build(
        second_missing,
        previously_requested_fields=(FactKey.CONTRACT_END_DATE, FactKey.EMPLOYEE_ROLE),
    )

    assert first == second
    assert first.model_dump_json() == second.model_dump_json()


def test_no_missing_facts_returns_no_clarification_questions() -> None:
    missing = _detect(
        facts=(
            _fact(FactKey.CONTRACT_TYPE, fact_id="CF-contract-type"),
            _fact(FactKey.CONTRACT_START_DATE, fact_id="CF-start"),
            _fact(FactKey.CONTRACT_END_DATE, fact_id="CF-end"),
        ),
    )

    result = TargetedClarificationBuilder().build(missing)

    assert result.reason_code is ClarificationReasonCode.NO_MISSING_FACTS
    assert result.fields_needed == ()
    assert result.questions == ()


def test_only_noncritical_gaps_use_required_fact_reason() -> None:
    registry = _registry_with_contract_critical_facts((FactKey.CONTRACT_TYPE,))
    missing = _detect(
        facts=(_fact(FactKey.CONTRACT_TYPE, fact_id="CF-contract-type"),),
        registry=registry,
    )

    result = TargetedClarificationBuilder().build(missing)

    assert result.reason_code is ClarificationReasonCode.REQUIRED_FACTS_MISSING
    assert all(question.critical is False for question in result.questions)


def test_multiple_issues_rank_shared_field_by_information_value_after_criticality() -> None:
    result = TargetedClarificationBuilder().build(
        _detect(issues=tuple(IssueCode)),
        max_questions=2,
    )

    assert tuple(question.fact_key for question in result.questions) == (
        FactKey.CONTRACT_TYPE,
        FactKey.NOTICE_SPECIAL_CASE,
    )
    assert result.questions[0].related_issue_codes == tuple(IssueCode)


def test_output_contains_typed_reason_fields_and_requirement_reasons() -> None:
    result = TargetedClarificationBuilder().build(_detect(), max_questions=1)

    assert result.reason_code is ClarificationReasonCode.CRITICAL_FACTS_MISSING
    assert tuple(field.fact_key for field in result.fields_needed) == (FactKey.CONTRACT_TYPE,)
    assert result.questions[0].requirement_reasons == (RequirementGapReason.FACT_NOT_PROVIDED,)
    assert result.questions[0].question.strip()


def test_questions_do_not_emit_legal_conclusion_language() -> None:
    result = TargetedClarificationBuilder().build(
        _detect(issues=tuple(IssueCode)),
        max_questions=5,
    )
    prohibited_phrases = (
        "bạn chắc chắn được quyền",
        "công ty chắc chắn vi phạm",
        "bạn nên kiện",
        "bạn được nghỉ ngay",
        "được quyền chấm dứt",
        "không được chấm dứt",
    )

    assert result.questions
    for question in result.questions:
        lowered = question.question.casefold()
        assert not any(phrase in lowered for phrase in prohibited_phrases)


@pytest.mark.parametrize("budget", (0, -1))
def test_invalid_question_budget_fails_closed(budget: int) -> None:
    with pytest.raises(ClarificationError) as captured:
        TargetedClarificationBuilder().build(_detect(), max_questions=budget)

    assert captured.value.code is ClarificationErrorCode.INVALID_QUESTION_BUDGET


def test_malformed_missing_fact_result_fails_closed() -> None:
    malformed = MissingFactResult.model_construct(
        issue_results=(),
        fields_needed=(),
        critical_missing=True,
    )

    with pytest.raises(ClarificationError) as captured:
        TargetedClarificationBuilder().build(malformed)

    assert captured.value.code is ClarificationErrorCode.MALFORMED_MISSING_FACT_RESULT


def test_unknown_previous_field_fails_closed() -> None:
    with pytest.raises(ClarificationError) as captured:
        TargetedClarificationBuilder().build(
            _detect(),
            previously_requested_fields=("MODEL_INVENTED_FACT",),
        )

    assert captured.value.code is ClarificationErrorCode.INVALID_PREVIOUS_REQUESTED_FIELD


def test_output_is_immutable() -> None:
    result = TargetedClarificationBuilder().build(_detect(), max_questions=1)

    with pytest.raises(ValidationError):
        result.reason_code = ClarificationReasonCode.NO_MISSING_FACTS


def test_clarification_module_stays_in_the_pure_decision_support_boundary() -> None:
    from vietnamese_labor_law_assistant.decision_support import clarification

    tree = ast.parse(inspect.getsource(clarification))
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
