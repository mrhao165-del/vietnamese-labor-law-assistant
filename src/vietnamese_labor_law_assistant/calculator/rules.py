"""Immutable source-backed rule registry; selection contains no legal text inference."""

from __future__ import annotations

from dataclasses import dataclass

from .enums import (
    ContractDurationType,
    ContractType,
    DurationUnit,
    EmployeeRole,
    NoticeSpecialCase,
    RuleSupportStatus,
)
from .errors import InvalidInputCombinationError, RuleNotFoundError
from .models import LegalBasis, NoticePeriodInput

SOURCE_CHUNK_ARTICLE_20 = "ll_d0c5f537983c0aad635529f412e426f5"
SOURCE_CHUNK_ARTICLE_35_NOTICE = "ll_6af59ba448952c1c927978713d34d984"
SOURCE_CHUNK_ARTICLE_35_NO_NOTICE = "ll_610e9077fc973dabc980978eb3f3da54"
SOURCE_SNAPSHOT_DATE = "2026-07-10"

STANDARD_NOTICE_WARNING = (
    "Kết quả chỉ áp dụng cho người lao động đơn phương chấm dứt hợp đồng trong phạm vi "
    "source snapshot hiện có và không thay thế tư vấn pháp lý chuyên nghiệp."
)
WORKING_DAY_WARNING = (
    "03 ngày làm việc không được quy đổi sang ngày lịch và tool không tính ngày làm việc cuối "
    "do không có lịch nghỉ lễ trong phạm vi Week 8; kết quả không thay thế tư vấn pháp lý "
    "chuyên nghiệp."
)
EXTERNAL_REGULATION_WARNING = (
    "Thời hạn đối với ngành, nghề hoặc công việc đặc thù cần quy định của Chính phủ ngoài corpus; "
    "tool không suy đoán số ngày và không thay thế tư vấn pháp lý chuyên nghiệp."
)


def _basis(article: int, clause: int, point: str, source_chunk_id: str) -> LegalBasis:
    return LegalBasis(
        document_id="labor_law",
        document_name="labor_law",
        article=article,
        clause=clause,
        point=point,
        source_chunk_id=source_chunk_id,
        source_label="labor_law.docx",
        source_snapshot_date=SOURCE_SNAPSHOT_DATE,
    )


@dataclass(frozen=True)
class NoticeRule:
    rule_id: str
    contract_type: ContractType | None
    special_case: NoticeSpecialCase
    employee_role: EmployeeRole
    notice_required: bool
    notice_days: int | None
    unit: DurationUnit
    support_status: RuleSupportStatus
    legal_basis: tuple[LegalBasis, ...]
    warning: str
    assumptions: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContractDurationRule:
    rule_id: str
    contract_type: ContractDurationType
    maximum_allowed_months: int | None
    legal_basis: tuple[LegalBasis, ...]


NOTICE_RULES: tuple[NoticeRule, ...] = (
    NoticeRule(
        "NOTICE_ART35_1_A_INDEFINITE",
        ContractType.INDEFINITE,
        NoticeSpecialCase.NONE,
        EmployeeRole.STANDARD,
        True,
        45,
        DurationUnit.CALENDAR_DAYS,
        RuleSupportStatus.SUPPORTED,
        (_basis(35, 1, "a", SOURCE_CHUNK_ARTICLE_35_NOTICE),),
        STANDARD_NOTICE_WARNING,
    ),
    NoticeRule(
        "NOTICE_ART35_1_B_FIXED_12_TO_36",
        ContractType.FIXED_TERM_12_TO_36_MONTHS,
        NoticeSpecialCase.NONE,
        EmployeeRole.STANDARD,
        True,
        30,
        DurationUnit.CALENDAR_DAYS,
        RuleSupportStatus.SUPPORTED,
        (_basis(35, 1, "b", SOURCE_CHUNK_ARTICLE_35_NOTICE),),
        STANDARD_NOTICE_WARNING,
    ),
    NoticeRule(
        "NOTICE_ART35_1_C_FIXED_UNDER_12",
        ContractType.FIXED_TERM_UNDER_12_MONTHS,
        NoticeSpecialCase.NONE,
        EmployeeRole.STANDARD,
        True,
        3,
        DurationUnit.WORKING_DAYS,
        RuleSupportStatus.SUPPORTED,
        (_basis(35, 1, "c", SOURCE_CHUNK_ARTICLE_35_NOTICE),),
        WORKING_DAY_WARNING,
    ),
    NoticeRule(
        "NOTICE_ART35_1_D_SPECIAL_OCCUPATION_EXTERNAL",
        None,
        NoticeSpecialCase.SPECIAL_OCCUPATION_EXTERNAL_REGULATION,
        EmployeeRole.SPECIAL_OCCUPATION,
        True,
        None,
        DurationUnit.CALENDAR_DAYS,
        RuleSupportStatus.EXTERNAL_REGULATION_REQUIRED,
        (_basis(35, 1, "d", SOURCE_CHUNK_ARTICLE_35_NOTICE),),
        EXTERNAL_REGULATION_WARNING,
        ("Cần đối chiếu quy định của Chính phủ không có trong corpus hiện tại.",),
    ),
    NoticeRule(
        "NOTICE_ART35_2_A_NO_AGREED_WORK",
        None,
        NoticeSpecialCase.WORK_OR_LOCATION_NOT_AS_AGREED,
        EmployeeRole.STANDARD,
        False,
        0,
        DurationUnit.NO_NOTICE,
        RuleSupportStatus.SUPPORTED,
        (_basis(35, 2, "a", SOURCE_CHUNK_ARTICLE_35_NO_NOTICE),),
        STANDARD_NOTICE_WARNING,
    ),
    NoticeRule(
        "NOTICE_ART35_2_B_UNPAID_OR_LATE_WAGES",
        None,
        NoticeSpecialCase.UNPAID_OR_LATE_WAGES,
        EmployeeRole.STANDARD,
        False,
        0,
        DurationUnit.NO_NOTICE,
        RuleSupportStatus.SUPPORTED,
        (_basis(35, 2, "b", SOURCE_CHUNK_ARTICLE_35_NO_NOTICE),),
        STANDARD_NOTICE_WARNING,
    ),
    NoticeRule(
        "NOTICE_ART35_2_C_MISTREATMENT_OR_FORCED_LABOR",
        None,
        NoticeSpecialCase.MISTREATMENT_OR_FORCED_LABOR,
        EmployeeRole.STANDARD,
        False,
        0,
        DurationUnit.NO_NOTICE,
        RuleSupportStatus.SUPPORTED,
        (_basis(35, 2, "c", SOURCE_CHUNK_ARTICLE_35_NO_NOTICE),),
        STANDARD_NOTICE_WARNING,
    ),
    NoticeRule(
        "NOTICE_ART35_2_D_WORKPLACE_SEXUAL_HARASSMENT",
        None,
        NoticeSpecialCase.WORKPLACE_SEXUAL_HARASSMENT,
        EmployeeRole.STANDARD,
        False,
        0,
        DurationUnit.NO_NOTICE,
        RuleSupportStatus.SUPPORTED,
        (_basis(35, 2, "d", SOURCE_CHUNK_ARTICLE_35_NO_NOTICE),),
        STANDARD_NOTICE_WARNING,
    ),
    NoticeRule(
        "NOTICE_ART35_2_DD_PREGNANT_MEDICAL",
        None,
        NoticeSpecialCase.PREGNANT_WORKER_MEDICAL_CERTIFICATION,
        EmployeeRole.STANDARD,
        False,
        0,
        DurationUnit.NO_NOTICE,
        RuleSupportStatus.SUPPORTED,
        (_basis(35, 2, "đ", SOURCE_CHUNK_ARTICLE_35_NO_NOTICE),),
        STANDARD_NOTICE_WARNING,
    ),
    NoticeRule(
        "NOTICE_ART35_2_E_RETIREMENT_AGE",
        None,
        NoticeSpecialCase.RETIREMENT_AGE_MET,
        EmployeeRole.STANDARD,
        False,
        0,
        DurationUnit.NO_NOTICE,
        RuleSupportStatus.SUPPORTED,
        (_basis(35, 2, "e", SOURCE_CHUNK_ARTICLE_35_NO_NOTICE),),
        STANDARD_NOTICE_WARNING,
    ),
    NoticeRule(
        "NOTICE_ART35_2_G_DISHONEST_INFORMATION",
        None,
        NoticeSpecialCase.EMPLOYER_DISHONEST_INFORMATION,
        EmployeeRole.STANDARD,
        False,
        0,
        DurationUnit.NO_NOTICE,
        RuleSupportStatus.SUPPORTED,
        (_basis(35, 2, "g", SOURCE_CHUNK_ARTICLE_35_NO_NOTICE),),
        STANDARD_NOTICE_WARNING,
    ),
)

DURATION_RULES: tuple[ContractDurationRule, ...] = (
    ContractDurationRule(
        "CONTRACT_ART20_1_A_INDEFINITE",
        ContractDurationType.INDEFINITE,
        None,
        (_basis(20, 1, "a", SOURCE_CHUNK_ARTICLE_20),),
    ),
    ContractDurationRule(
        "CONTRACT_ART20_1_B_FIXED_MAX_36_MONTHS",
        ContractDurationType.FIXED_TERM,
        36,
        (_basis(20, 1, "b", SOURCE_CHUNK_ARTICLE_20),),
    ),
)


def select_notice_rule(payload: NoticePeriodInput) -> NoticeRule:
    """Select one exact immutable notice rule without interpreting free-form scenarios."""
    if (
        payload.special_case == NoticeSpecialCase.SPECIAL_OCCUPATION_EXTERNAL_REGULATION
        and payload.employee_role != EmployeeRole.SPECIAL_OCCUPATION
    ):
        raise InvalidInputCombinationError("special occupation requires SPECIAL_OCCUPATION role")
    if (
        payload.special_case != NoticeSpecialCase.SPECIAL_OCCUPATION_EXTERNAL_REGULATION
        and payload.employee_role != EmployeeRole.STANDARD
    ):
        raise InvalidInputCombinationError("standard scope requires STANDARD role")
    for rule in NOTICE_RULES:
        if (
            rule.special_case == payload.special_case
            and rule.employee_role == payload.employee_role
            and rule.contract_type in (None, payload.contract_type)
        ):
            return rule
    raise RuleNotFoundError("no notice-period rule matches the validated inputs")


def select_contract_duration_rule(contract_type: ContractDurationType) -> ContractDurationRule:
    for rule in DURATION_RULES:
        if rule.contract_type == contract_type:
            return rule
    raise RuleNotFoundError("no contract-duration rule matches the validated inputs")
