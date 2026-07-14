from datetime import date
from pathlib import Path

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.ingestion.identifiers import calculate_content_sha256
from vietnamese_labor_law_assistant.ingestion.models import LegalChunk
from vietnamese_labor_law_assistant.retrieval import qdrant_store
from vietnamese_labor_law_assistant.retrieval.qdrant_store import QdrantStore, build_qdrant_point_id


def _chunk() -> LegalChunk:
    return LegalChunk(
        chunk_id="stable",
        document_id="law",
        document_name="Law",
        article_number=1,
        content="Nội dung",
        data_snapshot_date=date(2026, 1, 1),
        source_file="x",
        source_block_start=0,
        source_block_end=0,
        content_sha256=calculate_content_sha256("Nội dung"),
    )


def test_local_persistent_qdrant_upsert_is_idempotent(tmp_path: Path) -> None:
    settings = Settings(
        qdrant_mode="local", qdrant_local_path=tmp_path / "qdrant", qdrant_collection="test"
    )
    store = QdrantStore(settings)
    store.ensure_collection(2)
    chunk = _chunk()
    store.upsert_points([chunk], [[1.0, 0.0]], "a" * 64)
    store.upsert_points([chunk], [[1.0, 0.0]], "a" * 64)
    assert store.count_points() == 1
    payload = store.get_by_chunk_id("stable")
    assert payload is not None
    assert payload["article_number"] == 1
    assert build_qdrant_point_id("stable") == build_qdrant_point_id("stable")
    assert store.get_point_id_by_chunk_id("stable") == build_qdrant_point_id("stable")


def test_remote_qdrant_factory_uses_configured_url(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(qdrant_store, "QdrantClient", FakeClient)
    QdrantStore(Settings(qdrant_mode="remote", qdrant_url="http://127.0.0.1:6333"))
    assert captured["url"] == "http://127.0.0.1:6333"
