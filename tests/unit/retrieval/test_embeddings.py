from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.retrieval.embeddings import (
    BgeM3EmbeddingProvider,
    resolve_device,
)


class FakeModel:
    def encode(self, texts: list[str], **kwargs: object) -> dict[str, list[list[float]]]:
        return {"dense_vecs": [[1.0, 0.0] for _ in texts]}


def test_embedding_provider_reads_dense_vectors_without_loading_model() -> None:
    provider = BgeM3EmbeddingProvider(Settings(), model=FakeModel())
    assert provider.embed_documents(["a", "b"]) == [[1.0, 0.0], [1.0, 0.0]]
    assert provider.dimension == 2
    assert provider.embed_query("q") == [1.0, 0.0]


def test_device_policy() -> None:
    assert resolve_device(Settings(embedding_device="auto"), False) == "cpu"
    assert resolve_device(Settings(embedding_device="cpu"), True) == "cpu"
