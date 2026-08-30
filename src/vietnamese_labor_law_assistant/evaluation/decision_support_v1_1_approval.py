"""Human-review and threshold-approval contracts preceding the frozen v1.1 run."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1 import (
    V11EvaluationCandidateCase,
    V11ReviewValidation,
    V11ThresholdSpec,
    load_v1_1_threshold_spec,
    load_v1_1_threshold_spec_bytes,
    resolve_v1_1_week3_threshold_source,
    validate_v1_1_review_packet,
)
from vietnamese_labor_law_assistant.evaluation.review_policy import (
    reviewer_is_independent_human,
    reviewer_role_is_independent,
)


class V11ThresholdApprovalEvidence(BaseModel):
    """Immutable human approval of one exact pre-registered threshold proposal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["v1_1_threshold_approval_v1"] = "v1_1_threshold_approval_v1"
    spec_id: str
    threshold_spec_path: str
    threshold_spec_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    thresholds_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    threshold_count: Literal[18] = 18
    registered_spec_status: Literal["PROPOSED_PENDING_HUMAN_APPROVAL"]
    approval_status: Literal["HUMAN_APPROVED"] = "HUMAN_APPROVED"
    approval_decision: Literal["APPROVE_UNCHANGED"] = "APPROVE_UNCHANGED"
    human_approved: Literal[True] = True
    reviewer_identifier: str = Field(min_length=1)
    reviewer_name: str = Field(min_length=1)
    reviewer_role: str = Field(min_length=1)
    approved_at: datetime
    independent_from_project_author: Literal[True] = True
    used_ai_as_reviewer: Literal[False] = False
    changed_after_final_results: Literal[False] = False
    frozen_evaluation_run_at_approval: Literal[False] = False
    frozen_final: Literal[False] = False

    @field_validator("approved_at")
    @classmethod
    def approved_at_requires_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("approved_at must include a timezone")
        return value


class V11ThresholdApprovalValidation(BaseModel):
    """Result of matching approval evidence to the exact registered threshold bytes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["PASS", "FAIL"]
    policy_satisfied: bool
    human_approved: bool
    approver: str | None
    approved_at: str | None
    approval_decision: str | None
    thresholds_unchanged: bool
    threshold_spec_checksum_matches: bool
    threshold_values_checksum_matches: bool
    registration_approval_state_valid: bool
    errors: list[str]
    frozen_final: Literal[False] = False


def finalize_v1_1_review_packet(
    cases: Sequence[V11EvaluationCandidateCase],
    path: Path,
    *,
    project_author_name: str,
    reviewed_at: datetime | None = None,
) -> V11ReviewValidation:
    """Stamp a complete prefilled packet after validating all other cells unchanged."""

    recorded_at = _canonical_current_timestamp(reviewed_at)
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fields = list(reader.fieldnames or ())
    if not rows:
        raise ValueError("review packet has no rows")
    if any(row.get("reviewed_at", "").strip() for row in rows):
        raise ValueError("reviewed_at is already recorded; refusing to overwrite review evidence")
    for row in rows:
        row["reviewed_at"] = recorded_at

    temporary_path = _temporary_sibling(path)
    try:
        with temporary_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        validation = validate_v1_1_review_packet(
            cases,
            temporary_path,
            project_author_name=project_author_name,
        )
        if not validation.policy_satisfied:
            raise ValueError(
                "review packet failed canonical validation: " + "; ".join(validation.errors)
            )
        temporary_path.replace(path)
        return validation
    finally:
        temporary_path.unlink(missing_ok=True)


def record_v1_1_threshold_approval(
    threshold_spec_path: Path,
    approval_path: Path,
    *,
    reviewer_identifier: str,
    reviewer_name: str,
    reviewer_role: str,
    project_author_name: str,
    approved_at: datetime | None = None,
) -> V11ThresholdApprovalEvidence:
    """Record APPROVE_UNCHANGED beside, never inside, the registered proposal."""

    if approval_path.exists():
        raise FileExistsError("threshold approval evidence already exists; refusing to overwrite")
    _validate_reviewer(
        reviewer_identifier=reviewer_identifier,
        reviewer_name=reviewer_name,
        reviewer_role=reviewer_role,
        project_author_name=project_author_name,
    )
    spec = load_v1_1_threshold_spec(threshold_spec_path)
    evidence = V11ThresholdApprovalEvidence(
        spec_id=spec.spec_id,
        threshold_spec_path=threshold_spec_path.as_posix(),
        threshold_spec_sha256=_file_sha256(threshold_spec_path),
        thresholds_sha256=_thresholds_sha256(spec),
        registered_spec_status=spec.registration_status,
        reviewer_identifier=reviewer_identifier.strip(),
        reviewer_name=reviewer_name.strip(),
        reviewer_role=reviewer_role.strip(),
        approved_at=_timestamp_value(approved_at),
    )
    approval_path.parent.mkdir(parents=True, exist_ok=True)
    approval_path.write_text(
        json.dumps(evidence.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return evidence


def validate_v1_1_threshold_approval(
    threshold_spec_path: Path,
    approval_path: Path,
    *,
    project_author_name: str,
    threshold_spec_identity: str | None = None,
    repo_root: Path | None = None,
) -> V11ThresholdApprovalValidation:
    """Validate the approval identity, state, and unchanged threshold checksums."""

    try:
        threshold_spec_bytes = threshold_spec_path.read_bytes()
        unresolved_spec = V11ThresholdSpec.model_validate_json(threshold_spec_bytes)
        inherited_path = resolve_v1_1_week3_threshold_source(
            unresolved_spec,
            repo_root=repo_root,
        )
        inherited_threshold_source_bytes = inherited_path.read_bytes()
        approval_bytes = approval_path.read_bytes()
    except (OSError, ValueError) as exc:
        return _failed_threshold_validation(f"invalid threshold specification: {exc}")
    return validate_v1_1_threshold_approval_bytes(
        threshold_spec_bytes,
        approval_bytes,
        inherited_threshold_source_bytes=inherited_threshold_source_bytes,
        project_author_name=project_author_name,
        threshold_spec_identity=threshold_spec_identity or threshold_spec_path.as_posix(),
    )


def validate_v1_1_threshold_approval_bytes(
    threshold_spec_bytes: bytes,
    approval_bytes: bytes,
    *,
    inherited_threshold_source_bytes: bytes,
    project_author_name: str,
    threshold_spec_identity: str,
) -> V11ThresholdApprovalValidation:
    """Validate approval evidence from one captured set of governed payloads."""

    errors: list[str] = []
    try:
        spec = load_v1_1_threshold_spec_bytes(
            threshold_spec_bytes,
            inherited_threshold_source_bytes=inherited_threshold_source_bytes,
        )
    except (OSError, ValueError) as exc:
        return _failed_threshold_validation(f"invalid threshold specification: {exc}")
    try:
        evidence = V11ThresholdApprovalEvidence.model_validate_json(approval_bytes)
    except (OSError, ValueError) as exc:
        return _failed_threshold_validation(f"invalid threshold approval evidence: {exc}")

    spec_checksum_matches = (
        evidence.threshold_spec_sha256 == hashlib.sha256(threshold_spec_bytes).hexdigest()
    )
    threshold_values_match = evidence.thresholds_sha256 == _thresholds_sha256(spec)
    if evidence.spec_id != spec.spec_id:
        errors.append("approval spec_id differs from the registered proposal")
    if evidence.threshold_spec_path != threshold_spec_identity:
        errors.append("approval threshold_spec_path differs from the validated proposal")
    if not spec_checksum_matches:
        errors.append("threshold specification checksum differs from the approved proposal")
    if not threshold_values_match:
        errors.append("threshold values checksum differs from the approved proposal")
    try:
        _validate_reviewer(
            reviewer_identifier=evidence.reviewer_identifier,
            reviewer_name=evidence.reviewer_name,
            reviewer_role=evidence.reviewer_role,
            project_author_name=project_author_name,
        )
    except ValueError as exc:
        errors.append(str(exc))
    state_valid = (
        spec.registration_status == "PROPOSED_PENDING_HUMAN_APPROVAL"
        and evidence.registered_spec_status == spec.registration_status
        and evidence.approval_status == "HUMAN_APPROVED"
        and evidence.approval_decision == "APPROVE_UNCHANGED"
        and evidence.human_approved
        and not evidence.changed_after_final_results
        and not evidence.frozen_evaluation_run_at_approval
        and not evidence.frozen_final
    )
    if not state_valid:
        errors.append("registration/approval state is invalid")
    policy_satisfied = not errors
    return V11ThresholdApprovalValidation(
        status="PASS" if policy_satisfied else "FAIL",
        policy_satisfied=policy_satisfied,
        human_approved=evidence.human_approved,
        approver=evidence.reviewer_name,
        approved_at=evidence.approved_at.isoformat(),
        approval_decision=evidence.approval_decision,
        thresholds_unchanged=spec_checksum_matches and threshold_values_match,
        threshold_spec_checksum_matches=spec_checksum_matches,
        threshold_values_checksum_matches=threshold_values_match,
        registration_approval_state_valid=state_valid,
        errors=errors,
    )


def find_v1_1_frozen_evaluation_artifacts(results_dir: Path) -> list[str]:
    """Return final/frozen artifact paths without treating Week-3 development evidence as final."""

    if not results_dir.exists():
        return []
    return sorted(
        path.as_posix()
        for path in results_dir.rglob("*")
        if path.is_file() and any(marker in path.name.casefold() for marker in ("final", "frozen"))
    )


def _canonical_current_timestamp(value: datetime | None) -> str:
    return _timestamp_value(value).isoformat(timespec="seconds")


def _timestamp_value(value: datetime | None) -> datetime:
    result = value or datetime.now().astimezone()
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("review/approval timestamp must include a timezone")
    return result.replace(microsecond=0)


def _validate_reviewer(
    *,
    reviewer_identifier: str,
    reviewer_name: str,
    reviewer_role: str,
    project_author_name: str,
) -> None:
    if not reviewer_identifier.strip():
        raise ValueError("reviewer_identifier is required")
    if not reviewer_is_independent_human(reviewer_name):
        raise ValueError("reviewer_name is missing or identifies AI/machine")
    if reviewer_name.strip().casefold() == project_author_name.strip().casefold():
        raise ValueError("reviewer_name matches the project author")
    if not reviewer_role_is_independent(reviewer_role):
        raise ValueError("reviewer_role is missing or not independent")


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _thresholds_sha256(spec: V11ThresholdSpec) -> str:
    payload = json.dumps(
        spec.thresholds.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _temporary_sibling(path: Path) -> Path:
    file_descriptor, name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    os.close(file_descriptor)
    return Path(name)


def _failed_threshold_validation(error: str) -> V11ThresholdApprovalValidation:
    return V11ThresholdApprovalValidation(
        status="FAIL",
        policy_satisfied=False,
        human_approved=False,
        approver=None,
        approved_at=None,
        approval_decision=None,
        thresholds_unchanged=False,
        threshold_spec_checksum_matches=False,
        threshold_values_checksum_matches=False,
        registration_approval_state_valid=False,
        errors=[error],
    )
