"""Offline contracts for independent Case Intake provider boundaries."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from pydantic import SecretStr, ValidationError

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.decision_support import intake
from vietnamese_labor_law_assistant.decision_support.enums import (
    AssertionMode,
    VerificationStatus,
)
from vietnamese_labor_law_assistant.decision_support.fact_compiler import FactCompilationResult
from vietnamese_labor_law_assistant.decision_support.intake import (
    CaseIntakeError,
    OpenAIStructuredCaseIntakeExtractor,
)
from vietnamese_labor_law_assistant.decision_support.issue_registry import FactKey
from vietnamese_labor_law_assistant.decision_support.issues import IssueCode
from vietnamese_labor_law_assistant.decision_support.models import (
    CaseFact,
    CaseIntakeInput,
    SourceSpan,
)


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


def _gemini_settings() -> Settings:
    return Settings(
        openai_api_key=SecretStr("test-key"),
        openai_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        llm_model="gemini-test-model",
        llm_provider="gemini_openai_compatible",
        agent_structured_output_max_retries=0,
    )


def _case_input(source_text: str = "Hợp đồng có thời hạn 18 tháng.") -> CaseIntakeInput:
    return CaseIntakeInput(
        source_text=source_text,
        source_ref="user_message:split-boundary",
    )


def _fact_proposal(literal: str = "18 tháng") -> dict[str, object]:
    return {
        "fact_key": "CONTRACT_DURATION",
        "source_span": {"text": literal},
    }


def _fact_payload(*proposals: dict[str, object]) -> dict[str, object]:
    return {"fact_proposals": list(proposals)}


def _issue_payload(*issue_codes: str) -> dict[str, object]:
    return {"candidate_issues": [{"issue_code": code} for code in issue_codes]}


def _compile_duration_proposals(
    case_input: CaseIntakeInput,
    proposals: tuple[intake._ProviderFactProposal, ...],
) -> FactCompilationResult:
    """Test-only compiler double; Prompt 2 will supply the production policy compiler."""

    facts: list[CaseFact] = []
    for index, proposal in enumerate(proposals, start=1):
        assert proposal.fact_key is FactKey.CONTRACT_DURATION
        literal = proposal.source_span.text
        start = case_input.source_text.index(literal)
        facts.append(
            CaseFact(
                fact_id=f"CF-test-duration-{index}",
                fact_key=proposal.fact_key.value,
                fact_type="DURATION",
                raw_value=literal,
                normalized_value=int(literal.split()[0]),
                assertion_mode=AssertionMode.EXPLICIT,
                verification_status=VerificationStatus.UNVERIFIED,
                source_type=case_input.source_type,
                source_ref=case_input.source_ref,
                source_span=SourceSpan(
                    start_offset=start,
                    end_offset=start + len(literal),
                    text=literal,
                ),
            )
        )
    return FactCompilationResult(tuple(facts), ())


def _extractor(
    client: BoundaryParseClient,
    *,
    retries: int = 0,
) -> OpenAIStructuredCaseIntakeExtractor:
    return OpenAIStructuredCaseIntakeExtractor(
        _settings(retries=retries),
        client,
        fact_proposal_compiler=_compile_duration_proposals,
    )


def test_private_provider_schemas_have_one_responsibility_and_forbid_cross_layer_fields() -> None:
    fact_model = intake._ProviderFactExtractionResult
    issue_model = intake._ProviderCandidateIssueResult

    assert set(fact_model.model_fields) == {"fact_proposals"}
    assert set(issue_model.model_fields) == {"candidate_issues"}
    with pytest.raises(ValidationError):
        fact_model.model_validate({"fact_proposals": [], "candidate_issues": []})
    with pytest.raises(ValidationError):
        issue_model.model_validate({"candidate_issues": [], "fact_proposals": []})


def test_fact_proposal_schema_contains_only_closed_key_and_literal_span() -> None:
    schema = intake._ProviderFactExtractionResult.model_json_schema()
    proposal = schema["$defs"]["_ProviderFactProposal"]
    source_span = schema["$defs"]["_ProviderSourceSpan"]
    serialized = json.dumps(schema, sort_keys=True)

    assert set(schema["properties"]) == {"fact_proposals"}
    assert set(proposal["properties"]) == {"fact_key", "source_span"}
    assert set(source_span["properties"]) == {"text"}
    assert set(schema["$defs"]["FactKey"]["enum"]) == {value.value for value in FactKey}
    for forbidden in (
        "candidate_issues",
        "fact_type",
        "raw_value",
        "normalized_value",
        "assertion_mode",
        "verification_status",
        "evidence_status",
        "fact_id",
        "source_ref",
        "source_type",
        "start_offset",
        "end_offset",
        "legal_analysis",
    ):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    ("extra_field", "extra_value"),
    [
        ("normalized_value", 18),
        ("fact_type", "DURATION"),
        ("assertion_mode", "EXPLICIT"),
        ("verification_status", "UNVERIFIED"),
        ("evidence_status", "PRESENT_ASSERTED"),
        ("fact_id", "CF-provider-owned"),
        ("legal_analysis", "The employee should win."),
    ],
)
def test_fact_proposal_rejects_every_non_proposal_field(
    extra_field: str, extra_value: object
) -> None:
    proposal = _fact_proposal() | {extra_field: extra_value}

    with pytest.raises(ValidationError):
        intake._ProviderFactExtractionResult.model_validate(_fact_payload(proposal))


def test_issue_schema_has_no_fact_transport_fields() -> None:
    schema = intake._ProviderCandidateIssueResult.model_json_schema()
    serialized = json.dumps(schema, sort_keys=True)

    assert set(schema["properties"]) == {"candidate_issues"}
    assert set(schema["$defs"]["IssueCode"]["enum"]) == {
        "CONTRACT_TERM",
        "EMPLOYEE_UNILATERAL_TERMINATION",
    }
    assert "fact_proposals" not in serialized
    assert '"facts"' not in serialized
    assert "discriminator" not in serialized


@pytest.mark.asyncio
async def test_gemini_transport_omits_unsupported_array_limits() -> None:
    client = BoundaryParseClient([_fact_payload(), _issue_payload()])

    await OpenAIStructuredCaseIntakeExtractor(
        _gemini_settings(),
        client,
        fact_proposal_compiler=_compile_duration_proposals,
    ).extract(_case_input())

    fact_transport = client.requests[0]["response_format"]
    issue_transport = client.requests[1]["response_format"]
    assert isinstance(fact_transport, type)
    assert isinstance(issue_transport, type)
    assert "maxItems" not in json.dumps(fact_transport.model_json_schema())
    assert "maxItems" not in json.dumps(issue_transport.model_json_schema())
    assert (
        intake._ProviderFactExtractionResult.model_json_schema()["properties"]["fact_proposals"][
            "maxItems"
        ]
        == 50
    )
    assert (
        intake._ProviderCandidateIssueResult.model_json_schema()["properties"]["candidate_issues"][
            "maxItems"
        ]
        == 2
    )


@pytest.mark.asyncio
async def test_gemini_fact_transport_still_enforces_domain_array_limit_after_parsing() -> None:
    client = BoundaryParseClient([_fact_payload(*[_fact_proposal() for _ in range(51)])])

    with pytest.raises(CaseIntakeError, match="CASE_INTAKE_SCHEMA_INVALID"):
        await OpenAIStructuredCaseIntakeExtractor(
            _gemini_settings(),
            client,
            fact_proposal_compiler=_compile_duration_proposals,
        ).extract(_case_input())

    assert len(client.requests) == 1


@pytest.mark.asyncio
async def test_gemini_issue_transport_still_enforces_domain_array_limit_after_parsing() -> None:
    client = BoundaryParseClient(
        [
            _fact_payload(),
            _issue_payload("CONTRACT_TERM", "CONTRACT_TERM", "CONTRACT_TERM"),
        ]
    )

    with pytest.raises(CaseIntakeError, match="CASE_INTAKE_SCHEMA_INVALID"):
        await OpenAIStructuredCaseIntakeExtractor(
            _gemini_settings(),
            client,
            fact_proposal_compiler=_compile_duration_proposals,
        ).extract(_case_input())

    assert len(client.requests) == 2


@pytest.mark.asyncio
async def test_fact_and_issue_calls_receive_only_the_same_original_input_then_merge() -> None:
    client = BoundaryParseClient([_fact_payload(_fact_proposal()), _issue_payload("CONTRACT_TERM")])
    source = _case_input()

    result, audit = await _extractor(client).extract_with_transport_audit(source)

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
    assert "candidate_issues" not in fact_messages[1]["content"]
    assert "fact_proposals" not in issue_messages[1]["content"]
    assert audit.fact_proposal_count == 1
    assert audit.fact_request_attempt_count == 1
    assert audit.issue_request_attempt_count == 1


@pytest.mark.asyncio
async def test_fact_and_issue_boundaries_use_their_own_configured_models() -> None:
    client = BoundaryParseClient([_fact_payload(), _issue_payload()])
    configured = Settings(
        openai_api_key=SecretStr("test-key"),
        openai_base_url="https://provider.test/v1",
        llm_model=None,
        case_intake_fact_model="fact-specialist",
        case_intake_issue_model="issue-specialist",
        llm_provider="openai",
        agent_structured_output_max_retries=0,
    )

    await OpenAIStructuredCaseIntakeExtractor(
        configured,
        client,
        fact_proposal_compiler=_compile_duration_proposals,
    ).extract(_case_input())

    assert [request["model"] for request in client.requests] == [
        "fact-specialist",
        "issue-specialist",
    ]


@pytest.mark.asyncio
async def test_boundary_model_overrides_fall_back_independently_to_global_model() -> None:
    client = BoundaryParseClient([_fact_payload(), _issue_payload()])
    configured = Settings(
        openai_api_key=SecretStr("test-key"),
        openai_base_url="https://provider.test/v1",
        llm_model="global-fallback",
        case_intake_fact_model="fact-specialist",
        case_intake_issue_model=None,
        llm_provider="openai",
        agent_structured_output_max_retries=0,
    )

    await OpenAIStructuredCaseIntakeExtractor(
        configured,
        client,
        fact_proposal_compiler=_compile_duration_proposals,
    ).extract(_case_input())

    assert [request["model"] for request in client.requests] == [
        "fact-specialist",
        "global-fallback",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source_text", "fact_payload", "issue_payload", "fact_count", "issue_codes"),
    [
        (
            "Hợp đồng có thời hạn 18 tháng.",
            _fact_payload(_fact_proposal()),
            _issue_payload("CONTRACT_TERM"),
            1,
            ("CONTRACT_TERM",),
        ),
        (
            "Hợp đồng có thời hạn 18 tháng.",
            _fact_payload(_fact_proposal()),
            _issue_payload(),
            1,
            (),
        ),
        (
            "Tôi muốn nghỉ việc.",
            _fact_payload(),
            _issue_payload("EMPLOYEE_UNILATERAL_TERMINATION"),
            0,
            ("EMPLOYEE_UNILATERAL_TERMINATION",),
        ),
        ("Tôi cần hỗ trợ.", _fact_payload(), _issue_payload(), 0, ()),
    ],
)
async def test_all_fact_issue_presence_combinations_are_valid(
    source_text: str,
    fact_payload: dict[str, object],
    issue_payload: dict[str, object],
    fact_count: int,
    issue_codes: tuple[str, ...],
) -> None:
    client = BoundaryParseClient([fact_payload, issue_payload])

    result = await _extractor(client).extract(_case_input(source_text))

    assert len(result.facts) == fact_count
    assert tuple(issue.issue_code.value for issue in result.candidate_issues) == issue_codes


@pytest.mark.asyncio
async def test_fact_output_does_not_change_issue_eligibility() -> None:
    source = _case_input("Hợp đồng có thời hạn 18 tháng; tôi muốn nghỉ việc.")
    with_fact = BoundaryParseClient(
        [
            _fact_payload(_fact_proposal()),
            _issue_payload("EMPLOYEE_UNILATERAL_TERMINATION"),
        ]
    )
    without_fact = BoundaryParseClient(
        [_fact_payload(), _issue_payload("EMPLOYEE_UNILATERAL_TERMINATION")]
    )

    with_fact_result = await _extractor(with_fact).extract(source)
    without_fact_result = await _extractor(without_fact).extract(source)

    assert len(with_fact_result.facts) == 1
    assert without_fact_result.facts == []
    assert with_fact_result.candidate_issues == without_fact_result.candidate_issues
    assert [issue.issue_code for issue in with_fact_result.candidate_issues] == [
        IssueCode.EMPLOYEE_UNILATERAL_TERMINATION
    ]


@pytest.mark.asyncio
async def test_fact_retry_does_not_repeat_or_consume_issue_detection() -> None:
    client = BoundaryParseClient(
        [{"fact_proposals": "invalid"}, _fact_payload(), _issue_payload("CONTRACT_TERM")]
    )

    result, audit = await _extractor(client, retries=1).extract_with_transport_audit(_case_input())

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
        [_fact_payload(_fact_proposal()), {"candidate_issues": "invalid"}, _issue_payload()]
    )

    result, audit = await _extractor(client, retries=1).extract_with_transport_audit(_case_input())

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
async def test_ungrounded_proposal_is_audited_without_retrying_or_blocking_issue() -> None:
    client = BoundaryParseClient(
        [
            _fact_payload(_fact_proposal("literal not in source")),
            _issue_payload("CONTRACT_TERM"),
        ]
    )

    extractor = OpenAIStructuredCaseIntakeExtractor(_settings(retries=1), client)

    result, audit = await extractor.extract_with_transport_audit(_case_input())

    assert result.facts == []
    assert [issue.issue_code for issue in result.candidate_issues] == [IssueCode.CONTRACT_TERM]
    assert audit.fact_request_attempt_count == 1
    assert audit.fact_retry_count == 0
    assert audit.fact_compiler_rejected_count == 1
    assert tuple(reason.value for reason in audit.fact_compiler_rejection_reasons) == (
        "SOURCE_LITERAL_NOT_FOUND",
    )
    assert [request["response_format"] for request in client.requests] == [
        intake._ProviderFactExtractionResult,
        intake._ProviderCandidateIssueResult,
    ]


@pytest.mark.asyncio
async def test_ambiguous_proposal_is_audited_without_retrying_or_blocking_issue() -> None:
    literal = "18 tháng"
    client = BoundaryParseClient(
        [
            _fact_payload(_fact_proposal(literal)),
            _issue_payload("CONTRACT_TERM"),
        ]
    )
    extractor = OpenAIStructuredCaseIntakeExtractor(_settings(retries=1), client)

    result, audit = await extractor.extract_with_transport_audit(
        _case_input(f"Hợp đồng có thời hạn {literal} và gia hạn thêm {literal}.")
    )

    assert result.facts == []
    assert [issue.issue_code for issue in result.candidate_issues] == [IssueCode.CONTRACT_TERM]
    assert audit.fact_request_attempt_count == 1
    assert audit.fact_retry_count == 0
    assert audit.fact_compiler_rejected_count == 1
    assert tuple(reason.value for reason in audit.fact_compiler_rejection_reasons) == (
        "SOURCE_LITERAL_AMBIGUOUS",
    )
    assert [request["response_format"] for request in client.requests] == [
        intake._ProviderFactExtractionResult,
        intake._ProviderCandidateIssueResult,
    ]


@pytest.mark.asyncio
async def test_either_boundary_failure_fails_closed_without_partial_public_result() -> None:
    fact_failure = BoundaryParseClient([RuntimeError("fact unavailable")])
    with pytest.raises(CaseIntakeError, match="CASE_INTAKE_PROVIDER_ERROR") as fact_error:
        await _extractor(fact_failure).extract(_case_input())
    assert len(fact_failure.requests) == 1
    assert fact_error.value.boundary == "fact"
    assert fact_error.value.fact_request_attempt_count == 1
    assert fact_error.value.issue_request_attempt_count == 0

    issue_failure = BoundaryParseClient(
        [_fact_payload(_fact_proposal()), RuntimeError("issue unavailable")]
    )
    with pytest.raises(CaseIntakeError, match="CASE_INTAKE_PROVIDER_ERROR") as issue_error:
        await _extractor(issue_failure).extract(_case_input())
    assert len(issue_failure.requests) == 2
    assert issue_error.value.boundary == "issue"
    assert issue_error.value.fact_request_attempt_count == 1
    assert issue_error.value.issue_request_attempt_count == 1
    assert issue_error.value.fact_compiler_latency_ms > 0
