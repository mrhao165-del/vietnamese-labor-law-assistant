import pytest
from httpx import Request, Response
from openai import RateLimitError
from pydantic import SecretStr

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.generation import llm
from vietnamese_labor_law_assistant.generation.llm import OpenAICompatibleLegalAnswerGenerator
from vietnamese_labor_law_assistant.generation.models import AnswerClaim, AnswerDraft
from vietnamese_labor_law_assistant.retrieval.models import RetrievedChunk


class FakeMessage:
    def __init__(self, parsed):
        self.parsed = parsed


class FakeChoice:
    def __init__(self, parsed):
        self.message = FakeMessage(parsed)


class FakeCompletions:
    def __init__(self, parsed):
        self.parsed = parsed
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return type("Completion", (), {"choices": [FakeChoice(self.parsed)]})()


class FakeClient:
    def __init__(self, parsed):
        completions = FakeCompletions(parsed)
        self.beta = type("Beta", (), {"chat": type("Chat", (), {"completions": completions})()})()
        self.completions = completions


class RaisingClient:
    def __init__(self, error: Exception) -> None:
        def parse(**kwargs):
            raise error

        completions = type("Completions", (), {"parse": staticmethod(parse)})()
        self.beta = type("Beta", (), {"chat": type("Chat", (), {"completions": completions})()})()


def _settings() -> Settings:
    return Settings(
        openai_api_key=SecretStr("not-a-real-secret"),
        openai_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        llm_model="gemini-3.1-flash-lite",
        llm_provider="gemini_openai_compatible",
    )


def _context() -> RetrievedChunk:
    return RetrievedChunk(
        rank=1,
        score=0.9,
        chunk_id="one",
        document_id="law",
        document_name="Law",
        article_number=1,
        content="Nội dung",
        source_file="x",
        source_block_start=0,
        source_block_end=0,
        content_sha256="a" * 64,
    )


def test_gemini_compatible_chat_parse_uses_configured_model() -> None:
    draft = AnswerDraft(
        claims=[AnswerClaim(claim_id="CLM-001", text="Được", context_ids=["CTX-001"])]
    )
    client = FakeClient(draft)
    result = OpenAICompatibleLegalAnswerGenerator(_settings(), client=client).generate(
        "Câu hỏi", [_context()]
    )
    assert result == draft
    assert client.completions.calls[0]["model"] == "gemini-3.1-flash-lite"
    assert client.completions.calls[0]["response_format"] is AnswerDraft


def test_chat_parse_rejects_none_parsed() -> None:
    with pytest.raises(RuntimeError, match="LLM_RESPONSE_INVALID"):
        OpenAICompatibleLegalAnswerGenerator(_settings(), client=FakeClient(None)).generate("Q", [])


def test_client_uses_configured_base_url_and_does_not_expose_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class ConstructedClient:
        pass

    def build_client(**kwargs: object) -> ConstructedClient:
        captured.update(kwargs)
        return ConstructedClient()

    monkeypatch.setattr(llm, "OpenAI", build_client)
    generator = OpenAICompatibleLegalAnswerGenerator(_settings())
    generator._get_client()
    assert captured["base_url"] == "https://generativelanguage.googleapis.com/v1beta/openai/"
    assert captured["timeout"] == 60
    assert "not-a-real-secret" not in repr(generator)


def test_timeout_is_propagated_without_retrying_invalid_output() -> None:
    with pytest.raises(TimeoutError):
        OpenAICompatibleLegalAnswerGenerator(
            _settings(), client=RaisingClient(TimeoutError("timeout"))
        ).generate("Q", [])


def test_rate_limit_is_propagated_without_retrying_invalid_output() -> None:
    rate_limit = RateLimitError(
        "rate limited",
        response=Response(429, request=Request("POST", "https://example.test")),
        body=None,
    )
    with pytest.raises(RateLimitError):
        generator = OpenAICompatibleLegalAnswerGenerator(
            _settings(), client=RaisingClient(rate_limit)
        )
        generator.generate("Q", [])
