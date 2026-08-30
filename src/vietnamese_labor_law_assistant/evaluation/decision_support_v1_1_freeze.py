"""Offline-only governance for materializing the v1.1 frozen evaluation dataset."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1 import (
    V11EvaluationCandidateCase,
    candidate_quality_report,
    load_v1_1_candidate,
    load_v1_1_threshold_spec,
    resolve_v1_1_week3_threshold_source,
    validate_v1_1_review_packet,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_approval import (
    V11ThresholdApprovalEvidence,
    validate_v1_1_threshold_approval,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_artifacts import (
    V11_FREEZE_CODE_RELATIVE_PATHS,
    RepositoryState,
    V11ArtifactPaths,
    canonical_json_bytes,
    inspect_repository_state,
    require_pre_freeze_repository_state,
    sha256_bytes,
    sha256_file,
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

    require_pre_freeze_repository_state(repository_state)
    frozen_timestamp = _timezone_aware_timestamp(frozen_at, name="frozen timestamp")
    cases = load_v1_1_candidate(paths.corrected_candidate)
    if len(cases) != 26:
        raise ValueError("frozen v1.1 evaluation requires exactly 26 cases")
    quality = candidate_quality_report(cases)
    if (
        quality.schema_validation != "PASS"
        or quality.prediction_label_leakage_case_ids != []
        or quality.prediction_label_leakage_assessment != "CHECKED_NO_PREDICTION_ARTIFACT_INPUT"
    ):
        raise ValueError("candidate quality or prediction-input audit failed canonical validation")

    review = validate_v1_1_review_packet(
        cases,
        paths.review_packet,
        project_author_name=project_author_name,
    )
    if not review.policy_satisfied or review.total_rows != 26 or review.pass_count != 26:
        raise ValueError("review packet failed canonical validation: " + "; ".join(review.errors))
    reviewed_at = _review_timestamp(paths.review_packet)

    threshold_identity = paths.threshold_spec.relative_to(paths.repo_root).as_posix()
    threshold_validation = validate_v1_1_threshold_approval(
        paths.threshold_spec,
        paths.threshold_approval,
        project_author_name=project_author_name,
        threshold_spec_identity=threshold_identity,
        repo_root=paths.repo_root,
    )
    if not threshold_validation.policy_satisfied or not _is_canonical_approval_bytes(
        paths.threshold_approval
    ):
        errors = list(threshold_validation.errors)
        if not _is_canonical_approval_bytes(paths.threshold_approval):
            errors.append("threshold approval bytes are not canonical")
        raise ValueError("threshold approval failed canonical validation: " + "; ".join(errors))
    approval = V11ThresholdApprovalEvidence.model_validate_json(
        paths.threshold_approval.read_text(encoding="utf-8")
    )
    if approval.approved_at >= frozen_timestamp:
        raise ValueError("threshold approval must precede frozen timestamp")

    review_sha256 = sha256_file(paths.review_packet)
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
    threshold_spec = load_v1_1_threshold_spec(paths.threshold_spec, repo_root=paths.repo_root)
    evaluation_spec_path = resolve_v1_1_week3_threshold_source(
        threshold_spec,
        repo_root=paths.repo_root,
    )
    manifest = V11FrozenDatasetManifest(
        ordered_case_ids_sha256=sha256_bytes(
            canonical_json_bytes([case.case_id for case in frozen_cases])
        ),
        corrected_candidate_sha256=sha256_file(paths.corrected_candidate),
        frozen_dataset_sha256=sha256_bytes(dataset_bytes),
        review_packet_sha256=review_sha256,
        reviewed_at=reviewed_at,
        threshold_spec_sha256=sha256_file(paths.threshold_spec),
        threshold_approval_sha256=sha256_file(paths.threshold_approval),
        threshold_approved_at=approval.approved_at,
        evaluation_spec_sha256=sha256_file(evaluation_spec_path),
        code_file_sha256={
            relative_path: sha256_file(paths.repo_root / relative_path)
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

    cases = [
        V11FrozenEvaluationCase.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    case_ids = [case.case_id for case in cases]
    if len(cases) != 26 or len(case_ids) != len(set(case_ids)):
        raise ValueError("frozen v1.1 dataset requires exactly 26 unique case IDs")
    return cases


def _review_timestamp(review_packet_path: Path) -> datetime:
    with review_packet_path.open(encoding="utf-8", newline="") as handle:
        timestamps = {row.get("reviewed_at", "").strip() for row in csv.DictReader(handle)}
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
        evidence = V11ThresholdApprovalEvidence.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return False
    expected = json.dumps(evidence.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
    return path.read_text(encoding="utf-8") == expected
