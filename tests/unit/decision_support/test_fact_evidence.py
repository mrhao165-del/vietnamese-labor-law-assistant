"""Adversarial evidence/polarity tests for deterministic fact admission."""

from __future__ import annotations

import pytest

from vietnamese_labor_law_assistant.decision_support.fact_evidence import (
    FactEvidenceClassification,
    classify_fact_evidence,
)
from vietnamese_labor_law_assistant.decision_support.issue_registry import FactKey


def _classify(fact_key: FactKey, text: str) -> FactEvidenceClassification:
    return classify_fact_evidence(fact_key, text)


@pytest.mark.parametrize(
    ("fact_key", "text", "expected_status"),
    [
        (
            FactKey.INTENDED_TERMINATION_DATE,
            "Thông tin ngày nghỉ chưa được cung cấp.",
            "MISSING",
        ),
        (
            FactKey.INTENDED_TERMINATION_DATE,
            "Chưa xác định được ngày dự kiến nghỉ việc.",
            "UNKNOWN",
        ),
        (
            FactKey.EMPLOYEE_ROLE,
            "Tôi không phải là giám sát viên.",
            "NEGATED",
        ),
        (
            FactKey.CONTRACT_DURATION,
            "Tôi chưa biết hợp đồng kéo dài bao nhiêu tháng.",
            "UNKNOWN",
        ),
        (
            FactKey.NOTICE_SPECIAL_CASE,
            "Hồ sơ không có dữ liệu về trường hợp miễn báo trước.",
            "MISSING",
        ),
        (
            FactKey.WAGE_DELAY_FORCE_MAJEURE,
            "Không có dữ liệu về sự kiện bất khả kháng.",
            "MISSING",
        ),
        (
            FactKey.NOTICE_SPECIAL_CASE,
            "Thông tin về giá trị NONE chưa được cung cấp.",
            "MISSING",
        ),
    ],
)
def test_non_present_language_is_classified_before_normalization(
    fact_key: FactKey, text: str, expected_status: str
) -> None:
    classification = _classify(fact_key, text)

    assert classification.status.value == expected_status


@pytest.mark.parametrize(
    ("fact_key", "text"),
    [
        (
            FactKey.WAGE_DELAY_FORCE_MAJEURE,
            "Hồ sơ xác nhận không có sự kiện bất khả kháng.",
        ),
        (FactKey.NOTICE_SPECIAL_CASE, "Trường hợp miễn báo trước được ghi là NONE."),
        (FactKey.WAGE_PAYMENT_STATUS, "Tiền lương vẫn chưa được thanh toán."),
        (FactKey.CONTRACT_TYPE, "Hợp đồng không xác định thời hạn."),
    ],
)
def test_supported_canonical_absence_or_negative_grammar_remains_present(
    fact_key: FactKey, text: str
) -> None:
    classification = _classify(fact_key, text)

    assert classification.status.value == "PRESENT_ASSERTED"


@pytest.mark.parametrize(
    ("fact_key", "text"),
    [
        (FactKey.NOTICE_SPECIAL_CASE, "Trường hợp miễn báo trước không phải là NONE."),
        (
            FactKey.CONTRACT_TYPE,
            "Hợp đồng không phải là không xác định thời hạn.",
        ),
        (
            FactKey.WAGE_DELAY_FORCE_MAJEURE,
            "Hồ sơ không xác nhận không có sự kiện bất khả kháng.",
        ),
    ],
)
def test_explicit_denial_takes_precedence_over_canonical_absence_tokens(
    fact_key: FactKey, text: str
) -> None:
    classification = _classify(fact_key, text)

    assert classification.status.value == "NEGATED"


@pytest.mark.parametrize(
    ("fact_key", "text"),
    [
        (
            FactKey.CONTRACT_TYPE,
            "Chưa chắc hợp đồng không xác định thời hạn.",
        ),
        (
            FactKey.WAGE_DELAY_FORCE_MAJEURE,
            "Chưa chắc việc chậm trả không do sự kiện bất khả kháng.",
        ),
    ],
)
def test_uncertainty_takes_precedence_over_canonical_negative_values(
    fact_key: FactKey, text: str
) -> None:
    classification = _classify(fact_key, text)

    assert classification.status.value == "UNKNOWN"


@pytest.mark.parametrize(
    ("fact_key", "text", "expected_status"),
    [
        (
            FactKey.CONTRACT_TYPE,
            "Không chắc hợp đồng không xác định thời hạn.",
            "UNKNOWN",
        ),
        (
            FactKey.WAGE_DELAY_FORCE_MAJEURE,
            "Không chắc việc chậm trả không do sự kiện bất khả kháng.",
            "UNKNOWN",
        ),
        (
            FactKey.CONTRACT_TYPE,
            "Không đúng là hợp đồng không xác định thời hạn.",
            "NEGATED",
        ),
        (
            FactKey.WAGE_DELAY_FORCE_MAJEURE,
            "Không đúng là việc chậm trả không do sự kiện bất khả kháng.",
            "NEGATED",
        ),
    ],
)
def test_canonical_negative_value_does_not_hide_outer_non_present_language(
    fact_key: FactKey, text: str, expected_status: str
) -> None:
    classification = _classify(fact_key, text)

    assert classification.status.value == expected_status
