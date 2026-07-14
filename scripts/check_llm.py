"""Safely verify configured OpenAI-compatible structured LLM connectivity."""

from __future__ import annotations

import time

from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

from vietnamese_labor_law_assistant.common.settings import get_settings
from vietnamese_labor_law_assistant.generation.llm import OpenAICompatibleLegalAnswerGenerator
from vietnamese_labor_law_assistant.generation.models import AnswerDraft


def main() -> int:
    settings = get_settings()
    if not settings.llm_configured:
        print("LLM configuration is incomplete; OPENAI_API_KEY and LLM_MODEL are required.")
        return 2
    started = time.perf_counter()
    generator = OpenAICompatibleLegalAnswerGenerator(settings)
    try:
        draft = generator.generate("Xác nhận kết nối bằng một câu ngắn.", [])
    except APITimeoutError:
        print("LLM connectivity failed: timeout")
        return 1
    except RateLimitError:
        print("LLM connectivity failed: rate_limit_or_quota")
        return 1
    except APIConnectionError:
        print("LLM connectivity failed: network")
        return 1
    except APIStatusError as exc:
        print(f"LLM connectivity failed: http_status={exc.status_code}")
        return 1
    except Exception as exc:
        print(f"LLM connectivity failed: {type(exc).__name__}")
        return 1
    AnswerDraft.model_validate(draft)
    print(
        f"LLM connectivity succeeded: provider={settings.llm_provider}, "
        f"model={settings.llm_model}, latency_ms={(time.perf_counter() - started) * 1000:.1f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
