from pathlib import Path
from typing import Literal

import pytest
from pydantic import ValidationError

from vietnamese_labor_law_assistant.common.settings import Settings


def test_week11_settings_accept_runtime_path_and_cors() -> None:
    settings = Settings(
        app_db_path=Path("runtime/test.sqlite3"), cors_allowed_origins="http://one, http://two"
    )
    assert settings.app_db_path == Path("runtime/test.sqlite3")
    assert [item.strip() for item in settings.cors_allowed_origins.split(",")] == [
        "http://one",
        "http://two",
    ]
    assert settings.guardrail_semantic_timeout_seconds == 15
    assert settings.guardrail_semantic_batch_size == 4


@pytest.mark.parametrize("size", [0, 101])
def test_page_size_bounds(size: int) -> None:
    with pytest.raises(ValidationError):
        Settings(api_max_page_size=size)


@pytest.mark.parametrize(
    "field",
    [
        "guardrail_semantic_timeout_seconds",
        "guardrail_semantic_batch_size",
        "guardrail_semantic_max_contexts",
        "guardrail_semantic_max_text_characters",
    ],
)
def test_guardrail_semantic_bounds_are_validated(
    field: Literal[
        "guardrail_semantic_timeout_seconds",
        "guardrail_semantic_batch_size",
        "guardrail_semantic_max_contexts",
        "guardrail_semantic_max_text_characters",
    ],
) -> None:
    with pytest.raises(ValidationError):
        if field == "guardrail_semantic_timeout_seconds":
            Settings(guardrail_semantic_timeout_seconds=0)
        elif field == "guardrail_semantic_batch_size":
            Settings(guardrail_semantic_batch_size=0)
        elif field == "guardrail_semantic_max_contexts":
            Settings(guardrail_semantic_max_contexts=0)
        else:
            Settings(guardrail_semantic_max_text_characters=0)
