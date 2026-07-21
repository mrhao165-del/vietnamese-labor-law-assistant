"""Lazy process-level factory for the Week 6 Retrieval Engine."""

from __future__ import annotations

from functools import lru_cache

from vietnamese_labor_law_assistant.agent.service import AgentService
from vietnamese_labor_law_assistant.common.settings import get_settings
from vietnamese_labor_law_assistant.generation.llm import OpenAICompatibleLegalAnswerGenerator
from vietnamese_labor_law_assistant.generation.service import RagService
from vietnamese_labor_law_assistant.guardrails.judge import OpenAIStructuredClaimJudge
from vietnamese_labor_law_assistant.guardrails.service import CitationGuardrailService
from vietnamese_labor_law_assistant.guardrails.similarity import GuardrailSemanticScorer
from vietnamese_labor_law_assistant.guardrails.source_registry import CanonicalSourceRegistry
from vietnamese_labor_law_assistant.retrieval import factory as retrieval_factory
from vietnamese_labor_law_assistant.retrieval.embeddings import BgeM3EmbeddingProvider

from .conversation_repository import ConversationRepository

PRODUCTION_RETRIEVAL_MODES = retrieval_factory.PRODUCTION_RETRIEVAL_MODES
ensure_supported_production_retrieval_mode = (
    retrieval_factory.ensure_supported_production_retrieval_mode
)
get_store = retrieval_factory.get_store
get_dense_retriever = retrieval_factory.get_dense_retriever
get_sparse_retriever = retrieval_factory.get_sparse_retriever
get_reranker = retrieval_factory.get_reranker
get_retriever = retrieval_factory.get_retriever
get_legal_retriever = retrieval_factory.get_legal_retriever
readiness = retrieval_factory.readiness


@lru_cache(maxsize=1)
def get_rag_service() -> RagService:
    settings = get_settings()
    return RagService(
        get_legal_retriever(),
        OpenAICompatibleLegalAnswerGenerator(settings),
        settings,
        guardrail_service=get_guardrail_service(),
    )


@lru_cache(maxsize=1)
def get_guardrail_semantic_scorer() -> GuardrailSemanticScorer:
    settings = get_settings()
    return GuardrailSemanticScorer(
        BgeM3EmbeddingProvider(settings),
        max_claims=settings.guardrail_max_claims,
        max_contexts=settings.guardrail_semantic_max_contexts,
        max_text_characters=settings.guardrail_semantic_max_text_characters,
        batch_size=settings.guardrail_semantic_batch_size,
    )


@lru_cache(maxsize=1)
def get_guardrail_service() -> CitationGuardrailService:
    settings = get_settings()
    return CitationGuardrailService(
        CanonicalSourceRegistry(settings.guardrail_canonical_source_path),
        get_guardrail_semantic_scorer(),
        judge=OpenAIStructuredClaimJudge(settings)
        if settings.guardrail_llm_judge_enabled
        else None,
        lower_threshold=settings.guardrail_semantic_lower_threshold,
        high_threshold=settings.guardrail_semantic_high_threshold,
    )


@lru_cache(maxsize=1)
def get_agent_service() -> AgentService:
    return AgentService.from_settings(get_settings(), guardrail_service=get_guardrail_service())


@lru_cache(maxsize=1)
def get_conversation_repository() -> ConversationRepository:
    repository = ConversationRepository(get_settings().app_db_path)
    repository.initialize()
    return repository
