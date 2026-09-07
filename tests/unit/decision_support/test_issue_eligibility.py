"""Offline tests for deterministic candidate-issue semantic eligibility."""

from __future__ import annotations

import inspect

import pytest

from vietnamese_labor_law_assistant.decision_support.issue_eligibility import (
    IssueEligibilityRejectionCode,
    evaluate_issue_eligibility,
)
from vietnamese_labor_law_assistant.decision_support.issues import IssueCode
from vietnamese_labor_law_assistant.decision_support.models import (
    CandidateIssue,
    CaseIntakeInput,
)


def _input(source_text: str) -> CaseIntakeInput:
    return CaseIntakeInput(source_text=source_text, source_ref="user_message:issue-eligibility")


def _issues(*issue_codes: IssueCode) -> tuple[CandidateIssue, ...]:
    return tuple(CandidateIssue(issue_code=issue_code) for issue_code in issue_codes)


def _admitted(source_text: str, *issue_codes: IssueCode) -> tuple[IssueCode, ...]:
    result = evaluate_issue_eligibility(_input(source_text), _issues(*issue_codes))
    return tuple(issue.issue_code for issue in result.admitted_issues)


@pytest.mark.parametrize(
    "source_text",
    [
        "Tôi muốn nghỉ việc.",
        "Tôi đang xem xét nghỉ việc, nhưng ngày dự kiến chưa được cung cấp.",
        "Ngày dự kiến chưa xác định, nhưng tôi muốn nghỉ việc.",
        "Tôi muốn nghỉ việc, ngày dự kiến chưa xác định.",
    ],
)
def test_affirmative_termination_intent_is_admitted_despite_separate_missing_date(
    source_text: str,
) -> None:
    assert _admitted(source_text, IssueCode.EMPLOYEE_UNILATERAL_TERMINATION) == (
        IssueCode.EMPLOYEE_UNILATERAL_TERMINATION,
    )


@pytest.mark.parametrize(
    "source_text",
    [
        "Chưa xác định được ngày dự kiến nghỉ việc.",
        "Chưa xác định liệu tôi có nghỉ việc hay không.",
    ],
)
def test_missing_or_unknown_termination_mention_is_rejected(source_text: str) -> None:
    result = evaluate_issue_eligibility(
        _input(source_text),
        _issues(IssueCode.EMPLOYEE_UNILATERAL_TERMINATION),
    )

    assert result.admitted_issues == ()
    assert result.rejected_issues[0].reason_code is (
        IssueEligibilityRejectionCode.TERMINATION_EVIDENCE_MISSING_OR_UNKNOWN_ONLY
    )


def test_negated_termination_intent_is_rejected() -> None:
    result = evaluate_issue_eligibility(
        _input("Tôi không muốn nghỉ việc."),
        _issues(IssueCode.EMPLOYEE_UNILATERAL_TERMINATION),
    )

    assert result.admitted_issues == ()
    assert result.rejected_issues[0].reason_code is (
        IssueEligibilityRejectionCode.TERMINATION_EVIDENCE_NEGATED_ONLY
    )


def test_explicit_employee_termination_analysis_request_is_admitted() -> None:
    assert _admitted(
        "Tôi cần xem xét việc người lao động tự chấm dứt hợp đồng.",
        IssueCode.EMPLOYEE_UNILATERAL_TERMINATION,
    ) == (IssueCode.EMPLOYEE_UNILATERAL_TERMINATION,)


@pytest.mark.parametrize(
    "source_text",
    [
        "Tôi cần xem xét liệu người lao động có nghỉ việc hay không.",
        "Tôi cần xem xét việc người lao động không chấm dứt hợp đồng.",
    ],
)
def test_questioned_or_negated_analysis_request_is_not_affirmative(source_text: str) -> None:
    assert _admitted(source_text, IssueCode.EMPLOYEE_UNILATERAL_TERMINATION) == ()


@pytest.mark.parametrize(
    "source_text",
    [
        "Hợp đồng của tôi có thời hạn 12 tháng.",
        "Tôi cần xem xét thời hạn hợp đồng, nhưng loại và thời gian chưa được cung cấp.",
    ],
)
def test_contract_term_specific_subject_matter_is_admitted_without_case_facts(
    source_text: str,
) -> None:
    assert _admitted(source_text, IssueCode.CONTRACT_TERM) == (IssueCode.CONTRACT_TERM,)


def test_fixed_term_termination_admits_both_independently_supported_issues() -> None:
    assert _admitted(
        "Tôi muốn chấm dứt hợp đồng xác định thời hạn.",
        IssueCode.EMPLOYEE_UNILATERAL_TERMINATION,
        IssueCode.CONTRACT_TERM,
    ) == (
        IssueCode.EMPLOYEE_UNILATERAL_TERMINATION,
        IssueCode.CONTRACT_TERM,
    )


@pytest.mark.parametrize(
    "source_text",
    [
        "Tôi muốn chấm dứt hợp đồng.",
        "Tôi đang làm theo hợp đồng lao động.",
    ],
)
def test_bare_contract_reference_does_not_admit_contract_term(source_text: str) -> None:
    result = evaluate_issue_eligibility(
        _input(source_text),
        _issues(IssueCode.CONTRACT_TERM),
    )

    assert result.admitted_issues == ()
    assert result.rejected_issues[0].reason_code is (
        IssueEligibilityRejectionCode.CONTRACT_TERM_SIGNAL_ABSENT
    )


def test_bare_contract_termination_rejects_term_issue_but_preserves_termination() -> None:
    assert _admitted(
        "Tôi muốn chấm dứt hợp đồng.",
        IssueCode.CONTRACT_TERM,
        IssueCode.EMPLOYEE_UNILATERAL_TERMINATION,
    ) == (IssueCode.EMPLOYEE_UNILATERAL_TERMINATION,)


def test_notice_period_wording_does_not_open_contract_term_issue() -> None:
    assert (
        _admitted(
            "Tôi hỏi về thời hạn báo trước khi nghỉ việc.",
            IssueCode.CONTRACT_TERM,
        )
        == ()
    )


def test_issue_eligibility_is_independent_of_fact_output() -> None:
    source = _input("Tôi muốn nghỉ việc; vị trí công việc chưa được cung cấp.")
    proposals = _issues(IssueCode.EMPLOYEE_UNILATERAL_TERMINATION)

    first = evaluate_issue_eligibility(source, proposals)
    second = evaluate_issue_eligibility(source, proposals)

    assert first == second
    assert first.admitted_issues == proposals


def test_issue_eligibility_signature_accepts_no_fact_or_compiler_input() -> None:
    assert tuple(inspect.signature(evaluate_issue_eligibility).parameters) == (
        "case_input",
        "proposals",
    )


def test_adversarial_date_property_request_does_not_become_termination_intent() -> None:
    result = evaluate_issue_eligibility(
        _input("Tôi muốn xem xét thông tin ngày dự kiến nghỉ việc."),
        _issues(IssueCode.EMPLOYEE_UNILATERAL_TERMINATION),
    )

    assert result.admitted_issues == ()
    assert result.rejected_issues[0].reason_code is (
        IssueEligibilityRejectionCode.TERMINATION_AFFIRMATIVE_SIGNAL_ABSENT
    )
