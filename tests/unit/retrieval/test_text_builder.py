from datetime import date

from vietnamese_labor_law_assistant.ingestion.identifiers import calculate_content_sha256
from vietnamese_labor_law_assistant.ingestion.models import LegalChunk
from vietnamese_labor_law_assistant.retrieval.text_builder import build_embedding_text


def test_embedding_text_preserves_legal_metadata_and_vietnamese() -> None:
    chunk = LegalChunk(
        chunk_id="one",
        document_id="law",
        document_name="Bộ luật Lao động",
        chapter_number="I",
        chapter_title="Quy định chung",
        article_number=35,
        article_title="Chấm dứt hợp đồng",
        clause_number=1,
        point_labels=["a", "đ"],
        content="Người lao động được quyền.",
        data_snapshot_date=date(2026, 1, 1),
        source_file="source.docx",
        source_block_start=1,
        source_block_end=2,
        content_sha256=calculate_content_sha256("Người lao động được quyền."),
        chunk_type="clause",
    )
    text = build_embedding_text(chunk)
    assert "Điều 35: Chấm dứt hợp đồng" in text
    assert "Điểm: a, đ" in text
    assert text.endswith("Người lao động được quyền.")
