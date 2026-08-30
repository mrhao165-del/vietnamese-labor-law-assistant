"""Offline-only governance for materializing the v1.1 frozen evaluation dataset."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1 import (
    V11EvaluationCandidateCase,
    V11ThresholdSpec,
    candidate_quality_report,
    load_v1_1_candidate_bytes,
    resolve_v1_1_week3_threshold_source,
    validate_v1_1_review_packet_bytes,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_approval import (
    V11ThresholdApprovalEvidence,
    validate_v1_1_threshold_approval_bytes,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_artifacts import (
    V11_FREEZE_CODE_RELATIVE_PATHS,
    RepositoryState,
    V11ArtifactPaths,
    canonical_json_bytes,
    inspect_repository_state,
    require_pre_freeze_repository_state,
    sha256_bytes,
    write_exclusive,
)


class V11FrozenEvaluationCase(V11EvaluationCandidateCase):
    """A reviewed candidate row after the one-way finalization transition."""

    frozen_schema_version: Literal["v1_1_frozen_case_v1"] = "v1_1_frozen_case_v1"
    human_validated: Literal[True] = True
    review_status: Literal["PASS"] = "PASS"
    frozen_final: Literal[True] = True
    reviewed_at: datetime
    review_evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class V11FrozenDatasetManifest(BaseModel):
    """Byte-level provenance of the final, human-reviewed evaluation dataset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["v1_1_frozen_dataset_manifest_v1"] = "v1_1_frozen_dataset_manifest_v1"
    dataset_id: Literal["decision_support_v1_1_final"] = "decision_support_v1_1_final"
    dataset_version: Literal["v1_1_frozen"] = "v1_1_frozen"
    case_count: Literal[26] = 26
    ordered_case_ids_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    corrected_candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    frozen_dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_packet_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_status: Literal["PASS"] = "PASS"
    reviewed_at: datetime
    threshold_spec_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    threshold_approval_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    threshold_approval_decision: Literal["APPROVE_UNCHANGED"] = "APPROVE_UNCHANGED"
    threshold_approved_at: datetime
    evaluation_spec_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_file_sha256: dict[str, str]
    git_commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    pre_freeze_worktree_clean: Literal[True] = True
    frozen_at: datetime


class V11FreezeBundle(BaseModel):
    """Validated frozen rows and deterministic bytes, ready for exclusive persistence."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    cases: tuple[V11FrozenEvaluationCase, ...]
    dataset_bytes: bytes
    manifest: V11FrozenDatasetManifest


def prepare_v1_1_freeze(
    paths: V11ArtifactPaths,
    *,
    project_author_name: str,
    repository_state: RepositoryState,
    frozen_at: datetime | None = None,
) -> V11FreezeBundle:
    """Validate every immutable prerequisite and build, but do not write, a frozen bundle."""

    threshold_spec_bytes = paths.threshold_spec.read_bytes()
    unresolved_spec = V11ThresholdSpec.model_validate_json(threshold_spec_bytes)
    evaluation_spec_path = resolve_v1_1_week3_threshold_source(
        unresolved_spec,
        repo_root=paths.repo_root,
    )
    return prepare_v1_1_freeze_from_bytes(
        corrected_candidate_bytes=paths.corrected_candidate.read_bytes(),
        review_packet_bytes=paths.review_packet.read_bytes(),
        threshold_spec_bytes=threshold_spec_bytes,
        threshold_approval_bytes=paths.threshold_approval.read_bytes(),
        inherited_evaluation_spec_bytes=evaluation_spec_path.read_bytes(),
        code_file_bytes={
            relative_path: (paths.repo_root / relative_path).read_bytes()
            for relative_path in V11_FREEZE_CODE_RELATIVE_PATHS
        },
        threshold_spec_identity=paths.threshold_spec.relative_to(paths.repo_root).as_posix(),
        project_author_name=project_author_name,
        repository_state=repository_state,
        frozen_at=frozen_at,
    )


def prepare_v1_1_freeze_from_bytes(
    *,
    corrected_candidate_bytes: bytes,
    review_packet_bytes: bytes,
    threshold_spec_bytes: bytes,
    threshold_approval_bytes: bytes,
    inherited_evaluation_spec_bytes: bytes,
    code_file_bytes: Mapping[str, bytes],
    threshold_spec_identity: str,
    project_author_name: str,
    repository_state: RepositoryState,
    frozen_at: datetime | None = None,
) -> V11FreezeBundle:
    """Build a freeze bundle from one captured, wholly in-memory input set."""

    require_pre_freeze_repository_state(repository_state)
    frozen_timestamp = _timezone_aware_timestamp(frozen_at, name="frozen timestamp")
    cases = load_v1_1_candidate_bytes(corrected_candidate_bytes)
    if len(cases) != 26:
        raise ValueError("frozen v1.1 evaluation requires exactly 26 cases")
    quality = candidate_quality_report(cases)
    if (
        quality.schema_validation != "PASS"
        or quality.prediction_label_leakage_case_ids != []
        or quality.prediction_label_leakage_assessment != "CHECKED_NO_PREDICTION_ARTIFACT_INPUT"
    ):
        raise ValueError("candidate quality or prediction-input audit failed canonical validation")

    review = validate_v1_1_review_packet_bytes(
        cases,
        review_packet_bytes,
        project_author_name=project_author_name,
    )
    if not review.policy_satisfied or review.total_rows != 26 or review.pass_count != 26:
        raise ValueError("review packet failed canonical validation: " + "; ".join(review.errors))
    reviewed_at = _review_timestamp_bytes(review_packet_bytes)

    threshold_validation = validate_v1_1_threshold_approval_bytes(
        threshold_spec_bytes,
        threshold_approval_bytes,
        inherited_threshold_source_bytes=inherited_evaluation_spec_bytes,
        project_author_name=project_author_name,
        threshold_spec_identity=threshold_spec_identity,
    )
    canonical_approval = _is_canonical_approval_payload(threshold_approval_bytes)
    if not threshold_validation.policy_satisfied or not canonical_approval:
        errors = list(threshold_validation.errors)
        if not canonical_approval:
            errors.append("threshold approval bytes are not canonical")
        raise ValueError("threshold approval failed canonical validation: " + "; ".join(errors))
    approval = V11ThresholdApprovalEvidence.model_validate_json(threshold_approval_bytes)
    if approval.approved_at >= frozen_timestamp:
        raise ValueError("threshold approval must precede frozen timestamp")

    review_sha256 = sha256_bytes(review_packet_bytes)
    frozen_cases = tuple(
        V11FrozenEvaluationCase.model_validate(
            {
                **case.model_dump(mode="json"),
                "human_validated": True,
                "review_status": "PASS",
                "frozen_final": True,
                "reviewed_at": reviewed_at,
                "review_evidence_sha256": review_sha256,
            }
        )
        for case in sorted(cases, key=lambda item: item.case_id)
    )
    dataset_bytes = b"".join(
        canonical_json_bytes(case.model_dump(mode="json")) for case in frozen_cases
    )
    if set(code_file_bytes) != set(V11_FREEZE_CODE_RELATIVE_PATHS):
        raise ValueError("freeze code-file identity set differs from the canonical contract")
    manifest = V11FrozenDatasetManifest(
        ordered_case_ids_sha256=sha256_bytes(
            canonical_json_bytes([case.case_id for case in frozen_cases])
        ),
        corrected_candidate_sha256=sha256_bytes(corrected_candidate_bytes),
        frozen_dataset_sha256=sha256_bytes(dataset_bytes),
        review_packet_sha256=review_sha256,
        reviewed_at=reviewed_at,
        threshold_spec_sha256=sha256_bytes(threshold_spec_bytes),
        threshold_approval_sha256=sha256_bytes(threshold_approval_bytes),
        threshold_approved_at=approval.approved_at,
        evaluation_spec_sha256=sha256_bytes(inherited_evaluation_spec_bytes),
        code_file_sha256={
            relative_path: sha256_bytes(code_file_bytes[relative_path])
            for relative_path in V11_FREEZE_CODE_RELATIVE_PATHS
        },
        git_commit_sha=repository_state.commit_sha,
        frozen_at=frozen_timestamp,
    )
    return V11FreezeBundle(cases=frozen_cases, dataset_bytes=dataset_bytes, manifest=manifest)


def freeze_v1_1_evaluation(
    paths: V11ArtifactPaths,
    *,
    project_author_name: str,
    frozen_at: datetime | None = None,
) -> V11FrozenDatasetManifest:
    """Persist one validated freeze bundle in ordered, write-once dataset/manifest steps."""

    if paths.frozen_dataset.exists() or paths.freeze_manifest.exists():
        raise FileExistsError("frozen dataset or manifest already exists; refusing to overwrite")
    bundle = prepare_v1_1_freeze(
        paths,
        project_author_name=project_author_name,
        repository_state=inspect_repository_state(paths.repo_root),
        frozen_at=frozen_at,
    )
    write_exclusive(paths.frozen_dataset, bundle.dataset_bytes)
    write_exclusive(
        paths.freeze_manifest,
        canonical_json_bytes(bundle.manifest.model_dump(mode="json")),
    )
    return bundle.manifest


def load_v1_1_frozen_dataset(path: Path) -> list[V11FrozenEvaluationCase]:
    """Load final rows and reject empty or duplicate frozen case identifiers."""

    return load_v1_1_frozen_dataset_bytes(path.read_bytes())


def load_v1_1_frozen_dataset_bytes(payload: bytes) -> list[V11FrozenEvaluationCase]:
    """Load final rows from one already-captured byte payload."""

    cases = [
        V11FrozenEvaluationCase.model_validate_json(line)
        for line in payload.splitlines()
        if line.strip()
    ]
    case_ids = [case.case_id for case in cases]
    if len(cases) != 26 or len(case_ids) != len(set(case_ids)):
        raise ValueError("frozen v1.1 dataset requires exactly 26 unique case IDs")
    return cases


def _review_timestamp(review_packet_path: Path) -> datetime:
    return _review_timestamp_bytes(review_packet_path.read_bytes())


def _review_timestamp_bytes(payload: bytes) -> datetime:
    lines = payload.decode("utf-8").splitlines()
    timestamps = {row.get("reviewed_at", "").strip() for row in csv.DictReader(lines)}
    if len(timestamps) != 1:
        raise ValueError("review packet requires exactly one reviewed_at timestamp")
    value = timestamps.pop()
    try:
        reviewed_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("reviewed_at timestamps must use ISO-8601 format") from exc
    return _timezone_aware_timestamp(reviewed_at, name="reviewed_at timestamps")


def _timezone_aware_timestamp(value: datetime | None, *, name: str) -> datetime:
    timestamp = value or datetime.now().astimezone()
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return timestamp.replace(microsecond=0)


def _is_canonical_approval_bytes(path: Path) -> bool:
    try:
        return _is_canonical_approval_payload(path.read_bytes())
    except OSError:
        return False


def _is_canonical_approval_payload(payload: bytes) -> bool:
    try:
        evidence = V11ThresholdApprovalEvidence.model_validate_json(payload)
        normalized_text = payload.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    except (UnicodeDecodeError, ValueError):
        return False
    expected = json.dumps(evidence.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
    return normalized_text == expected
