"""End-to-end unit tests for the deterministic FactProposal compiler."""

from __future__ import annotations

import ast
import inspect
from importlib import import_module

import pytest

from vietnamese_labor_law_assistant.decision_support.enums import (
    AssertionMode,
    SourceType,
    VerificationStatus,
)
from vietnamese_labor_law_assistant.decision_support.fact_compiler import (
    FactCompilationResult,
    FactProposal,
    compile_fact_proposals,
)
from vietnamese_labor_law_assistant.decision_support.fact_contract import FactType
from vietnamese_labor_law_assistant.decision_support.issue_registry import FactKey
from vietnamese_labor_law_assistant.decision_support.models import CaseIntakeInput


def _source(text: str, source_ref: str = "user_message:fact-compiler") -> CaseIntakeInput:
    return CaseIntakeInput(source_text=text, source_ref=source_ref)


def _proposal(fact_key: FactKey, literal: str) -> FactProposal:
    return FactProposal(fact_key=fact_key, source_span_text=literal)


def _compile(text: str, *proposals: FactProposal) -> FactCompilationResult:
    return compile_fact_proposals(_source(text), proposals)


@pytest.mark.parametrize(
    ("fact_key", "source_text", "literal", "reason"),
    [
        (
            FactKey.INTENDED_TERMINATION_DATE,
            "Thông tin ngày nghỉ chưa được cung cấp.",
            "Thông tin ngày nghỉ chưa được cung cấp",
            "EVIDENCE_MISSING",
        ),
        (
            FactKey.INTENDED_TERMINATION_DATE,
            "Chưa xác định được ngày dự kiến nghỉ việc.",
            "Chưa xác định được ngày dự kiến nghỉ việc",
            "EVIDENCE_UNKNOWN",
        ),
        (
            FactKey.EMPLOYEE_ROLE,
            "Tôi không phải là giám sát viên.",
            "không phải là giám sát viên",
            "EVIDENCE_NEGATED",
        ),
    ],
)
def test_missing_unknown_and_negated_proposals_never_become_positive_facts(
    fact_key: FactKey, source_text: str, literal: str, reason: str
) -> None:
    result = _compile(source_text, _proposal(fact_key, literal))

    assert result.admitted_facts == ()
    assert tuple(rejection.reason_code.value for rejection in result.rejections) == (reason,)


@pytest.mark.parametrize(
    ("fact_key", "source_text", "literal", "fact_type", "normalized_value"),
    [
        (
            FactKey.CONTRACT_DURATION,
            "Hợp đồng có thời hạn 24 tháng.",
            "Hợp đồng có thời hạn 24 tháng",
            FactType.DURATION,
            24,
        ),
        (
            FactKey.CONTRACT_EXPIRY_STATEMENT,
            "Hợp đồng này sắp hết hạn.",
            "sắp hết hạn",
            FactType.TEXT,
            "sắp hết hạn",
        ),
        (
            FactKey.CONTRACT_SIGNED_DATE,
            "Hợp đồng được ký ngày 2027-04-22.",
            "2027-04-22",
            FactType.DATE,
            "2027-04-22",
        ),
        (
            FactKey.CONTRACT_TYPE,
            "Loại hợp đồng là FIXED_TERM.",
            "FIXED_TERM",
            FactType.TEXT,
            "FIXED_TERM",
        ),
        (
            FactKey.EVENT_TIME,
            "Sự việc xảy ra vào cuối tuần trước.",
            "cuối tuần trước",
            FactType.TEMPORAL_EXPRESSION,
            "cuối tuần trước",
        ),
        (
            FactKey.UNPAID_WAGES_AMOUNT,
            "Khoản lương còn thiếu là 7.250.000 đồng.",
            "7.250.000 đồng",
            FactType.MONEY,
            7_250_000,
        ),
        (
            FactKey.UNPAID_WAGES_DURATION,
            "Doanh nghiệp nợ lương trong 2 tháng.",
            "2 tháng",
            FactType.DURATION,
            2,
        ),
        (
            FactKey.CONTRACT_START_DATE,
            "Hợp đồng bắt đầu ngày 2027-03-10.",
            "2027-03-10",
            FactType.DATE,
            "2027-03-10",
        ),
        (
            FactKey.CONTRACT_END_DATE,
            "Hợp đồng kết thúc ngày 2028-03-09.",
            "2028-03-09",
            FactType.DATE,
            "2028-03-09",
        ),
        (
            FactKey.NOTICE_SPECIAL_CASE,
            "Trường hợp miễn báo trước được ghi là NONE.",
            "NONE",
            FactType.TEXT,
            "NONE",
        ),
        (
            FactKey.EMPLOYEE_ROLE,
            "Vai trò của tôi là nhân viên vận hành.",
            "nhân viên vận hành",
            FactType.TEXT,
            "nhân viên vận hành",
        ),
        (
            FactKey.INTENDED_TERMINATION_DATE,
            "Tôi dự kiến nghỉ việc vào đầu quý tới.",
            "đầu quý tới",
            FactType.TEMPORAL_EXPRESSION,
            "đầu quý tới",
        ),
        (
            FactKey.INTENDED_TERMINATION_REFERENCE_DATE,
            "Ngày làm mốc tính dự kiến nghỉ là 2027-01-10.",
            "2027-01-10",
            FactType.DATE,
            "2027-01-10",
        ),
        (
            FactKey.WAGE_PAYMENT_PROBLEM,
            "Doanh nghiệp đang nợ lương.",
            "nợ lương",
            FactType.TEXT,
            "WAGE_PAYMENT_PROBLEM_REPORTED",
        ),
        (
            FactKey.WAGE_PAYMENT_DUE_DATE,
            "Hạn thanh toán lương là 2027-09-30.",
            "2027-09-30",
            FactType.DATE,
            "2027-09-30",
        ),
        (
            FactKey.WAGE_PAYMENT_STATUS,
            "Tiền lương bị trả chậm.",
            "trả chậm",
            FactType.TEXT,
            "trả chậm",
        ),
        (
            FactKey.WAGE_DELAY_FORCE_MAJEURE,
            "Hồ sơ xác nhận không có sự kiện bất khả kháng.",
            "không có sự kiện bất khả kháng",
            FactType.TEXT,
            "không có sự kiện bất khả kháng",
        ),
    ],
)
def test_compiler_has_positive_deterministic_behavior_for_all_17_keys(
    fact_key: FactKey,
    source_text: str,
    literal: str,
    fact_type: FactType,
    normalized_value: str | int,
) -> None:
    result = _compile(source_text, _proposal(fact_key, literal))

    assert result.rejections == ()
    assert len(result.admitted_facts) == 1
    fact = result.admitted_facts[0]
    assert fact.fact_key == fact_key.value
    assert fact.fact_type == fact_type.value
    assert fact.normalized_value == normalized_value
    assert fact.assertion_mode is AssertionMode.EXPLICIT
    assert fact.verification_status is VerificationStatus.UNVERIFIED
    assert fact.source_type is SourceType.USER_MESSAGE
    assert fact.source_ref == "user_message:fact-compiler"
    assert (
        source_text[fact.source_span.start_offset : fact.source_span.end_offset] == fact.raw_value
    )


def test_contract_type_start_and_end_are_compiled_as_three_atomic_facts() -> None:
    text = "Hợp đồng loại FIXED_TERM bắt đầu 2027-03-10 và kết thúc 2028-03-09."
    result = _compile(
        text,
        _proposal(FactKey.CONTRACT_TYPE, "Hợp đồng loại FIXED_TERM"),
        _proposal(FactKey.CONTRACT_START_DATE, "bắt đầu 2027-03-10"),
        _proposal(FactKey.CONTRACT_END_DATE, "kết thúc 2028-03-09"),
    )

    assert result.rejections == ()
    assert tuple(fact.fact_key for fact in result.admitted_facts) == (
        FactKey.CONTRACT_TYPE.value,
        FactKey.CONTRACT_START_DATE.value,
        FactKey.CONTRACT_END_DATE.value,
    )
    assert tuple(fact.raw_value for fact in result.admitted_facts) == (
        "FIXED_TERM",
        "2027-03-10",
        "2028-03-09",
    )


def test_wage_problem_amount_and_duration_do_not_create_a_summary_fact() -> None:
    text = "Doanh nghiệp nợ lương 5.900.000 đồng trong 2 tháng."
    result = _compile(
        text,
        _proposal(FactKey.WAGE_PAYMENT_PROBLEM, "nợ lương"),
        _proposal(FactKey.UNPAID_WAGES_AMOUNT, "5.900.000 đồng"),
        _proposal(FactKey.UNPAID_WAGES_DURATION, "2 tháng"),
    )

    assert result.rejections == ()
    assert tuple(fact.fact_key for fact in result.admitted_facts) == (
        FactKey.WAGE_PAYMENT_PROBLEM.value,
        FactKey.UNPAID_WAGES_AMOUNT.value,
        FactKey.UNPAID_WAGES_DURATION.value,
    )
    assert len(result.admitted_facts) == 3


def test_missing_or_ambiguous_source_literals_are_rejected() -> None:
    missing = _compile(
        "Hợp đồng có thời hạn 24 tháng.",
        _proposal(FactKey.CONTRACT_DURATION, "36 tháng"),
    )
    repeated = _compile(
        "Hợp đồng ghi 12 tháng, phụ lục cũng ghi 12 tháng.",
        _proposal(FactKey.CONTRACT_DURATION, "12 tháng"),
    )

    assert missing.rejections[0].reason_code.value == "SOURCE_LITERAL_NOT_FOUND"
    assert repeated.rejections[0].reason_code.value == "SOURCE_LITERAL_AMBIGUOUS"


def test_ambiguous_normalization_is_rejected_instead_of_guessed() -> None:
    text = "Hợp đồng có thời hạn từ 12 đến 24 tháng."
    result = _compile(
        text,
        _proposal(FactKey.CONTRACT_DURATION, "từ 12 đến 24 tháng"),
    )

    assert result.admitted_facts == ()
    assert result.rejections[0].reason_code.value == "ATOMIC_VALUE_AMBIGUOUS"


def test_semantically_wrong_key_is_rejected_even_when_value_shape_is_valid() -> None:
    text = "Doanh nghiệp nợ lương trong 24 tháng."
    result = _compile(text, _proposal(FactKey.CONTRACT_DURATION, "24 tháng"))

    assert result.admitted_facts == ()
    assert result.rejections[0].reason_code.value == "SEMANTIC_CONTEXT_UNSUPPORTED"


@pytest.mark.parametrize(
    ("fact_key", "source_text", "literal"),
    [
        (
            FactKey.INTENDED_TERMINATION_DATE,
            "Tôi dự kiến họp vào cuối quý tới.",
            "cuối quý tới",
        ),
        (
            FactKey.UNPAID_WAGES_AMOUNT,
            "Tổng số tiền là 7200000 đồng.",
            "7200000 đồng",
        ),
        (
            FactKey.EMPLOYEE_ROLE,
            "Tôi làm việc tại doanh nghiệp địa phương.",
            "tại doanh nghiệp địa phương",
        ),
        (
            FactKey.CONTRACT_EXPIRY_STATEMENT,
            "Thẻ ra vào của tôi sắp hết hạn.",
            "sắp hết hạn",
        ),
        (
            FactKey.UNPAID_WAGES_DURATION,
            "Tôi thiếu 2 tháng để hoàn thành dự án.",
            "2 tháng",
        ),
        (
            FactKey.WAGE_PAYMENT_STATUS,
            "Doanh nghiệp đang nợ lương.",
            "nợ lương",
        ),
    ],
)
def test_shape_and_generic_words_cannot_substitute_for_property_semantics(
    fact_key: FactKey, source_text: str, literal: str
) -> None:
    result = _compile(source_text, _proposal(fact_key, literal))

    assert result.admitted_facts == ()
    assert result.rejections[0].reason_code.value in {
        "ATOMIC_VALUE_NOT_FOUND",
        "NORMALIZATION_UNSAFE",
        "SEMANTIC_CONTEXT_UNSUPPORTED",
    }


@pytest.mark.parametrize(
    ("fact_key", "source_text", "literal", "normalized_value"),
    [
        (
            FactKey.INTENDED_TERMINATION_DATE,
            "Tôi dự kiến nghỉ vào cuối tuần kế tiếp.",
            "cuối tuần kế tiếp",
            "cuối tuần kế tiếp",
        ),
        (
            FactKey.CONTRACT_SIGNED_DATE,
            "Ngày ký văn bản lao động là 2027-04-22.",
            "2027-04-22",
            "2027-04-22",
        ),
        (
            FactKey.CONTRACT_DURATION,
            "Thời hạn được ghi: 9 tháng; cần kiểm tra điều khoản thời hạn.",
            "9 tháng",
            9,
        ),
        (
            FactKey.CONTRACT_START_DATE,
            "Hợp đồng kéo dài 12 tháng, bắt đầu 2026-09-15.",
            "2026-09-15",
            "2026-09-15",
        ),
        (
            FactKey.CONTRACT_END_DATE,
            "Hợp đồng kéo dài 12 tháng, kết thúc 2027-09-14.",
            "2027-09-14",
            "2027-09-14",
        ),
        (
            FactKey.UNPAID_WAGES_AMOUNT,
            ("Trong mục số tiền lương chưa trả của biểu mẫu, giá trị được ghi là 7.250.000 đồng."),
            "7.250.000 đồng",
            7_250_000,
        ),
        (
            FactKey.UNPAID_WAGES_AMOUNT,
            "Mục số tiền lương chưa trả trong bảng đối chiếu ghi 6.800.000 đồng.",
            "6.800.000 đồng",
            6_800_000,
        ),
        (
            FactKey.UNPAID_WAGES_AMOUNT,
            "Doanh nghiệp đang nợ lương; số tiền là 5.900.000 đồng.",
            "5.900.000 đồng",
            5_900_000,
        ),
        (
            FactKey.UNPAID_WAGES_AMOUNT,
            "Công ty chậm trả lương với số tiền 9100000 đồng.",
            "9100000",
            9_100_000,
        ),
        (
            FactKey.UNPAID_WAGES_DURATION,
            (
                "Tôi ghi nhận tiền lương bị thiếu trong 1 tháng, "
                "nhưng bảng chấm công thể hiện 2 tháng."
            ),
            "2 tháng",
            2,
        ),
    ],
)
def test_bounded_property_associations_admit_development_wording(
    fact_key: FactKey,
    source_text: str,
    literal: str,
    normalized_value: str | int,
) -> None:
    result = _compile(source_text, _proposal(fact_key, literal))

    assert result.rejections == ()
    assert result.admitted_facts[0].normalized_value == normalized_value


@pytest.mark.parametrize(
    ("fact_key", "source_text", "literal"),
    [
        (
            FactKey.UNPAID_WAGES_AMOUNT,
            "Doanh nghiệp đang nợ lương; số tiền dự án là 5.900.000 đồng.",
            "5.900.000 đồng",
        ),
        (
            FactKey.UNPAID_WAGES_DURATION,
            "Hợp đồng kéo dài 24 tháng, nhưng bảng chấm công thể hiện 2 tháng.",
            "2 tháng",
        ),
        (
            FactKey.INTENDED_TERMINATION_DATE,
            "Tôi dự kiến nghỉ việc vào đầu quý và họp vào cuối quý.",
            "cuối quý",
        ),
    ],
)
def test_neighboring_unrelated_property_does_not_authorize_a_fact(
    fact_key: FactKey, source_text: str, literal: str
) -> None:
    result = _compile(source_text, _proposal(fact_key, literal))

    assert result.admitted_facts == ()
    assert result.rejections[0].reason_code.value == "SEMANTIC_CONTEXT_UNSUPPORTED"


@pytest.mark.parametrize(
    "fact_key",
    [FactKey.WAGE_PAYMENT_PROBLEM, FactKey.WAGE_PAYMENT_STATUS],
)
def test_form_field_label_is_not_an_asserted_wage_problem_or_status(
    fact_key: FactKey,
) -> None:
    text = "Trong mục số tiền lương chưa trả của biểu mẫu, giá trị được ghi là 7.250.000 đồng."
    result = _compile(text, _proposal(fact_key, "lương chưa trả"))

    assert result.admitted_facts == ()
    assert result.rejections[0].reason_code.value == "SEMANTIC_CONTEXT_UNSUPPORTED"


@pytest.mark.parametrize(
    ("fact_key", "source_text", "literal"),
    [
        (
            FactKey.WAGE_PAYMENT_PROBLEM,
            "Doanh nghiệp không nợ lương.",
            "không nợ lương",
        ),
        (
            FactKey.WAGE_PAYMENT_STATUS,
            "Tiền lương không bị trả chậm.",
            "không bị trả chậm",
        ),
        (
            FactKey.INTENDED_TERMINATION_DATE,
            "Tôi không muốn nghỉ việc vào cuối quý tới.",
            "không muốn nghỉ việc vào cuối quý tới",
        ),
        (
            FactKey.CONTRACT_EXPIRY_STATEMENT,
            "Hợp đồng này chưa hết hạn.",
            "chưa hết hạn",
        ),
        (
            FactKey.WAGE_PAYMENT_PROBLEM,
            "Doanh nghiệp không chậm trả lương.",
            "không chậm trả lương",
        ),
        (
            FactKey.WAGE_PAYMENT_STATUS,
            "Doanh nghiệp không trả chậm lương.",
            "không trả chậm lương",
        ),
        (
            FactKey.INTENDED_TERMINATION_DATE,
            "Tôi sẽ không nghỉ việc vào cuối quý tới.",
            "sẽ không nghỉ việc vào cuối quý tới",
        ),
        (
            FactKey.CONTRACT_SIGNED_DATE,
            "Hợp đồng không được ký ngày 2027-04-22.",
            "không được ký ngày 2027-04-22",
        ),
        (
            FactKey.CONTRACT_DURATION,
            "Hợp đồng không kéo dài 24 tháng.",
            "không kéo dài 24 tháng",
        ),
        (
            FactKey.CONTRACT_START_DATE,
            "Hợp đồng không bắt đầu ngày 2027-03-10.",
            "không bắt đầu ngày 2027-03-10",
        ),
        (
            FactKey.CONTRACT_END_DATE,
            "Hợp đồng không kết thúc ngày 2028-03-09.",
            "không kết thúc ngày 2028-03-09",
        ),
        (
            FactKey.EVENT_TIME,
            "Sự việc không xảy ra vào cuối tuần trước.",
            "không xảy ra vào cuối tuần trước",
        ),
        (
            FactKey.WAGE_PAYMENT_DUE_DATE,
            "Tiền lương không đến hạn ngày 2027-09-30.",
            "không đến hạn ngày 2027-09-30",
        ),
        (
            FactKey.EMPLOYEE_ROLE,
            "Vai trò của tôi không còn là giám sát viên.",
            "không còn là giám sát viên",
        ),
        (
            FactKey.UNPAID_WAGES_DURATION,
            "Doanh nghiệp không nợ lương trong 2 tháng.",
            "không nợ lương trong 2 tháng",
        ),
    ],
)
def test_property_specific_negation_never_becomes_a_positive_fact(
    fact_key: FactKey, source_text: str, literal: str
) -> None:
    result = _compile(source_text, _proposal(fact_key, literal))

    assert result.admitted_facts == ()
    assert result.rejections[0].reason_code.value == "EVIDENCE_NEGATED"


def test_supported_force_majeure_absence_preserves_its_negative_literal() -> None:
    literal = "không do sự kiện bất khả kháng"
    result = _compile(
        f"Việc chậm trả lương {literal}.",
        _proposal(FactKey.WAGE_DELAY_FORCE_MAJEURE, literal),
    )

    assert result.rejections == ()
    assert result.admitted_facts[0].raw_value == literal
    assert result.admitted_facts[0].normalized_value == literal


@pytest.mark.parametrize(
    ("fact_key", "source_text", "literal"),
    [
        (
            FactKey.CONTRACT_DURATION,
            "Thời hạn dự án là 24 tháng.",
            "24 tháng",
        ),
        (
            FactKey.CONTRACT_SIGNED_DATE,
            "Biên bản được ký ngày 2027-04-22.",
            "2027-04-22",
        ),
        (
            FactKey.CONTRACT_START_DATE,
            "Dự án bắt đầu ngày 2027-03-10.",
            "2027-03-10",
        ),
        (
            FactKey.CONTRACT_END_DATE,
            "Dự án kết thúc ngày 2028-03-09.",
            "2028-03-09",
        ),
    ],
)
def test_contract_keys_require_explicit_contract_context(
    fact_key: FactKey, source_text: str, literal: str
) -> None:
    result = _compile(source_text, _proposal(fact_key, literal))

    assert result.admitted_facts == ()
    assert result.rejections[0].reason_code.value == "SEMANTIC_CONTEXT_UNSUPPORTED"


def test_broad_role_proposal_is_narrowed_before_a_neighboring_contract_property() -> None:
    source_text = "Vai trò của tôi là kỹ sư và hợp đồng có thời hạn 24 tháng."
    literal = "Vai trò của tôi là kỹ sư và hợp đồng có thời hạn 24 tháng"
    result = _compile(
        source_text,
        _proposal(FactKey.EMPLOYEE_ROLE, literal),
    )

    assert result.rejections == ()
    assert result.admitted_facts[0].raw_value == "kỹ sư"
    assert result.admitted_facts[0].normalized_value == "kỹ sư"

    value_only_result = _compile(
        source_text,
        _proposal(
            FactKey.EMPLOYEE_ROLE,
            "kỹ sư và hợp đồng có thời hạn 24 tháng",
        ),
    )
    assert value_only_result.rejections == ()
    assert value_only_result.admitted_facts[0].raw_value == "kỹ sư"


@pytest.mark.parametrize(
    "neighboring_property",
    [
        "dự kiến nghỉ việc vào cuối quý tới",
        "ngày dự kiến nghỉ việc là 2027-10-18",
    ],
)
def test_broad_role_proposal_is_narrowed_before_a_neighboring_termination_property(
    neighboring_property: str,
) -> None:
    literal = f"Vai trò của tôi là kỹ sư và {neighboring_property}"
    result = _compile(
        f"{literal}.",
        _proposal(FactKey.EMPLOYEE_ROLE, literal),
    )

    assert result.rejections == ()
    assert result.admitted_facts[0].raw_value == "kỹ sư"
    assert result.admitted_facts[0].normalized_value == "kỹ sư"


def test_generic_recorded_project_duration_does_not_use_contract_oracle_exception() -> None:
    text = "Thời hạn được ghi: 9 tháng; đây là tiến độ dự án."
    result = _compile(text, _proposal(FactKey.CONTRACT_DURATION, "9 tháng"))

    assert result.admitted_facts == ()
    assert result.rejections[0].reason_code.value == "SEMANTIC_CONTEXT_UNSUPPORTED"


def test_contract_duration_oracle_exception_is_tied_to_its_own_value_span() -> None:
    text = (
        "Thời hạn được ghi: 9 tháng; cần kiểm tra điều khoản thời hạn. Tiến độ dự án là 12 tháng."
    )
    result = _compile(text, _proposal(FactKey.CONTRACT_DURATION, "12 tháng"))

    assert result.admitted_facts == ()
    assert result.rejections[0].reason_code.value == "SEMANTIC_CONTEXT_UNSUPPORTED"


@pytest.mark.parametrize(
    ("fact_key", "source_text", "literal"),
    [
        (
            FactKey.UNPAID_WAGES_AMOUNT,
            "Doanh nghiệp không nợ lương; số tiền là 5.900.000 đồng.",
            "5.900.000 đồng",
        ),
        (
            FactKey.UNPAID_WAGES_DURATION,
            "Doanh nghiệp không nợ lương 1 tháng, nhưng bảng chấm công thể hiện 2 tháng.",
            "2 tháng",
        ),
        (
            FactKey.CONTRACT_START_DATE,
            "Không có hợp đồng và bắt đầu ngày 2027-03-10.",
            "2027-03-10",
        ),
        (
            FactKey.CONTRACT_SIGNED_DATE,
            "Không có hợp đồng và được ký ngày 2027-03-10.",
            "2027-03-10",
        ),
        (
            FactKey.CONTRACT_DURATION,
            "Thời hạn được ghi: 9 tháng; đây không phải điều khoản thời hạn hợp đồng.",
            "9 tháng",
        ),
    ],
)
def test_non_present_semantic_support_cannot_authorize_a_positive_fact(
    fact_key: FactKey, source_text: str, literal: str
) -> None:
    result = _compile(source_text, _proposal(fact_key, literal))

    assert result.admitted_facts == ()
    assert result.rejections[0].reason_code.value == "EVIDENCE_NEGATED"


@pytest.mark.parametrize(
    ("fact_key", "source_text", "literal"),
    [
        (
            FactKey.CONTRACT_TYPE,
            "Chưa chắc hợp đồng không xác định thời hạn.",
            "hợp đồng không xác định thời hạn",
        ),
        (
            FactKey.WAGE_DELAY_FORCE_MAJEURE,
            "Chưa chắc việc chậm trả không do sự kiện bất khả kháng.",
            "không do sự kiện bất khả kháng",
        ),
        (
            FactKey.CONTRACT_TYPE,
            "Không chắc hợp đồng không xác định thời hạn.",
            "hợp đồng không xác định thời hạn",
        ),
        (
            FactKey.WAGE_DELAY_FORCE_MAJEURE,
            "Không chắc việc chậm trả không do sự kiện bất khả kháng.",
            "không do sự kiện bất khả kháng",
        ),
    ],
)
def test_uncertain_canonical_negative_values_are_rejected(
    fact_key: FactKey, source_text: str, literal: str
) -> None:
    result = _compile(source_text, _proposal(fact_key, literal))

    assert result.admitted_facts == ()
    assert result.rejections[0].reason_code.value == "EVIDENCE_UNKNOWN"


@pytest.mark.parametrize(
    ("fact_key", "source_text", "literal"),
    [
        (
            FactKey.CONTRACT_TYPE,
            "Không đúng là hợp đồng không xác định thời hạn.",
            "hợp đồng không xác định thời hạn",
        ),
        (
            FactKey.WAGE_DELAY_FORCE_MAJEURE,
            "Không đúng là việc chậm trả không do sự kiện bất khả kháng.",
            "không do sự kiện bất khả kháng",
        ),
    ],
)
def test_outer_negation_rejects_an_embedded_canonical_negative_value(
    fact_key: FactKey, source_text: str, literal: str
) -> None:
    result = _compile(source_text, _proposal(fact_key, literal))

    assert result.admitted_facts == ()
    assert result.rejections[0].reason_code.value == "EVIDENCE_NEGATED"


def test_role_is_narrowed_before_a_bare_termination_clause() -> None:
    literal = "Vai trò của tôi là kỹ sư và nghỉ việc vào cuối quý tới"
    result = _compile(
        f"{literal}.",
        _proposal(FactKey.EMPLOYEE_ROLE, literal),
    )

    assert result.rejections == ()
    assert result.admitted_facts[0].raw_value == "kỹ sư"
    assert result.admitted_facts[0].normalized_value == "kỹ sư"


def test_empty_role_before_neighboring_property_is_rejected() -> None:
    literal = "Vai trò của tôi là và hợp đồng có thời hạn 24 tháng"
    result = _compile(
        f"{literal}.",
        _proposal(FactKey.EMPLOYEE_ROLE, literal),
    )

    assert result.admitted_facts == ()
    assert result.rejections[0].reason_code.value == "NORMALIZATION_UNSAFE"


def test_postposed_uncertainty_qualifier_rejects_the_preceding_value() -> None:
    text = "Ngày dự kiến nghỉ việc là cuối quý tới, nhưng chưa chắc."
    result = _compile(
        text,
        _proposal(FactKey.INTENDED_TERMINATION_DATE, "cuối quý tới"),
    )

    assert result.admitted_facts == ()
    assert result.rejections[0].reason_code.value == "EVIDENCE_UNKNOWN"


@pytest.mark.parametrize(
    "literal",
    [
        "7200000 đồng",
        "7200000 đồng, nhưng chưa chắc",
        "Tiền lương chưa trả là 7200000 đồng, nhưng chưa chắc",
    ],
)
def test_money_unit_cannot_hide_a_postposed_uncertainty_qualifier(literal: str) -> None:
    text = "Tiền lương chưa trả là 7200000 đồng, nhưng chưa chắc."
    result = _compile(
        text,
        _proposal(FactKey.UNPAID_WAGES_AMOUNT, literal),
    )

    assert result.admitted_facts == ()
    assert result.rejections[0].reason_code.value == "EVIDENCE_UNKNOWN"


@pytest.mark.parametrize(
    "neighboring_property",
    [
        "sẽ rời công việc vào cuối quý tới",
        "sẽ kết thúc công việc vào cuối quý tới",
        "trường hợp đặc biệt là NONE",
    ],
)
def test_role_is_narrowed_before_all_supported_neighbor_property_vocabularies(
    neighboring_property: str,
) -> None:
    literal = f"Vai trò của tôi là kỹ sư và {neighboring_property}"
    result = _compile(
        f"{literal}.",
        _proposal(FactKey.EMPLOYEE_ROLE, literal),
    )

    assert result.rejections == ()
    assert result.admitted_facts[0].raw_value == "kỹ sư"
    assert result.admitted_facts[0].normalized_value == "kỹ sư"


@pytest.mark.parametrize(
    "neighboring_property",
    [
        "thời điểm sự việc là cuối tuần trước",
        "ngày tham chiếu là 2027-01-10",
        "ngày đến hạn lương là 2027-09-30",
        "FIXED_TERM",
        "WORK_OR_LOCATION_NOT_AS_AGREED",
        "MISTREATMENT_OR_FORCED_LABOR",
        "sắp hết hạn",
    ],
)
def test_role_uses_complete_policy_owned_neighbor_property_starts(
    neighboring_property: str,
) -> None:
    literal = f"Vai trò của tôi là kỹ sư và {neighboring_property}"
    result = _compile(
        f"{literal}.",
        _proposal(FactKey.EMPLOYEE_ROLE, literal),
    )

    assert result.rejections == ()
    assert result.admitted_facts[0].raw_value == "kỹ sư"
    assert result.admitted_facts[0].normalized_value == "kỹ sư"


@pytest.mark.parametrize("separator", ["nhưng", "đồng thời"])
def test_role_uses_the_same_atomic_property_separators_as_the_compiler(separator: str) -> None:
    literal = f"Vai trò của tôi là kỹ sư {separator} hợp đồng xác định thời hạn"
    result = _compile(
        f"{literal}.",
        _proposal(FactKey.EMPLOYEE_ROLE, literal),
    )

    assert result.rejections == ()
    assert result.admitted_facts[0].raw_value == "kỹ sư"
    assert result.admitted_facts[0].normalized_value == "kỹ sư"


@pytest.mark.parametrize(
    "literal",
    [
        "7 triệu đồng",
        "200 nghìn đồng",
        "7tr",
        "7 USD",
        "7 tháng",
    ],
)
def test_money_normalization_rejects_unsupported_magnitude_currency_or_unit(
    literal: str,
) -> None:
    result = _compile(
        f"Tiền lương chưa trả là {literal}.",
        _proposal(FactKey.UNPAID_WAGES_AMOUNT, literal),
    )

    assert result.admitted_facts == ()
    assert result.rejections[0].reason_code.value == "ATOMIC_VALUE_NOT_FOUND"


@pytest.mark.parametrize("separator", ["nhưng", "đồng thời"])
def test_empty_role_starting_with_any_property_separator_is_rejected(separator: str) -> None:
    literal = f"Vai trò của tôi là {separator} hợp đồng xác định thời hạn"
    result = _compile(
        f"{literal}.",
        _proposal(FactKey.EMPLOYEE_ROLE, literal),
    )

    assert result.admitted_facts == ()
    assert result.rejections[0].reason_code.value == "NORMALIZATION_UNSAFE"


@pytest.mark.parametrize(
    ("fact_key", "source_text", "literal"),
    [
        (
            FactKey.CONTRACT_TYPE,
            "Loại hợp đồng: NOT_FIXED_TERM_TEST.",
            "NOT_FIXED_TERM_TEST",
        ),
        (
            FactKey.NOTICE_SPECIAL_CASE,
            "Trường hợp đặc biệt: NOT_WORK_OR_LOCATION_NOT_AS_AGREED_X.",
            "NOT_WORK_OR_LOCATION_NOT_AS_AGREED_X",
        ),
        (
            FactKey.CONTRACT_SIGNED_DATE,
            "Hợp đồng ký theo mã ABC2026-09-05XYZ.",
            "ABC2026-09-05XYZ",
        ),
        (
            FactKey.CONTRACT_DURATION,
            "Hợp đồng có thời hạn A24 tháng.",
            "A24 tháng",
        ),
    ],
)
def test_strict_families_reject_embedded_canonical_substrings(
    fact_key: FactKey, source_text: str, literal: str
) -> None:
    result = _compile(source_text, _proposal(fact_key, literal))

    assert result.admitted_facts == ()


@pytest.mark.parametrize(
    ("fact_key", "source_text", "literal"),
    [
        (
            FactKey.CONTRACT_TYPE,
            "Loại hợp đồng: NOT_FIXED_TERM_TEST.",
            "FIXED_TERM",
        ),
        (
            FactKey.NOTICE_SPECIAL_CASE,
            "Trường hợp đặc biệt: NOT_WORK_OR_LOCATION_NOT_AS_AGREED_X.",
            "WORK_OR_LOCATION_NOT_AS_AGREED",
        ),
        (
            FactKey.CONTRACT_SIGNED_DATE,
            "Hợp đồng ký theo mã ABC2026-09-05XYZ.",
            "2026-09-05",
        ),
        (
            FactKey.CONTRACT_DURATION,
            "Hợp đồng có thời hạn A24 tháng.",
            "24 tháng",
        ),
    ],
)
def test_source_token_boundaries_reject_a_maliciously_narrowed_proposal(
    fact_key: FactKey, source_text: str, literal: str
) -> None:
    result = _compile(source_text, _proposal(fact_key, literal))

    assert result.admitted_facts == ()
    assert result.rejections[0].reason_code.value == "NORMALIZATION_UNSAFE"


@pytest.mark.parametrize(
    "literal",
    ["7 GBP", "7 AUD", "7 giờ", "ABC7", "7abc", "7 vạn đồng"],
)
def test_money_rejects_every_non_terminated_or_embedded_numeric_substring(literal: str) -> None:
    result = _compile(
        f"Tiền lương chưa trả là {literal}.",
        _proposal(FactKey.UNPAID_WAGES_AMOUNT, literal),
    )

    assert result.admitted_facts == ()


def test_source_unit_boundary_rejects_a_money_proposal_narrowed_to_one_digit() -> None:
    result = _compile(
        "Tiền lương chưa trả là 7 GBP.",
        _proposal(FactKey.UNPAID_WAGES_AMOUNT, "7"),
    )

    assert result.admitted_facts == ()
    assert result.rejections[0].reason_code.value == "NORMALIZATION_UNSAFE"


@pytest.mark.parametrize("currency", ["gbp", "usd", "eur", "aud"])
def test_lowercase_unsupported_currency_prefix_is_rejected(currency: str) -> None:
    literal = f"{currency} 7"
    result = _compile(
        f"Tiền lương chưa trả là {literal}.",
        _proposal(FactKey.UNPAID_WAGES_AMOUNT, literal),
    )

    assert result.admitted_facts == ()


@pytest.mark.parametrize(
    ("source_text", "literal"),
    [
        ("Tiền lương chưa trả là 7,000 GBP.", "7,000 GBP"),
        ("Tiền lương chưa trả là 7,000 GBP.", "7"),
        ("Tiền lương chưa trả là 7,5 triệu đồng.", "7"),
        ("Tiền lương chưa trả là 7.5 triệu đồng.", "7"),
    ],
)
def test_numeric_punctuation_cannot_terminate_a_partial_money_value(
    source_text: str, literal: str
) -> None:
    result = _compile(
        source_text,
        _proposal(FactKey.UNPAID_WAGES_AMOUNT, literal),
    )

    assert result.admitted_facts == ()


@pytest.mark.parametrize(
    ("fact_key", "source_text", "literal"),
    [
        (
            FactKey.CONTRACT_DURATION,
            "Hợp đồng có thời hạn khoảng 24 tháng.",
            "24 tháng",
        ),
        (
            FactKey.CONTRACT_DURATION,
            "Hợp đồng có thời hạn từ 12 đến 24 tháng.",
            "24 tháng",
        ),
        (
            FactKey.CONTRACT_DURATION,
            "Hợp đồng có thời hạn 24 tháng đến 36 tháng.",
            "24 tháng",
        ),
        (
            FactKey.UNPAID_WAGES_AMOUNT,
            "Tiền lương chưa trả khoảng 7200000 đồng.",
            "7200000 đồng",
        ),
        (
            FactKey.UNPAID_WAGES_AMOUNT,
            "Tiền lương chưa trả trên 7200000 đồng.",
            "7200000",
        ),
    ],
)
def test_minimal_proposal_cannot_bypass_source_approximation_or_range(
    fact_key: FactKey, source_text: str, literal: str
) -> None:
    result = _compile(source_text, _proposal(fact_key, literal))

    assert result.admitted_facts == ()
    assert result.rejections[0].reason_code.value == "NORMALIZATION_UNSAFE"


@pytest.mark.parametrize(
    ("source_text", "literal"),
    [
        ("Hợp đồng có thời hạn 12–24 tháng.", "24 tháng"),
        ("Hợp đồng có thời hạn từ 12 tháng đến 2 năm.", "12 tháng"),
        ("Hợp đồng có thời hạn 12 hoặc 24 tháng.", "24 tháng"),
    ],
)
def test_minimal_duration_proposal_cannot_bypass_alternative_source_values(
    source_text: str, literal: str
) -> None:
    result = _compile(
        source_text,
        _proposal(FactKey.CONTRACT_DURATION, literal),
    )

    assert result.admitted_facts == ()
    assert result.rejections[0].reason_code.value == "NORMALIZATION_UNSAFE"


@pytest.mark.parametrize(
    "source_text",
    [
        "Ngày dự kiến nghỉ việc là 2027-10-18 hoặc cuối quý tới.",
        "Ngày dự kiến nghỉ việc là khoảng 2027-10-18.",
    ],
)
def test_minimal_termination_date_cannot_bypass_ambiguous_source_expression(
    source_text: str,
) -> None:
    result = _compile(
        source_text,
        _proposal(FactKey.INTENDED_TERMINATION_DATE, "2027-10-18"),
    )

    assert result.admitted_facts == ()
    assert result.rejections[0].reason_code.value == "NORMALIZATION_UNSAFE"


@pytest.mark.parametrize(
    ("fact_key", "source_text", "literal"),
    [
        (
            FactKey.INTENDED_TERMINATION_DATE,
            "Ngày dự kiến nghỉ việc là sau 2027-10-18.",
            "2027-10-18",
        ),
        (
            FactKey.INTENDED_TERMINATION_DATE,
            "Tôi dự kiến nghỉ việc trước ngày 2027-10-18.",
            "2027-10-18",
        ),
        (
            FactKey.CONTRACT_END_DATE,
            "Hợp đồng kết thúc trước ngày 2027-12-31.",
            "2027-12-31",
        ),
        (
            FactKey.CONTRACT_START_DATE,
            "Hợp đồng bắt đầu sau ngày 2027-01-01.",
            "2027-01-01",
        ),
        (
            FactKey.WAGE_PAYMENT_DUE_DATE,
            "Lương đến hạn trước ngày 2027-09-30.",
            "2027-09-30",
        ),
    ],
)
def test_exact_date_policy_rejects_relational_source_bounds(
    fact_key: FactKey, source_text: str, literal: str
) -> None:
    result = _compile(source_text, _proposal(fact_key, literal))

    assert result.admitted_facts == ()
    assert result.rejections[0].reason_code.value == "NORMALIZATION_UNSAFE"


@pytest.mark.parametrize(
    ("fact_key", "source_text", "literal"),
    [
        (
            FactKey.CONTRACT_START_DATE,
            "Hợp đồng có hiệu lực từ 2027-01-01.",
            "2027-01-01",
        ),
        (
            FactKey.CONTRACT_START_DATE,
            "Hợp đồng bắt đầu từ ngày 2027-01-01.",
            "2027-01-01",
        ),
        (
            FactKey.CONTRACT_END_DATE,
            "Hợp đồng có hiệu lực đến ngày 2027-12-31.",
            "2027-12-31",
        ),
        (
            FactKey.INTENDED_TERMINATION_REFERENCE_DATE,
            "Ngày tham chiếu tính từ ngày 2027-01-01.",
            "2027-01-01",
        ),
    ],
)
def test_exact_date_policy_accepts_canonical_from_and_until_anchors(
    fact_key: FactKey, source_text: str, literal: str
) -> None:
    result = _compile(source_text, _proposal(fact_key, literal))

    assert result.rejections == ()
    assert result.admitted_facts[0].normalized_value == literal


@pytest.mark.parametrize("alternative", ["hoặc", "hay"])
def test_employee_role_alternatives_are_rejected_as_ambiguous(alternative: str) -> None:
    literal = f"Vai trò của tôi là kỹ sư {alternative} giám sát viên"
    result = _compile(
        f"{literal}.",
        _proposal(FactKey.EMPLOYEE_ROLE, literal),
    )

    assert result.admitted_facts == ()
    assert result.rejections[0].reason_code.value == "NORMALIZATION_UNSAFE"


@pytest.mark.parametrize("alternative", ["hoặc", "hay"])
def test_employee_role_cannot_start_with_an_alternative_separator(alternative: str) -> None:
    literal = f"Vai trò của tôi là {alternative} kỹ sư"
    result = _compile(
        f"{literal}.",
        _proposal(FactKey.EMPLOYEE_ROLE, literal),
    )

    assert result.admitted_facts == ()
    assert result.rejections[0].reason_code.value == "NORMALIZATION_UNSAFE"


@pytest.mark.parametrize("alternative", ["hoặc", "hay"])
def test_closed_text_alternatives_cannot_be_narrowed_to_one_value(
    alternative: str,
) -> None:
    source_text = f"Loại hợp đồng là FIXED_TERM {alternative} INDEFINITE."
    result = _compile(
        source_text,
        _proposal(FactKey.CONTRACT_TYPE, "FIXED_TERM"),
    )

    assert result.admitted_facts == ()
    assert result.rejections[0].reason_code.value == "NORMALIZATION_UNSAFE"


def test_none_is_not_reused_as_an_employee_role_absence_value() -> None:
    result = _compile(
        "Vai trò của người lao động được ghi là NONE.",
        _proposal(FactKey.EMPLOYEE_ROLE, "NONE"),
    )

    assert result.admitted_facts == ()
    assert result.rejections[0].reason_code.value == "NORMALIZATION_UNSAFE"


def test_exact_duplicate_is_deduplicated_but_explicit_conflicts_are_preserved() -> None:
    text = "Một bản ghi nêu nợ lương 2 tháng, bản khác nêu 3 tháng."
    two_months = _proposal(FactKey.UNPAID_WAGES_DURATION, "2 tháng")
    result = _compile(
        text,
        two_months,
        two_months,
        _proposal(FactKey.UNPAID_WAGES_DURATION, "3 tháng"),
    )

    assert tuple(fact.normalized_value for fact in result.admitted_facts) == (2, 3)
    assert tuple(rejection.reason_code.value for rejection in result.rejections) == (
        "DUPLICATE_PROPOSAL",
    )


def test_fact_id_and_offsets_are_stable_application_owned_values() -> None:
    source = _source("Hợp đồng có thời hạn 24 tháng.", "user_message:stable")
    proposal = _proposal(FactKey.CONTRACT_DURATION, "Hợp đồng có thời hạn 24 tháng")

    first = compile_fact_proposals(source, (proposal,)).admitted_facts[0]
    second = compile_fact_proposals(source, (proposal,)).admitted_facts[0]

    assert first == second
    assert first.fact_id.startswith("CF-")
    assert first.raw_value == "24 tháng"
    assert first.source_span.start_offset == source.source_text.index("24 tháng")


def test_compiler_layer_has_no_provider_or_downstream_reasoning_dependency() -> None:
    prohibited = (
        "openai",
        "vietnamese_labor_law_assistant.agent",
        "vietnamese_labor_law_assistant.api",
        "vietnamese_labor_law_assistant.calculator",
        "vietnamese_labor_law_assistant.mcp_",
        "vietnamese_labor_law_assistant.retrieval",
    )

    for module_name in (
        "fact_compiler",
        "fact_evidence",
        "fact_normalization",
        "fact_policies",
    ):
        module = import_module(f"vietnamese_labor_law_assistant.decision_support.{module_name}")
        tree = ast.parse(inspect.getsource(module))
        imported_modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        imported_modules.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        assert not any(dependency.startswith(prohibited) for dependency in imported_modules)
