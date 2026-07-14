from datetime import date
from pathlib import Path

from vietnamese_labor_law_assistant.ingestion.identifiers import calculate_content_sha256
from vietnamese_labor_law_assistant.ingestion.models import LegalChunk
from vietnamese_labor_law_assistant.ingestion.writers import read_chunks_jsonl, write_chunks_jsonl


def test_jsonl_round_trip_is_utf8_and_deterministic(tmp_path: Path) -> None:
    chunk = LegalChunk(
        chunk_id="one",
        document_id="law",
        document_name="Luật",
        article_number=1,
        content="Người lao động",
        data_snapshot_date=date(2026, 1, 1),
        source_file="source.docx",
        source_block_start=0,
        source_block_end=0,
        content_sha256=calculate_content_sha256("Người lao động"),
    )
    path = tmp_path / "chunks.jsonl"
    write_chunks_jsonl(path, [chunk])
    first = path.read_bytes()
    assert read_chunks_jsonl(path) == [chunk]
    write_chunks_jsonl(path, [chunk])
    assert path.read_bytes() == first
