"""Offline contracts for independent Case Intake provider boundaries."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from pydantic import SecretStr, ValidationError

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.decision_support import intake
from vietnamese_labor_law_assistant.decision_support.intake import (
    CaseIntakeError,
    OpenAIStructuredCaseIntakeExtractor,
)
from vietnamese_labor_law_assistant.decision_support.issues import IssueCode
from vietnamese_labor_law_assistant.decision_support.models import CaseIntakeInput


class BoundaryParseClient:
    """Specific fake for the external structured-provider boundary."""

    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.requests: list[dict[str, object]] = []
        self.beta = SimpleNamespace(chat=SimpleNamespace(completions=self))

    def parse(self, **kwargs: object) -> object:
        self.requests.append(kwargs)
        outcome = self.outcomes[len(self.requests) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(parsed=outcome, refusal=None))]
        )


def _settings(*, retries: int = 0) -> Settings:
    return Settings(
        openai_api_key=SecretStr("test-key"),
        openai_base_url="https://provider.test/v1",
        llm_model="test-model",
        llm_provider="openai",
        agent_structured_output_max_retries=retries,
    )


def _case_input(source_text: str = "Hợp đồng có thời hạn 18 tháng.") -> CaseIntakeInput:
    return CaseIntakeInput(
        source_text=source_text,
        source_ref="user_message:split-boundary",
    )


def _fact_observation(raw_value: str = "18 tháng") -> dict[str, object]:
    return {
        "fact_id": "CF-contract-duration",
        "fact_key": "CONTRACT_DURATION",
        "fact_type": "DURATION",
        "raw_value": raw_value,
        "normalized_value": 18,
        "assertion_mode": "EXPLICIT",
        "verification_status": "UNVERIFIED",
        "source_type": "USER_MESSAGE",
        "source_ref": "user_message:split-boundary",
        "source_span": {"text": raw_value},
        "evidence_status": "PRESENT_ASSERTED",
    }


def _fact_payload(*facts: dict[str, object]) -> dict[str, object]:
    return {"facts": list(facts)}


def _issue_payload(*issue_codes: str) -> dict[str, object]:
    return {"candidate_issues": [{"issue_code": code} for code in issue_codes]}


def test_private_provider_schemas_have_one_responsibility_and_forbid_cross_layer_fields() -> None:
    fact_model = intake._ProviderFactExtractionResult
    issue_model = intake._ProviderCandidateIssueResult

    assert set(fact_model.model_fields) == {"facts"}
    assert set(issue_model.model_fields) == {"candidate_issues"}
    with pytest.raises(ValidationError):
        fact_model.model_validate({"facts": [], "candidate_issues": []})
    with pytest.raises(ValidationError):
        issue_model.model_validate({"candidate_issues": [], "facts": []})


def test_split_provider_schemas_keep_closed_provider_compatible_enums() -> None:
    fact_schema = intake._ProviderFactExtractionResult.model_json_schema()
    issue_schema = intake._ProviderCandidateIssueResult.model_json_schema()

    assert set(fact_schema["properties"]) == {"facts"}
    assert set(issue_schema["properties"]) == {"candidate_issues"}
    assert set(fact_schema["$defs"]["FactKey"]["enum"]) == {value.value for value in intake.FactKey}
    assert set(fact_schema["$defs"]["FactType"]["enum"]) == {
        "TEXT",
        "DATE",
        "DURATION",
        "MONEY",
        "TEMPORAL_EXPRESSION",
    }
    assert set(issue_schema["$defs"]["IssueCode"]["enum"]) == {
        "CONTRACT_TERM",
        "EMPLOYEE_UNILATERAL_TERMINATION",
    }
    assert "discriminator" not in json.dumps(fact_schema, sort_keys=True)
    assert "discriminator" not in json.dumps(issue_schema, sort_keys=True)


@pytest.mark.asyncio
async def test_fact_and_issue_calls_receive_only_the_same_original_input_then_merge() -> None:
    client = BoundaryParseClient(
        [_fact_payload(_fact_observation()), _issue_payload("CONTRACT_TERM")]
    )
    source = _case_input()

    result, audit = await OpenAIStructuredCaseIntakeExtractor(
        _settings(), client
    ).extract_with_transport_audit(source)

    assert [fact.fact_key for fact in result.facts] == ["CONTRACT_DURATION"]
    assert [issue.issue_code for issue in result.candidate_issues] == [IssueCode.CONTRACT_TERM]
    assert len(client.requests) == 2
    assert client.requests[0]["response_format"] is intake._ProviderFactExtractionResult
    assert client.requests[1]["response_format"] is intake._ProviderCandidateIssueResult
    fact_messages = client.requests[0]["messages"]
    issue_messages = client.requests[1]["messages"]
    assert isinstance(fact_messages, list) and isinstance(issue_messages, list)
    assert fact_messages[1] == issue_messages[1]
    assert fact_messages[0]["content"] == intake.FACT_EXTRACTION_SYSTEM_PROMPT
    assert issue_messages[0]["content"] == intake.CANDIDATE_ISSUE_SYSTEM_PROMPT
    assert audit.fact_request_attempt_count == 1
    assert audit.issue_request_attempt_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fact_payload", "issue_payload", "fact_count", "issue_codes"),
    [
        (
            _fact_payload(_fact_observation()),
            _issue_payload("CONTRACT_TERM"),
            1,
            ("CONTRACT_TERM",),
        ),
        (_fact_payload(_fact_observation()), _issue_payload(), 1, ()),
        (
            _fact_payload(),
            _issue_payload("EMPLOYEE_UNILATERAL_TERMINATION"),
            0,
            ("EMPLOYEE_UNILATERAL_TERMINATION",),
        ),
        (_fact_payload(), _issue_payload(), 0, ()),
    ],
)
async def test_all_fact_issue_presence_combinations_are_valid(
    fact_payload: dict[str, object],
    issue_payload: dict[str, object],
    fact_count: int,
    issue_codes: tuple[str, ...],
) -> None:
    client = BoundaryParseClient([fact_payload, issue_payload])

    result = await OpenAIStructuredCaseIntakeExtractor(_settings(), client).extract(_case_input())

    assert len(result.facts) == fact_count
    assert tuple(issue.issue_code.value for issue in result.candidate_issues) == issue_codes


@pytest.mark.asyncio
async def test_fact_retry_does_not_repeat_or_consume_issue_detection() -> None:
    client = BoundaryParseClient(
        [RuntimeError("fact schema invalid"), _fact_payload(), _issue_payload("CONTRACT_TERM")]
    )

    result, audit = await OpenAIStructuredCaseIntakeExtractor(
        _settings(retries=1), client
    ).extract_with_transport_audit(_case_input())

    assert [request["response_format"] for request in client.requests] == [
        intake._ProviderFactExtractionResult,
        intake._ProviderFactExtractionResult,
        intake._ProviderCandidateIssueResult,
    ]
    assert [issue.issue_code for issue in result.candidate_issues] == [IssueCode.CONTRACT_TERM]
    assert audit.fact_request_attempt_count == 2
    assert audit.fact_retry_count == 1
    assert audit.issue_request_attempt_count == 1
    assert audit.issue_retry_count == 0


@pytest.mark.asyncio
async def test_issue_retry_never_repeats_successful_fact_extraction() -> None:
    client = BoundaryParseClient(
        [_fact_payload(_fact_observation()), RuntimeError("issue invalid"), _issue_payload()]
    )

    result, audit = await OpenAIStructuredCaseIntakeExtractor(
        _settings(retries=1), client
    ).extract_with_transport_audit(_case_input())

    assert len(result.facts) == 1
    assert [request["response_format"] for request in client.requests] == [
        intake._ProviderFactExtractionResult,
        intake._ProviderCandidateIssueResult,
        intake._ProviderCandidateIssueResult,
    ]
    assert audit.fact_request_attempt_count == 1
    assert audit.issue_request_attempt_count == 2
    assert audit.issue_retry_count == 1


@pytest.mark.asyncio
async def test_fact_canonicalization_failure_is_repaired_inside_fact_boundary() -> None:
    invalid = _fact_observation("literal not in source")
    client = BoundaryParseClient(
        [_fact_payload(invalid), _fact_payload(_fact_observation()), _issue_payload()]
    )

    result, audit = await OpenAIStructuredCaseIntakeExtractor(
        _settings(retries=1), client
    ).extract_with_transport_audit(_case_input())

    assert [fact.raw_value for fact in result.facts] == ["18 tháng"]
    assert audit.fact_request_attempt_count == 2
    assert [request["response_format"] for request in client.requests] == [
        intake._ProviderFactExtractionResult,
        intake._ProviderFactExtractionResult,
        intake._ProviderCandidateIssueResult,
    ]


@pytest.mark.asyncio
async def test_either_boundary_failure_fails_closed_without_partial_public_result() -> None:
    fact_failure = BoundaryParseClient([RuntimeError("fact unavailable")])
    with pytest.raises(CaseIntakeError, match="CASE_INTAKE_PROVIDER_ERROR") as fact_error:
        await OpenAIStructuredCaseIntakeExtractor(_settings(), fact_failure).extract(_case_input())
    assert len(fact_failure.requests) == 1
    assert fact_error.value.boundary == "fact"
    assert fact_error.value.fact_request_attempt_count == 1
    assert fact_error.value.issue_request_attempt_count == 0

    issue_failure = BoundaryParseClient(
        [_fact_payload(_fact_observation()), RuntimeError("issue unavailable")]
    )
    with pytest.raises(CaseIntakeError, match="CASE_INTAKE_PROVIDER_ERROR") as issue_error:
        await OpenAIStructuredCaseIntakeExtractor(_settings(), issue_failure).extract(_case_input())
    assert len(issue_failure.requests) == 2
    assert issue_error.value.boundary == "issue"
    assert issue_error.value.fact_request_attempt_count == 1
    assert issue_error.value.issue_request_attempt_count == 1
