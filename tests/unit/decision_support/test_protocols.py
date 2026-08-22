"""Offline tests for the provider-neutral Case Intake extraction port."""

from __future__ import annotations

import inspect
import socket
import subprocess
import sys

import pytest

from vietnamese_labor_law_assistant.decision_support import models, protocols
from vietnamese_labor_law_assistant.decision_support.issues import IssueCode
from vietnamese_labor_law_assistant.decision_support.models import (
    CandidateIssue,
    CaseIntakeInput,
    CaseIntakeResult,
)
from vietnamese_labor_law_assistant.decision_support.protocols import CaseIntakeExtractor


class DeterministicFakeIntake:
    def __init__(self, result: CaseIntakeResult) -> None:
        self.result = result
        self.received: list[CaseIntakeInput] = []

    async def extract(self, case_input: CaseIntakeInput) -> CaseIntakeResult:
        self.received.append(case_input)
        return self.result


async def extract_with(
    extractor: CaseIntakeExtractor, case_input: CaseIntakeInput
) -> CaseIntakeResult:
    return await extractor.extract(case_input)


def fail_network(*_args: object, **_kwargs: object) -> None:
    pytest.fail("network")


@pytest.mark.asyncio
async def test_fake_intake_is_deterministic_and_never_uses_a_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = CaseIntakeResult(
        candidate_issues=[CandidateIssue(issue_code=IssueCode.CONTRACT_TERM)]
    )
    fake = DeterministicFakeIntake(expected)
    extractor: CaseIntakeExtractor = fake
    case_input = CaseIntakeInput(
        source_text="Tôi ký hợp đồng 24 tháng.",
        source_ref="user_message:case-1",
    )
    monkeypatch.setattr(socket, "create_connection", fail_network)

    result = await extract_with(extractor, case_input)

    assert result is expected
    assert fake.received == [case_input]


def test_protocol_module_import_has_no_output_or_provider_dependency() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import vietnamese_labor_law_assistant.decision_support.protocols",
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode == 0
    assert completed.stdout == ""
    assert completed.stderr == ""


def test_domain_contracts_do_not_import_the_openai_sdk() -> None:
    assert "openai" not in inspect.getsource(models).casefold()
    assert "openai" not in inspect.getsource(protocols).casefold()
