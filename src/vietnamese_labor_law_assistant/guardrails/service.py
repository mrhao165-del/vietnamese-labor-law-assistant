"""Three-layer deterministic claim grounding service."""

from __future__ import annotations

import re
from collections.abc import Sequence

from .enums import ReasonCode, VerificationStatus
from .models import (
    AtomicClaim,
    ClaimVerification,
    EvidenceContext,
    LegalReference,
    VerificationResult,
)
from .similarity import SemanticScorer, TokenCosineScorer
from .source_registry import CanonicalSourceRegistry


def _numbers(value: str) -> set[str]:
    return set(re.findall(r"\d+", value))


class CitationGuardrailService:
    def __init__(
        self,
        registry: CanonicalSourceRegistry,
        scorer: SemanticScorer | None = None,
        *,
        lower_threshold: float = 0.35,
        high_threshold: float = 0.75,
    ) -> None:
        self.registry = registry
        self.scorer = scorer or TokenCosineScorer()
        self.lower_threshold = lower_threshold
        self.high_threshold = high_threshold

    def verify(
        self,
        claims: Sequence[AtomicClaim],
        contexts: Sequence[EvidenceContext],
        *,
        out_of_scope_refusal: bool = False,
    ) -> VerificationResult:
        if out_of_scope_refusal:
            return VerificationResult(
                status=VerificationStatus.INSUFFICIENT_CONTEXT,
                claims=[],
                warnings=[ReasonCode.OUT_OF_SCOPE_REFUSAL.value],
            )
        results = [self._verify_claim(claim, contexts) for claim in claims]
        statuses = {item.status for item in results}
        if VerificationStatus.UNSUPPORTED in statuses:
            overall = VerificationStatus.UNSUPPORTED
        elif VerificationStatus.INSUFFICIENT_CONTEXT in statuses:
            overall = VerificationStatus.INSUFFICIENT_CONTEXT
        elif VerificationStatus.PARTIALLY_SUPPORTED in statuses:
            overall = VerificationStatus.PARTIALLY_SUPPORTED
        else:
            overall = VerificationStatus.SUPPORTED
        return VerificationResult(status=overall, claims=results)

    def _verify_claim(
        self, claim: AtomicClaim, contexts: Sequence[EvidenceContext]
    ) -> ClaimVerification:
        if not claim.cited_context_ids:
            return ClaimVerification(
                claim_id=claim.claim_id,
                status=VerificationStatus.INSUFFICIENT_CONTEXT,
                reason_codes=[ReasonCode.MISSING_CITATION],
            )
        evidence_by_id = {item.chunk_id: item for item in contexts}
        evidence: list[EvidenceContext] = []
        for chunk_id in dict.fromkeys(claim.cited_context_ids):
            canonical = self.registry.get(chunk_id)
            if canonical is None:
                return ClaimVerification(
                    claim_id=claim.claim_id,
                    status=VerificationStatus.UNSUPPORTED,
                    reason_codes=[ReasonCode.CITATION_NOT_FOUND],
                )
            if chunk_id not in evidence_by_id:
                return ClaimVerification(
                    claim_id=claim.claim_id,
                    status=VerificationStatus.UNSUPPORTED,
                    reason_codes=[ReasonCode.CITATION_NOT_IN_RETRIEVED_CONTEXT],
                )
            evidence.append(evidence_by_id[chunk_id])
        if any(
            not self._reference_matches(reference, evidence) for reference in claim.legal_references
        ):
            return ClaimVerification(
                claim_id=claim.claim_id,
                status=VerificationStatus.UNSUPPORTED,
                reason_codes=[ReasonCode.LEGAL_REFERENCE_MISMATCH],
                evidence_ids=[item.chunk_id for item in evidence],
            )
        claim_numbers = _numbers(claim.text)
        evidence_numbers = set().union(*(_numbers(item.content) for item in evidence))
        if claim_numbers - evidence_numbers:
            return ClaimVerification(
                claim_id=claim.claim_id,
                status=VerificationStatus.UNSUPPORTED,
                reason_codes=[ReasonCode.NUMERIC_CONTRADICTION],
                evidence_ids=[item.chunk_id for item in evidence],
            )
        score = max(self.scorer.score(claim.text, item.content) for item in evidence)
        if score >= self.high_threshold:
            return ClaimVerification(
                claim_id=claim.claim_id,
                status=VerificationStatus.SUPPORTED,
                evidence_ids=[item.chunk_id for item in evidence],
                score=score,
            )
        if score >= self.lower_threshold:
            return ClaimVerification(
                claim_id=claim.claim_id,
                status=VerificationStatus.PARTIALLY_SUPPORTED,
                reason_codes=[ReasonCode.PARTIAL_EVIDENCE],
                evidence_ids=[item.chunk_id for item in evidence],
                score=score,
            )
        return ClaimVerification(
            claim_id=claim.claim_id,
            status=VerificationStatus.UNSUPPORTED,
            reason_codes=[ReasonCode.LOW_SEMANTIC_SUPPORT],
            evidence_ids=[item.chunk_id for item in evidence],
            score=score,
        )

    @staticmethod
    def _reference_matches(reference: LegalReference, evidence: Sequence[EvidenceContext]) -> bool:
        return any(
            reference.article == item.article_number
            and (reference.clause is None or reference.clause == item.clause_number)
            and (reference.point is None or reference.point == item.point_label)
            for item in evidence
        )
