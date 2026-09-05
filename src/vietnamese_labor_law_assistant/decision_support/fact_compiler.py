"""Deterministic compiler from grounded property proposals to canonical Case Facts."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from vietnamese_labor_law_assistant.decision_support.enums import (
    AssertionMode,
    VerificationStatus,
)
from vietnamese_labor_law_assistant.decision_support.fact_contract import (
    validate_canonical_fact_value,
)
from vietnamese_labor_law_assistant.decision_support.fact_evidence import (
    FactEvidenceStatus,
    classify_fact_evidence,
)
from vietnamese_labor_law_assistant.decision_support.fact_normalization import (
    FactNormalizationError,
    FactNormalizationFailureCode,
    normalize_fact_value,
    validate_atomic_source_context,
)
from vietnamese_labor_law_assistant.decision_support.fact_policies import (
    PROPERTY_CLAUSE_SEPARATOR_PATTERN,
    find_fact_semantic_support,
)
from vietnamese_labor_law_assistant.decision_support.issue_registry import FactKey
from vietnamese_labor_law_assistant.decision_support.models import (
    CaseFact,
    CaseIntakeInput,
    SourceSpan,
)


class FactProposal(BaseModel):
    """Application-owned projection of the private provider proposal transport."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_key: FactKey
    source_span_text: str = Field(min_length=1, max_length=2000)


class FactRejectionReasonCode(StrEnum):
    """Closed diagnostics for every fail-closed compiler exit."""

    SOURCE_LITERAL_NOT_FOUND = "SOURCE_LITERAL_NOT_FOUND"
    SOURCE_LITERAL_AMBIGUOUS = "SOURCE_LITERAL_AMBIGUOUS"
    EVIDENCE_MISSING = "EVIDENCE_MISSING"
    EVIDENCE_UNKNOWN = "EVIDENCE_UNKNOWN"
    EVIDENCE_NEGATED = "EVIDENCE_NEGATED"
    SEMANTIC_CONTEXT_UNSUPPORTED = "SEMANTIC_CONTEXT_UNSUPPORTED"
    ATOMIC_VALUE_NOT_FOUND = "ATOMIC_VALUE_NOT_FOUND"
    ATOMIC_VALUE_AMBIGUOUS = "ATOMIC_VALUE_AMBIGUOUS"
    NORMALIZATION_UNSAFE = "NORMALIZATION_UNSAFE"
    DUPLICATE_PROPOSAL = "DUPLICATE_PROPOSAL"


@dataclass(frozen=True, slots=True)
class RejectedFactProposal:
    """One proposal rejected with typed evidence and reason diagnostics."""

    proposal: FactProposal
    reason_code: FactRejectionReasonCode
    evidence_status: FactEvidenceStatus | None = None


@dataclass(frozen=True, slots=True)
class FactCompilationResult:
    """Canonical admissions plus all typed rejections in deterministic order."""

    admitted_facts: tuple[CaseFact, ...]
    rejections: tuple[RejectedFactProposal, ...]


CompiledFactProposal = CaseFact | RejectedFactProposal

_CLAUSE_BOUNDARY = re.compile(
    rf"[,;!?\n]|(?<!\d)\.(?!\d)|\b{PROPERTY_CLAUSE_SEPARATOR_PATTERN}\b",
    re.IGNORECASE,
)
_POSTPOSED_NON_PRESENT_QUALIFIER = re.compile(
    r"^\s*(?:(?:(?:đồng|VND)\b|₫)\s*)?[,;:]?\s*(?:nhưng\s+)?(?:vẫn\s+)?"
    r"(?:chưa|không)\s+(?:chắc|rõ|biết|xác\s+định(?:\s+được)?)\b",
    re.IGNORECASE,
)


def _reject(
    proposal: FactProposal,
    reason_code: FactRejectionReasonCode,
    evidence_status: FactEvidenceStatus | None = None,
) -> RejectedFactProposal:
    return RejectedFactProposal(
        proposal=proposal,
        reason_code=reason_code,
        evidence_status=evidence_status,
    )


def _resolve_literal(source_text: str, literal: str) -> tuple[int, int] | FactRejectionReasonCode:
    start = source_text.find(literal)
    if start < 0:
        return FactRejectionReasonCode.SOURCE_LITERAL_NOT_FOUND
    if source_text.find(literal, start + 1) >= 0:
        return FactRejectionReasonCode.SOURCE_LITERAL_AMBIGUOUS
    return start, start + len(literal)


def _bounded_context(source_text: str, start_offset: int, end_offset: int) -> str:
    left = 0
    right = len(source_text)
    for boundary in _CLAUSE_BOUNDARY.finditer(source_text):
        if boundary.end() <= start_offset:
            left = boundary.end()
            continue
        if boundary.start() >= end_offset:
            right = boundary.start()
            break
    return source_text[left:right].strip()


def _evidence_context(source_text: str, start_offset: int, end_offset: int) -> str:
    context = _bounded_context(source_text, start_offset, end_offset)
    postposed = _POSTPOSED_NON_PRESENT_QUALIFIER.match(source_text[end_offset:])
    if postposed is None:
        return context
    return f"{context} {postposed.group(0).strip()}"


def _evidence_rejection(
    proposal: FactProposal, status: FactEvidenceStatus
) -> RejectedFactProposal | None:
    reasons = {
        FactEvidenceStatus.MISSING: FactRejectionReasonCode.EVIDENCE_MISSING,
        FactEvidenceStatus.UNKNOWN: FactRejectionReasonCode.EVIDENCE_UNKNOWN,
        FactEvidenceStatus.NEGATED: FactRejectionReasonCode.EVIDENCE_NEGATED,
    }
    reason = reasons.get(status)
    return _reject(proposal, reason, status) if reason is not None else None


def _normalization_reason(error: FactNormalizationError) -> FactRejectionReasonCode:
    return {
        FactNormalizationFailureCode.VALUE_NOT_FOUND: (
            FactRejectionReasonCode.ATOMIC_VALUE_NOT_FOUND
        ),
        FactNormalizationFailureCode.VALUE_AMBIGUOUS: (
            FactRejectionReasonCode.ATOMIC_VALUE_AMBIGUOUS
        ),
        FactNormalizationFailureCode.UNSAFE_VALUE: FactRejectionReasonCode.NORMALIZATION_UNSAFE,
    }[error.code]


def _stable_fact_id(
    case_input: CaseIntakeInput,
    fact_key: FactKey,
    start_offset: int,
    end_offset: int,
    raw_value: str,
    normalized_value: str | int,
) -> str:
    identity = "\x1f".join(
        (
            case_input.source_ref,
            fact_key.value,
            str(start_offset),
            str(end_offset),
            raw_value,
            str(normalized_value),
        )
    )
    return f"CF-{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:32]}"


def compile_fact_proposal(
    case_input: CaseIntakeInput, proposal: FactProposal
) -> CompiledFactProposal:
    """Compile one proposal without inventing another property or unresolved value."""

    location = _resolve_literal(case_input.source_text, proposal.source_span_text)
    if isinstance(location, FactRejectionReasonCode):
        return _reject(proposal, location)
    proposal_start, _proposal_end = location

    try:
        atomic = normalize_fact_value(proposal.fact_key, proposal.source_span_text)
    except FactNormalizationError as error:
        classification = classify_fact_evidence(proposal.fact_key, proposal.source_span_text)
        evidence_rejection = _evidence_rejection(proposal, classification.status)
        if evidence_rejection is not None:
            return evidence_rejection
        return _reject(proposal, _normalization_reason(error), classification.status)

    start_offset = proposal_start + atomic.start_offset
    end_offset = proposal_start + atomic.end_offset
    context = _evidence_context(case_input.source_text, start_offset, end_offset)
    classification = classify_fact_evidence(proposal.fact_key, context)
    evidence_rejection = _evidence_rejection(proposal, classification.status)
    if evidence_rejection is not None:
        return evidence_rejection
    try:
        validate_atomic_source_context(
            proposal.fact_key,
            case_input.source_text,
            start_offset,
            end_offset,
        )
    except FactNormalizationError as error:
        return _reject(proposal, _normalization_reason(error), classification.status)
    semantic_support = find_fact_semantic_support(
        proposal.fact_key,
        context,
        case_input.source_text,
        start_offset,
    )
    if semantic_support is None:
        return _reject(
            proposal,
            FactRejectionReasonCode.SEMANTIC_CONTEXT_UNSUPPORTED,
            classification.status,
        )
    support_classification = classify_fact_evidence(proposal.fact_key, semantic_support)
    support_rejection = _evidence_rejection(proposal, support_classification.status)
    if support_rejection is not None:
        return support_rejection

    validate_canonical_fact_value(
        proposal.fact_key,
        atomic.fact_type,
        atomic.normalized_value,
    )
    return CaseFact(
        fact_id=_stable_fact_id(
            case_input,
            proposal.fact_key,
            start_offset,
            end_offset,
            atomic.raw_value,
            atomic.normalized_value,
        ),
        fact_key=proposal.fact_key.value,
        fact_type=atomic.fact_type.value,
        raw_value=atomic.raw_value,
        normalized_value=atomic.normalized_value,
        assertion_mode=AssertionMode.EXPLICIT,
        verification_status=VerificationStatus.UNVERIFIED,
        source_type=case_input.source_type,
        source_ref=case_input.source_ref,
        source_span=SourceSpan(
            start_offset=start_offset,
            end_offset=end_offset,
            text=atomic.raw_value,
        ),
    )


def compile_fact_proposals(
    case_input: CaseIntakeInput, proposals: Sequence[FactProposal]
) -> FactCompilationResult:
    """Compile proposals in order, deduplicating only exact canonical representations."""

    facts: list[CaseFact] = []
    rejections: list[RejectedFactProposal] = []
    seen: set[tuple[object, ...]] = set()
    for proposal in proposals:
        outcome = compile_fact_proposal(case_input, proposal)
        if isinstance(outcome, RejectedFactProposal):
            rejections.append(outcome)
            continue
        representation = (
            outcome.fact_key,
            outcome.fact_type,
            outcome.raw_value,
            outcome.normalized_value,
            outcome.source_span.start_offset,
            outcome.source_span.end_offset,
        )
        if representation in seen:
            rejections.append(
                _reject(
                    proposal,
                    FactRejectionReasonCode.DUPLICATE_PROPOSAL,
                    FactEvidenceStatus.PRESENT_ASSERTED,
                )
            )
            continue
        seen.add(representation)
        facts.append(outcome)
    return FactCompilationResult(tuple(facts), tuple(rejections))
