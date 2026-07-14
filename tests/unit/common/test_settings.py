from pydantic import SecretStr

from vietnamese_labor_law_assistant.common.settings import Settings


def test_settings_defaults_and_secret_redaction() -> None:
    settings = Settings(openai_api_key=SecretStr("secret"), llm_model=None)
    assert settings.embedding_device == "auto"
    assert settings.dense_top_k == 5
    assert not settings.llm_configured
    assert "secret" not in repr(settings)


def test_settings_infers_gemini_provider_from_compatible_base_url() -> None:
    settings = Settings(
        openai_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )
    assert settings.llm_provider == "gemini_openai_compatible"
