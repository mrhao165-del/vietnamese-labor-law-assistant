from pathlib import Path

import pytest

from vietnamese_labor_law_assistant.guardrails.citation_parser import parse_legal_citation
from vietnamese_labor_law_assistant.guardrails.enums import ReasonCode, VerificationStatus
from vietnamese_labor_law_assistant.guardrails.models import (
    AtomicClaim,
    EvidenceContext,
    LegalReference,
)
from vietnamese_labor_law_assistant.guardrails.policy import guarded_answer
from vietnamese_labor_law_assistant.guardrails.service import CitationGuardrailService
from vietnamese_labor_law_assistant.guardrails.source_registry import CanonicalSourceRegistry

SOURCE = Path("data/processed/labor_law_clauses.jsonl")
CHUNK = "ll_6af59ba448952c1c927978713d34d984"


def service() -> CitationGuardrailService:
    return CitationGuardrailService(CanonicalSourceRegistry(SOURCE))


def evidence(content: str = "người lao động báo trước 45 ngày") -> EvidenceContext:
    return EvidenceContext(chunk_id=CHUNK, content=content, article_number=35, clause_number=1)


def test_parser_normalizes_order_unicode_and_rejects_malformed() -> None:
    parsed = parse_legal_citation("Điểm A  Khoản 1  Điều 35")
    assert parsed == LegalReference(article=35, clause=1, point="a")
    assert parse_legal_citation("Khoản một") is None


def test_supported_partial_and_policy_fail_closed() -> None:
    supported = service().verify(
        [
            AtomicClaim(
                claim_id="a", text="người lao động báo trước 45 ngày", cited_context_ids=[CHUNK]
            )
        ],
        [evidence()],
    )
    assert supported.status is VerificationStatus.SUPPORTED
    partial = service().verify(
        [
            AtomicClaim(
                claim_id="b",
                text="người lao động báo trước hợp đồng điều khoản công việc",
                cited_context_ids=[CHUNK],
            )
        ],
        [evidence("người lao động báo trước")],
    )
    assert partial.status is VerificationStatus.PARTIALLY_SUPPORTED
    assert (
        guarded_answer("hallucinated", service().verify([AtomicClaim(claim_id="c", text="x")], []))[
            0
        ]
        != "hallucinated"
    )


@pytest.mark.parametrize(
    ("claim", "contexts", "reason"),
    [
        (AtomicClaim(claim_id="a", text="x"), [], ReasonCode.MISSING_CITATION),
        (
            AtomicClaim(claim_id="a", text="x", cited_context_ids=["unknown"]),
            [],
            ReasonCode.CITATION_NOT_FOUND,
        ),
        (
            AtomicClaim(claim_id="a", text="x", cited_context_ids=[CHUNK]),
            [],
            ReasonCode.CITATION_NOT_IN_RETRIEVED_CONTEXT,
        ),
        (
            AtomicClaim(
                claim_id="a",
                text="người lao động báo trước",
                cited_context_ids=[CHUNK],
                legal_references=[LegalReference(article=35, clause=2)],
            ),
            [evidence("người lao động báo trước")],
            ReasonCode.LEGAL_REFERENCE_MISMATCH,
        ),
        (
            AtomicClaim(
                claim_id="a", text="người lao động báo trước 99 ngày", cited_context_ids=[CHUNK]
            ),
            [evidence()],
            ReasonCode.NUMERIC_CONTRADICTION,
        ),
    ],
)
def test_failure_reason_codes(
    claim: AtomicClaim, contexts: list[EvidenceContext], reason: ReasonCode
) -> None:
    result = service().verify([claim], contexts)
    assert result.status in {
        VerificationStatus.UNSUPPORTED,
        VerificationStatus.INSUFFICIENT_CONTEXT,
    }
    assert reason in result.claims[0].reason_codes


def test_out_of_scope_is_safe_refusal() -> None:
    result = service().verify([], [], out_of_scope_refusal=True)
    assert result.status is VerificationStatus.INSUFFICIENT_CONTEXT
    assert ReasonCode.OUT_OF_SCOPE_REFUSAL.value in result.warnings
