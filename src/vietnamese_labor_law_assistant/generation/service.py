"""End-to-end dense RAG orchestration, independent from web routes."""

from __future__ import annotations

import time
import uuid
from typing import Protocol

import structlog

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.guardrails.models import AtomicClaim, EvidenceContext
from vietnamese_labor_law_assistant.guardrails.policy import guarded_answer
from vietnamese_labor_law_assistant.guardrails.service import CitationGuardrailService
from vietnamese_labor_law_assistant.retrieval.models import DenseSearchResult, SearchResponse

from .citations import (
    CitationValidationError,
    build_citations,
    format_answer_with_citations,
    validate_answer_draft,
)
from .llm import LegalAnswerGenerator
from .models import QueryResponse
from .prompts import build_legal_qa_prompt

DISCLAIMER = "Hệ thống chỉ hỗ trợ tra cứu, không thay thế tư vấn pháp lý chuyên nghiệp."


class Retriever(Protocol):
    def search(self, query: str, top_k: int) -> DenseSearchResult | SearchResponse: ...


class RagService:
    """Retrieval-neutral generation and citation-validation service."""

    def __init__(
        self,
        retriever: Retriever,
        generator: LegalAnswerGenerator,
        settings: Settings,
        guardrail_service: CitationGuardrailService | None = None,
    ) -> None:
        self.retriever = retriever
        self.generator = generator
        self.settings = settings
        self.guardrail_service = guardrail_service
        self.logger = structlog.get_logger(__name__)

    def query(self, question: str, top_k: int = 5, include_contexts: bool = False) -> QueryResponse:
        request_id = str(uuid.uuid4())
        started = time.perf_counter()
        search = self.retriever.search(question, top_k)
        if not search.results:
            return QueryResponse(
                request_id=request_id,
                question=search.query,
                answer="Không tìm thấy context phù hợp để trả lời.",
                insufficient_context=True,
                warning="Không có context truy hồi.",
                disclaimer=DISCLAIMER,
                retrieval=search.model_dump(mode="json", exclude={"results"}),
                generation={"called": False},
                total_latency_ms=(time.perf_counter() - started) * 1000,
                contexts=[] if include_contexts else None,
            )
        self.logger.info(
            "llm_generation_started",
            request_id=request_id,
            model=self.settings.llm_model,
            retrieved_count=len(search.results),
            contexts=[
                {
                    "chunk_id": item.chunk_id,
                    "article_number": item.article_number,
                    "clause_number": item.clause_number,
                }
                for item in search.results
            ],
        )
        generated_started = time.perf_counter()
        draft = self.generator.generate(search.query, search.results)
        generation_ms = (time.perf_counter() - generated_started) * 1000
        self.logger.info(
            "llm_generation_completed", request_id=request_id, generation_latency_ms=generation_ms
        )
        context_map = build_legal_qa_prompt(search.query, search.results).context_map
        try:
            validate_answer_draft(draft, context_map)
            answer = format_answer_with_citations(draft, context_map)
            citations = build_citations(draft, context_map)
            warning = draft.general_warning
        except CitationValidationError:
            answer = "Không thể xác minh trích dẫn của câu trả lời."
            citations = []
            warning = "CITATION_VALIDATION_FAILED"
        verification: dict[str, object] | None = None
        if self.settings.guardrail_enabled and all(
            item.chunk_id.startswith("ll_") for item in search.results
        ):
            guardrail = self.guardrail_service
            if guardrail is None:
                # A request must never construct a semantic model.  API composition injects
                # the warmed singleton; other callers fail closed when it is unavailable.
                answer = "Không thể xác minh ngữ nghĩa của câu trả lời."
                citations = []
                warning = "GUARDRAIL_UNAVAILABLE"
                verification = {"status": "INSUFFICIENT_CONTEXT", "reason": warning}
                return QueryResponse(
                    request_id=request_id,
                    question=search.query,
                    answer=answer,
                    citations=citations,
                    insufficient_context=True,
                    warning=warning,
                    disclaimer=DISCLAIMER,
                    retrieval=search.model_dump(mode="json", exclude={"results"}),
                    generation={"called": True, "latency_ms": generation_ms},
                    total_latency_ms=(time.perf_counter() - started) * 1000,
                    contexts=[item.model_dump(mode="json") for item in search.results]
                    if include_contexts
                    else None,
                    verification=verification,
                )
            claims = [
                AtomicClaim(
                    claim_id=claim.claim_id,
                    text=claim.text,
                    cited_context_ids=[context_map[item].chunk_id for item in claim.context_ids],
                    legal_references=claim.legal_references,
                )
                for claim in draft.claims
            ]
            evidence = [
                EvidenceContext(
                    chunk_id=item.chunk_id,
                    content=item.content,
                    article_number=item.article_number,
                    clause_number=item.clause_number,
                    point_label=item.point_label,
                    point_labels=item.point_labels,
                )
                for item in search.results
            ]
            result = guardrail.verify(claims, evidence)
            answer, policy_warnings = guarded_answer(answer, result, claims)
            verification = result.model_dump(mode="json")
            if policy_warnings:
                warning = "; ".join(policy_warnings)
            if result.status.value in {"UNSUPPORTED", "INSUFFICIENT_CONTEXT"}:
                citations = []
        self.logger.info(
            "citation_validation_completed",
            request_id=request_id,
            citation_count=len(citations),
            status="failed" if warning == "CITATION_VALIDATION_FAILED" else "ok",
        )
        return QueryResponse(
            request_id=request_id,
            question=search.query,
            answer=answer,
            citations=citations,
            insufficient_context=draft.insufficient_context,
            warning=warning,
            disclaimer=DISCLAIMER,
            retrieval=search.model_dump(mode="json", exclude={"results"}),
            generation={"called": True, "latency_ms": generation_ms},
            total_latency_ms=(time.perf_counter() - started) * 1000,
            contexts=[item.model_dump(mode="json") for item in search.results]
            if include_contexts
            else None,
            verification=verification,
        )


# Retained for callers created before the Week 6 retrieval-neutral refactor.
DenseRagService = RagService
