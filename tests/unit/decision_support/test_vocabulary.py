"""Offline contract tests for the minimal Week-2 case-intake vocabulary."""

from __future__ import annotations

import inspect
import subprocess
import sys

import pytest
from pydantic import ValidationError

from vietnamese_labor_law_assistant.decision_support import issues
from vietnamese_labor_law_assistant.decision_support.enums import (
    AssertionMode,
    SourceType,
    VerificationStatus,
)
from vietnamese_labor_law_assistant.decision_support.issues import IssueCode
from vietnamese_labor_law_assistant.decision_support.models import CandidateIssue


def test_fact_enum_values_are_stable_and_unique() -> None:
    assert [member.value for member in AssertionMode] == ["EXPLICIT", "INFERRED"]
    assert [member.value for member in VerificationStatus] == ["UNVERIFIED"]
    assert [member.value for member in SourceType] == ["USER_MESSAGE"]


def test_candidate_issue_values_and_serialization_are_deterministic() -> None:
    assert [member.value for member in IssueCode] == [
        "CONTRACT_TERM",
        "EMPLOYEE_UNILATERAL_TERMINATION",
    ]
    issue = CandidateIssue(issue_code=IssueCode.CONTRACT_TERM)
    assert issue.model_dump(mode="json") == {"issue_code": "CONTRACT_TERM"}
    assert issue.model_dump_json() == '{"issue_code":"CONTRACT_TERM"}'


def test_candidate_issue_boundary_rejects_unsupported_codes_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        CandidateIssue.model_validate({"issue_code": "EMPLOYER_TERMINATION"})
    with pytest.raises(ValidationError):
        CandidateIssue.model_validate(
            {"issue_code": "CONTRACT_TERM", "required_facts": ["contract_type"]}
        )


def test_candidate_issue_has_no_registry_requirements() -> None:
    assert set(CandidateIssue.model_fields) == {"issue_code"}
    assert "IssueRegistry" not in inspect.getsource(issues)


def test_decision_support_package_import_has_no_output_or_side_effect() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import vietnamese_labor_law_assistant.decision_support",
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode == 0
    assert completed.stdout == ""
    assert completed.stderr == ""
