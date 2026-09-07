"""Deterministic semantic admission for provider-proposed candidate issues."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from vietnamese_labor_law_assistant.decision_support.issues import IssueCode
from vietnamese_labor_law_assistant.decision_support.models import (
    CandidateIssue,
    CaseIntakeInput,
)


class IssueEligibilityRejectionCode(StrEnum):
    """Closed internal reasons why a schema-valid issue proposal was not admitted."""

    TERMINATION_EVIDENCE_MISSING_OR_UNKNOWN_ONLY = (
        "ISSUE_TERMINATION_EVIDENCE_MISSING_OR_UNKNOWN_ONLY"
    )
    TERMINATION_EVIDENCE_NEGATED_ONLY = "ISSUE_TERMINATION_EVIDENCE_NEGATED_ONLY"
    TERMINATION_AFFIRMATIVE_SIGNAL_ABSENT = "ISSUE_TERMINATION_AFFIRMATIVE_SIGNAL_ABSENT"
    CONTRACT_TERM_SIGNAL_ABSENT = "ISSUE_CONTRACT_TERM_SIGNAL_ABSENT"


@dataclass(frozen=True, slots=True)
class RejectedCandidateIssue:
    """One provider proposal excluded by raw-message semantic eligibility."""

    candidate_issue: CandidateIssue
    reason_code: IssueEligibilityRejectionCode


@dataclass(frozen=True, slots=True)
class IssueEligibilityResult:
    """Deterministic issue admissions and internal rejection observations."""

    admitted_issues: tuple[CandidateIssue, ...]
    rejected_issues: tuple[RejectedCandidateIssue, ...]


_CLAUSE_BOUNDARY: Final = re.compile(
    r"(?:[;.!?]+|\r?\n+|,\s*(?=(?:nhưng|tuy\s+nhiên)\b)|\bnhưng\b)",
    re.IGNORECASE,
)
_TERMINATION_ACTION: Final = re.compile(
    r"\b(?:nghỉ(?:\s+việc)?|thôi\s+việc|"
    r"(?:tự\s+(?:mình\s+)?)?(?:chấm\s+dứt|kết\s+thúc)"
    r"(?:\s+(?:hợp\s+đồng|quan\s+hệ\s+lao\s+động|việc\s+làm))?)\b",
    re.IGNORECASE,
)
_AFFIRMATIVE_INTENT: Final = re.compile(
    r"\b(?:muốn|dự\s+kiến|dự\s+định|định|đang\s+xem\s+xét|xem\s+xét|cân\s+nhắc|"
    r"quyết\s+định|có\s+kế\s+hoạch|sẽ|xin)\b",
    re.IGNORECASE,
)
_TERMINATION_REQUEST: Final = re.compile(
    r"\b(?:cần|muốn|xin)\s+(?:xem\s+xét|phân\s+tích|hỏi|tư\s+vấn)\b"
    r"[^;.!?]{0,120}\b(?:người\s+lao\s+động|nhân\s+viên|tôi)\b"
    r"[^;.!?]{0,80}\b(?:nghỉ(?:\s+việc)?|thôi\s+việc|chấm\s+dứt)\b",
    re.IGNORECASE,
)
_MISSING_OR_UNKNOWN: Final = re.compile(
    r"\b(?:chưa\s+(?:được\s+)?(?:xác\s+định|cung\s+cấp|xác\s+lập|quyết\s+định)|"
    r"không\s+(?:biết|rõ|có\s+thông\s+tin)|chưa\s+rõ|để\s+trống|"
    r"liệu\b[^;.!?]{0,100}\bhay\s+không)\b",
    re.IGNORECASE,
)
_NEGATED_TERMINATION: Final = re.compile(
    r"\b(?:không|chưa)\s+(?:muốn|định|dự\s+định|có\s+kế\s+hoạch|"
    r"quyết\s+định|xin|nghỉ|thôi\s+việc|chấm\s+dứt)\b",
    re.IGNORECASE,
)
_PROPERTY_WORD_BETWEEN_INTENT_AND_ACTION: Final = re.compile(
    r"\b(?:ngày|thời\s+điểm|thông\s+tin|liệu)\b",
    re.IGNORECASE,
)
_DATE_PROPERTY_BEFORE_INTENT: Final = re.compile(
    r"\b(?:ngày|thời\s+điểm)\s+$",
    re.IGNORECASE,
)

_CONTRACT_TERM_SIGNALS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(
        r"\b(?:loại|thời\s+hạn)\s+(?:của\s+)?hợp\s+đồng\b|"
        r"\bhợp\s+đồng\b[^;.!?]{0,80}\b(?:loại|có\s+thời\s+hạn|"
        r"xác\s+định\s+thời\s+hạn|không\s+xác\s+định\s+thời\s+hạn|"
        r"FIXED_TERM|INDEFINITE|\d{1,3}\s*tháng)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:ngày\s+)?(?:ký|bắt\s+đầu|kết\s+thúc|hết\s+hạn|đáo\s+hạn)\b"
        r"[^;.!?]{0,80}\bhợp\s+đồng\b|"
        r"\bhợp\s+đồng\b[^;.!?]{0,80}\b(?:ngày\s+)?"
        r"(?:ký|bắt\s+đầu|kết\s+thúc|hết\s+hạn|đáo\s+hạn|kéo\s+dài)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bđiều\s+khoản\s+thời\s+hạn\b|"
        r"\bthời\s+hạn\b(?!\s+báo\s+trước)[^;.!?]{0,60}\b\d{1,3}\s*tháng\b",
        re.IGNORECASE,
    ),
)


def _normalize_text(source_text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", source_text)).strip()


def _clauses(source_text: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in _CLAUSE_BOUNDARY.split(source_text) if part.strip())


def _clause_has_affirmative_termination(clause: str) -> bool:
    request = _TERMINATION_REQUEST.search(clause)
    if request is not None:
        negative = _NEGATED_TERMINATION.search(clause)
        if negative is not None and negative.start() < request.end():
            return False
        uncertain = _MISSING_OR_UNKNOWN.search(clause)
        if uncertain is not None and uncertain.start() < request.end():
            return False
        return True
    action = _TERMINATION_ACTION.search(clause)
    if action is None:
        return False
    intents = tuple(_AFFIRMATIVE_INTENT.finditer(clause, 0, action.start()))
    if not intents:
        return False
    intent = intents[-1]
    if _DATE_PROPERTY_BEFORE_INTENT.search(clause[: intent.start()]):
        return False
    if _PROPERTY_WORD_BETWEEN_INTENT_AND_ACTION.search(clause, intent.end(), action.start()):
        return False
    negative = _NEGATED_TERMINATION.search(clause)
    if negative is not None and negative.start() <= intent.start():
        return False
    uncertain = _MISSING_OR_UNKNOWN.search(clause)
    return uncertain is None or uncertain.start() > action.end()


def _termination_eligibility(source_text: str) -> IssueEligibilityRejectionCode | None:
    clauses = _clauses(source_text)
    if any(_clause_has_affirmative_termination(clause) for clause in clauses):
        return None
    if _NEGATED_TERMINATION.search(source_text) is not None:
        return IssueEligibilityRejectionCode.TERMINATION_EVIDENCE_NEGATED_ONLY
    if _MISSING_OR_UNKNOWN.search(source_text) is not None:
        return IssueEligibilityRejectionCode.TERMINATION_EVIDENCE_MISSING_OR_UNKNOWN_ONLY
    return IssueEligibilityRejectionCode.TERMINATION_AFFIRMATIVE_SIGNAL_ABSENT


def _contract_term_eligibility(source_text: str) -> IssueEligibilityRejectionCode | None:
    if any(pattern.search(source_text) is not None for pattern in _CONTRACT_TERM_SIGNALS):
        return None
    return IssueEligibilityRejectionCode.CONTRACT_TERM_SIGNAL_ABSENT


def evaluate_issue_eligibility(
    case_input: CaseIntakeInput,
    proposals: Sequence[CandidateIssue],
) -> IssueEligibilityResult:
    """Admit issue proposals solely from bounded semantics in the original user message."""

    source_text = _normalize_text(case_input.source_text)
    admitted: list[CandidateIssue] = []
    rejected: list[RejectedCandidateIssue] = []
    for proposal in proposals:
        if proposal.issue_code is IssueCode.EMPLOYEE_UNILATERAL_TERMINATION:
            reason = _termination_eligibility(source_text)
        else:
            reason = _contract_term_eligibility(source_text)
        if reason is None:
            admitted.append(proposal)
        else:
            rejected.append(RejectedCandidateIssue(proposal, reason))
    return IssueEligibilityResult(tuple(admitted), tuple(rejected))
