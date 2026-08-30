"""Label-isolated preflight contracts for the governed v1.1 prediction capture."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.decision_support.models import CaseIntakeInput
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


def project_runtime_case(case: V11FrozenEvaluationCase) -> V11RuntimeCase:
    """Copy only legitimate production input fields out of one frozen labeled row."""

    return V11RuntimeCase(
        case_id=case.case_id,
        case_input=CaseIntakeInput(
            source_text=case.raw_user_input,
            source_ref=case.source_ref,
        ),
    )


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
