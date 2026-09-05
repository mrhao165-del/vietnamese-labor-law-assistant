from pathlib import Path

import pytest
from pydantic import SecretStr

from vietnamese_labor_law_assistant.common.settings import Settings


def test_settings_defaults_and_secret_redaction() -> None:
    settings = Settings(openai_api_key=SecretStr("secret"), llm_model=None)
    assert settings.embedding_device == "auto"
    assert settings.dense_top_k == 5
    assert not settings.llm_configured
    assert "secret" not in repr(settings)


def test_settings_infers_gemini_provider_from_compatible_base_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    settings = Settings(
        openai_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )
    assert settings.llm_provider == "gemini_openai_compatible"


def test_case_intake_models_strip_overrides_and_fall_back_independently() -> None:
    settings = Settings(
        openai_api_key=SecretStr("secret"),
        llm_model=" global-model ",
        case_intake_fact_model=" fact-model ",
        case_intake_issue_model="   ",
    )

    assert settings.llm_model == "global-model"
    assert settings.case_intake_fact_model == "fact-model"
    assert settings.case_intake_issue_model is None
    assert settings.resolved_case_intake_fact_model == "fact-model"
    assert settings.resolved_case_intake_issue_model == "global-model"
    assert settings.case_intake_configured


def test_boundary_only_models_configure_case_intake_without_configuring_global_llm() -> None:
    settings = Settings(
        openai_api_key=SecretStr("secret"),
        llm_model=None,
        case_intake_fact_model="fact-model",
        case_intake_issue_model="issue-model",
    )

    assert not settings.llm_configured
    assert settings.case_intake_configured


def test_case_intake_requires_both_resolved_boundary_models() -> None:
    settings = Settings(
        openai_api_key=SecretStr("secret"),
        llm_model=None,
        case_intake_fact_model="fact-model",
        case_intake_issue_model=None,
    )

    assert not settings.case_intake_configured
