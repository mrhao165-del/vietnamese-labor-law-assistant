"""Safe Hugging Face cache settings for project-owned MCP subprocesses."""

from __future__ import annotations

import os
from collections.abc import Mapping

HUGGINGFACE_CACHE_ENVIRONMENT_KEYS = (
    "HF_HOME",
    "HF_HUB_CACHE",
    "HUGGINGFACE_HUB_CACHE",
    "HF_HUB_OFFLINE",
)

RETRIEVAL_RUNTIME_ENVIRONMENT_KEYS = (
    "QDRANT_MODE",
    "QDRANT_URL",
    "QDRANT_COLLECTION",
)


def select_huggingface_cache_environment(
    environment: Mapping[str, str] | None = None,
) -> dict[str, str] | None:
    """Return only configured, non-secret Hugging Face cache settings."""
    source = os.environ if environment is None else environment
    selected = {
        key: value for key in HUGGINGFACE_CACHE_ENVIRONMENT_KEYS if (value := source.get(key))
    }
    return selected or None


def select_retrieval_mcp_environment(
    environment: Mapping[str, str] | None = None,
) -> dict[str, str] | None:
    """Return only cache and non-secret retrieval runtime settings for the stdio child."""
    source = os.environ if environment is None else environment
    keys = HUGGINGFACE_CACHE_ENVIRONMENT_KEYS + RETRIEVAL_RUNTIME_ENVIRONMENT_KEYS
    selected = {key: value for key in keys if (value := source.get(key))}
    return selected or None
