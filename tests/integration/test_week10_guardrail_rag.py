"""Offline RAG proof: retrieval -> atomic generation -> guardrail -> safe response."""

from collections.abc import Sequence
from pathlib import Path

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.generation.models import AnswerClaim, AnswerDraft
from vietnamese_labor_law_assistant.generation.service import RagService
from vietnamese_labor_law_assistant.guardrails.service import CitationGuardrailService
from vietnamese_labor_law_assistant.guardrails.source_registry import CanonicalSourceRegistry
from vietnamese_labor_law_assistant.ingestion.models import LegalChunk
from vietnamese_labor_law_assistant.retrieval.models import DenseSearchResult, RetrievedChunk

SOURCE = Path("data/processed/labor_law_clauses.jsonl")
CHUNK_ID = "ll_6af59ba448952c1c927978713d34d984"


def canonical_record() -> LegalChunk:
    record = CanonicalSourceRegistry(SOURCE).get(CHUNK_ID)
    if record is not None:
        return record
    raise RuntimeError("canonical fixture is missing")


RECORD = canonical_record()


class Retriever:
    def search(self, query: str, top_k: int) -> DenseSearchResult:
        del top_k
        return DenseSearchResult(
            query=query,
            results=[
                RetrievedChunk(
                    rank=1,
                    score=1,
                    chunk_id=CHUNK_ID,
                    document_id="labor-law",
                    document_name="Bộ luật Lao động",
                    article_number=RECORD.article_number,
                    clause_number=RECORD.clause_number,
                    point_label=RECORD.point_label,
                    content=RECORD.content,
                    source_file="labor_law.docx",
                    source_block_start=1,
                    source_block_end=1,
                    content_sha256="a" * 64,
                )
            ],
            latency_ms=1,
            embedding_latency_ms=0,
            qdrant_latency_ms=1,
            collection_name="fixture",
            embedding_model="fixture",
        )


class Generator:
    def __init__(self, claims: list[AnswerClaim]) -> None:
        self.claims = claims

    def generate(self, question: str, contexts: Sequence[RetrievedChunk]) -> AnswerDraft:
        del question, contexts
        return AnswerDraft(claims=self.claims)


class Scorer:
    def score(self, claim: str, evidence: str) -> float:
        del evidence
        return 0.9 if "đúng" in claim else 0.1


def service(claims: list[AnswerClaim]) -> RagService:
    guardrail = CitationGuardrailService(
        CanonicalSourceRegistry(SOURCE), Scorer(), lower_threshold=0.35, high_threshold=0.75
    )
    return RagService(Retriever(), Generator(claims), Settings(), guardrail)


def test_rag_verifies_multiple_atomic_claims_and_keeps_valid_citation() -> None:
    response = service(
        [
            AnswerClaim(
                claim_id="CLM-001", text="Nội dung đúng theo Điều 35", context_ids=["CTX-001"]
            ),
            AnswerClaim(claim_id="CLM-002", text="Một ý đúng khác", context_ids=["CTX-001"]),
        ]
    ).query("quy định gì?")
    assert response.verification and response.verification["status"] == "SUPPORTED"
    assert len(response.verification["claims"]) == 2
    assert [item["claim_id"] for item in response.verification["claims"]] == ["CLM-001", "CLM-002"]
    assert [item.chunk_id for item in response.citations] == [CHUNK_ID]
    assert "Nội dung đúng" in response.answer


def test_rag_blocks_hallucinated_claim_instead_of_returning_original_answer() -> None:
    hallucination = "Nội dung bịa đặt không được nguồn hỗ trợ"
    response = service(
        [
            AnswerClaim(claim_id="CLM-001", text="Một ý đúng", context_ids=["CTX-001"]),
            AnswerClaim(claim_id="CLM-002", text=hallucination, context_ids=["CTX-001"]),
        ]
    ).query("quy định gì?")
    assert response.verification and response.verification["status"] == "UNSUPPORTED"
    assert response.answer == "INSUFFICIENT_VERIFIED_EVIDENCE"
    assert hallucination not in response.answer
    assert response.citations == []
