# syntax=docker/dockerfile:1.7
FROM python:3.11-slim AS api
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=cache,target=/root/.cache/uv \
    pip install --no-cache-dir uv && uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY scripts/index_dense.py ./scripts/index_dense.py
COPY scripts/diagnose_guardrail_semantic_scorer.py ./scripts/diagnose_guardrail_semantic_scorer.py
COPY scripts/diagnose_structured_router.py ./scripts/diagnose_structured_router.py
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev
EXPOSE 8000
CMD ["/app/.venv/bin/python", "-m", "uvicorn", "vietnamese_labor_law_assistant.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
