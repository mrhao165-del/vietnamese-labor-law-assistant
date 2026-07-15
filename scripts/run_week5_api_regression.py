"""Exercise Week 5 API routes with deterministic in-process dependencies."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from fastapi.testclient import TestClient
from pydantic import SecretStr

from vietnamese_labor_law_assistant.api import main as api_main
from vietnamese_labor_law_assistant.api.dependencies import (
    ensure_supported_production_retrieval_mode,
    get_rag_service,
    get_store,
)
from vietnamese_labor_law_assistant.api.main import create_app
from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.generation.models import AnswerClaim, AnswerDraft
from vietnamese_labor_law_assistant.generation.service import DenseRagService
from vietnamese_labor_law_assistant.retrieval.models import DenseSearchResult, RetrievedChunk

ROOT = Path(__file__).resolve().parents[1]


class Store:
    def get_by_chunk_id(self, chunk_id: str):
        return (
            {"chunk_id": "one", "article_number": 1, "content": "Nguồn"}
            if chunk_id == "one"
            else None
        )


class Retriever:
    def __init__(self, source: str, empty: bool = False) -> None:
        self.source = source
        self.empty = empty

    def search(self, query: str, top_k: int) -> DenseSearchResult:
        results = []
        if not self.empty:
            results = [
                RetrievedChunk(
                    rank=1,
                    score=0.9,
                    chunk_id="one",
                    document_id="law",
                    document_name="Labor Law",
                    article_number=1,
                    content="Nội dung nguồn.",
                    source_file="law.docx",
                    source_block_start=1,
                    source_block_end=1,
                    content_sha256="a" * 64,
                    retrieval_source=self.source,
                )
            ]
        return DenseSearchResult(
            query=query,
            results=results,
            latency_ms=1.0,
            embedding_latency_ms=0.0,
            qdrant_latency_ms=1.0,
            collection_name=self.source,
            embedding_model="test",
        )


class Generator:
    def generate(self, question: str, contexts: Sequence[RetrievedChunk]) -> AnswerDraft:
        return AnswerDraft(
            claims=[AnswerClaim(text="Trả lời có trích dẫn.", context_ids=["CTX-001"])]
        )


def client_for(
    mode: Literal["dense", "dense_rerank", "hybrid_underthesea_rerank"],
    enabled: bool,
    source: str,
    empty: bool = False,
) -> TestClient:
    settings = Settings(
        retrieval_mode=mode,
        reranker_enabled=enabled,
        openai_api_key=SecretStr("test"),
        llm_model="test-model",
    )
    app = create_app(settings)
    app.dependency_overrides[get_rag_service] = lambda: DenseRagService(
        Retriever(source, empty), Generator(), settings
    )
    app.dependency_overrides[get_store] = Store
    return TestClient(app)


def main() -> int:
    api_main.readiness = lambda _settings: {
        "settings_valid": True,
        "qdrant_ready": True,
        "embedding_ready": True,
        "llm_configured": True,
    }
    results: dict[str, object] = {}
    with client_for("dense", False, "dense") as client:
        results["health"] = client.get("/health").status_code
        results["ready"] = client.get("/ready").status_code
        disabled = client.post(
            "/api/v1/query", json={"question": "Câu hỏi", "include_contexts": True}
        )
        results["reranker_disabled"] = disabled.status_code
        results["citation"] = len(disabled.json()["citations"])
        results["source_endpoint"] = client.get("/api/v1/sources/one").status_code
    # Benchmark-only rerank modes must remain unavailable in the production API before Week 6.
    for mode in ("dense_rerank", "hybrid_underthesea_rerank"):
        try:
            ensure_supported_production_retrieval_mode(
                Settings(retrieval_mode=mode, reranker_enabled=True)
            )
        except ValueError:
            results[f"{mode}_rejected_pre_week6"] = True
        else:
            results[f"{mode}_rejected_pre_week6"] = False
    """
    with client_for("dense_rerank", True, "rerank") as client:
        results["dense_rerank"] = client.post(
            "/api/v1/query", json={"question": "Câu hỏi"}
        ).status_code
    with client_for("hybrid_underthesea_rerank", True, "rerank") as client:
        results["h2_rerank"] = client.post(
            "/api/v1/query", json={"question": "Câu hỏi"}
        ).status_code
    """
    with client_for("dense", False, "dense", empty=True) as client:
        response = client.post("/api/v1/query", json={"question": "Ngoài phạm vi"})
        results["out_of_scope"] = response.status_code
        results["out_of_scope_insufficient_context"] = response.json()["insufficient_context"]
    expected = {
        "health": 200,
        "ready": 200,
        "reranker_disabled": 200,
        "out_of_scope": 200,
        "source_endpoint": 200,
    }
    for name, status in expected.items():
        if results[name] != status:
            raise RuntimeError(f"API regression failed: {name} returned {results[name]}")
    if (
        not results["dense_rerank_rejected_pre_week6"]
        or not results["hybrid_underthesea_rerank_rejected_pre_week6"]
    ):
        raise RuntimeError("API regression failed: benchmark-only modes must remain rejected")
    if results["citation"] != 1 or not results["out_of_scope_insufficient_context"]:
        raise RuntimeError("API regression failed: citation or out-of-scope behavior")
    report = {
        "status": "PASS",
        "results": results,
        "api_lifecycle": "TestClient exited; no API process remains.",
    }
    path = ROOT / "evaluation/results/week5_api_regression.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
