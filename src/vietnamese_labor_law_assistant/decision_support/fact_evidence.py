"""Deterministic evidence and polarity classification for fact proposals."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from vietnamese_labor_law_assistant.decision_support.fact_policies import (
    FACT_POLICY_REGISTRY,
)
from vietnamese_labor_law_assistant.decision_support.issue_registry import FactKey


class FactEvidenceStatus(StrEnum):
    """Closed application-owned evidence states for one proposed property."""

    PRESENT_ASSERTED = "PRESENT_ASSERTED"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"
    NEGATED = "NEGATED"


@dataclass(frozen=True, slots=True)
class FactEvidenceClassification:
    """Deterministic polarity result retained for admission diagnostics."""

    status: FactEvidenceStatus


_MISSING_PATTERNS = (
    re.compile(r"chưa\s+(?:được\s+)?cung\s+cấp", re.IGNORECASE),
    re.compile(r"(?:không|chưa)\s+có\s+(?:thông\s+tin|dữ\s+liệu)", re.IGNORECASE),
    re.compile(
        r"(?:thông\s+tin|dữ\s+liệu|chi\s+tiết).{0,100}(?:còn\s+thiếu|chưa\s+có)", re.IGNORECASE
    ),
    re.compile(r"(?:đang\s+)?để\s+trống", re.IGNORECASE),
    re.compile(r"mọi\s+dữ\s+kiện.{0,60}(?:còn\s+thiếu|chưa\s+có)", re.IGNORECASE),
    re.compile(r"chưa\s+nêu", re.IGNORECASE),
)

_UNKNOWN_PATTERNS = (
    re.compile(r"(?:chưa|không)\s+chắc", re.IGNORECASE),
    re.compile(r"chưa\s+(?:được\s+)?xác\s+định(?:\s+được)?", re.IGNORECASE),
    re.compile(r"không\s+xác\s+định\s+được", re.IGNORECASE),
    re.compile(r"(?:chưa|không)\s+biết", re.IGNORECASE),
    re.compile(r"(?:chưa|không)\s+rõ", re.IGNORECASE),
)

_STRONG_NEGATED_PATTERNS = (
    re.compile(r"không\s+phải(?:\s+là)?", re.IGNORECASE),
    re.compile(r"không\s+thuộc", re.IGNORECASE),
    re.compile(r"không\s+dự\s+kiến", re.IGNORECASE),
    re.compile(r"không\s+(?:khẳng\s+định|xác\s+nhận)", re.IGNORECASE),
)

_NEGATED_PATTERNS = (re.compile(r"\b(?:không|chưa)\b", re.IGNORECASE),)

_SUPPORTED_FORCE_MAJEURE_ABSENCE = re.compile(
    r"(?:không\s+có|không\s+do)(?:\s+[\wÀ-ỹ]+){0,4}\s+bất\s+khả\s+kháng",
    re.IGNORECASE,
)
_UNPAID_STATUS = re.compile(
    r"(?:lương|tiền\s+lương).{0,40}chưa\s+(?:được\s+)?(?:trả|thanh\s+toán)",
    re.IGNORECASE,
)
_INDEFINITE_CONTRACT = re.compile(
    r"không\s+xác\s+định\s+thời\s+hạn",
    re.IGNORECASE,
)


def _contains_nonpresent_outside_match(evidence_text: str, match: re.Match[str]) -> bool:
    remaining = evidence_text[: match.start()] + evidence_text[match.end() :]
    return _NEGATED_PATTERNS[0].search(remaining) is not None


def classify_fact_evidence(fact_key: FactKey, evidence_text: str) -> FactEvidenceClassification:
    """Classify bounded Vietnamese polarity patterns without semantic inference."""

    for pattern in _MISSING_PATTERNS:
        if pattern.search(evidence_text):
            return FactEvidenceClassification(FactEvidenceStatus.MISSING)
    for pattern in _UNKNOWN_PATTERNS:
        if pattern.search(evidence_text):
            return FactEvidenceClassification(FactEvidenceStatus.UNKNOWN)
    for pattern in _STRONG_NEGATED_PATTERNS:
        if pattern.search(evidence_text):
            return FactEvidenceClassification(FactEvidenceStatus.NEGATED)
    force_absence = _SUPPORTED_FORCE_MAJEURE_ABSENCE.search(evidence_text)
    if (
        FACT_POLICY_REGISTRY[fact_key].supports_explicit_negative_absence
        and force_absence is not None
        and not _contains_nonpresent_outside_match(evidence_text, force_absence)
    ):
        return FactEvidenceClassification(FactEvidenceStatus.PRESENT_ASSERTED)
    if (
        fact_key is FactKey.NOTICE_SPECIAL_CASE
        and re.search(r"\bNONE\b", evidence_text, re.IGNORECASE)
        and _NEGATED_PATTERNS[0].search(evidence_text) is None
    ):
        return FactEvidenceClassification(FactEvidenceStatus.PRESENT_ASSERTED)
    unpaid_status = _UNPAID_STATUS.search(evidence_text)
    if (
        fact_key
        in {
            FactKey.UNPAID_WAGES_AMOUNT,
            FactKey.UNPAID_WAGES_DURATION,
            FactKey.WAGE_PAYMENT_PROBLEM,
            FactKey.WAGE_PAYMENT_STATUS,
        }
        and unpaid_status is not None
        and not _contains_nonpresent_outside_match(evidence_text, unpaid_status)
    ):
        return FactEvidenceClassification(FactEvidenceStatus.PRESENT_ASSERTED)
    indefinite_contract = _INDEFINITE_CONTRACT.search(evidence_text)
    if (
        fact_key is FactKey.CONTRACT_TYPE
        and indefinite_contract is not None
        and not _contains_nonpresent_outside_match(evidence_text, indefinite_contract)
    ):
        return FactEvidenceClassification(FactEvidenceStatus.PRESENT_ASSERTED)
    for pattern in _NEGATED_PATTERNS:
        if pattern.search(evidence_text):
            return FactEvidenceClassification(FactEvidenceStatus.NEGATED)
    return FactEvidenceClassification(FactEvidenceStatus.PRESENT_ASSERTED)
