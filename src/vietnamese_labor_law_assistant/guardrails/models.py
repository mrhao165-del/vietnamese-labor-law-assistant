"""Typed inputs and outputs for the fail-closed guardrail."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .enums import ReasonCode, VerificationStatus


class LegalReference(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    article: int = Field(gt=0)
    clause: int | None = Field(default=None, gt=0)
    point: str | None = Field(default=None, min_length=1, max_length=8)


class EvidenceContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chunk_id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    article_number: int = Field(gt=0)
    clause_number: int | None = Field(default=None, gt=0)
    point_label: str | None = None
    source_kind: str = "retrieval"


class AtomicClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=6000)
    cited_context_ids: list[str] = Field(default_factory=list, max_length=10)
    legal_references: list[LegalReference] = Field(default_factory=list, max_length=10)


class ClaimVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_id: str
    status: VerificationStatus
    reason_codes: list[ReasonCode] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    score: float | None = Field(default=None, ge=0, le=1)


class VerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: VerificationStatus
    claims: list[ClaimVerification] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
