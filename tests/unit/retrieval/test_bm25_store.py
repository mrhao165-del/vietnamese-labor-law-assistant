from datetime import date
from pathlib import Path

import pytest

from vietnamese_labor_law_assistant.ingestion.models import LegalChunk
from vietnamese_labor_law_assistant.retrieval.bm25_store import Bm25Store
from vietnamese_labor_law_assistant.retrieval.lexical_tokenizers import WhitespaceTokenizer


def chunk(chunk_id: str, content: str) -> LegalChunk:
    return LegalChunk(
        chunk_id=chunk_id,
        document_id="law",
        document_name="Luật",
        article_number=35,
        clause_number=1,
        content=content,
        source_file="x",
        data_snapshot_date=date.today(),
        source_block_start=0,
        source_block_end=0,
        content_sha256="a" * 64,
        chunk_type="clause",
    )


def test_bm25_build_save_load_and_search_in_temp_directory(tmp_path: Path) -> None:
    path = tmp_path / "bm25"
    original = Bm25Store(
        path,
        WhitespaceTokenizer(),
        [chunk("a", "Điều 35 người lao động"), chunk("b", "tiền lương")],
    )
    original.build()
    original.save({"version": "test"})
    restored = Bm25Store(path, WhitespaceTokenizer())
    restored.load()
    hits = restored.search("Điều 35", 2)
    assert restored.count() == 2 and hits[0][0].chunk_id == "a"
    assert (path / "manifest.json").exists() and (path / "chunks.json").exists()


def test_bm25_requires_index_before_save_or_search(tmp_path: Path) -> None:
    store = Bm25Store(tmp_path / "x", WhitespaceTokenizer())
    with pytest.raises(RuntimeError):
        store.save({})
    with pytest.raises(RuntimeError):
        store.search("Điều", 1)
