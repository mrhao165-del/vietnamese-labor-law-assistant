"""Atomic deterministic normalization for canonical fact proposals."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from vietnamese_labor_law_assistant.decision_support.fact_contract import FactType
from vietnamese_labor_law_assistant.decision_support.fact_policies import (
    CONTRACT_EXPIRY_VALUE_PATTERN,
    CONTRACT_TYPE_VALUE_PATTERN,
    EXACT_ISO_DATE_VALUE_PATTERN,
    FACT_POLICY_REGISTRY,
    NON_ROLE_PROPERTY_START_PATTERN,
    NOTICE_SPECIAL_CASE_VALUE_PATTERN,
    PROPERTY_CLAUSE_SEPARATOR_PATTERN,
    WAGE_DELAY_FORCE_MAJEURE_VALUE_PATTERN,
    WAGE_PAYMENT_PROBLEM_VALUE_PATTERN,
    WAGE_PAYMENT_STATUS_VALUE_PATTERN,
    FactNormalizationKind,
)
from vietnamese_labor_law_assistant.decision_support.issue_registry import FactKey


class FactNormalizationFailureCode(StrEnum):
    """Closed failure states mapped to compiler rejection diagnostics."""

    VALUE_NOT_FOUND = "VALUE_NOT_FOUND"
    VALUE_AMBIGUOUS = "VALUE_AMBIGUOUS"
    UNSAFE_VALUE = "UNSAFE_VALUE"


class FactNormalizationError(ValueError):
    """Typed fail-closed normalization error."""

    def __init__(self, code: FactNormalizationFailureCode) -> None:
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class AtomicFactValue:
    """One normalized value and its half-open offsets inside a proposal literal."""

    fact_type: FactType
    raw_value: str
    normalized_value: str | int
    start_offset: int
    end_offset: int


_DATE_PATTERN = re.compile(EXACT_ISO_DATE_VALUE_PATTERN)
_DURATION_PATTERN = re.compile(
    r"(?<![\w/-])(?P<months>\d{1,3})\s*tháng(?![\wÀ-ỹ])",
    re.IGNORECASE,
)
_DURATION_RANGE = re.compile(
    r"(?:từ\s+)?\d+\s*(?:(?:tháng|năm)\s*)?"
    r"(?:[-–—]|đến|tới|hoặc|hay)\s*\d+\s*(?:tháng|năm)\b",
    re.IGNORECASE,
)
_APPROXIMATE_VALUE_PREFIX = re.compile(
    r"(?:khoảng|hơn|trên|dưới|ít\s+nhất|tối\s+đa|chậm\s+nhất|sớm\s+nhất"
    r"|không\s+(?:trước|sau|muộn|sớm)\s+hơn"
    r"|(?:trước|sau)(?:\s+ngày)?)\s*$",
    re.IGNORECASE,
)
_VALUE_PUNCTUATION_TERMINATOR = r"(?:,(?!\d)|\.(?!\d)|[;!?])"
_MONEY_PATTERN = re.compile(
    rf"(?<![\w/-])(?P<number>\d{{1,3}}(?:\.\d{{3}})+|\d+)"
    rf"(?P<currency>\s*(?:đồng|VND|₫))?(?![\w/-])"
    rf"(?=\s*(?:(?:tiền\s+)?lương\b(?=\s*(?:{PROPERTY_CLAUSE_SEPARATOR_PATTERN}\b|"
    rf"{_VALUE_PUNCTUATION_TERMINATOR}|$))|{PROPERTY_CLAUSE_SEPARATOR_PATTERN}\b|"
    rf"{_VALUE_PUNCTUATION_TERMINATOR}|$))",
    re.IGNORECASE,
)
_UNSUPPORTED_MONEY_PREFIX = re.compile(
    r"(?:\b[A-Z]{3}|(?i:\b(?:USD|EUR|GBP|AUD|CAD|JPY|CNY|KRW|SGD|THB|CHF|HKD)\b)"
    r"|(?i:\bđô\s+la|\bdollars?)|[$€£])\s*$",
)
_AMBIGUOUS_VALUE_PREFIX = re.compile(
    r"(?:\S+(?:\s+\S+){0,4}\s+(?:đến|tới|hoặc|hay)|\S+\s*[-–—])\s*$",
    re.IGNORECASE,
)
_AMBIGUOUS_VALUE_SUFFIX = re.compile(
    r"^\s*(?:[-–—]|đến\b|tới\b|hoặc\b|hay\b)",
    re.IGNORECASE,
)
_ALTERNATIVE_VALUE_PREFIX = re.compile(
    r"\S+(?:\s+\S+){0,4}\s+(?:hoặc|hay)\s*$",
    re.IGNORECASE,
)
_ALTERNATIVE_VALUE_SUFFIX = re.compile(
    r"^\s*(?:hoặc|hay)\b",
    re.IGNORECASE,
)
_TEMPORAL_PATTERN = re.compile(
    r"(?<!\w)(?:(?:đầu|giữa|cuối)\s+"
    r"(?:tháng\s+Chạp|kỳ\s+lương|tuần|tháng|quý|năm)"
    r"(?:\s+(?:này|tới|sau|kế\s+tiếp|trước))?"
    r"|hôm\s+nay|hôm\s+qua|ngày\s+mai)(?!\w)",
    re.IGNORECASE,
)

_CONTRACT_TYPE_PATTERN = re.compile(
    CONTRACT_TYPE_VALUE_PATTERN,
    re.IGNORECASE,
)
_CONTRACT_EXPIRY_PATTERN = re.compile(
    CONTRACT_EXPIRY_VALUE_PATTERN,
    re.IGNORECASE,
)
_NOTICE_SPECIAL_CASE_PATTERN = re.compile(
    NOTICE_SPECIAL_CASE_VALUE_PATTERN,
    re.IGNORECASE,
)
_EMPLOYEE_ROLE_CAPTURE = re.compile(
    r"(?:vai\s+trò|chức\s+danh|vị\s+trí(?:\s+công\s+việc)?)"
    r".{0,50}?(?:được\s+ghi\s+là|ghi\s+là|là)\s+"
    r"(?P<value>[^,;.!?]+)",
    re.IGNORECASE,
)
_EMPLOYEE_ROLE_WORK = re.compile(
    r"tôi\s+làm(?:\s+việc)?(?:\s+với\s+vai\s+trò)?\s+"
    r"(?P<value>.+?)(?=\s+và\s+|[,;.!?]|$)",
    re.IGNORECASE,
)
_EMPLOYEE_ROLE_PROPERTY_BOUNDARY = re.compile(
    rf"\s+{PROPERTY_CLAUSE_SEPARATOR_PATTERN}\s+(?={NON_ROLE_PROPERTY_START_PATTERN})",
    re.IGNORECASE,
)
_EMPLOYEE_ROLE_SEPARATOR_PATTERN = rf"(?:{PROPERTY_CLAUSE_SEPARATOR_PATTERN}|hoặc|hay)"
_EMPLOYEE_ROLE_ANY_SEPARATOR = re.compile(
    rf"\s+{_EMPLOYEE_ROLE_SEPARATOR_PATTERN}\s+",
    re.IGNORECASE,
)
_WAGE_PROBLEM_PATTERN = re.compile(
    WAGE_PAYMENT_PROBLEM_VALUE_PATTERN,
    re.IGNORECASE,
)
_WAGE_STATUS_PATTERN = re.compile(
    WAGE_PAYMENT_STATUS_VALUE_PATTERN,
    re.IGNORECASE,
)
_FORCE_MAJEURE_PATTERN = re.compile(
    WAGE_DELAY_FORCE_MAJEURE_VALUE_PATTERN,
    re.IGNORECASE,
)
_MONEY_SOURCE_SUFFIX = re.compile(
    rf"^\s*(?:(?:đồng|VND|₫)\s*)?(?:(?:tiền\s+)?lương\b\s*)?"
    rf"(?=$|{_VALUE_PUNCTUATION_TERMINATOR}|{PROPERTY_CLAUSE_SEPARATOR_PATTERN}\b|"
    r"trong\s+\d{1,3}\s*tháng\b)",
    re.IGNORECASE,
)


def _single_match(pattern: re.Pattern[str], text: str) -> re.Match[str]:
    matches = list(pattern.finditer(text))
    if not matches:
        raise FactNormalizationError(FactNormalizationFailureCode.VALUE_NOT_FOUND)
    if len(matches) != 1:
        raise FactNormalizationError(FactNormalizationFailureCode.VALUE_AMBIGUOUS)
    return matches[0]


def _from_match(
    match: re.Match[str], fact_type: FactType, normalized_value: str | int
) -> AtomicFactValue:
    return AtomicFactValue(
        fact_type=fact_type,
        raw_value=match.group(0),
        normalized_value=normalized_value,
        start_offset=match.start(),
        end_offset=match.end(),
    )


def _normalize_date(text: str) -> AtomicFactValue:
    match = _single_match(_DATE_PATTERN, text)
    raw_value = match.group(0)
    try:
        date.fromisoformat(raw_value)
    except ValueError as exc:
        raise FactNormalizationError(FactNormalizationFailureCode.UNSAFE_VALUE) from exc
    return _from_match(match, FactType.DATE, raw_value)


def _normalize_duration(text: str) -> AtomicFactValue:
    if _DURATION_RANGE.search(text):
        raise FactNormalizationError(FactNormalizationFailureCode.VALUE_AMBIGUOUS)
    match = _single_match(_DURATION_PATTERN, text)
    leading = text[max(0, match.start() - 12) : match.start()]
    if _APPROXIMATE_VALUE_PREFIX.search(leading):
        raise FactNormalizationError(FactNormalizationFailureCode.UNSAFE_VALUE)
    months = int(match.group("months"))
    if months <= 0:
        raise FactNormalizationError(FactNormalizationFailureCode.UNSAFE_VALUE)
    return _from_match(match, FactType.DURATION, months)


def _normalize_money(text: str) -> AtomicFactValue:
    match = _single_match(_MONEY_PATTERN, text)
    leading = text[max(0, match.start() - 12) : match.start()]
    if _APPROXIMATE_VALUE_PREFIX.search(leading):
        raise FactNormalizationError(FactNormalizationFailureCode.UNSAFE_VALUE)
    if _UNSUPPORTED_MONEY_PREFIX.search(leading):
        raise FactNormalizationError(FactNormalizationFailureCode.UNSAFE_VALUE)
    number = match.group("number")
    if (len(number) > 1 and number.startswith("0")) or int(number.replace(".", "")) <= 0:
        raise FactNormalizationError(FactNormalizationFailureCode.UNSAFE_VALUE)
    normalized_value = int(number.replace(".", ""))
    if "." not in number:
        return AtomicFactValue(
            fact_type=FactType.MONEY,
            raw_value=number,
            normalized_value=normalized_value,
            start_offset=match.start("number"),
            end_offset=match.end("number"),
        )
    return _from_match(match, FactType.MONEY, normalized_value)


def _normalize_temporal(text: str) -> AtomicFactValue:
    match = _single_match(_TEMPORAL_PATTERN, text)
    raw_value = match.group(0)
    return _from_match(match, FactType.TEMPORAL_EXPRESSION, raw_value)


def _normalize_literal_text(pattern: re.Pattern[str], text: str) -> AtomicFactValue:
    match = _single_match(pattern, text)
    raw_value = match.group(0)
    return _from_match(match, FactType.TEXT, raw_value)


def _atomic_employee_role_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    if re.match(rf"{_EMPLOYEE_ROLE_SEPARATOR_PATTERN}\b", text[start:end], re.IGNORECASE):
        raise FactNormalizationError(FactNormalizationFailureCode.UNSAFE_VALUE)
    boundary = _EMPLOYEE_ROLE_PROPERTY_BOUNDARY.search(text, start, end)
    if boundary is not None:
        end = boundary.start()
    elif _EMPLOYEE_ROLE_ANY_SEPARATOR.search(text, start, end) is not None:
        raise FactNormalizationError(FactNormalizationFailureCode.UNSAFE_VALUE)
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _normalize_employee_role(text: str) -> AtomicFactValue:
    token = re.fullmatch(r"\s*(STANDARD|SPECIAL_OCCUPATION)\s*", text, re.IGNORECASE)
    if token is not None:
        start, end = token.span(1)
        raw_value = text[start:end]
        return AtomicFactValue(FactType.TEXT, raw_value, raw_value, start, end)
    for pattern in (_EMPLOYEE_ROLE_CAPTURE, _EMPLOYEE_ROLE_WORK):
        match = pattern.search(text)
        if match is not None:
            start, end = match.span("value")
            start, end = _atomic_employee_role_bounds(text, start, end)
            raw_value = text[start:end]
            return AtomicFactValue(FactType.TEXT, raw_value, raw_value, start, end)
    stripped = text.strip(" \t\r\n,;.!?")
    if not stripped or len(stripped) > 120 or re.search(r"[,;.!?]", stripped):
        raise FactNormalizationError(FactNormalizationFailureCode.VALUE_NOT_FOUND)
    if stripped.casefold() in {"none", "unknown", "missing", "not provided"}:
        raise FactNormalizationError(FactNormalizationFailureCode.UNSAFE_VALUE)
    if re.match(r"(?:tại|ở|cho|trong|với)\b", stripped, re.IGNORECASE):
        raise FactNormalizationError(FactNormalizationFailureCode.UNSAFE_VALUE)
    start = text.index(stripped)
    start, end = _atomic_employee_role_bounds(text, start, start + len(stripped))
    raw_value = text[start:end]
    return AtomicFactValue(FactType.TEXT, raw_value, raw_value, start, end)


def normalize_fact_value(fact_key: FactKey, proposal_text: str) -> AtomicFactValue:
    """Extract one atomic value and normalize it under the key's explicit policy."""

    policy = FACT_POLICY_REGISTRY[fact_key]
    kind = policy.normalization_kind
    if fact_key is FactKey.INTENDED_TERMINATION_DATE:
        date_matches = list(_DATE_PATTERN.finditer(proposal_text))
        temporal_matches = list(_TEMPORAL_PATTERN.finditer(proposal_text))
        if len(date_matches) + len(temporal_matches) > 1:
            raise FactNormalizationError(FactNormalizationFailureCode.VALUE_AMBIGUOUS)
        if date_matches:
            return _normalize_date(proposal_text)
    if kind is FactNormalizationKind.MONTH_DURATION:
        return _normalize_duration(proposal_text)
    if kind is FactNormalizationKind.MONEY_VND:
        return _normalize_money(proposal_text)
    if kind is FactNormalizationKind.EXACT_ISO_DATE:
        return _normalize_date(proposal_text)
    if kind is FactNormalizationKind.TEMPORAL_EXPRESSION:
        return _normalize_temporal(proposal_text)
    if kind is FactNormalizationKind.CONTRACT_TYPE:
        return _normalize_literal_text(_CONTRACT_TYPE_PATTERN, proposal_text)
    if kind is FactNormalizationKind.CONTRACT_EXPIRY_STATEMENT:
        return _normalize_literal_text(_CONTRACT_EXPIRY_PATTERN, proposal_text)
    if kind is FactNormalizationKind.NOTICE_SPECIAL_CASE:
        return _normalize_literal_text(_NOTICE_SPECIAL_CASE_PATTERN, proposal_text)
    if kind is FactNormalizationKind.EMPLOYEE_ROLE:
        return _normalize_employee_role(proposal_text)
    if kind is FactNormalizationKind.WAGE_PAYMENT_PROBLEM:
        match = _single_match(_WAGE_PROBLEM_PATTERN, proposal_text)
        return _from_match(match, FactType.TEXT, "WAGE_PAYMENT_PROBLEM_REPORTED")
    if kind is FactNormalizationKind.WAGE_PAYMENT_STATUS:
        return _normalize_literal_text(_WAGE_STATUS_PATTERN, proposal_text)
    if kind is FactNormalizationKind.WAGE_DELAY_FORCE_MAJEURE:
        return _normalize_literal_text(_FORCE_MAJEURE_PATTERN, proposal_text)
    raise FactNormalizationError(FactNormalizationFailureCode.VALUE_NOT_FOUND)


def validate_atomic_source_context(
    fact_key: FactKey,
    source_text: str,
    start_offset: int,
    end_offset: int,
) -> None:
    """Reject a normalized substring that is attached to a larger source token or unit."""

    before = source_text[start_offset - 1 : start_offset]
    after = source_text[end_offset : end_offset + 1]
    if re.search(r"[\w/-]", before) or re.search(r"[\w/-]", after):
        raise FactNormalizationError(FactNormalizationFailureCode.UNSAFE_VALUE)
    source_prefix = source_text[max(0, start_offset - 64) : start_offset]
    source_suffix = source_text[end_offset : min(len(source_text), end_offset + 64)]
    approximate_sensitive_keys = {
        FactKey.CONTRACT_DURATION,
        FactKey.UNPAID_WAGES_DURATION,
        FactKey.UNPAID_WAGES_AMOUNT,
        FactKey.CONTRACT_SIGNED_DATE,
        FactKey.CONTRACT_START_DATE,
        FactKey.CONTRACT_END_DATE,
        FactKey.INTENDED_TERMINATION_DATE,
        FactKey.INTENDED_TERMINATION_REFERENCE_DATE,
        FactKey.WAGE_PAYMENT_DUE_DATE,
    }
    if fact_key in approximate_sensitive_keys and _APPROXIMATE_VALUE_PREFIX.search(source_prefix):
        raise FactNormalizationError(FactNormalizationFailureCode.UNSAFE_VALUE)
    if _ALTERNATIVE_VALUE_PREFIX.search(source_prefix) or _ALTERNATIVE_VALUE_SUFFIX.search(
        source_suffix
    ):
        raise FactNormalizationError(FactNormalizationFailureCode.UNSAFE_VALUE)
    if fact_key in approximate_sensitive_keys and (
        _AMBIGUOUS_VALUE_PREFIX.search(source_prefix)
        or _AMBIGUOUS_VALUE_SUFFIX.search(source_suffix)
    ):
        raise FactNormalizationError(FactNormalizationFailureCode.UNSAFE_VALUE)
    if fact_key in {
        FactKey.CONTRACT_DURATION,
        FactKey.UNPAID_WAGES_DURATION,
    }:
        for duration_range in _DURATION_RANGE.finditer(source_text):
            if duration_range.start() <= start_offset and end_offset <= duration_range.end():
                raise FactNormalizationError(FactNormalizationFailureCode.UNSAFE_VALUE)
    if fact_key is FactKey.UNPAID_WAGES_AMOUNT and _UNSUPPORTED_MONEY_PREFIX.search(source_prefix):
        raise FactNormalizationError(FactNormalizationFailureCode.UNSAFE_VALUE)
    if (
        fact_key is FactKey.UNPAID_WAGES_AMOUNT
        and _MONEY_SOURCE_SUFFIX.match(source_text[end_offset:]) is None
    ):
        raise FactNormalizationError(FactNormalizationFailureCode.UNSAFE_VALUE)
