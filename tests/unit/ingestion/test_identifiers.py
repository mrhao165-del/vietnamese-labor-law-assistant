from pathlib import Path

from vietnamese_labor_law_assistant.ingestion.identifiers import (
    build_chunk_id,
    calculate_content_sha256,
    calculate_file_sha256,
)


def test_ids_and_hashes_are_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "source.txt"
    path.write_text("Nội dung", encoding="utf-8")
    identifier = build_chunk_id("law", 1, 2, None, 0, "clause")
    assert identifier == build_chunk_id("law", 1, 2, None, 0, "clause")
    assert identifier != build_chunk_id("law", 1, 3, None, 0, "clause")
    assert len(calculate_content_sha256("Nội dung")) == 64
    assert calculate_file_sha256(path) == calculate_file_sha256(path)
