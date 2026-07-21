"""Three-layer deterministic claim grounding service."""

from __future__ import annotations

import re
from collections.abc import Sequence

import structlog

from .citation_parser import parse_citations
from .enums import ReasonCode, VerificationStatus
from .judge import JudgeInvalidOutputError, JudgeUnavailableError, StructuredJudge
from .models import (
    AtomicClaim,
    ClaimVerification,
    EvidenceContext,
    LegalReference,
    VerificationResult,
)
from .similarity import BatchSemanticScorer, SemanticScorer, TokenCosineScorer
from .source_registry import CanonicalSourceRegistry


def _numbers(value: str) -> set[str]:
    return set(re.findall(r"\d+", value))


class CitationGuardrailService:
    def __init__(
        self,
        registry: CanonicalSourceRegistry,
        scorer: SemanticScorer | None = None,
        *,
        judge: StructuredJudge | None = None,
        lower_threshold: float = 0.35,
        high_threshold: float = 0.75,
    ) -> None:
        self.registry = registry
        self.scorer = scorer or TokenCosineScorer()
        self.judge = judge
        self.lower_threshold = lower_threshold
        self.high_threshold = high_threshold
        self.logger = structlog.get_logger(__name__)

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
        if not claims:
            return VerificationResult(
                status=VerificationStatus.INSUFFICIENT_CONTEXT,
                warnings=[ReasonCode.MISSING_CITATION.value],
            )
        semantic_scores = self._semantic_scores(claims, contexts)
        results = [self._verify_claim(claim, contexts, semantic_scores) for claim in claims]
        for item in results:
            self.logger.info(
                "guardrail_claim_verified",
                claim_id=item.claim_id,
                cited_evidence_ids=item.evidence_ids,
                status=item.status.value,
                reason_codes=[code.value for code in item.reason_codes],
                score=item.score,
            )
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

    def _semantic_scores(
        self, claims: Sequence[AtomicClaim], contexts: Sequence[EvidenceContext]
    ) -> dict[tuple[str, str], float] | None:
        """Use a single dense matrix whenever the scorer supports batching."""
        if not isinstance(self.scorer, BatchSemanticScorer):
            return None
        unique_contexts = list(dict.fromkeys(item.content for item in contexts))
        scores = self.scorer.score_matrix([claim.text for claim in claims], unique_contexts)
        return {
            (claim.text, context): scores[claim_index][context_index]
            for claim_index, claim in enumerate(claims)
            for context_index, context in enumerate(unique_contexts)
        }

    def _verify_claim(
        self,
        claim: AtomicClaim,
        contexts: Sequence[EvidenceContext],
        semantic_scores: dict[tuple[str, str], float] | None = None,
    ) -> ClaimVerification:
        parsed = parse_citations(claim.text)
        duplicate_citation = parsed.duplicate_count > 0 or len(claim.cited_context_ids) != len(
            set(claim.cited_context_ids)
        )
        if parsed.malformed:
            return ClaimVerification(
                claim_id=claim.claim_id,
                status=VerificationStatus.UNSUPPORTED,
                reason_codes=[ReasonCode.MALFORMED_CITATION],
            )
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
        references = list(
            {
                (item.article, item.clause, item.point): item
                for item in [*claim.legal_references, *parsed.references]
            }.values()
        )
        if any(not self._reference_matches(reference, evidence) for reference in references):
            return ClaimVerification(
                claim_id=claim.claim_id,
                status=VerificationStatus.UNSUPPORTED,
                reason_codes=[ReasonCode.LEGAL_REFERENCE_MISMATCH],
                evidence_ids=[item.chunk_id for item in evidence],
            )
        claim_numbers = _numbers(claim.text)
        evidence_numbers = set().union(*(_numbers(item.content) for item in evidence))
        evidence_numbers.update(str(item.article_number) for item in evidence)
        evidence_numbers.update(
            str(item.clause_number) for item in evidence if item.clause_number is not None
        )
        if claim_numbers - evidence_numbers:
            return ClaimVerification(
                claim_id=claim.claim_id,
                status=VerificationStatus.UNSUPPORTED,
                reason_codes=[ReasonCode.NUMERIC_CONTRADICTION],
                evidence_ids=[item.chunk_id for item in evidence],
            )
        score = max(
            (
                semantic_scores[(claim.text, item.content)]
                if semantic_scores is not None
                else self.scorer.score(claim.text, item.content)
            )
            for item in evidence
        )
        if score >= self.high_threshold:
            return ClaimVerification(
                claim_id=claim.claim_id,
                status=VerificationStatus.SUPPORTED,
                reason_codes=[ReasonCode.DUPLICATE_CITATION] if duplicate_citation else [],
                evidence_ids=[item.chunk_id for item in evidence],
                score=score,
            )
        if score >= self.lower_threshold and self.judge is not None:
            try:
                decision = self.judge.judge(claim, evidence)
            except JudgeInvalidOutputError:
                return ClaimVerification(
                    claim_id=claim.claim_id,
                    status=VerificationStatus.INSUFFICIENT_CONTEXT,
                    reason_codes=[ReasonCode.JUDGE_INVALID_OUTPUT],
                    evidence_ids=[item.chunk_id for item in evidence],
                    score=score,
                )
            except (JudgeUnavailableError, TimeoutError, RuntimeError):
                return ClaimVerification(
                    claim_id=claim.claim_id,
                    status=VerificationStatus.INSUFFICIENT_CONTEXT,
                    reason_codes=[ReasonCode.JUDGE_UNAVAILABLE],
                    evidence_ids=[item.chunk_id for item in evidence],
                    score=score,
                )
            judge_reasons: list[ReasonCode] = []
            if decision.status is VerificationStatus.PARTIALLY_SUPPORTED:
                judge_reasons = [ReasonCode.PARTIAL_EVIDENCE]
            elif decision.status is VerificationStatus.UNSUPPORTED:
                judge_reasons = [ReasonCode.LOW_SEMANTIC_SUPPORT]
            return ClaimVerification(
                claim_id=claim.claim_id,
                status=decision.status,
                reason_codes=judge_reasons,
                evidence_ids=[item.chunk_id for item in evidence],
                score=score,
            )
        if score >= self.lower_threshold:
            reasons = [ReasonCode.PARTIAL_EVIDENCE]
            if duplicate_citation:
                reasons.append(ReasonCode.DUPLICATE_CITATION)
            return ClaimVerification(
                claim_id=claim.claim_id,
                status=VerificationStatus.PARTIALLY_SUPPORTED,
                reason_codes=reasons,
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
            and (
                reference.point is None
                or reference.point == item.point_label
                or reference.point in item.point_labels
            )
            for item in evidence
        )
