"""Environment-backed, validated runtime configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded lazily from environment and optional `.env`."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"
    qdrant_mode: Literal["remote", "local"] = "local"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: SecretStr | None = None
    qdrant_collection: str = "labor_law_chunks"
    qdrant_local_path: Path = Path("data/qdrant_local")
    embedding_model: str = "BAAI/bge-m3"
    embedding_device: Literal["auto", "cpu", "cuda"] = "auto"
    embedding_use_fp16: bool | None = None
    embedding_batch_size: int = Field(default=4, ge=1, le=64)
    embedding_max_length: int = Field(default=1024, ge=1)
    long_chunk_policy: Literal["error", "truncate_with_warning"] = "error"
    dense_top_k: int = Field(default=5, ge=1)
    dense_max_top_k: int = Field(default=10, ge=1, le=100)
    retrieval_mode: Literal[
        "dense",
        "sparse_whitespace",
        "sparse_underthesea",
        "hybrid_whitespace",
        "hybrid_underthesea",
        "dense_rerank",
        "hybrid_underthesea_rerank",
    ] = "hybrid_underthesea_rerank"
    reranker_enabled: bool = True
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_device: Literal["auto", "cpu", "cuda"] = "auto"
    reranker_use_fp16: bool | None = None
    reranker_batch_size: int = Field(default=1, ge=1, le=32)
    reranker_max_length: int = Field(default=512, ge=1, le=2048)
    reranker_candidate_k: int = Field(default=10, ge=1, le=100)
    reranker_output_k: int = Field(default=5, ge=1, le=100)
    reranker_fallback_mode: Literal["skip", "error"] = "error"
    reranker_cache_size: int = Field(default=128, ge=0, le=4096)
    query_embedding_cache_enabled: bool = True
    query_embedding_cache_size: int = Field(default=256, ge=0, le=4096)
    query_embedding_cache_ttl_seconds: int = Field(default=3600, ge=0, le=86400)
    openai_api_key: SecretStr | None = None
    openai_base_url: str | None = None
    llm_model: str | None = None
    llm_provider: Literal["openai", "gemini_openai_compatible"] = "openai"
    llm_timeout_seconds: float = Field(default=60, gt=0)
    llm_max_retries: int = Field(default=2, ge=0, le=10)
    guardrail_enabled: bool = True
    guardrail_canonical_source_path: Path = Path("data/processed/labor_law_clauses.jsonl")
    guardrail_semantic_lower_threshold: float = Field(default=0.35, ge=0, le=1)
    guardrail_semantic_high_threshold: float = Field(default=0.75, ge=0, le=1)
    guardrail_semantic_timeout_seconds: float = Field(default=15, gt=0, le=120)
    guardrail_semantic_batch_size: int = Field(default=4, ge=1, le=64)
    guardrail_semantic_max_contexts: int = Field(default=10, ge=1, le=50)
    guardrail_semantic_max_text_characters: int = Field(default=12000, ge=128, le=100000)
    guardrail_llm_judge_enabled: bool = False
    guardrail_judge_timeout_seconds: float = Field(default=10, gt=0, le=120)
    guardrail_max_claims: int = Field(default=12, ge=1, le=50)
    guardrail_max_citations_per_claim: int = Field(default=10, ge=1, le=20)
    guardrail_fail_closed: bool = True
    agent_max_input_length: int = Field(default=4000, ge=1, le=16000)
    agent_max_tool_calls: int = Field(default=3, ge=1, le=10)
    agent_tool_timeout_seconds: float = Field(default=30, gt=0, le=120)
    agent_workflow_timeout_seconds: float = Field(default=90, gt=0, le=300)
    agent_max_transport_retries: int = Field(default=1, ge=0, le=3)
    agent_structured_output_max_retries: int = Field(default=2, ge=0, le=2)
    agent_max_retrieval_top_k: int = Field(default=5, ge=1, le=10)
    agent_tool_output_max_chars: int = Field(default=12000, ge=256, le=100000)
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    app_db_path: Path = Path("data/runtime/app.sqlite3")
    cors_allowed_origins: str = "http://localhost:5173,http://localhost:8080"
    api_max_page_size: int = Field(default=50, ge=1, le=100)

    @field_validator("llm_model")
    @classmethod
    def strip_optional_model(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None

    @model_validator(mode="after")
    def validate_top_k_range(self) -> Settings:
        if self.dense_top_k > self.dense_max_top_k:
            raise ValueError("DENSE_TOP_K must not exceed DENSE_MAX_TOP_K")
        if self.reranker_output_k > self.reranker_candidate_k:
            raise ValueError("RERANKER_OUTPUT_K must not exceed RERANKER_CANDIDATE_K")
        if self.guardrail_semantic_lower_threshold >= self.guardrail_semantic_high_threshold:
            raise ValueError("GUARDRAIL_SEMANTIC_LOWER_THRESHOLD must be lower than high threshold")
        if self.reranker_device == "cpu" and self.reranker_use_fp16:
            raise ValueError("RERANKER_USE_FP16 cannot be enabled on CPU")
        if self.openai_base_url:
            parsed = urlparse(self.openai_base_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("OPENAI_BASE_URL must be an absolute HTTP(S) URL")
            if (
                self.llm_provider == "gemini_openai_compatible"
                and parsed.hostname != "generativelanguage.googleapis.com"
            ):
                raise ValueError(
                    "Gemini OpenAI-compatible mode requires the Generative Language base URL"
                )
            if (
                self.llm_provider == "openai"
                and "llm_provider" not in self.model_fields_set
                and parsed.hostname == "generativelanguage.googleapis.com"
            ):
                self.llm_provider = "gemini_openai_compatible"
        return self

    @property
    def llm_configured(self) -> bool:
        """Whether both required LLM settings have nonempty values."""
        return (
            self.openai_api_key is not None
            and self.llm_model is not None
            and (self.llm_provider == "openai" or self.openai_base_url is not None)
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return one cached process-level settings object."""
    return Settings()
