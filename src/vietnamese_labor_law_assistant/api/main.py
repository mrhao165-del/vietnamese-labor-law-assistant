"""FastAPI application factory and production-safe exception responses."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, Any, Protocol

import structlog
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from vietnamese_labor_law_assistant.agent.models import AgentResult
from vietnamese_labor_law_assistant.agent.service import AgentService
from vietnamese_labor_law_assistant.common.logging import configure_logging, question_preview
from vietnamese_labor_law_assistant.common.settings import Settings, get_settings
from vietnamese_labor_law_assistant.generation.models import (
    ErrorResponse,
    QueryRequest,
    QueryResponse,
)
from vietnamese_labor_law_assistant.generation.service import RagService
from vietnamese_labor_law_assistant.guardrails.source_registry import (
    CanonicalSourceRegistry,
    SourceRegistryError,
)
from vietnamese_labor_law_assistant.retrieval.errors import RetrievalError
from vietnamese_labor_law_assistant.retrieval.models import SearchRequest
from vietnamese_labor_law_assistant.retrieval.service import LegalRetriever

from .chat_models import (
    ChatRequest,
    ChatResponse,
    ConversationCreateRequest,
    ConversationResponse,
    FeedbackRequest,
    MessageResponse,
)
from .conversation_repository import ConversationRepository, ConversationRepositoryError
from .dependencies import (
    ensure_supported_production_retrieval_mode,
    get_agent_service,
    get_conversation_repository,
    get_guardrail_semantic_scorer,
    get_legal_retriever,
    get_rag_service,
    get_store,
    readiness,
)
from .public_mapper import (
    citations_for,
    public_answer,
    public_message_content,
    tool_trace_for,
    verification_code,
    verification_for,
)


def _error(
    request_id: str,
    code: str,
    message: str,
    retryable: bool = False,
    details: dict[str, Any] | None = None,
) -> ErrorResponse:
    return ErrorResponse(
        request_id=request_id,
        error_code=code,
        message=message,
        retryable=retryable,
        details=details,
        timestamp=datetime.now(UTC).isoformat(),
    )


class SemanticScorerLifecycle(Protocol):
    @property
    def is_ready(self) -> bool: ...

    def warmup(self) -> None: ...


def create_app(
    settings: Settings | None = None,
    *,
    semantic_scorer: SemanticScorerLifecycle | None = None,
) -> FastAPI:
    """Create an override-friendly FastAPI MVP without loading BGE-M3 at import time."""
    active_settings = settings or get_settings()
    active_scorer = semantic_scorer or get_guardrail_semantic_scorer()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        configure_logging(active_settings)
        ConversationRepository(active_settings.app_db_path).initialize()
        if active_settings.guardrail_enabled:
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(active_scorer.warmup),
                    timeout=active_settings.guardrail_semantic_timeout_seconds,
                )
            except (TimeoutError, RuntimeError, ValueError):
                # Keep liveness available for diagnostics; readiness and chat fail closed.
                pass
        yield

    app = FastAPI(title="Vietnamese Labor Law AI Assistant", version="0.2.0", lifespan=lifespan)
    ensure_supported_production_retrieval_mode(active_settings)
    origins = [
        item.strip() for item in active_settings.cors_allowed_origins.split(",") if item.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "X-Request-ID"],
    )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        code = str(exc.detail) if isinstance(exc.detail, str) else "HTTP_ERROR"
        return JSONResponse(
            status_code=exc.status_code,
            content=_error(request_id, code, "Yêu cầu không thể được xử lý.").model_dump(
                mode="json"
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        return JSONResponse(
            status_code=422,
            content=_error(
                request_id,
                "INVALID_QUERY",
                "Dữ liệu yêu cầu không hợp lệ.",
                details={"errors": jsonable_encoder(exc.errors())},
            ).model_dump(mode="json"),
        )

    @app.middleware("http")
    async def request_logging(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        started = time.perf_counter()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            response = await call_next(request)
        except Exception as exc:
            structlog.get_logger(__name__).error(
                "api_request_failed",
                request_id=request_id,
                exception_type=type(exc).__name__,
            )
            response = JSONResponse(
                status_code=500,
                content=_error(request_id, "INTERNAL_ERROR", "Lỗi nội bộ máy chủ.").model_dump(
                    mode="json"
                ),
            )
        response.headers["X-Request-ID"] = request_id
        structlog.get_logger(__name__).info(
            "api_request_completed",
            request_id=request_id,
            path=request.url.path,
            latency_ms=(time.perf_counter() - started) * 1000,
            status=response.status_code,
        )
        structlog.contextvars.clear_contextvars()
        return response

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def ready() -> JSONResponse:
        checks = readiness(active_settings)
        checks["guardrail_semantic"] = (
            active_scorer.is_ready if active_settings.guardrail_enabled else True
        )
        try:
            ConversationRepository(active_settings.app_db_path).initialize()
            checks["runtime_database"] = True
        except ConversationRepositoryError:
            checks["runtime_database"] = False
        ready_state = all(checks.values())
        return JSONResponse(
            status_code=200 if ready_state else 503,
            content={"ready": ready_state, "checks": checks},
        )

    @app.post(
        "/api/v1/chat", response_model=ChatResponse, responses={503: {"model": ErrorResponse}}
    )
    async def chat(
        payload: ChatRequest,
        service: Annotated[AgentService, Depends(get_agent_service)],
        repository: Annotated[ConversationRepository, Depends(get_conversation_repository)],
    ) -> ChatResponse:
        question = " ".join(payload.question.split())
        if not question:
            raise HTTPException(status_code=422, detail="INVALID_QUERY")
        if payload.conversation_id is not None:
            try:
                conversation = repository.ensure_conversation(
                    payload.conversation_id, question[:120]
                )
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="CONVERSATION_NOT_FOUND") from exc
        else:
            conversation = None
        # AgentService owns the MCP-only workflow and the final Week 10 guardrail.
        result: AgentResult = await service.run(question, include_trace=True)
        if result.workflow_verification.get("status") != "PASS":
            raise HTTPException(status_code=503, detail="AGENT_WORKFLOW_UNAVAILABLE")
        if conversation is None:
            conversation = repository.create_conversation(question[:120])
        try:
            registry = CanonicalSourceRegistry(active_settings.guardrail_canonical_source_path)
            citations = citations_for(result, registry)
        except SourceRegistryError:
            citations = []
        verification = verification_for(result)
        warnings = list(verification.warnings) if verification else []
        answer_text = public_answer(result.answer, result.verification)
        machine_code = verification_code(result.verification)
        user_facing_message = answer_text if answer_text != result.answer else None
        metadata = {
            "route": result.intent.value if result.intent else None,
            "final_status": result.status.value,
            "citations": [item.model_dump(mode="json") for item in citations],
            "tool_trace": [item.model_dump(mode="json") for item in tool_trace_for(result)],
            "verification": verification.model_dump(mode="json") if verification else None,
            "warnings": warnings,
            "answer_text": answer_text,
            "verification_code": machine_code,
            "user_facing_message": user_facing_message,
            "request_id": result.request_id,
            "latency_ms": result.latency_ms,
            "pipeline_version": "week11-agent-guardrail",
        }
        user = repository.add_message(conversation["id"], "user", question, {})
        assistant = repository.add_message(conversation["id"], "assistant", answer_text, metadata)
        return ChatResponse(
            request_id=result.request_id,
            conversation_id=conversation["id"],
            user_message_id=user["id"],
            assistant_message_id=assistant["id"],
            answer=answer_text,
            answer_text=answer_text,
            verification_code=machine_code,
            user_facing_message=user_facing_message,
            route=metadata["route"],
            final_status=result.status.value,
            citations=citations,
            tool_trace=tool_trace_for(result),
            verification=verification,
            warnings=warnings,
            latency_ms=result.latency_ms,
            created_at=assistant["created_at"],
        )

    @app.get("/api/v1/conversations", response_model=list[ConversationResponse])
    def conversations(
        repository: Annotated[ConversationRepository, Depends(get_conversation_repository)],
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> list[ConversationResponse]:
        return [
            ConversationResponse.model_validate(row) for row in repository.list_conversations(limit)
        ]

    @app.post("/api/v1/conversations", response_model=ConversationResponse)
    def create_conversation(
        payload: ConversationCreateRequest,
        repository: Annotated[ConversationRepository, Depends(get_conversation_repository)],
    ) -> ConversationResponse:
        return ConversationResponse.model_validate(
            repository.create_conversation(payload.title.strip())
        )

    @app.get(
        "/api/v1/conversations/{conversation_id}/messages", response_model=list[MessageResponse]
    )
    def conversation_messages(
        conversation_id: str,
        repository: Annotated[ConversationRepository, Depends(get_conversation_repository)],
    ) -> list[MessageResponse]:
        try:
            return [
                MessageResponse.model_validate(
                    {
                        **{key: value for key, value in row.items() if key != "metadata_json"},
                        "content": public_message_content(row["content"], row.get("metadata", {})),
                    }
                )
                for row in repository.messages(conversation_id)
            ]
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="CONVERSATION_NOT_FOUND") from exc

    @app.delete("/api/v1/conversations/{conversation_id}", status_code=204)
    def delete_conversation(
        conversation_id: str,
        repository: Annotated[ConversationRepository, Depends(get_conversation_repository)],
    ) -> None:
        if not repository.delete_conversation(conversation_id):
            raise HTTPException(status_code=404, detail="CONVERSATION_NOT_FOUND")

    @app.put("/api/v1/messages/{message_id}/feedback", status_code=204)
    def feedback(
        message_id: str,
        payload: FeedbackRequest,
        repository: Annotated[ConversationRepository, Depends(get_conversation_repository)],
    ) -> None:
        if not repository.set_feedback(
            message_id, payload.value, payload.note.strip() if payload.note else None
        ):
            raise HTTPException(status_code=404, detail="MESSAGE_NOT_FOUND")

    @app.post(
        "/api/v1/query", response_model=QueryResponse, responses={503: {"model": ErrorResponse}}
    )
    def query(
        payload: QueryRequest, service: Annotated[RagService, Depends(get_rag_service)]
    ) -> QueryResponse:
        if not active_settings.llm_configured:
            raise HTTPException(status_code=503, detail="LLM_NOT_CONFIGURED")
        logger = structlog.get_logger(__name__)
        logger.info(
            "api_request_started",
            question_preview=question_preview(payload.question),
            top_k=payload.top_k,
        )
        try:
            return service.query(payload.question, payload.top_k, payload.include_contexts)
        except RuntimeError as exc:
            code = str(exc)
            if code in {"LLM_NOT_CONFIGURED", "LLM_RESPONSE_INVALID"}:
                raise HTTPException(status_code=503, detail=code) from exc
            raise HTTPException(status_code=503, detail="QDRANT_UNAVAILABLE") from exc
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/v1/rag/query", response_model=QueryResponse)
    def rag_query(
        payload: QueryRequest, service: Annotated[RagService, Depends(get_rag_service)]
    ) -> QueryResponse:
        """Backward-compatible explicit alias for the established RAG endpoint."""
        if not active_settings.llm_configured:
            raise HTTPException(status_code=503, detail="LLM_NOT_CONFIGURED")
        try:
            return service.query(payload.question, payload.top_k, payload.include_contexts)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail="RETRIEVAL_OR_LLM_UNAVAILABLE") from exc

    @app.post("/api/v1/search")
    def search(
        payload: SearchRequest, retriever: Annotated[LegalRetriever, Depends(get_legal_retriever)]
    ) -> dict[str, Any]:
        """Direct legal retrieval without a language-model call."""
        request_id = str(uuid.uuid4())
        try:
            response = retriever.search(
                payload.query,
                top_k=payload.top_k,
                mode=payload.mode,
                candidate_k=payload.candidate_k,
                filters=payload.filters,
                include_content=payload.include_content,
                include_scores=payload.include_scores,
                request_id=request_id,
            )
        except RetrievalError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc
        body = response.model_dump(mode="json")
        for row in body["results"]:
            if not payload.include_content:
                row.pop("content", None)
            if not payload.include_scores:
                for field in (
                    "score",
                    "dense_score",
                    "sparse_score",
                    "rrf_score",
                    "reranker_score",
                ):
                    row.pop(field, None)
        return body

    @app.get("/api/v1/articles/{article_number}")
    def article(
        article_number: int, retriever: Annotated[LegalRetriever, Depends(get_legal_retriever)]
    ) -> dict[str, Any]:
        try:
            return retriever.get_article(article_number).model_dump(mode="json")
        except RetrievalError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc

    @app.get("/api/v1/articles/{article_number}/clauses/{clause_number}")
    def clause(
        article_number: int,
        clause_number: int,
        retriever: Annotated[LegalRetriever, Depends(get_legal_retriever)],
    ) -> dict[str, Any]:
        try:
            return retriever.get_clause(article_number, clause_number).model_dump(mode="json")
        except RetrievalError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc

    @app.get("/api/v1/sources/{chunk_id}")
    def source(chunk_id: str, store: Annotated[Any, Depends(get_store)]) -> dict[str, Any]:
        payload = store.get_by_chunk_id(chunk_id)
        if payload is None:
            raise HTTPException(status_code=404, detail="SOURCE_NOT_FOUND")
        return payload

    return app


app = create_app()
