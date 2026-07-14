import json
from pathlib import Path

import pytest

from vietnamese_labor_law_assistant.ingestion.chunking import build_articles, build_chunks
from vietnamese_labor_law_assistant.ingestion.identifiers import calculate_file_sha256
from vietnamese_labor_law_assistant.ingestion.models import SourceMetadata
from vietnamese_labor_law_assistant.ingestion.parser import LegalDocumentParser
from vietnamese_labor_law_assistant.ingestion.validation import validate_ingestion
from vietnamese_labor_law_assistant.ingestion.writers import (
    write_articles_jsonl,
    write_chunks_jsonl,
)


@pytest.mark.integration
def test_real_docx_outputs_are_reproducible(tmp_path: Path) -> None:
    source = Path("data/raw/labor_law.docx")
    if not source.exists():
        pytest.skip("real DOCX source is not available")
    metadata = SourceMetadata.model_validate_json(
        Path("data/raw/source_metadata.json").read_text(encoding="utf-8")
    )
    parsed = LegalDocumentParser().parse_docx(source)
    articles = build_articles(parsed, metadata)
    chunks = build_chunks(parsed, metadata)
    first_articles = tmp_path / "first_articles.jsonl"
    first_chunks = tmp_path / "first_chunks.jsonl"
    second_articles = tmp_path / "second_articles.jsonl"
    second_chunks = tmp_path / "second_chunks.jsonl"
    write_articles_jsonl(first_articles, articles)
    write_chunks_jsonl(first_chunks, chunks)
    write_articles_jsonl(second_articles, build_articles(parsed, metadata))
    write_chunks_jsonl(second_chunks, build_chunks(parsed, metadata))
    assert first_articles.read_bytes() == second_articles.read_bytes()
    assert first_chunks.read_bytes() == second_chunks.read_bytes()
    assert articles and chunks
    report = validate_ingestion(
        parsed, articles, chunks, calculate_file_sha256(source), metadata.source_file
    )
    repeated_report = validate_ingestion(
        parsed,
        build_articles(parsed, metadata),
        build_chunks(parsed, metadata),
        calculate_file_sha256(source),
        metadata.source_file,
    )
    assert report.empty_chunk_count == 0
    assert report.duplicate_chunk_id_count == 0
    assert report.status == "PASS"
    first = report.model_dump(mode="json")
    second = repeated_report.model_dump(mode="json")
    first.pop("generated_at")
    second.pop("generated_at")
    assert json.dumps(first, ensure_ascii=False, sort_keys=True) == json.dumps(
        second, ensure_ascii=False, sort_keys=True
    )
