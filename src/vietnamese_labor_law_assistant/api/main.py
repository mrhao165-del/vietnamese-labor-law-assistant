"""FastAPI application factory and production-safe exception responses."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, Any

import structlog
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from vietnamese_labor_law_assistant.common.logging import configure_logging, question_preview
from vietnamese_labor_law_assistant.common.settings import Settings, get_settings
from vietnamese_labor_law_assistant.generation.models import (
    ErrorResponse,
    QueryRequest,
    QueryResponse,
)
from vietnamese_labor_law_assistant.generation.service import DenseRagService

from .dependencies import (
    ensure_supported_production_retrieval_mode,
    get_rag_service,
    get_store,
    readiness,
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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging(get_settings())
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an override-friendly FastAPI MVP without loading BGE-M3 at import time."""
    app = FastAPI(title="Vietnamese Labor Law AI Assistant", version="0.2.0", lifespan=lifespan)
    active_settings = settings or get_settings()
    ensure_supported_production_retrieval_mode(active_settings)

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
        ready_state = all(checks.values())
        return JSONResponse(
            status_code=200 if ready_state else 503,
            content={"ready": ready_state, "checks": checks},
        )

    @app.post(
        "/api/v1/query", response_model=QueryResponse, responses={503: {"model": ErrorResponse}}
    )
    def query(
        payload: QueryRequest, service: Annotated[DenseRagService, Depends(get_rag_service)]
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

    @app.get("/api/v1/sources/{chunk_id}")
    def source(chunk_id: str, store: Annotated[Any, Depends(get_store)]) -> dict[str, Any]:
        payload = store.get_by_chunk_id(chunk_id)
        if payload is None:
            raise HTTPException(status_code=404, detail="SOURCE_NOT_FOUND")
        return payload

    return app


app = create_app()
