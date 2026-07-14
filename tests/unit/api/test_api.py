import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from vietnamese_labor_law_assistant.api import main as api_main
from vietnamese_labor_law_assistant.api.dependencies import get_rag_service, get_store
from vietnamese_labor_law_assistant.api.main import create_app
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
        return AnswerDraft(claims=[AnswerClaim(text="Trả lời", context_ids=["CTX-001"])])


class FakeStore:
    def get_by_chunk_id(self, chunk_id: str):
        return (
            {"chunk_id": chunk_id, "article_number": 1, "content": "Nội dung"}
            if chunk_id == "one"
            else None
        )


def test_api_health_query_and_source() -> None:
    settings = Settings(openai_api_key=SecretStr("test"), llm_model="configured")
    app = create_app(settings)
    app.dependency_overrides[get_rag_service] = lambda: DenseRagService(
        FakeRetriever(), FakeGenerator(), settings
    )
    app.dependency_overrides[get_store] = FakeStore
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        response = client.post("/api/v1/query", json={"question": "Câu hỏi"})
        assert response.status_code == 200
        assert response.headers["X-Request-ID"]
        assert client.get("/api/v1/sources/one").status_code == 200
        assert client.get("/api/v1/sources/missing").status_code == 404
        assert client.post("/api/v1/query", json={"question": "   "}).status_code == 422


def test_api_ready_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        api_main,
        "readiness",
        lambda settings: {
            "settings_valid": True,
            "qdrant_ready": True,
            "embedding_ready": True,
            "llm_configured": True,
        },
    )
    with TestClient(create_app(Settings())) as client:
        response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["ready"] is True


def test_api_rejects_benchmark_only_retrieval_mode() -> None:
    with pytest.raises(ValueError, match="not wired into the production API"):
        create_app(Settings(retrieval_mode="hybrid_underthesea_rerank"))
