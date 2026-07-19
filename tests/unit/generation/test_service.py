from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.generation.models import AnswerClaim, AnswerDraft
from vietnamese_labor_law_assistant.generation.service import DenseRagService
from vietnamese_labor_law_assistant.retrieval.models import DenseSearchResult, RetrievedChunk


class FakeRetriever:
    def search(self, query: str, top_k: int):
        chunk = RetrievedChunk(
            rank=1,
            score=0.9,
            chunk_id="one",
            document_id="law",
            document_name="Law",
            article_number=1,
            content="Nội dung",
            source_file="x",
            source_block_start=0,
            source_block_end=0,
            content_sha256="a" * 64,
        )
        return DenseSearchResult(
            query=query,
            results=[chunk],
            latency_ms=1,
            embedding_latency_ms=0,
            qdrant_latency_ms=1,
            collection_name="test",
            embedding_model="fake",
        )


class FakeGenerator:
    def generate(self, question: str, contexts):
        return AnswerDraft(
            claims=[AnswerClaim(claim_id="CLM-001", text="Trả lời", context_ids=["CTX-001"])]
        )


def test_service_formats_cited_answer() -> None:
    response = DenseRagService(FakeRetriever(), FakeGenerator(), Settings()).query("Câu hỏi")
    assert "Điều 1" in response.answer
    assert response.citations[0].source_endpoint == "/api/v1/sources/one"
