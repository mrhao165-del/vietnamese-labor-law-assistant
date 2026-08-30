"""Label-isolated preflight and write-once governed v1.1 prediction capture."""

from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import BinaryIO, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.decision_support.intake import (
    CaseIntakeError,
    OpenAIStructuredCaseIntakeExtractor,
    validate_case_intake_result,
)
from vietnamese_labor_law_assistant.decision_support.models import (
    CaseIntakeInput,
    CaseIntakeResult,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1 import (
    V11ThresholdSpec,
    candidate_quality_report,
    load_v1_1_candidate_bytes,
    validate_v1_1_review_packet_bytes,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_approval import (
    validate_v1_1_threshold_approval_bytes,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_artifacts import (
    V11_FREEZE_CODE_RELATIVE_PATHS,
    RepositoryState,
    V11ArtifactPaths,
    canonical_json_bytes,
    inspect_repository_state,
    require_capture_repository_state,
    sha256_bytes,
    write_exclusive,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_freeze import (
    V11FrozenDatasetManifest,
    V11FrozenEvaluationCase,
    load_v1_1_frozen_dataset_bytes,
    prepare_v1_1_freeze_from_bytes,
)

_EXTRACTOR_CLASS = (
    "vietnamese_labor_law_assistant.decision_support.intake.OpenAIStructuredCaseIntakeExtractor"
)
_INTAKE_IMPLEMENTATION_PATH = "src/vietnamese_labor_law_assistant/decision_support/intake.py"
_RESPONSE_SCHEMA_IDENTITY = (
    "vietnamese_labor_law_assistant.decision_support.models.CaseIntakeResult"
)


@dataclass(frozen=True)
class _FileIdentity:
    device: int
    inode: int
    mode: int
    size: int
    modified_ns: int
    changed_ns: int

    @classmethod
    def from_stat(cls, value: os.stat_result) -> _FileIdentity:
        return cls(
            device=value.st_dev,
            inode=value.st_ino,
            mode=value.st_mode,
            size=value.st_size,
            modified_ns=value.st_mtime_ns,
            changed_ns=value.st_ctime_ns,
        )


@dataclass(frozen=True)
class _CapturedFile:
    path: Path
    relative_path: str
    payload: bytes
    identity: _FileIdentity


@dataclass(frozen=True)
class _CaptureSnapshot:
    files: dict[str, _CapturedFile]

    def captured(self, path: Path, repo_root: Path) -> _CapturedFile:
        relative = _relative_path(repo_root, path).as_posix()
        return self.files[relative]


@dataclass(frozen=True)
class _PredictionStreamBinding:
    parent_identity: _FileIdentity
    file_identity: _FileIdentity


@dataclass(frozen=True)
class _CaptureOutputDirectoryBinding:
    path: Path
    identity: _FileIdentity
    descriptor: int | None


class V11RuntimeCase(BaseModel):
    """Bookkeeping identity and the only object permitted to reach the extractor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    case_input: CaseIntakeInput


class V11NonSecretGenerationSettings(BaseModel):
    """Explicitly selected production settings safe to persist as capture metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["openai", "gemini_openai_compatible"]
    model: str
    base_url: str | None
    timeout_seconds: float
    transport_max_retries: int
    structured_output_max_retries: int
    temperature: Literal[0] = 0
    nominal_parse_calls: Literal[26] = 26
    maximum_parse_invocations: int
    theoretical_maximum_http_attempts: int


class V11CapturePlan(BaseModel):
    """Fully validated, label-free inputs and provenance for one future live capture."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    runtime_cases: tuple[V11RuntimeCase, ...]
    dataset_id: Literal["decision_support_v1_1_final"]
    dataset_version: Literal["v1_1_frozen"]
    case_count: Literal[26]
    review_status: Literal["PASS"]
    threshold_approval_decision: Literal["APPROVE_UNCHANGED"]
    frozen_dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    freeze_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    corrected_candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_packet_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    threshold_spec_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    threshold_approval_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    git_commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    extractor_class: Literal[
        "vietnamese_labor_law_assistant.decision_support.intake.OpenAIStructuredCaseIntakeExtractor"
    ]
    extractor_implementation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_identity_method: Literal["BOUND_TO_FULL_INTAKE_MODULE_BYTES"]
    response_schema_identity: Literal[
        "vietnamese_labor_law_assistant.decision_support.models.CaseIntakeResult"
    ]
    generation_settings: V11NonSecretGenerationSettings


class V11PredictionStatus(StrEnum):
    """Per-case result state persisted in the production prediction stream."""

    SUCCESS = "SUCCESS"
    ERROR = "ERROR"


class V11PredictionFailureReason(StrEnum):
    """The complete non-secret allowlist for persisted Case Intake failures."""

    PROVIDER_UNAVAILABLE = "CASE_INTAKE_PROVIDER_UNAVAILABLE"
    EMPTY_OUTPUT = "CASE_INTAKE_EMPTY_OUTPUT"
    SOURCE_INVALID = "CASE_INTAKE_SOURCE_INVALID"
    SCHEMA_INVALID = "CASE_INTAKE_SCHEMA_INVALID"
    TIMEOUT = "CASE_INTAKE_TIMEOUT"
    PROVIDER_ERROR = "CASE_INTAKE_PROVIDER_ERROR"
    UNEXPECTED_ERROR = "CASE_INTAKE_UNEXPECTED_ERROR"


class V11CaseIntakePredictionRecord(BaseModel):
    """One canonical, label-free production prediction or sanitized failure."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int = Field(ge=1, le=26)
    case_id: str
    status: V11PredictionStatus
    result: CaseIntakeResult | None = None
    failure_reason: V11PredictionFailureReason | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> V11CaseIntakePredictionRecord:
        if (self.status is V11PredictionStatus.SUCCESS) != (self.result is not None):
            raise ValueError("SUCCESS requires one validated CaseIntakeResult")
        if (self.status is V11PredictionStatus.ERROR) != (self.failure_reason is not None):
            raise ValueError("ERROR requires one typed failure reason")
        return self


class _V11CaptureIdentity(BaseModel):
    """Plan-bound identity fields safe to persist without runtime inputs or labels."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: Literal["decision_support_v1_1_final"]
    dataset_version: Literal["v1_1_frozen"]
    case_count: Literal[26]
    frozen_dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    freeze_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    corrected_candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_packet_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    threshold_spec_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    threshold_approval_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    git_commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    extractor_class: Literal[
        "vietnamese_labor_law_assistant.decision_support.intake.OpenAIStructuredCaseIntakeExtractor"
    ]
    extractor_implementation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_identity_method: Literal["BOUND_TO_FULL_INTAKE_MODULE_BYTES"]
    response_schema_identity: Literal[
        "vietnamese_labor_law_assistant.decision_support.models.CaseIntakeResult"
    ]
    generation_settings: V11NonSecretGenerationSettings


class V11CaptureIntent(_V11CaptureIdentity):
    """Exclusive audit claim created before extractor construction or provider use."""

    schema_version: Literal["v1_1_capture_intent_v1"] = "v1_1_capture_intent_v1"
    status: Literal["STARTED"] = "STARTED"
    started_at: datetime

    @model_validator(mode="after")
    def validate_started_at(self) -> V11CaptureIntent:
        _require_timezone_aware(self.started_at, "capture start timestamp")
        return self


class V11PredictionSnapshotManifest(_V11CaptureIdentity):
    """Final checksum-bound status created only after all cases were attempted."""

    schema_version: Literal["v1_1_prediction_snapshot_manifest_v1"] = (
        "v1_1_prediction_snapshot_manifest_v1"
    )
    status: Literal["COMPLETE", "FAILED"]
    started_at: datetime
    completed_at: datetime
    predictions_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    total_count: Literal[26] = 26
    success_count: int = Field(ge=0, le=26)
    failure_count: int = Field(ge=0, le=26)

    @model_validator(mode="after")
    def validate_final_status(self) -> V11PredictionSnapshotManifest:
        _require_timezone_aware(self.started_at, "capture start timestamp")
        _require_timezone_aware(self.completed_at, "capture completion timestamp")
        if self.completed_at < self.started_at:
            raise ValueError("capture completion timestamp must not precede start")
        if self.success_count + self.failure_count != self.total_count:
            raise ValueError("prediction counts must total 26")
        complete = self.success_count == 26 and self.failure_count == 0
        if (self.status == "COMPLETE") != complete:
            raise ValueError("COMPLETE requires 26 successful prediction records")
        return self


def project_runtime_case(case: V11FrozenEvaluationCase) -> V11RuntimeCase:
    """Copy only legitimate production input fields out of one frozen labeled row."""

    return V11RuntimeCase(
        case_id=case.case_id,
        case_input=CaseIntakeInput(
            source_text=case.raw_user_input,
            source_ref=case.source_ref,
        ),
    )


def load_v1_1_prediction_records(path: Path) -> list[V11CaseIntakePredictionRecord]:
    """Load canonical prediction rows and verify frozen sequence/identity invariants."""

    return _load_v1_1_prediction_records_bytes(path.read_bytes())


def _load_v1_1_prediction_records_bytes(
    payload: bytes,
) -> list[V11CaseIntakePredictionRecord]:
    records = [
        V11CaseIntakePredictionRecord.model_validate_json(line)
        for line in payload.decode("utf-8").splitlines()
        if line.strip()
    ]
    if [record.sequence for record in records] != list(range(1, len(records) + 1)):
        raise ValueError("prediction records must use contiguous frozen order")
    case_ids = [record.case_id for record in records]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("prediction records contain duplicate case IDs")
    return records


async def capture_v1_1_predictions(
    paths: V11ArtifactPaths,
    plan: V11CapturePlan,
    settings: Settings,
    *,
    captured_at: datetime | None = None,
) -> V11PredictionSnapshotManifest:
    """Claim and execute exactly one durable production Case Intake capture attempt."""

    _require_canonical_paths(paths)
    _require_execution_plan(plan, settings)
    started_at = _capture_start_timestamp(captured_at)
    _require_no_existing_capture_artifact(paths)

    paths.capture_intent.parent.mkdir(parents=True, exist_ok=True)
    with _bind_capture_output_directory(paths) as output_directory:
        intent = _capture_intent(plan, started_at)
        intent_bytes = canonical_json_bytes(intent.model_dump(mode="json"))
        write_exclusive(paths.capture_intent, intent_bytes)

        _require_safe_output_path(paths.repo_root, paths.predictions)
        with paths.predictions.open("x+b") as handle:
            stream_binding = _bind_prediction_stream(
                paths,
                handle,
                output_directory.identity,
            )
            runtime_cases = _revalidate_execution_boundary(
                paths,
                plan,
                intent_bytes,
                handle,
                stream_binding,
            )
            extractor = OpenAIStructuredCaseIntakeExtractor(settings)
            success_count = 0
            failure_count = 0
            row_payloads: list[bytes] = []
            for sequence, runtime_case in enumerate(runtime_cases, start=1):
                try:
                    extracted = await extractor.extract(runtime_case.case_input)
                    result = validate_case_intake_result(runtime_case.case_input, extracted)
                    record = V11CaseIntakePredictionRecord(
                        sequence=sequence,
                        case_id=runtime_case.case_id,
                        status=V11PredictionStatus.SUCCESS,
                        result=result,
                    )
                    success_count += 1
                except CaseIntakeError as exc:
                    record = _failure_record(sequence, runtime_case.case_id, exc.reason)
                    failure_count += 1
                except Exception:
                    record = _failure_record(
                        sequence,
                        runtime_case.case_id,
                        V11PredictionFailureReason.UNEXPECTED_ERROR,
                    )
                    failure_count += 1
                row_payload = canonical_json_bytes(record.model_dump(mode="json"))
                row_payloads.append(row_payload)
                handle.write(row_payload)
                handle.flush()
                os.fsync(handle.fileno())

            expected_payload = b"".join(row_payloads)
            predictions_sha256 = _validate_final_prediction_stream(
                paths,
                handle,
                stream_binding,
                expected_payload=expected_payload,
                runtime_cases=runtime_cases,
                success_count=success_count,
                failure_count=failure_count,
            )
            manifest = _prediction_snapshot_manifest(
                plan,
                started_at=started_at,
                completed_at=_timestamp_value(None),
                predictions_sha256=predictions_sha256,
                success_count=success_count,
                failure_count=failure_count,
            )
            _publish_prediction_manifest(
                paths,
                handle,
                stream_binding,
                output_directory,
                manifest,
                expected_payload=expected_payload,
                runtime_cases=runtime_cases,
                success_count=success_count,
                failure_count=failure_count,
            )
            return manifest


def preflight_v1_1_capture(
    paths: V11ArtifactPaths,
    settings: Settings,
    *,
    project_author_name: str,
    repository_state: RepositoryState | None = None,
) -> V11CapturePlan:
    """Fail closed on any governance drift and return a label-isolated capture plan."""

    _require_canonical_paths(paths)
    _require_no_existing_capture_artifact(paths)
    generation_settings = _non_secret_generation_settings(settings)
    initial_state = repository_state or inspect_repository_state(paths.repo_root)
    _require_repository_identity(initial_state, paths)

    snapshot = _snapshot_governed_files(paths)
    manifest_file = snapshot.captured(paths.freeze_manifest, paths.repo_root)
    manifest = V11FrozenDatasetManifest.model_validate_json(manifest_file.payload)
    if manifest_file.payload != canonical_json_bytes(manifest.model_dump(mode="json")):
        raise ValueError("freeze manifest bytes are not canonical")
    if initial_state.commit_sha != manifest.git_commit_sha:
        raise ValueError("Git source commit changed after the governed freeze")

    _require_snapshot_checksum(
        snapshot,
        paths.corrected_candidate,
        paths,
        manifest.corrected_candidate_sha256,
        "corrected candidate checksum changed",
    )
    _require_snapshot_checksum(
        snapshot,
        paths.review_packet,
        paths,
        manifest.review_packet_sha256,
        "human review checksum changed",
    )
    _require_snapshot_checksum(
        snapshot,
        paths.threshold_spec,
        paths,
        manifest.threshold_spec_sha256,
        "threshold specification checksum changed",
    )
    _require_snapshot_checksum(
        snapshot,
        paths.threshold_approval,
        paths,
        manifest.threshold_approval_sha256,
        "threshold approval checksum changed",
    )
    _require_snapshot_checksum(
        snapshot,
        paths.frozen_dataset,
        paths,
        manifest.frozen_dataset_sha256,
        "frozen dataset checksum changed",
    )

    _require_code_identity(snapshot, paths, manifest)
    candidate_payload = snapshot.captured(paths.corrected_candidate, paths.repo_root).payload
    review_payload = snapshot.captured(paths.review_packet, paths.repo_root).payload
    threshold_payload = snapshot.captured(paths.threshold_spec, paths.repo_root).payload
    approval_payload = snapshot.captured(paths.threshold_approval, paths.repo_root).payload
    frozen_payload = snapshot.captured(paths.frozen_dataset, paths.repo_root).payload
    threshold_spec = V11ThresholdSpec.model_validate_json(threshold_payload)
    inherited_path = paths.repo_root / Path(threshold_spec.week3_threshold_source)
    inherited_payload = snapshot.captured(inherited_path, paths.repo_root).payload

    candidate_cases = load_v1_1_candidate_bytes(candidate_payload)
    quality = candidate_quality_report(candidate_cases)
    if (
        len(candidate_cases) != 26
        or quality.schema_validation != "PASS"
        or quality.prediction_label_leakage_case_ids
        or quality.prediction_label_leakage_assessment != "CHECKED_NO_PREDICTION_ARTIFACT_INPUT"
    ):
        raise ValueError("corrected candidate failed canonical capture validation")

    review = validate_v1_1_review_packet_bytes(
        candidate_cases,
        review_payload,
        project_author_name=project_author_name,
    )
    if (
        not review.policy_satisfied
        or review.total_rows != 26
        or review.pass_count != 26
        or review.status != "PASS"
    ):
        raise ValueError("human review is no longer 26/26 PASS")

    threshold_identity = paths.threshold_spec.relative_to(paths.repo_root).as_posix()
    approval = validate_v1_1_threshold_approval_bytes(
        threshold_payload,
        approval_payload,
        inherited_threshold_source_bytes=inherited_payload,
        project_author_name=project_author_name,
        threshold_spec_identity=threshold_identity,
    )
    if (
        not approval.policy_satisfied
        or approval.status != "PASS"
        or approval.approval_decision != "APPROVE_UNCHANGED"
        or not approval.thresholds_unchanged
        or not approval.registration_approval_state_valid
    ):
        raise ValueError("threshold approval state is invalid")

    frozen_cases = load_v1_1_frozen_dataset_bytes(frozen_payload)
    ordered_case_ids = [case.case_id for case in frozen_cases]
    ordered_case_ids_sha256 = sha256_bytes(canonical_json_bytes(ordered_case_ids))
    if ordered_case_ids_sha256 != manifest.ordered_case_ids_sha256:
        raise ValueError("ordered frozen case IDs changed")
    if ordered_case_ids != sorted(case.case_id for case in candidate_cases):
        raise ValueError("frozen case IDs differ from the corrected candidate")

    regenerated = prepare_v1_1_freeze_from_bytes(
        corrected_candidate_bytes=candidate_payload,
        review_packet_bytes=review_payload,
        threshold_spec_bytes=threshold_payload,
        threshold_approval_bytes=approval_payload,
        inherited_evaluation_spec_bytes=inherited_payload,
        code_file_bytes={
            relative_path: snapshot.captured(
                paths.repo_root / relative_path,
                paths.repo_root,
            ).payload
            for relative_path in V11_FREEZE_CODE_RELATIVE_PATHS
        },
        threshold_spec_identity=threshold_identity,
        project_author_name=project_author_name,
        repository_state=RepositoryState(
            commit_sha=manifest.git_commit_sha,
            tracked_dirty=False,
            untracked_paths=(),
            git_top_level=paths.repo_root,
        ),
        frozen_at=manifest.frozen_at,
    )
    if regenerated.dataset_bytes != frozen_payload:
        raise ValueError("frozen dataset differs from the governed freeze inputs")
    if regenerated.manifest != manifest:
        raise ValueError("freeze manifest differs from revalidated governance state")
    runtime_cases = tuple(project_runtime_case(case) for case in frozen_cases)

    plan = V11CapturePlan(
        runtime_cases=runtime_cases,
        dataset_id=manifest.dataset_id,
        dataset_version=manifest.dataset_version,
        case_count=manifest.case_count,
        review_status=manifest.review_status,
        threshold_approval_decision=manifest.threshold_approval_decision,
        frozen_dataset_sha256=manifest.frozen_dataset_sha256,
        freeze_manifest_sha256=sha256_bytes(manifest_file.payload),
        corrected_candidate_sha256=manifest.corrected_candidate_sha256,
        review_packet_sha256=manifest.review_packet_sha256,
        threshold_spec_sha256=manifest.threshold_spec_sha256,
        threshold_approval_sha256=manifest.threshold_approval_sha256,
        git_commit_sha=manifest.git_commit_sha,
        extractor_class=_EXTRACTOR_CLASS,
        extractor_implementation_sha256=manifest.code_file_sha256[_INTAKE_IMPLEMENTATION_PATH],
        prompt_identity_method="BOUND_TO_FULL_INTAKE_MODULE_BYTES",
        response_schema_identity=_RESPONSE_SCHEMA_IDENTITY,
        generation_settings=generation_settings,
    )
    _revalidate_before_return(
        paths,
        snapshot,
        manifest,
        repository_state=repository_state,
    )
    return plan


def _require_canonical_paths(paths: V11ArtifactPaths) -> None:
    try:
        resolved_root = paths.repo_root.resolve(strict=True)
    except OSError as exc:
        raise ValueError("capture repository root does not exist") from exc
    if not resolved_root.is_dir() or paths.repo_root != resolved_root:
        raise ValueError("capture repository root is not canonical")
    expected = V11ArtifactPaths.from_root(paths.repo_root)
    if paths != expected:
        raise ValueError("capture paths differ from the canonical v1.1 artifact contract")


def _require_no_existing_capture_artifact(paths: V11ArtifactPaths) -> None:
    for path in (paths.capture_intent, paths.predictions, paths.snapshot_manifest):
        if os.path.lexists(path):
            raise FileExistsError(f"capture artifact already exists: {path}")
        _require_safe_output_path(paths.repo_root, path)


def _snapshot_governed_files(paths: V11ArtifactPaths) -> _CaptureSnapshot:
    captured: dict[str, _CapturedFile] = {}
    for path in (
        paths.corrected_candidate,
        paths.review_packet,
        paths.threshold_spec,
        paths.threshold_approval,
        paths.frozen_dataset,
        paths.freeze_manifest,
    ):
        item = _snapshot_file(paths.repo_root, path)
        captured[item.relative_path] = item

    threshold_payload = captured[
        _relative_path(paths.repo_root, paths.threshold_spec).as_posix()
    ].payload
    threshold_spec = V11ThresholdSpec.model_validate_json(threshold_payload)
    evaluation_relative = Path(threshold_spec.week3_threshold_source)
    if evaluation_relative.is_absolute():
        raise ValueError("governed threshold source must remain repository-relative")
    evaluation_path = paths.repo_root / evaluation_relative
    evaluation = _snapshot_file(paths.repo_root, evaluation_path)
    captured[evaluation.relative_path] = evaluation

    for relative_path in V11_FREEZE_CODE_RELATIVE_PATHS:
        item = _snapshot_file(paths.repo_root, paths.repo_root / relative_path)
        captured[item.relative_path] = item
    return _CaptureSnapshot(files=captured)


def _snapshot_file(repo_root: Path, path: Path) -> _CapturedFile:
    _require_safe_existing_file(repo_root, path)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        before = _FileIdentity.from_stat(os.fstat(descriptor))
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 1024 * 1024):
            chunks.append(chunk)
        after = _FileIdentity.from_stat(os.fstat(descriptor))
    finally:
        os.close(descriptor)
    if before != after or _FileIdentity.from_stat(os.lstat(path)) != after:
        raise ValueError(f"governed file changed while being captured: {path}")
    relative = _relative_path(repo_root, path).as_posix()
    return _CapturedFile(
        path=path,
        relative_path=relative,
        payload=b"".join(chunks),
        identity=after,
    )


def _revalidate_before_return(
    paths: V11ArtifactPaths,
    snapshot: _CaptureSnapshot,
    manifest: V11FrozenDatasetManifest,
    *,
    repository_state: RepositoryState | None,
) -> None:
    _require_canonical_paths(paths)
    final_files: dict[str, _CapturedFile] = {}
    for captured in snapshot.files.values():
        final = _snapshot_file(paths.repo_root, captured.path)
        final_files[final.relative_path] = final
    for relative_path, captured in snapshot.files.items():
        final = final_files[relative_path]
        if final.payload != captured.payload:
            raise ValueError(f"governed file bytes changed during preflight: {captured.path}")
        if final.identity != captured.identity:
            raise ValueError(f"governed file identity changed during preflight: {captured.path}")
    final_state = repository_state or inspect_repository_state(paths.repo_root)
    _require_repository_identity(final_state, paths)
    if final_state.commit_sha != manifest.git_commit_sha:
        raise ValueError("Git source commit changed during capture preflight")
    _require_no_existing_capture_artifact(paths)


def _require_repository_identity(state: RepositoryState, paths: V11ArtifactPaths) -> None:
    require_capture_repository_state(state, paths)
    if state.git_top_level is None:
        raise ValueError("Git top-level identity is required for capture preflight")
    try:
        top_level = state.git_top_level.resolve(strict=True)
    except OSError as exc:
        raise ValueError("Git top-level identity does not exist") from exc
    if top_level != paths.repo_root:
        raise ValueError("repository root differs from Git top-level")


def _relative_path(repo_root: Path, path: Path) -> Path:
    try:
        relative = path.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError(f"governed path escapes the repository root: {path}") from exc
    if ".." in relative.parts:
        raise ValueError(f"governed path escapes the repository root: {path}")
    return relative


def _require_safe_existing_file(repo_root: Path, path: Path) -> None:
    relative = _relative_path(repo_root, path)
    _reject_symlink_components(repo_root, relative)
    if not os.path.lexists(path):
        raise FileNotFoundError(f"required capture preflight artifact is missing: {path}")
    try:
        path.resolve(strict=True).relative_to(repo_root)
    except (OSError, ValueError) as exc:
        raise ValueError(f"governed path escapes the repository root: {path}") from exc
    if not path.is_file():
        raise ValueError(f"governed path is not a regular file: {path}")


def _require_safe_output_path(repo_root: Path, path: Path) -> None:
    relative = _relative_path(repo_root, path)
    _reject_symlink_components(repo_root, relative.parent)
    try:
        path.parent.resolve(strict=False).relative_to(repo_root)
    except ValueError as exc:
        raise ValueError(f"capture output path escapes the repository root: {path}") from exc


def _reject_symlink_components(repo_root: Path, relative: Path) -> None:
    current = repo_root
    for part in relative.parts:
        current /= part
        if os.path.lexists(current) and current.is_symlink():
            raise ValueError(f"governed paths must not contain symlinks: {current}")


def _non_secret_generation_settings(settings: Settings) -> V11NonSecretGenerationSettings:
    if settings.llm_provider == "gemini_openai_compatible" and settings.openai_base_url is None:
        raise ValueError("Gemini provider requires a configured base URL")
    if (
        not settings.llm_configured
        or settings.openai_api_key is None
        or not settings.openai_api_key.get_secret_value().strip()
        or settings.llm_model is None
    ):
        raise ValueError("production LLM provider is not configured")
    if settings.openai_base_url is not None:
        parsed = urlparse(settings.openai_base_url)
        if (
            parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("provider base URL contains non-persistable components")

    parse_attempts = settings.agent_structured_output_max_retries + 1
    http_attempts = settings.llm_max_retries + 1
    maximum_parse_invocations = 26 * parse_attempts
    theoretical_maximum_http_attempts = maximum_parse_invocations * http_attempts
    return V11NonSecretGenerationSettings(
        provider=settings.llm_provider,
        model=settings.llm_model,
        base_url=settings.openai_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
        transport_max_retries=settings.llm_max_retries,
        structured_output_max_retries=settings.agent_structured_output_max_retries,
        maximum_parse_invocations=maximum_parse_invocations,
        theoretical_maximum_http_attempts=theoretical_maximum_http_attempts,
    )


def _require_snapshot_checksum(
    snapshot: _CaptureSnapshot,
    path: Path,
    paths: V11ArtifactPaths,
    expected: str,
    error: str,
) -> None:
    if sha256_bytes(snapshot.captured(path, paths.repo_root).payload) != expected:
        raise ValueError(error)


def _require_code_identity(
    snapshot: _CaptureSnapshot,
    paths: V11ArtifactPaths,
    manifest: V11FrozenDatasetManifest,
) -> None:
    if set(manifest.code_file_sha256) != set(V11_FREEZE_CODE_RELATIVE_PATHS):
        raise ValueError("freeze manifest code-file identity set changed")
    for relative_path in V11_FREEZE_CODE_RELATIVE_PATHS:
        code_path = paths.repo_root / relative_path
        captured = snapshot.captured(code_path, paths.repo_root)
        if sha256_bytes(captured.payload) != manifest.code_file_sha256[relative_path]:
            raise ValueError(f"code file checksum changed: {relative_path}")


def _require_execution_plan(plan: V11CapturePlan, settings: Settings) -> None:
    runtime_case_ids = [runtime.case_id for runtime in plan.runtime_cases]
    if len(plan.runtime_cases) != 26 or plan.case_count != len(plan.runtime_cases):
        raise ValueError("capture plan must contain exactly 26 runtime cases")
    if len(runtime_case_ids) != len(set(runtime_case_ids)):
        raise ValueError("capture plan contains duplicate case IDs")
    if runtime_case_ids != sorted(runtime_case_ids):
        raise ValueError("capture plan case IDs differ from frozen order")
    if any(type(runtime.case_input) is not CaseIntakeInput for runtime in plan.runtime_cases):
        raise ValueError("capture plan must contain only exact CaseIntakeInput objects")
    if (
        plan.extractor_class != _EXTRACTOR_CLASS
        or plan.prompt_identity_method != "BOUND_TO_FULL_INTAKE_MODULE_BYTES"
        or plan.response_schema_identity != _RESPONSE_SCHEMA_IDENTITY
    ):
        raise ValueError("capture plan production identity changed after preflight")
    if _non_secret_generation_settings(settings) != plan.generation_settings:
        raise ValueError("generation settings changed after capture preflight")


def _capture_identity(plan: V11CapturePlan) -> _V11CaptureIdentity:
    return _V11CaptureIdentity(
        dataset_id=plan.dataset_id,
        dataset_version=plan.dataset_version,
        case_count=plan.case_count,
        frozen_dataset_sha256=plan.frozen_dataset_sha256,
        freeze_manifest_sha256=plan.freeze_manifest_sha256,
        corrected_candidate_sha256=plan.corrected_candidate_sha256,
        review_packet_sha256=plan.review_packet_sha256,
        threshold_spec_sha256=plan.threshold_spec_sha256,
        threshold_approval_sha256=plan.threshold_approval_sha256,
        git_commit_sha=plan.git_commit_sha,
        extractor_class=plan.extractor_class,
        extractor_implementation_sha256=plan.extractor_implementation_sha256,
        prompt_identity_method=plan.prompt_identity_method,
        response_schema_identity=plan.response_schema_identity,
        generation_settings=plan.generation_settings,
    )


def _capture_intent(plan: V11CapturePlan, started_at: datetime) -> V11CaptureIntent:
    return V11CaptureIntent(
        **_capture_identity(plan).model_dump(mode="python"),
        started_at=started_at,
    )


def _prediction_snapshot_manifest(
    plan: V11CapturePlan,
    *,
    started_at: datetime,
    completed_at: datetime,
    predictions_sha256: str,
    success_count: int,
    failure_count: int,
) -> V11PredictionSnapshotManifest:
    status: Literal["COMPLETE", "FAILED"] = (
        "COMPLETE" if success_count == 26 and failure_count == 0 else "FAILED"
    )
    return V11PredictionSnapshotManifest(
        **_capture_identity(plan).model_dump(mode="python"),
        status=status,
        started_at=started_at,
        completed_at=completed_at,
        predictions_sha256=predictions_sha256,
        success_count=success_count,
        failure_count=failure_count,
    )


def _failure_record(
    sequence: int,
    case_id: str,
    reason: str | V11PredictionFailureReason,
) -> V11CaseIntakePredictionRecord:
    try:
        allowed_reason = V11PredictionFailureReason(reason)
    except (TypeError, ValueError):
        allowed_reason = V11PredictionFailureReason.UNEXPECTED_ERROR
    return V11CaseIntakePredictionRecord(
        sequence=sequence,
        case_id=case_id,
        status=V11PredictionStatus.ERROR,
        failure_reason=allowed_reason,
    )


def _revalidate_execution_boundary(
    paths: V11ArtifactPaths,
    plan: V11CapturePlan,
    expected_intent_bytes: bytes,
    handle: BinaryIO,
    stream_binding: _PredictionStreamBinding,
) -> tuple[V11RuntimeCase, ...]:
    """Recheck bound bytes after claiming outputs, without silently rerunning preflight."""

    _require_canonical_paths(paths)
    intent = _snapshot_file(paths.repo_root, paths.capture_intent)
    if intent.payload != expected_intent_bytes:
        raise ValueError("capture intent changed after exclusive claim")
    _require_prediction_stream_binding(paths, handle, stream_binding)
    if os.fstat(handle.fileno()).st_size:
        raise ValueError("prediction stream was not empty after exclusive claim")
    if os.path.lexists(paths.snapshot_manifest):
        raise FileExistsError(f"capture artifact already exists: {paths.snapshot_manifest}")
    _require_safe_output_path(paths.repo_root, paths.snapshot_manifest)

    snapshot = _snapshot_governed_files(paths)
    manifest_file = snapshot.captured(paths.freeze_manifest, paths.repo_root)
    manifest = V11FrozenDatasetManifest.model_validate_json(manifest_file.payload)
    if manifest_file.payload != canonical_json_bytes(manifest.model_dump(mode="json")):
        raise ValueError("freeze manifest bytes are not canonical")
    if sha256_bytes(manifest_file.payload) != plan.freeze_manifest_sha256:
        raise ValueError("freeze manifest checksum changed")

    for path, expected, error in (
        (
            paths.corrected_candidate,
            plan.corrected_candidate_sha256,
            "corrected candidate checksum changed",
        ),
        (paths.review_packet, plan.review_packet_sha256, "human review checksum changed"),
        (
            paths.threshold_spec,
            plan.threshold_spec_sha256,
            "threshold specification checksum changed",
        ),
        (
            paths.threshold_approval,
            plan.threshold_approval_sha256,
            "threshold approval checksum changed",
        ),
        (
            paths.frozen_dataset,
            plan.frozen_dataset_sha256,
            "frozen dataset checksum changed",
        ),
    ):
        _require_snapshot_checksum(snapshot, path, paths, expected, error)

    manifest_identity = (
        manifest.dataset_id,
        manifest.dataset_version,
        manifest.case_count,
        manifest.review_status,
        manifest.threshold_approval_decision,
        manifest.frozen_dataset_sha256,
        manifest.corrected_candidate_sha256,
        manifest.review_packet_sha256,
        manifest.threshold_spec_sha256,
        manifest.threshold_approval_sha256,
        manifest.git_commit_sha,
        manifest.code_file_sha256.get(_INTAKE_IMPLEMENTATION_PATH),
    )
    plan_identity = (
        plan.dataset_id,
        plan.dataset_version,
        plan.case_count,
        plan.review_status,
        plan.threshold_approval_decision,
        plan.frozen_dataset_sha256,
        plan.corrected_candidate_sha256,
        plan.review_packet_sha256,
        plan.threshold_spec_sha256,
        plan.threshold_approval_sha256,
        plan.git_commit_sha,
        plan.extractor_implementation_sha256,
    )
    if manifest_identity != plan_identity:
        raise ValueError("capture plan identity differs from the frozen manifest")
    _require_code_identity(snapshot, paths, manifest)

    frozen_payload = snapshot.captured(paths.frozen_dataset, paths.repo_root).payload
    canonical_runtime_cases = tuple(
        project_runtime_case(case) for case in load_v1_1_frozen_dataset_bytes(frozen_payload)
    )
    if canonical_runtime_cases != plan.runtime_cases:
        raise ValueError("capture plan runtime cases differ from the frozen dataset")

    _require_execution_snapshot_stable(paths, snapshot)
    state = inspect_repository_state(paths.repo_root)
    _require_execution_repository_state(state, paths, manifest)

    final_intent = _snapshot_file(paths.repo_root, paths.capture_intent)
    if final_intent.payload != intent.payload:
        raise ValueError("capture intent bytes changed during execution revalidation")
    if final_intent.identity != intent.identity:
        raise ValueError("capture intent identity changed during execution revalidation")
    _require_prediction_stream_binding(paths, handle, stream_binding)
    if os.path.lexists(paths.snapshot_manifest):
        raise FileExistsError(f"capture artifact already exists: {paths.snapshot_manifest}")
    return plan.runtime_cases


def _require_execution_snapshot_stable(
    paths: V11ArtifactPaths,
    snapshot: _CaptureSnapshot,
) -> None:
    for captured in snapshot.files.values():
        final = _snapshot_file(paths.repo_root, captured.path)
        if final.payload != captured.payload:
            raise ValueError(
                f"governed file bytes changed during capture execution: {captured.path}"
            )
        if final.identity != captured.identity:
            raise ValueError(
                f"governed file identity changed during capture execution: {captured.path}"
            )


def _require_execution_repository_state(
    state: RepositoryState,
    paths: V11ArtifactPaths,
    manifest: V11FrozenDatasetManifest,
) -> None:
    if state.git_top_level is None:
        raise ValueError("Git top-level identity is required at capture execution boundary")
    try:
        top_level = state.git_top_level.resolve(strict=True)
    except OSError as exc:
        raise ValueError(
            "Git top-level identity does not exist at capture execution boundary"
        ) from exc
    if top_level != paths.repo_root:
        raise ValueError("repository root differs from Git top-level at capture execution boundary")
    if state.commit_sha != manifest.git_commit_sha:
        raise ValueError("Git source commit changed at capture execution boundary")
    expected_untracked = tuple(
        sorted(
            path.relative_to(paths.repo_root).as_posix()
            for path in (
                paths.frozen_dataset,
                paths.freeze_manifest,
                paths.capture_intent,
                paths.predictions,
            )
        )
    )
    if state.tracked_dirty or tuple(sorted(state.untracked_paths)) != expected_untracked:
        raise ValueError("unexpected worktree delta at capture execution boundary")


def _path_identity(path: Path) -> _FileIdentity:
    return _FileIdentity.from_stat(os.lstat(path))


def _same_filesystem_object(left: _FileIdentity, right: _FileIdentity) -> bool:
    return (left.device, left.inode, left.mode) == (right.device, right.inode, right.mode)


@contextmanager
def _bind_capture_output_directory(
    paths: V11ArtifactPaths,
) -> Iterator[_CaptureOutputDirectoryBinding]:
    parent = paths.predictions.parent
    _require_safe_output_path(paths.repo_root, paths.predictions)
    parent_identity = _path_identity(parent)
    if not stat.S_ISDIR(parent_identity.mode):
        raise ValueError("capture output parent is not a directory")

    descriptor: int | None = None
    if os.name == "posix":
        directory_flag = getattr(os, "O_DIRECTORY", 0)
        no_follow_flag = getattr(os, "O_NOFOLLOW", 0)
        if os.open not in os.supports_dir_fd or not directory_flag or not no_follow_flag:
            raise OSError("safe directory-relative capture publication is unavailable")
        descriptor = os.open(
            parent,
            os.O_RDONLY | directory_flag | no_follow_flag | getattr(os, "O_CLOEXEC", 0),
        )
        descriptor_identity = _FileIdentity.from_stat(os.fstat(descriptor))
        if not _same_filesystem_object(descriptor_identity, parent_identity):
            os.close(descriptor)
            raise ValueError("capture output parent changed while being bound")
    elif os.name != "nt":
        raise OSError("safe capture publication is unsupported on this platform")

    binding = _CaptureOutputDirectoryBinding(
        path=parent,
        identity=parent_identity,
        descriptor=descriptor,
    )
    try:
        yield binding
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _require_capture_output_directory_binding(
    paths: V11ArtifactPaths,
    binding: _CaptureOutputDirectoryBinding,
) -> None:
    _require_safe_output_path(paths.repo_root, paths.snapshot_manifest)
    current_identity = _path_identity(binding.path)
    if not _same_filesystem_object(current_identity, binding.identity):
        raise ValueError("prediction output parent identity changed")
    if binding.descriptor is not None:
        descriptor_identity = _FileIdentity.from_stat(os.fstat(binding.descriptor))
        if not _same_filesystem_object(descriptor_identity, binding.identity):
            raise ValueError("capture output directory descriptor identity changed")


def _bind_prediction_stream(
    paths: V11ArtifactPaths,
    handle: BinaryIO,
    expected_parent_identity: _FileIdentity,
) -> _PredictionStreamBinding:
    parent_identity = _path_identity(paths.predictions.parent)
    if not _same_filesystem_object(parent_identity, expected_parent_identity):
        raise ValueError("prediction output parent identity changed during exclusive claim")
    file_identity = _FileIdentity.from_stat(os.fstat(handle.fileno()))
    if not stat.S_ISREG(file_identity.mode):
        raise ValueError("prediction stream is not a regular file")
    binding = _PredictionStreamBinding(
        parent_identity=parent_identity,
        file_identity=file_identity,
    )
    _require_prediction_stream_binding(paths, handle, binding)
    return binding


def _require_prediction_stream_binding(
    paths: V11ArtifactPaths,
    handle: BinaryIO,
    binding: _PredictionStreamBinding,
) -> None:
    _require_safe_existing_file(paths.repo_root, paths.predictions)
    current_parent = _path_identity(paths.predictions.parent)
    if not _same_filesystem_object(current_parent, binding.parent_identity):
        raise ValueError("prediction output parent identity changed")
    descriptor_identity = _FileIdentity.from_stat(os.fstat(handle.fileno()))
    if not _same_filesystem_object(descriptor_identity, binding.file_identity):
        raise ValueError("prediction stream descriptor identity changed")
    path_identity = _path_identity(paths.predictions)
    if not _same_filesystem_object(path_identity, binding.file_identity):
        raise ValueError("prediction stream path identity changed")


def _validate_final_prediction_stream(
    paths: V11ArtifactPaths,
    handle: BinaryIO,
    binding: _PredictionStreamBinding,
    *,
    expected_payload: bytes,
    runtime_cases: tuple[V11RuntimeCase, ...],
    success_count: int,
    failure_count: int,
) -> str:
    _require_prediction_stream_binding(paths, handle, binding)
    handle.flush()
    handle.seek(0)
    durable_payload = handle.read()
    if durable_payload != expected_payload:
        raise ValueError("prediction stream content changed outside the claimed descriptor")

    records = _load_v1_1_prediction_records_bytes(durable_payload)
    if len(records) != 26:
        raise ValueError("final prediction stream must contain exactly 26 records")
    if [record.case_id for record in records] != [case.case_id for case in runtime_cases]:
        raise ValueError("final prediction stream differs from frozen case order")
    observed_successes = sum(record.status is V11PredictionStatus.SUCCESS for record in records)
    observed_failures = sum(record.status is V11PredictionStatus.ERROR for record in records)
    if (observed_successes, observed_failures) != (success_count, failure_count):
        raise ValueError("final prediction stream counts differ from capture counts")

    _require_prediction_stream_binding(paths, handle, binding)
    canonical = _snapshot_file(paths.repo_root, paths.predictions)
    if not _same_filesystem_object(canonical.identity, binding.file_identity):
        raise ValueError("prediction stream canonical path identity changed")
    if canonical.payload != durable_payload:
        raise ValueError("prediction stream canonical path content changed")
    return sha256_bytes(durable_payload)


def _publish_prediction_manifest(
    paths: V11ArtifactPaths,
    prediction_handle: BinaryIO,
    stream_binding: _PredictionStreamBinding,
    output_directory: _CaptureOutputDirectoryBinding,
    manifest: V11PredictionSnapshotManifest,
    *,
    expected_payload: bytes,
    runtime_cases: tuple[V11RuntimeCase, ...],
    success_count: int,
    failure_count: int,
) -> None:
    """Revalidate exact final prediction bytes and publish through the bound parent."""

    manifest_payload = canonical_json_bytes(manifest.model_dump(mode="json"))
    _require_capture_output_directory_binding(paths, output_directory)
    publication_checksum = _validate_final_prediction_stream(
        paths,
        prediction_handle,
        stream_binding,
        expected_payload=expected_payload,
        runtime_cases=runtime_cases,
        success_count=success_count,
        failure_count=failure_count,
    )
    if publication_checksum != manifest.predictions_sha256:
        raise ValueError("prediction stream checksum changed before manifest publication")

    descriptor = _open_bound_manifest_descriptor(paths, output_directory)
    created_identity = _FileIdentity.from_stat(os.fstat(descriptor))
    try:
        if not stat.S_ISREG(created_identity.mode):
            raise ValueError("prediction snapshot manifest is not a regular file")
        _require_capture_output_directory_binding(paths, output_directory)
        _require_prediction_stream_binding(paths, prediction_handle, stream_binding)
        path_identity = _path_identity(paths.snapshot_manifest)
        if not _same_filesystem_object(path_identity, created_identity):
            raise ValueError("prediction snapshot manifest path identity changed")
    except Exception:
        os.close(descriptor)
        raise

    with os.fdopen(descriptor, "wb") as handle:
        handle.write(manifest_payload)
        handle.flush()
        os.fsync(handle.fileno())

    persisted_checksum = _validate_final_prediction_stream(
        paths,
        prediction_handle,
        stream_binding,
        expected_payload=expected_payload,
        runtime_cases=runtime_cases,
        success_count=success_count,
        failure_count=failure_count,
    )
    if persisted_checksum != manifest.predictions_sha256:
        raise ValueError("prediction stream checksum changed during manifest publication")
    _require_capture_output_directory_binding(paths, output_directory)
    persisted_manifest = _snapshot_file(paths.repo_root, paths.snapshot_manifest)
    if not _same_filesystem_object(persisted_manifest.identity, created_identity):
        raise ValueError("prediction snapshot manifest path identity changed")
    if persisted_manifest.payload != manifest_payload:
        raise ValueError("prediction snapshot manifest content changed during publication")


def _open_bound_manifest_descriptor(
    paths: V11ArtifactPaths,
    output_directory: _CaptureOutputDirectoryBinding,
) -> int:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    if output_directory.descriptor is not None:
        return os.open(
            paths.snapshot_manifest.name,
            flags,
            0o600,
            dir_fd=output_directory.descriptor,
        )
    if os.name != "nt":
        raise OSError("safe directory-relative manifest publication is unavailable")
    return os.open(paths.snapshot_manifest, flags, 0o600)


def _capture_start_timestamp(value: datetime | None) -> datetime:
    if value is None:
        return _timestamp_value(None)
    timestamp = _timestamp_value(value)
    observed_now = datetime.now().astimezone().replace(microsecond=0)
    if timestamp > observed_now:
        raise ValueError("capture start timestamp must not be in the future")
    return timestamp


def _timestamp_value(value: datetime | None) -> datetime:
    timestamp = value or datetime.now().astimezone()
    _require_timezone_aware(timestamp, "capture timestamp")
    return timestamp.replace(microsecond=0)


def _require_timezone_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
