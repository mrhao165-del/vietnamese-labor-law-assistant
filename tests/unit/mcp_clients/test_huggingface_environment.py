from __future__ import annotations

from vietnamese_labor_law_assistant.mcp_clients.huggingface_environment import (
    HUGGINGFACE_CACHE_ENVIRONMENT_KEYS,
    RETRIEVAL_RUNTIME_ENVIRONMENT_KEYS,
    select_huggingface_cache_environment,
    select_retrieval_mcp_environment,
)
from vietnamese_labor_law_assistant.mcp_clients.legal_retrieval import LegalRetrievalMcpClient


def test_select_huggingface_cache_environment_includes_each_allowlisted_value() -> None:
    environment = {
        "HF_HOME": "cache-home",
        "HF_HUB_CACHE": "hub-cache",
        "HUGGINGFACE_HUB_CACHE": "legacy-hub-cache",
        "HF_HUB_OFFLINE": "1",
    }

    assert select_huggingface_cache_environment(environment) == environment


def test_select_huggingface_cache_environment_ignores_empty_values_and_returns_none() -> None:
    environment = {key: "" for key in HUGGINGFACE_CACHE_ENVIRONMENT_KEYS}

    assert select_huggingface_cache_environment(environment) is None


def test_select_huggingface_cache_environment_excludes_secrets_and_arbitrary_values() -> None:
    environment = {
        "HF_HUB_CACHE": "hub-cache",
        "HF_TOKEN": "must-not-leak",
        "OPENAI_API_KEY": "must-not-leak",
        "PATH": "must-not-copy",
        "ARBITRARY_ENVIRONMENT_VALUE": "must-not-copy",
    }

    assert select_huggingface_cache_environment(environment) == {"HF_HUB_CACHE": "hub-cache"}


def test_select_huggingface_cache_environment_does_not_mutate_input() -> None:
    environment = {"HF_HOME": "cache-home", "HF_TOKEN": "must-not-leak"}
    original = environment.copy()

    select_huggingface_cache_environment(environment)

    assert environment == original


def test_select_retrieval_mcp_environment_includes_only_non_secret_runtime_settings() -> None:
    environment = {
        "HF_HOME": "cache-home",
        "QDRANT_MODE": "remote",
        "QDRANT_URL": "http://qdrant:6333",
        "QDRANT_COLLECTION": "labor_law_chunks",
        "QDRANT_API_KEY": "must-not-leak",
        "OPENAI_API_KEY": "must-not-leak",
    }

    assert select_retrieval_mcp_environment(environment) == {
        key: environment[key]
        for key in (*HUGGINGFACE_CACHE_ENVIRONMENT_KEYS, *RETRIEVAL_RUNTIME_ENVIRONMENT_KEYS)
        if key in environment
    }


def test_legal_retrieval_client_passes_safe_environment_to_stdio_parameters(monkeypatch) -> None:
    monkeypatch.setenv("HF_HOME", "cache-home")
    monkeypatch.setenv("HF_HUB_CACHE", "hub-cache")
    monkeypatch.setenv("HUGGINGFACE_HUB_CACHE", "legacy-hub-cache")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("HF_TOKEN", "must-not-leak")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-leak")
    monkeypatch.setenv("QDRANT_MODE", "remote")
    monkeypatch.setenv("QDRANT_URL", "http://qdrant:6333")
    monkeypatch.setenv("QDRANT_COLLECTION", "labor_law_chunks")

    parameters = LegalRetrievalMcpClient()._server_parameters()

    assert parameters.env == {
        "HF_HOME": "cache-home",
        "HF_HUB_CACHE": "hub-cache",
        "HUGGINGFACE_HUB_CACHE": "legacy-hub-cache",
        "HF_HUB_OFFLINE": "1",
        "QDRANT_MODE": "remote",
        "QDRANT_URL": "http://qdrant:6333",
        "QDRANT_COLLECTION": "labor_law_chunks",
    }
