"""Offline HTTP contract tests for the finite Week-4 Case Analysis workflow."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vietnamese_labor_law_assistant.agent.assistant_service import AssistantService
from vietnamese_labor_law_assistant.agent.case_graph import CaseGraph
from vietnamese_labor_law_assistant.agent.mode_routing import RequestMode
from vietnamese_labor_law_assistant.agent.models import AgentResult
from vietnamese_labor_law_assistant.api import main as api_main
from vietnamese_labor_law_assistant.api.conversation_repository import ConversationRepository
from vietnamese_labor_law_assistant.api.dependencies import (
    get_assistant_service,
    get_conversation_repository,
)
from vietnamese_labor_law_assistant.api.main import create_app
from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.decision_support.enums import (
    AssertionMode,
    SourceType,
    VerificationStatus,
)
from vietnamese_labor_law_assistant.decision_support.issue_registry import FactKey
from vietnamese_labor_law_assistant.decision_support.issues import IssueCode
from vietnamese_labor_law_assistant.decision_support.models import (
    CandidateIssue,
    CaseFact,
    CaseIntakeInput,
    CaseIntakeResult,
    SourceSpan,
)
from vietnamese_labor_law_assistant.guardrails.enums import ReasonCode
from vietnamese_labor_law_assistant.guardrails.enums import (
    VerificationStatus as GuardrailVerificationStatus,
)
from vietnamese_labor_law_assistant.guardrails.models import VerificationResult


class CaseModeRouter:
    async def route(self, question: str) -> RequestMode:
        del question
        return RequestMode.CASE_ANALYSIS


class RecordingDirectService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def run(self, question: str, *, include_trace: bool = False) -> AgentResult:
        del include_trace
        self.calls.append(question)
        raise AssertionError("direct QA must not run for Case Analysis")


class ReadyScorer:
    @property
    def is_ready(self) -> bool:
        return True

    def warmup(self) -> None:
        return None


IntakeFactory = Callable[[CaseIntakeInput], CaseIntakeResult]


class IntakeExtractorStub:
    def __init__(self, outcome: IntakeFactory | Exception) -> None:
        self.outcome = outcome
        self.calls: list[CaseIntakeInput] = []

    async def extract(self, case_input: CaseIntakeInput) -> CaseIntakeResult:
        self.calls.append(case_input)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome(case_input)


def refusal_verification() -> VerificationResult:
    return VerificationResult(
        status=GuardrailVerificationStatus.INSUFFICIENT_CONTEXT,
        warnings=[ReasonCode.OUT_OF_SCOPE_REFUSAL.value],
    )


def _intake_for(
    case_input: CaseIntakeInput,
    *,
    issue_codes: tuple[IssueCode, ...],
    fact_values: tuple[tuple[FactKey, str], ...] = (),
) -> CaseIntakeResult:
    facts: list[CaseFact] = []
    for index, (fact_key, raw_value) in enumerate(fact_values, start=1):
        start = case_input.source_text.index(raw_value)
        facts.append(
            CaseFact(
                fact_id=f"CF-{index}",
                fact_key=fact_key.value,
                fact_type="TEXT",
                raw_value=raw_value,
                normalized_value=raw_value,
                assertion_mode=AssertionMode.EXPLICIT,
                verification_status=VerificationStatus.UNVERIFIED,
                source_type=SourceType.USER_MESSAGE,
                source_ref=case_input.source_ref,
                source_span=SourceSpan(
                    start_offset=start,
                    end_offset=start + len(raw_value),
                    text=raw_value,
                ),
            )
        )
    return CaseIntakeResult(
        facts=facts,
        candidate_issues=[CandidateIssue(issue_code=code) for code in issue_codes],
    )


@pytest.fixture
def case_client_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    build_count = 0

    def build(
        extractor: IntakeExtractorStub,
    ) -> tuple[TestClient, ConversationRepository, RecordingDirectService]:
        nonlocal build_count
        build_count += 1
        settings = Settings(app_db_path=tmp_path / f"week4-{build_count}.sqlite3")
        repository = ConversationRepository(settings.app_db_path)
        repository.initialize()
        direct = RecordingDirectService()
        service = AssistantService(
            CaseModeRouter(),
            direct,
            CaseGraph(extractor),
            refusal_verification,
        )
        app = create_app(settings, semantic_scorer=ReadyScorer())
        app.dependency_overrides[get_assistant_service] = lambda: service
        app.dependency_overrides[get_conversation_repository] = lambda: repository
        monkeypatch.setattr(api_main, "readiness", lambda _: {"retrieval": True, "llm": True})
        return TestClient(app), repository, direct

    return build


def test_case_analysis_missing_critical_facts_returns_sanitized_clarification(
    case_client_factory,
) -> None:
    extractor = IntakeExtractorStub(
        lambda case_input: _intake_for(
            case_input,
            issue_codes=(IssueCode.CONTRACT_TERM,),
        )
    )
    client, repository, direct = case_client_factory(extractor)

    with client:
        response = client.post("/api/v1/chat", json={"question": "Analyze my contract."})

    assert response.status_code == 200
    body = response.json()
    case = body["case_analysis"]
    assert body["final_status"] == "CLARIFICATION_REQUIRED"
    assert case["status"] == "CLARIFICATION_REQUIRED"
    assert case["error_code"] is None
    assert case["substantive_analysis_blocked"] is True
    assert 1 <= len(case["clarification_questions"]) <= 3
    assert len({item["fact_key"] for item in case["missing_fields"]}) == len(case["missing_fields"])
    assert body["citations"] == [] and body["tool_trace"] == []
    assert direct.calls == [] and len(extractor.calls) == 1
    persisted = repository.messages(body["conversation_id"])[1]["metadata"]
    assert persisted["case_analysis"] == case


def test_case_analysis_complete_facts_returns_nonexecuting_evidence_metadata(
    case_client_factory,
) -> None:
    question = "FIXED_TERM started 2026-01-01 and ended 2026-12-31."
    extractor = IntakeExtractorStub(
        lambda case_input: _intake_for(
            case_input,
            issue_codes=(IssueCode.CONTRACT_TERM,),
            fact_values=(
                (FactKey.CONTRACT_TYPE, "FIXED_TERM"),
                (FactKey.CONTRACT_START_DATE, "2026-01-01"),
                (FactKey.CONTRACT_END_DATE, "2026-12-31"),
            ),
        )
    )
    client, _, direct = case_client_factory(extractor)

    with client:
        response = client.post("/api/v1/chat", json={"question": question})

    assert response.status_code == 200
    body = response.json()
    case = body["case_analysis"]
    assert case["status"] == "EVIDENCE_REQUEST_READY"
    assert case["refined_issues"][0]["status"] == "ACTIVE"
    assert case["evidence_requests"][0]["article"] == 20
    assert case["calculator_requests"][0]["capability"] == "CONTRACT_DURATION"
    assert case["substantive_analysis_blocked"] is False
    assert body["answer"] != "INSUFFICIENT_VERIFIED_EVIDENCE"
    assert body["citations"] == [] and body["tool_trace"] == []
    assert direct.calls == []


def test_case_analysis_multi_issue_shared_field_is_exposed_once(
    case_client_factory,
) -> None:
    extractor = IntakeExtractorStub(
        lambda case_input: _intake_for(case_input, issue_codes=tuple(IssueCode))
    )
    client, _, _ = case_client_factory(extractor)

    with client:
        response = client.post("/api/v1/chat", json={"question": "Analyze both issues."})

    case = response.json()["case_analysis"]
    shared_fields = [item for item in case["missing_fields"] if item["fact_key"] == "CONTRACT_TYPE"]
    shared_questions = [
        item for item in case["clarification_questions"] if item["fact_key"] == "CONTRACT_TYPE"
    ]
    assert len(shared_fields) == 1 and len(shared_questions) == 1
    assert shared_fields[0]["required_by_issues"] == [code.value for code in IssueCode]


def test_case_analysis_provider_failure_is_allowlisted_and_redacted(
    case_client_factory,
) -> None:
    extractor = IntakeExtractorStub(RuntimeError("provider-secret private-payload"))
    client, repository, direct = case_client_factory(extractor)

    with client:
        response = client.post(
            "/api/v1/chat",
            json={"question": "Analyze this failure safely."},
        )

    assert response.status_code == 200
    body = response.json()
    case = body["case_analysis"]
    assert case == {
        "status": "CASE_INTAKE_FAILED",
        "error_code": "CASE_INTAKE_PROVIDER_ERROR",
        "known_facts": [],
        "candidate_issues": [],
        "missing_fields": [],
        "clarification_reason_code": None,
        "clarification_questions": [],
        "refined_issues": [],
        "evidence_requests": [],
        "calculator_requests": [],
        "substantive_analysis_blocked": True,
    }
    serialized = response.text
    persisted = repository.messages(body["conversation_id"])[1]["metadata"]
    assert "provider-secret" not in serialized and "private-payload" not in serialized
    assert "provider-secret" not in str(persisted) and "private-payload" not in str(persisted)
    assert direct.calls == []
    assert not {
        "message",
        "prompt",
        "provider_payload",
        "registry_role",
        "query",
        "budget",
        "legal_outcome",
        "recommendation",
    } & set(case)
