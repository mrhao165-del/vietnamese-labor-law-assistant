import pytest

from vietnamese_labor_law_assistant.generation.citations import (
    CitationValidationError,
    display_label,
    validate_answer_draft,
)
from vietnamese_labor_law_assistant.generation.models import AnswerClaim, AnswerDraft
from vietnamese_labor_law_assistant.retrieval.models import RetrievedChunk


def _chunk() -> RetrievedChunk:
    return RetrievedChunk(
        rank=1,
        score=0.9,
        chunk_id="one",
        document_id="law",
        document_name="Law",
        article_number=35,
        clause_number=1,
        point_label="a",
        content="Nội dung",
        source_file="x",
        source_block_start=0,
        source_block_end=1,
        content_sha256="a" * 64,
    )


def test_citation_validation_and_display() -> None:
    context = {"CTX-001": _chunk()}
    draft = AnswerDraft(claims=[AnswerClaim(text="Nội dung", context_ids=["CTX-001", "CTX-001"])])
    assert validate_answer_draft(draft, context).claims[0].context_ids == ["CTX-001"]
    assert display_label(_chunk()) == "Điều 35, Khoản 1, Điểm a"
    with pytest.raises(CitationValidationError):
        validate_answer_draft(
            AnswerDraft(claims=[AnswerClaim(text="x", context_ids=["CTX-999"])]), context
        )
