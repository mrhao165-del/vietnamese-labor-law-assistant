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


def select_huggingface_cache_environment(
    environment: Mapping[str, str] | None = None,
) -> dict[str, str] | None:
    """Return only configured, non-secret Hugging Face cache settings."""
    source = os.environ if environment is None else environment
    selected = {
        key: value for key in HUGGINGFACE_CACHE_ENVIRONMENT_KEYS if (value := source.get(key))
    }
    return selected or None
