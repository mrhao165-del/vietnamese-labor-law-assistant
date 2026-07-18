"""Safe response policy derived from an aggregate verification result."""

from __future__ import annotations

from .enums import VerificationStatus
from .models import VerificationResult


def guarded_answer(answer: str, verification: VerificationResult) -> tuple[str, list[str]]:
    if verification.status is VerificationStatus.SUPPORTED:
        return answer, verification.warnings
    if verification.status is VerificationStatus.PARTIALLY_SUPPORTED:
        return answer, [*verification.warnings, "PARTIAL_EVIDENCE_WARNING"]
    return "INSUFFICIENT_VERIFIED_EVIDENCE", [
        *verification.warnings,
        "FAIL_CLOSED_GUARDRAIL",
    ]
