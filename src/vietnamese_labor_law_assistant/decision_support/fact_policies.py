"""Immutable deterministic admission policy overlay for canonical Case Facts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from vietnamese_labor_law_assistant.decision_support.fact_contract import (
    CANONICAL_FACT_CONTRACT,
    CanonicalFactDefinition,
)
from vietnamese_labor_law_assistant.decision_support.issue_registry import FactKey


class FactNormalizationKind(StrEnum):
    """Closed deterministic normalization families used by the compiler."""

    MONTH_DURATION = "MONTH_DURATION"
    MONEY_VND = "MONEY_VND"
    EXACT_ISO_DATE = "EXACT_ISO_DATE"
    TEMPORAL_EXPRESSION = "TEMPORAL_EXPRESSION"
    CONTRACT_TYPE = "CONTRACT_TYPE"
    CONTRACT_EXPIRY_STATEMENT = "CONTRACT_EXPIRY_STATEMENT"
    NOTICE_SPECIAL_CASE = "NOTICE_SPECIAL_CASE"
    EMPLOYEE_ROLE = "EMPLOYEE_ROLE"
    WAGE_PAYMENT_PROBLEM = "WAGE_PAYMENT_PROBLEM"
    WAGE_PAYMENT_STATUS = "WAGE_PAYMENT_STATUS"
    WAGE_DELAY_FORCE_MAJEURE = "WAGE_DELAY_FORCE_MAJEURE"


TERMINATION_ACTION_PATTERN: Final[str] = (
    r"(?:nghỉ(?:\s+việc)?|thôi\s+việc|chấm\s+dứt|"
    r"kết\s+thúc\s+công\s+việc|rời\s+công\s+việc)"
)
NOTICE_SPECIAL_CASE_PROPERTY_PATTERN: Final[str] = (
    r"trường\s+hợp\s+(?:đặc\s+biệt|miễn(?:\s+báo\s+trước)?|báo\s+trước)"
)
EXACT_ISO_DATE_VALUE_PATTERN: Final[str] = r"(?<![\w/-])\d{4}-\d{2}-\d{2}(?![\w/-])"
_MONTH_DURATION_VALUE_START = r"(?<![\w/-])\d{1,3}\s*tháng(?![\wÀ-ỹ])"
_MONEY_VALUE_START = (
    r"(?<![\w/-])(?:\d{1,3}(?:\.\d{3})+|\d+)"
    r"(?:\s*(?:(?:đồng|VND)\b|₫))?(?![\w/-])"
)
_TEMPORAL_VALUE_START = (
    r"(?<!\w)(?:(?:đầu|giữa|cuối)\s+"
    r"(?:tháng\s+Chạp|kỳ\s+lương|tuần|tháng|quý|năm)"
    r"(?:\s+(?:này|tới|sau|kế\s+tiếp|trước))?"
    r"|hôm\s+nay|hôm\s+qua|ngày\s+mai)(?!\w)"
)
CONTRACT_TYPE_VALUE_PATTERN: Final[str] = (
    r"(?<!\w)(?:không\s+xác\s+định\s+thời\s+hạn|"
    r"xác\s+định\s+thời\s+hạn|FIXED_TERM|INDEFINITE)(?!\w)"
)
CONTRACT_EXPIRY_VALUE_PATTERN: Final[str] = (
    r"(?<!\w)(?:sắp\s+hết\s+hạn|đã\s+hết\s+hạn|hết\s+hạn|đáo\s+hạn)(?!\w)"
)
NOTICE_SPECIAL_CASE_VALUE_PATTERN: Final[str] = (
    r"(?<!\w)(?:WORK_OR_LOCATION_NOT_AS_AGREED|UNPAID_OR_LATE_WAGES|"
    r"MISTREATMENT_OR_FORCED_LABOR|WORKPLACE_SEXUAL_HARASSMENT|"
    r"PREGNANT_WORKER_MEDICAL_CERTIFICATION|RETIREMENT_AGE_MET|"
    r"EMPLOYER_DISHONEST_INFORMATION|SPECIAL_OCCUPATION_EXTERNAL_REGULATION|NONE|"
    r"bị\s+quấy\s+rối\s+tình\s+dục\s+tại\s+nơi\s+làm\s+việc)(?!\w)"
)
WAGE_PAYMENT_PROBLEM_VALUE_PATTERN: Final[str] = (
    r"(?<!\w)(?:chậm\s+trả\s+lương|nợ\s+lương|tiền\s+lương\s+còn\s+thiếu|"
    r"lương\s+còn\s+thiếu|lương\s+bị\s+thiếu|trả\s+chậm|"
    r"lương\s+chưa\s+(?:được\s+)?(?:trả|thanh\s+toán))(?!\w)"
)
WAGE_PAYMENT_STATUS_VALUE_PATTERN: Final[str] = (
    r"(?<!\w)(?:chậm\s+trả\s+lương|trả\s+chậm|"
    r"lương\s+chưa\s+(?:được\s+)?(?:trả|thanh\s+toán))(?!\w)"
)
WAGE_DELAY_FORCE_MAJEURE_VALUE_PATTERN: Final[str] = (
    r"(?<!\w)(?:(?:không\s+có|không\s+do)(?:\s+[\wÀ-ỹ]+){0,4}\s+"
    r"bất\s+khả\s+kháng|bất\s+khả\s+kháng)(?!\w)"
)
PROPERTY_CLAUSE_SEPARATOR_PATTERN: Final[str] = r"(?:và|nhưng|đồng\s+thời)"


@dataclass(frozen=True, slots=True)
class FactPolicy:
    """One semantic-admission overlay referencing the canonical fact definition."""

    definition: CanonicalFactDefinition
    normalization_kind: FactNormalizationKind
    semantic_anchors: tuple[str, ...]
    property_start_patterns: tuple[str, ...]
    semantic_exclusions: tuple[str, ...] = ()
    supports_explicit_negative_absence: bool = False


def _policy(
    fact_key: FactKey,
    normalization_kind: FactNormalizationKind,
    *semantic_anchors: str,
    property_start_patterns: tuple[str, ...] = (),
    semantic_exclusions: tuple[str, ...] = (),
    supports_explicit_negative_absence: bool = False,
) -> FactPolicy:
    return FactPolicy(
        definition=CANONICAL_FACT_CONTRACT[fact_key],
        normalization_kind=normalization_kind,
        semantic_anchors=semantic_anchors,
        property_start_patterns=property_start_patterns,
        semantic_exclusions=semantic_exclusions,
        supports_explicit_negative_absence=supports_explicit_negative_absence,
    )


FACT_POLICY_REGISTRY: Final = MappingProxyType(
    {
        FactKey.CONTRACT_DURATION: _policy(
            FactKey.CONTRACT_DURATION,
            FactNormalizationKind.MONTH_DURATION,
            r"hợp đồng|điều khoản\s+thời hạn",
            r"thời hạn|kéo dài",
            property_start_patterns=(
                rf"(?:hợp\s+đồng|điều\s+khoản\s+thời\s+hạn|thời\s+hạn|{_MONTH_DURATION_VALUE_START})",
            ),
        ),
        FactKey.CONTRACT_EXPIRY_STATEMENT: _policy(
            FactKey.CONTRACT_EXPIRY_STATEMENT,
            FactNormalizationKind.CONTRACT_EXPIRY_STATEMENT,
            r"hợp đồng",
            r"hết hạn|đáo hạn",
            property_start_patterns=(
                rf"(?:hợp\s+đồng|tình\s+trạng\s+hết\s+hạn|{CONTRACT_EXPIRY_VALUE_PATTERN})",
            ),
        ),
        FactKey.CONTRACT_SIGNED_DATE: _policy(
            FactKey.CONTRACT_SIGNED_DATE,
            FactNormalizationKind.EXACT_ISO_DATE,
            r"hợp đồng|văn bản\s+lao động",
            r"(?:ngày\s+)?ký|ký\s+(?:vào\s+)?ngày",
            property_start_patterns=(
                rf"(?:ngày\s+ký|hợp\s+đồng\s+(?:được\s+)?ký|văn\s+bản\s+lao\s+động|{EXACT_ISO_DATE_VALUE_PATTERN})",
            ),
        ),
        FactKey.CONTRACT_TYPE: _policy(
            FactKey.CONTRACT_TYPE,
            FactNormalizationKind.CONTRACT_TYPE,
            r"loại\s+hợp đồng|hợp đồng",
            property_start_patterns=(
                rf"(?:loại\s+hợp\s+đồng|hợp\s+đồng|{CONTRACT_TYPE_VALUE_PATTERN})",
            ),
        ),
        FactKey.EVENT_TIME: _policy(
            FactKey.EVENT_TIME,
            FactNormalizationKind.TEMPORAL_EXPRESSION,
            r"sự việc|sự kiện|xảy ra|diễn ra|thời điểm",
            property_start_patterns=(
                rf"(?:thời\s+điểm|sự\s+việc|sự\s+kiện|xảy\s+ra|diễn\s+ra|{_TEMPORAL_VALUE_START})",
            ),
        ),
        FactKey.UNPAID_WAGES_AMOUNT: _policy(
            FactKey.UNPAID_WAGES_AMOUNT,
            FactNormalizationKind.MONEY_VND,
            r"lương|tiền lương|UNPAID_WAGES_AMOUNT",
            r"nợ|thiếu|chậm trả|trả chậm|chưa trả|chưa thanh toán|UNPAID_WAGES_AMOUNT",
            property_start_patterns=(
                rf"(?:số\s+tiền|mức\s+lương|khoản\s+lương|UNPAID_WAGES_AMOUNT|{_MONEY_VALUE_START})",
            ),
        ),
        FactKey.UNPAID_WAGES_DURATION: _policy(
            FactKey.UNPAID_WAGES_DURATION,
            FactNormalizationKind.MONTH_DURATION,
            r"lương|tiền lương|bản khác nêu",
            r"nợ|thiếu|chưa trả|chưa thanh toán|bản khác nêu",
            property_start_patterns=(
                rf"(?:thời\s+gian\s+(?:nợ|thiếu|chưa\s+trả)\s+lương|nợ\s+lương|lương|{_MONTH_DURATION_VALUE_START})",
            ),
        ),
        FactKey.CONTRACT_START_DATE: _policy(
            FactKey.CONTRACT_START_DATE,
            FactNormalizationKind.EXACT_ISO_DATE,
            r"hợp đồng",
            r"bắt đầu|ngày bắt đầu|có hiệu lực từ",
            property_start_patterns=(
                rf"(?:ngày\s+bắt\s+đầu|hợp\s+đồng|có\s+hiệu\s+lực\s+từ|bắt\s+đầu|{EXACT_ISO_DATE_VALUE_PATTERN})",
            ),
        ),
        FactKey.CONTRACT_END_DATE: _policy(
            FactKey.CONTRACT_END_DATE,
            FactNormalizationKind.EXACT_ISO_DATE,
            r"hợp đồng",
            r"kết thúc|ngày kết thúc|đến ngày",
            property_start_patterns=(
                rf"(?:ngày\s+kết\s+thúc|hợp\s+đồng|kết\s+thúc|{EXACT_ISO_DATE_VALUE_PATTERN})",
            ),
        ),
        FactKey.NOTICE_SPECIAL_CASE: _policy(
            FactKey.NOTICE_SPECIAL_CASE,
            FactNormalizationKind.NOTICE_SPECIAL_CASE,
            rf"miễn báo trước|{NOTICE_SPECIAL_CASE_PROPERTY_PATTERN}|không cần báo trước|"
            rf"{NOTICE_SPECIAL_CASE_VALUE_PATTERN}",
            property_start_patterns=(
                rf"(?:{NOTICE_SPECIAL_CASE_PROPERTY_PATTERN}|{NOTICE_SPECIAL_CASE_VALUE_PATTERN})",
            ),
        ),
        FactKey.EMPLOYEE_ROLE: _policy(
            FactKey.EMPLOYEE_ROLE,
            FactNormalizationKind.EMPLOYEE_ROLE,
            r"vai trò|chức danh|vị trí công việc|tôi làm|STANDARD|SPECIAL_OCCUPATION",
            property_start_patterns=(),
        ),
        FactKey.INTENDED_TERMINATION_DATE: _policy(
            FactKey.INTENDED_TERMINATION_DATE,
            FactNormalizationKind.TEMPORAL_EXPRESSION,
            rf"(?=.*{TERMINATION_ACTION_PATTERN})"
            r"(?=.*(?:dự kiến|dự định|muốn|sẽ|kế hoạch))",
            property_start_patterns=(
                rf"(?:(?:dự\s+kiến|dự\s+định|muốn|sẽ|kế\s+hoạch)\s+{TERMINATION_ACTION_PATTERN}|"
                rf"ngày\s+dự\s+kiến\s+{TERMINATION_ACTION_PATTERN}|{TERMINATION_ACTION_PATTERN}|"
                rf"{_TEMPORAL_VALUE_START}|{EXACT_ISO_DATE_VALUE_PATTERN})",
            ),
        ),
        FactKey.INTENDED_TERMINATION_REFERENCE_DATE: _policy(
            FactKey.INTENDED_TERMINATION_REFERENCE_DATE,
            FactNormalizationKind.EXACT_ISO_DATE,
            r"mốc.*(?:nghỉ|chấm dứt)|ngày tham chiếu|ngày làm mốc|tính từ ngày",
            property_start_patterns=(
                rf"(?:ngày\s+tham\s+chiếu|ngày\s+làm\s+mốc|mốc\s+(?:nghỉ|chấm\s+dứt)|tính\s+từ\s+ngày|{EXACT_ISO_DATE_VALUE_PATTERN})",
            ),
        ),
        FactKey.WAGE_PAYMENT_PROBLEM: _policy(
            FactKey.WAGE_PAYMENT_PROBLEM,
            FactNormalizationKind.WAGE_PAYMENT_PROBLEM,
            r"nợ lương|chậm trả lương|trả chậm|lương.*(?:thiếu|chưa trả|chưa thanh toán)",
            property_start_patterns=(rf"(?:{WAGE_PAYMENT_PROBLEM_VALUE_PATTERN}|lương)",),
            semantic_exclusions=(r"(?:trong\s+)?mục\s+số\s+tiền\s+lương\s+chưa\s+trả\b",),
        ),
        FactKey.WAGE_PAYMENT_DUE_DATE: _policy(
            FactKey.WAGE_PAYMENT_DUE_DATE,
            FactNormalizationKind.EXACT_ISO_DATE,
            r"đến hạn.*lương|hạn thanh toán lương|lương.*đến hạn",
            property_start_patterns=(
                rf"(?:ngày\s+đến\s+hạn\s+lương|hạn\s+thanh\s+toán\s+lương|lương\s+đến\s+hạn|{EXACT_ISO_DATE_VALUE_PATTERN})",
            ),
        ),
        FactKey.WAGE_PAYMENT_STATUS: _policy(
            FactKey.WAGE_PAYMENT_STATUS,
            FactNormalizationKind.WAGE_PAYMENT_STATUS,
            r"chậm trả lương|trả chậm|lương.*(?:chưa trả|chưa thanh toán)",
            property_start_patterns=(
                rf"(?:trạng\s+thái\s+thanh\s+toán\s+lương|{WAGE_PAYMENT_STATUS_VALUE_PATTERN}|lương)",
            ),
            semantic_exclusions=(r"(?:trong\s+)?mục\s+số\s+tiền\s+lương\s+chưa\s+trả\b",),
        ),
        FactKey.WAGE_DELAY_FORCE_MAJEURE: _policy(
            FactKey.WAGE_DELAY_FORCE_MAJEURE,
            FactNormalizationKind.WAGE_DELAY_FORCE_MAJEURE,
            r"bất khả kháng",
            property_start_patterns=(
                rf"(?:(?:sự\s+kiện\s+)?{WAGE_DELAY_FORCE_MAJEURE_VALUE_PATTERN})",
            ),
            supports_explicit_negative_absence=True,
        ),
    }
)

if tuple(FACT_POLICY_REGISTRY) != tuple(FactKey):
    raise RuntimeError("fact policy registry must follow complete canonical FactKey order")
if any(
    not policy.property_start_patterns
    for fact_key, policy in FACT_POLICY_REGISTRY.items()
    if fact_key is not FactKey.EMPLOYEE_ROLE
):
    raise RuntimeError("every non-role fact policy must declare atomic neighbor starts")

NON_ROLE_PROPERTY_START_PATTERN: Final[str] = (
    "(?:"
    + "|".join(
        pattern
        for fact_key, policy in FACT_POLICY_REGISTRY.items()
        if fact_key is not FactKey.EMPLOYEE_ROLE
        for pattern in policy.property_start_patterns
    )
    + ")"
)


_WAGE_AMOUNT_CONTINUATION = re.compile(
    r"(?:nợ\s+lương|(?:lương|tiền\s+lương).{0,40}"
    r"(?:nợ|thiếu|chưa\s+trả|chưa\s+thanh\s+toán))"
    r"[^.!?\n]{0,100}(?:,\s*giá\s+trị\s+được\s+ghi\s+là|;\s*số\s+tiền\s+là)\s*$",
    re.IGNORECASE,
)
_WAGE_DURATION_COMPARISON = re.compile(
    r"(?:nợ\s+lương|(?:lương|tiền\s+lương).{0,40}"
    r"(?:nợ|thiếu|chưa\s+trả|chưa\s+thanh\s+toán))"
    r"[^.!?\n]{0,120},\s*nhưng\s+(?:bảng\s+chấm\s+công|bản\s+khác)"
    r".{0,40}(?:thể\s+hiện|ghi|nêu)\s*$",
    re.IGNORECASE,
)
_RECORDED_CONTRACT_DURATION = re.compile(
    r"\bthời\s+hạn\s+được\s+ghi\s*:\s*(?P<value>\d{1,3}\s*tháng)\s*;"
    r"[^.!?\n]{0,100}\bđiều\s+khoản\s+thời\s+hạn\b",
    re.IGNORECASE,
)
_CONTRACT_CONTINUATION_PATTERNS = {
    FactKey.CONTRACT_DURATION: re.compile(
        r"hợp\s+đồng[^.;!?\n]{0,180}(?:\bvà|,)\s+"
        r"(?:có\s+thời\s+hạn|kéo\s+dài)\s*$",
        re.IGNORECASE,
    ),
    FactKey.CONTRACT_SIGNED_DATE: re.compile(
        r"hợp\s+đồng[^.;!?\n]{0,180}(?:\bvà|,)\s+"
        r"(?:được\s+)?ký(?:\s+vào)?(?:\s+ngày)?\s*$",
        re.IGNORECASE,
    ),
    FactKey.CONTRACT_START_DATE: re.compile(
        r"hợp\s+đồng[^.;!?\n]{0,180}(?:\bvà|,)\s+"
        r"(?:được\s+)?bắt\s+đầu(?:\s+ngày)?\s*$",
        re.IGNORECASE,
    ),
    FactKey.CONTRACT_END_DATE: re.compile(
        r"hợp\s+đồng[^.;!?\n]{0,180}(?:\bvà|,)\s+"
        r"(?:được\s+)?kết\s+thúc(?:\s+ngày)?\s*$",
        re.IGNORECASE,
    ),
}


def _sentence_supporting_prefix(prefix: str) -> str:
    boundary = max(prefix.rfind(marker) for marker in (".", "!", "?", "\n"))
    return prefix[boundary + 1 :].strip()


def find_fact_semantic_support(
    fact_key: FactKey,
    local_context: str,
    source_text: str,
    value_start_offset: int,
) -> str | None:
    """Return the exact text supporting property semantics, or fail closed."""

    policy = FACT_POLICY_REGISTRY[fact_key]
    if any(
        re.search(pattern, local_context, re.IGNORECASE) for pattern in policy.semantic_exclusions
    ):
        return None
    if all(re.search(anchor, local_context, re.IGNORECASE) for anchor in policy.semantic_anchors):
        return local_context

    prefix = source_text[max(0, value_start_offset - 240) : value_start_offset]
    if fact_key is FactKey.CONTRACT_DURATION:
        recorded_duration = _RECORDED_CONTRACT_DURATION.search(source_text)
        if recorded_duration is not None and recorded_duration.start("value") == value_start_offset:
            return recorded_duration.group(0)
    contract_continuation = _CONTRACT_CONTINUATION_PATTERNS.get(fact_key)
    if contract_continuation is not None:
        if contract_continuation.search(prefix) is not None:
            return _sentence_supporting_prefix(prefix)
        return None
    if fact_key is FactKey.UNPAID_WAGES_AMOUNT:
        if _WAGE_AMOUNT_CONTINUATION.search(prefix) is not None:
            return _sentence_supporting_prefix(prefix)
        return None
    if fact_key is FactKey.UNPAID_WAGES_DURATION:
        if _WAGE_DURATION_COMPARISON.search(prefix) is not None:
            return _sentence_supporting_prefix(prefix)
        return None
    return None


def is_fact_semantically_eligible(
    fact_key: FactKey,
    local_context: str,
    source_text: str,
    value_start_offset: int,
) -> bool:
    """Compatibility predicate backed by the evidence-bearing semantic seam."""

    return (
        find_fact_semantic_support(
            fact_key,
            local_context,
            source_text,
            value_start_offset,
        )
        is not None
    )
