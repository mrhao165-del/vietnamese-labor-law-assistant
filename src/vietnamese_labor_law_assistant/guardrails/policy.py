"""Safe response policy derived from an aggregate verification result."""

from __future__ import annotations

from .enums import VerificationStatus
from .models import AtomicClaim, VerificationResult


def guarded_answer(
    answer: str,
    verification: VerificationResult,
    claims: list[AtomicClaim] | None = None,
) -> tuple[str, list[str]]:
    if verification.status is VerificationStatus.SUPPORTED:
        return answer, verification.warnings
    if verification.status is VerificationStatus.PARTIALLY_SUPPORTED:
        outcomes = {item.claim_id: item.status for item in verification.claims}
        safe_parts = [
            claim.text
            if outcomes.get(claim.claim_id) is VerificationStatus.SUPPORTED
            else f"Chưa được xác minh đầy đủ: {claim.text}"
            for claim in claims or []
            if outcomes.get(claim.claim_id)
            in {VerificationStatus.SUPPORTED, VerificationStatus.PARTIALLY_SUPPORTED}
        ]
        return "\n\n".join(safe_parts) or "INSUFFICIENT_VERIFIED_EVIDENCE", [
            *verification.warnings,
            "PARTIAL_EVIDENCE_WARNING",
        ]
    return "INSUFFICIENT_VERIFIED_EVIDENCE", [
        *verification.warnings,
        "FAIL_CLOSED_GUARDRAIL",
    ]
