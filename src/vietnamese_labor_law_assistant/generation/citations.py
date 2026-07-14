"""Server-owned citation validation and formatting for retrieved legal contexts."""

from __future__ import annotations

from collections.abc import Mapping

from vietnamese_labor_law_assistant.retrieval.models import RetrievedChunk

from .models import AnswerDraft, CitationResponse


class CitationValidationError(ValueError):
    """Raised when an LLM claim references invalid or missing retrieved contexts."""


def display_label(chunk: RetrievedChunk) -> str:
    """Build a human-readable legal citation exclusively from retrieved metadata."""
    label = f"Điều {chunk.article_number}"
    if chunk.clause_number:
        label += f", Khoản {chunk.clause_number}"
    if chunk.point_label:
        label += f", Điểm {chunk.point_label}"
    return label


def build_source_endpoint(chunk_id: str) -> str:
    return f"/api/v1/sources/{chunk_id}"


def validate_answer_draft(
    draft: AnswerDraft, context_map: Mapping[str, RetrievedChunk]
) -> AnswerDraft:
    """Reject uncited legal claims and unknown context IDs without guessing citations."""
    for claim in draft.claims:
        if not claim.text.strip():
            raise CitationValidationError("Claim text is empty")
        claim.context_ids[:] = list(dict.fromkeys(claim.context_ids))
        if not draft.insufficient_context and not claim.context_ids:
            raise CitationValidationError("Legal claim has no context citation")
        unknown = set(claim.context_ids).difference(context_map)
        if unknown:
            raise CitationValidationError(f"Unknown context IDs: {sorted(unknown)}")
    return draft


def build_citations(
    draft: AnswerDraft, context_map: Mapping[str, RetrievedChunk]
) -> list[CitationResponse]:
    """Map valid context references to citations; metadata never comes from the LLM."""
    citations: list[CitationResponse] = []
    seen: set[str] = set()
    for claim in draft.claims:
        for context_id in claim.context_ids:
            if context_id in seen:
                continue
            seen.add(context_id)
            chunk = context_map[context_id]
            citations.append(
                CitationResponse(
                    citation_id=f"CIT-{len(citations) + 1:03d}",
                    context_id=context_id,
                    display_label=display_label(chunk),
                    chunk_id=chunk.chunk_id,
                    article_number=chunk.article_number,
                    article_title=chunk.article_title,
                    clause_number=chunk.clause_number,
                    point_label=chunk.point_label,
                    source_file=chunk.source_file,
                    source_url=chunk.source_url,
                    source_block_start=chunk.source_block_start,
                    source_block_end=chunk.source_block_end,
                    content_preview=chunk.content[:300],
                    source_endpoint=build_source_endpoint(chunk.chunk_id),
                )
            )
    return citations


def format_answer_with_citations(
    draft: AnswerDraft, context_map: Mapping[str, RetrievedChunk]
) -> str:
    """Append server-derived citation labels to each response claim."""
    parts = []
    for claim in draft.claims:
        labels = [display_label(context_map[context_id]) for context_id in claim.context_ids]
        suffix = f" 【{'; '.join(labels)}】" if labels else ""
        parts.append(claim.text.strip() + suffix)
    return "\n\n".join(parts)
