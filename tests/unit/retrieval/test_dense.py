from collections.abc import Sequence

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.retrieval.dense import DenseRetriever


class FakeEmbeddings:
    dimension = 2

    def ensure_available(self) -> None:
        return None

    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


class FakePoint:
    def __init__(self, score: float, payload: dict):
        self.score, self.payload = score, payload


class FakeStore:
    collection_name = "test"

    def query_dense(self, *args: object):
        return [
            FakePoint(
                0.9,
                {
                    "chunk_id": "one",
                    "document_id": "law",
                    "document_name": "Law",
                    "article_number": 1,
                    "content": "Nội dung",
                    "source_file": "x",
                    "source_block_start": 0,
                    "source_block_end": 0,
                    "content_sha256": "a" * 64,
                },
            )
        ]


def test_dense_retriever_maps_payload_and_rejects_invalid_top_k() -> None:
    retriever = DenseRetriever(FakeEmbeddings(), FakeStore(), Settings())
    result = retriever.search("câu hỏi")
    assert result.results[0].rank == 1
    assert result.results[0].article_number == 1
