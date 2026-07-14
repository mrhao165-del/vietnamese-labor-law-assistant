from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from vietnamese_labor_law_assistant.ingestion.identifiers import calculate_content_sha256
from vietnamese_labor_law_assistant.ingestion.models import LegalArticle, LegalChunk


def _chunk(**changes: object) -> LegalChunk:
    data: dict[str, Any] = {
        "chunk_id": "chunk",
        "document_id": "law",
        "document_name": "Law",
        "article_number": 1,
        "content": "Nội dung",
        "data_snapshot_date": date(2026, 1, 1),
        "source_file": "data/raw/law.docx",
        "source_block_start": 1,
        "source_block_end": 1,
        "content_sha256": calculate_content_sha256("Nội dung"),
    }
    data.update(changes)
    return LegalChunk(**data)


def test_model_validations() -> None:
    assert _chunk(point_label="Đ").point_label == "đ"
    with pytest.raises(ValidationError):
        _chunk(content="")
    with pytest.raises(ValidationError):
        _chunk(article_number=0)
    with pytest.raises(ValidationError):
        _chunk(clause_number=0)
    with pytest.raises(ValidationError):
        _chunk(source_block_start=2, source_block_end=1)
    with pytest.raises(ValidationError):
        _chunk(content_sha256="bad")
    with pytest.raises(ValidationError):
        LegalArticle(
            document_id="law",
            document_name="Law",
            article_number=1,
            content="x",
            clause_count=0,
            point_count=0,
            source_file="source",
            source_block_start=1,
            source_block_end=1,
            content_sha256="bad",
        )
