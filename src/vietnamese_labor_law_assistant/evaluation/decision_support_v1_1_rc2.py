"""Write-once RC2 registration and label-isolated production capture contracts."""

from __future__ import annotations

import asyncio
import os
import subprocess
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

import vietnamese_labor_law_assistant.decision_support.intake as intake_module
from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.decision_support.intake import (
    CASE_INTAKE_SYSTEM_PROMPT,
    CaseIntakeError,
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
    RepositoryState,
    V11ArtifactPaths,
    atomic_temporary_path,
    canonical_json_bytes,
    inspect_repository_state,
    sha256_bytes,
    sha256_file,
    write_exclusive,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_capture import (
    V11CaseIntakePredictionRecord,
    V11PredictionFailureReason,
    V11PredictionSnapshotManifest,
    V11PredictionStatus,
    V11RuntimeCase,
    project_runtime_case,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_freeze import (
    V11FrozenDatasetManifest,
    load_v1_1_frozen_dataset_bytes,
)

RC2_REMEDIATION_COMMIT_SHA = "6b846de192aff26ae8ac1f84e12365868f9c3971"
RC2_MODEL = "mistral-small-2603"
RC2_BASE_URL = "https://api.mistral.ai/v1"
RC2_INTER_CASE_PACING_SECONDS = 1.0
RC2_FROZEN_DATASET_SHA256 = "5f726893300176d1c3b4e915253682b70ef343376903e3e7e243d838e245c29e"
RC2_THRESHOLD_SHA256 = "373aa3d4512e6d5cb75e7bcba3dbcc6ef2541ced8603b67b18e6bcd80b31ad5c"
RC2_HUMAN_REVIEW_SHA256 = "bae5fe6826c0d92ec4f85f433e7fdd640bc182bcaefaaf93ee3d4d0b1a2068d6"
RC2_PROMPT_SHA256 = "64e75d2491f1832bd1aabbb92fea58b786965912d7f1fb588bd946327edae935"
RC2_REGISTRATION_V1_SHA256 = "7561fad80e75d0cea84f144471596cb7ae31cd70b6786ac4e410fe814e3e30ac"
RC1_CAPTURE_INTENT_SHA256 = "37ac396778226f84efdb655003e2cd738def7650c0904f65c142fd28cfe4e0f9"
RC1_PREDICTIONS_SHA256 = "d59815facf4c3360dba5c8471f446de3262ddeca42f6e25adad3268a60a44d9a"
RC1_SNAPSHOT_MANIFEST_SHA256 = "4ea2d90d03eff5db5b4d972d487508b07b88ef1274050641973089ba11a86415"

_EXTRACTOR_RELATIVE_PATH = "src/vietnamese_labor_law_assistant/decision_support/intake.py"
_CANONICAL_MODEL_RELATIVE_PATH = "src/vietnamese_labor_law_assistant/decision_support/models.py"
_TRANSPORT_SCHEMA_IDENTITY = (
    "vietnamese_labor_law_assistant.decision_support.intake._ProviderCaseIntakeResult"
)
_CANONICAL_SCHEMA_IDENTITY = (
    "vietnamese_labor_law_assistant.decision_support.models.CaseIntakeResult"
)


class _CaseIntakeExtractor(Protocol):
    async def extract(self, case_input: CaseIntakeInput) -> CaseIntakeResult: ...


@dataclass(frozen=True)
class RC2ArtifactPaths:
    """Canonical governed inputs and distinct RC2 output paths."""

    repo_root: Path
    governed: V11ArtifactPaths
    output_directory: Path
    registration_revision_1: Path
    registration_revision_2: Path
    capture_manifest: Path
    capture_started: Path
    capture_journal: Path
    capture_completed: Path
    predictions: Path
    prediction_metadata: Path
    metrics: Path
    failed_samples: Path
    release_report: Path
    evaluation_started: Path
    evaluation_completed: Path
    release_terminal: Path
    capture_adapter: Path
    capture_runner: Path
    journal_finalizer: Path
    offline_evaluator: Path
    extractor_implementation: Path

    @classmethod
    def from_root(cls, repo_root: Path) -> RC2ArtifactPaths:
        root = repo_root.resolve()
        output = root / "evaluation/results/decision_support/v1_1/rc2"
        return cls(
            repo_root=root,
            governed=V11ArtifactPaths.from_root(root),
            output_directory=output,
            registration_revision_1=output / "rc2_capture_manifest.json",
            registration_revision_2=output / "rc2_registration_v2.json",
            capture_manifest=output / "rc2_capture_manifest.json",
            capture_started=output / "rc2_capture_started.json",
            capture_journal=output / "rc2_capture_journal.jsonl",
            capture_completed=output / "rc2_capture_completed.json",
            predictions=output / "rc2_production_predictions.jsonl",
            prediction_metadata=output / "rc2_prediction_metadata.json",
            metrics=output / "rc2_metrics.json",
            failed_samples=output / "rc2_failed_samples.jsonl",
            release_report=output / "rc2_release_evaluation.md",
            evaluation_started=output / "rc2_evaluation_started.json",
            evaluation_completed=output / "rc2_evaluation_completed.json",
            release_terminal=output / "rc2_release_terminal.json",
            capture_adapter=root / "scripts/capture_decision_support_v1_1_rc2.py",
            capture_runner=(
                root / "src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1_rc2.py"
            ),
            journal_finalizer=(
                root / "src/vietnamese_labor_law_assistant/evaluation/"
                "decision_support_v1_1_rc2_capture.py"
            ),
            offline_evaluator=(
                root / "src/vietnamese_labor_law_assistant/evaluation/"
                "decision_support_v1_1_rc2_release.py"
            ),
            extractor_implementation=(
                root / "src/vietnamese_labor_law_assistant/decision_support/intake.py"
            ),
        )


class RC2GenerationConfig(BaseModel):
    """Exact non-secret production generation configuration registered for RC2."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["openai"] = "openai"
    model: Literal["mistral-small-2603"] = "mistral-small-2603"
    base_url: Literal["https://api.mistral.ai/v1"] = "https://api.mistral.ai/v1"
    model_alias_used: Literal[False] = False
    temperature: Literal[0] = 0
    timeout_seconds: float = 60.0
    sdk_max_retries: Literal[2] = 2
    structured_max_retries: Literal[2] = 2
    concurrency: Literal[1] = 1
    inter_case_pacing_seconds: float = 1.0

    @model_validator(mode="after")
    def validate_numeric_identity(self) -> RC2GenerationConfig:
        if self.timeout_seconds != 60.0:
            raise ValueError("RC2 timeout must remain exactly 60 seconds")
        if self.inter_case_pacing_seconds != RC2_INTER_CASE_PACING_SECONDS:
            raise ValueError("RC2 inter-case pacing must remain exactly 1 second")
        return self

    @classmethod
    def from_settings(cls, settings: Settings) -> RC2GenerationConfig:
        if settings.llm_provider != "openai":
            raise ValueError("RC2 requires the OpenAI-compatible provider path")
        if settings.llm_model != RC2_MODEL:
            raise ValueError("configured model differs from the exact RC2 model")
        if settings.openai_base_url != RC2_BASE_URL:
            raise ValueError("configured base URL differs from the exact RC2 base URL")
        if settings.llm_timeout_seconds != 60:
            raise ValueError("configured timeout differs from the registered RC2 timeout")
        if settings.llm_max_retries != 2:
            raise ValueError("configured SDK retries differ from the registered RC2 policy")
        if settings.agent_structured_output_max_retries != 2:
            raise ValueError("configured structured retries differ from the RC2 policy")
        if (
            settings.openai_api_key is None
            or not settings.openai_api_key.get_secret_value().strip()
        ):
            raise ValueError("production LLM provider is not configured")
        return cls()


class RC2RegisteredPaths(BaseModel):
    """Repository-relative, non-secret locations bound before capture."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    capture_manifest: str
    future_predictions: str
    future_prediction_metadata: str
    future_metrics: str
    future_failed_samples: str
    future_release_report: str

    @classmethod
    def from_artifact_paths(cls, paths: RC2ArtifactPaths) -> RC2RegisteredPaths:
        def relative(path: Path) -> str:
            return path.relative_to(paths.repo_root).as_posix()

        return cls(
            capture_manifest=relative(paths.capture_manifest),
            future_predictions=relative(paths.predictions),
            future_prediction_metadata=relative(paths.prediction_metadata),
            future_metrics=relative(paths.metrics),
            future_failed_samples=relative(paths.failed_samples),
            future_release_report=relative(paths.release_report),
        )


class RC2RegisteredPathsV2(BaseModel):
    """Every immutable lifecycle and final-output path registered for revision 2."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    registration_revision_1: str
    registration_revision_2: str
    capture_started: str
    capture_journal: str
    capture_completed: str
    predictions: str
    prediction_metadata: str
    metrics: str
    failed_samples: str
    release_report: str
    evaluation_started: str
    evaluation_completed: str
    release_terminal: str

    @classmethod
    def from_artifact_paths(cls, paths: RC2ArtifactPaths) -> RC2RegisteredPathsV2:
        def relative(path: Path) -> str:
            return path.relative_to(paths.repo_root).as_posix()

        return cls(
            registration_revision_1=relative(paths.registration_revision_1),
            registration_revision_2=relative(paths.registration_revision_2),
            capture_started=relative(paths.capture_started),
            capture_journal=relative(paths.capture_journal),
            capture_completed=relative(paths.capture_completed),
            predictions=relative(paths.predictions),
            prediction_metadata=relative(paths.prediction_metadata),
            metrics=relative(paths.metrics),
            failed_samples=relative(paths.failed_samples),
            release_report=relative(paths.release_report),
            evaluation_started=relative(paths.evaluation_started),
            evaluation_completed=relative(paths.evaluation_completed),
            release_terminal=relative(paths.release_terminal),
        )


class RC2SupersededRegistration(BaseModel):
    """Immutable description of why revision 1 cannot operate the first RC2 capture."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    release_candidate: Literal["v1_1_rc2"] = "v1_1_rc2"
    registration_revision: Literal[1] = 1
    registration_path: str
    registration_sha256: Literal["7561fad80e75d0cea84f144471596cb7ae31cd70b6786ac4e410fe814e3e30ac"]
    state: Literal["SUPERSEDED_BEFORE_CAPTURE"] = "SUPERSEDED_BEFORE_CAPTURE"
    reason: Literal["INCOMPLETE_CLOSEOUT_CAPABILITY"] = "INCOMPLETE_CLOSEOUT_CAPABILITY"
    frozen_provider_calls: Literal[0] = 0


class RC2CodeIdentities(BaseModel):
    """Committed code, prompt, and schema checksums required for capture and evaluation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    registration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    capture_runner_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    journal_finalizer_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    offline_evaluator_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    metrics_producer_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    report_producer_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    extractor_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_schema_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    transport_schema_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RC2RegistrationV2(BaseModel):
    """Second immutable pre-capture registration for the same unconsumed RC2."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["v1_1_rc2_registration_v2"] = "v1_1_rc2_registration_v2"
    release_candidate: Literal["v1_1_rc2"] = "v1_1_rc2"
    registration_revision: Literal[2] = 2
    status: Literal["PREPARED_NOT_CAPTURED"] = "PREPARED_NOT_CAPTURED"
    supersedes: RC2SupersededRegistration
    parent: Literal["v1_1_rc1"] = "v1_1_rc1"
    parent_result: Literal["FAILED_PROVIDER_CAPTURE"] = "FAILED_PROVIDER_CAPTURE"
    parent_immutable: Literal[True] = True
    parent_successful_predictions: Literal[0] = 0
    parent_artifact_sha256: dict[str, str]
    frozen_dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_count: Literal[26] = 26
    human_review_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    human_review_pass_count: Literal[26] = 26
    human_review_unresolved_count: Literal[0] = 0
    threshold_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    threshold_decision: Literal["APPROVE_UNCHANGED"] = "APPROVE_UNCHANGED"
    implementation_commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    registered_untracked_paths: tuple[str, ...] = ()
    code_identities: RC2CodeIdentities
    generation_config: RC2GenerationConfig
    paths: RC2RegisteredPathsV2
    label_isolation: Literal[True] = True
    expected_labels_visible_during_capture: Literal[False] = False
    frozen_provider_calls: Literal[0] = 0
    rc2_capture_started: Literal[False] = False
    capture_started_at: Literal[None] = None
    prediction_checksum: Literal[None] = None
    expected_labels_unchanged: Literal[True] = True
    legal_semantics_changed: Literal[False] = False
    case_intake_semantics_changed: Literal[False] = False
    source_span_validation_weakened: Literal[False] = False
    week5_functionality_added: Literal[False] = False


class RC2RegistrationPlan(BaseModel):
    """Validated revision 2 plus only the label-free cases allowed into capture."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    registration: RC2RegistrationV2
    runtime_cases: tuple[V11RuntimeCase, ...]


class RC2CaptureManifest(BaseModel):
    """Immutable pre-capture registration for the distinct v1.1 RC2 attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["v1_1_rc2_capture_manifest_v1"] = "v1_1_rc2_capture_manifest_v1"
    release_candidate: Literal["v1_1_rc2"]
    parent: Literal["v1_1_rc1"]
    parent_result: Literal["FAILED_PROVIDER_CAPTURE"]
    frozen_dataset_path: str
    frozen_dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_count: Literal[26]
    human_review_path: str
    human_review_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    human_review_pass_count: Literal[26]
    human_review_unresolved_count: Literal[0]
    threshold_path: str
    threshold_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    threshold_approval_valid: Literal[True]
    dataset_bytes_unchanged: Literal[True]
    expected_labels_unchanged: Literal[True]
    thresholds_unchanged: Literal[True]
    remediation_commit_sha: Literal["6b846de192aff26ae8ac1f84e12365868f9c3971"]
    current_git_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    worktree_clean: bool
    tracked_worktree_dirty: bool
    untracked_worktree_paths: tuple[str, ...]
    capture_runner_code_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    capture_adapter_code_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    extractor_implementation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    transport_schema_identity: Literal[
        "vietnamese_labor_law_assistant.decision_support.intake._ProviderCaseIntakeResult"
    ]
    transport_schema_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_schema_identity: Literal[
        "vietnamese_labor_law_assistant.decision_support.models.CaseIntakeResult"
    ]
    canonical_schema_version: Literal["CHECKSUM_BOUND_UNVERSIONED"]
    canonical_schema_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    generation_config: RC2GenerationConfig
    paths: RC2RegisteredPaths
    label_isolation: Literal[True]
    expected_labels_visible_to_extractor: Literal[False]
    thresholds_visible_to_extractor: Literal[False]
    reviewer_data_visible_to_extractor: Literal[False]
    production_extractor_implementation_changed: Literal[True]
    legal_semantics_changed: Literal[False]
    canonical_case_intake_result_changed: Literal[False]
    source_span_invariant_changed: Literal[False]
    prompt_semantic_policy_changed: Literal[False]
    metric_based_prompt_tuning_performed: Literal[False]
    successful_rc1_predictions_existed: Literal[False]
    capture_started_at: Literal[None] = None
    capture_completed_at: Literal[None] = None
    prediction_checksum: Literal[None] = None
    status: Literal["PREPARED_NOT_CAPTURED"]


class RC2CapturePlan(BaseModel):
    """Validated registration plus the only label-free rows available to live capture."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest: RC2CaptureManifest
    runtime_cases: tuple[V11RuntimeCase, ...]


class RC2PredictionMetadata(BaseModel):
    """Final non-secret identity written once after all captured rows are durable."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["v1_1_rc2_prediction_metadata_v1"] = "v1_1_rc2_prediction_metadata_v1"
    release_candidate: Literal["v1_1_rc2"] = "v1_1_rc2"
    status: Literal["COMPLETE", "FAILED"]
    started_at: datetime
    completed_at: datetime
    predictions_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    total_count: Literal[26] = 26
    success_count: int = Field(ge=0, le=26)
    failure_count: int = Field(ge=0, le=26)
    capture_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_capture_outcome(self) -> RC2PredictionMetadata:
        if self.success_count + self.failure_count != self.total_count:
            raise ValueError("prediction counts must total 26")
        if self.status == "COMPLETE" and (self.success_count != 26 or self.failure_count != 0):
            raise ValueError("COMPLETE requires 26 successful prediction records")
        if self.status == "FAILED" and self.failure_count == 0:
            raise ValueError("FAILED requires at least one failed prediction record")
        if self.started_at.tzinfo is None or self.started_at.utcoffset() is None:
            raise ValueError("capture start timestamp must be timezone-aware")
        if self.completed_at.tzinfo is None or self.completed_at.utcoffset() is None:
            raise ValueError("capture completion timestamp must be timezone-aware")
        if self.completed_at < self.started_at:
            raise ValueError("capture completion timestamp must not precede start")
        return self


def require_rc2_future_outputs_absent(paths: RC2ArtifactPaths) -> None:
    """Fail before provider use if any final RC2 output path is already claimed."""

    for path in (
        paths.predictions,
        paths.prediction_metadata,
        paths.metrics,
        paths.failed_samples,
        paths.release_report,
    ):
        if os.path.lexists(path):
            raise FileExistsError(f"RC2 artifact already exists: {path}")


def write_rc2_manifest(paths: RC2ArtifactPaths, manifest: RC2CaptureManifest) -> None:
    """Exclusively materialize the pre-capture manifest and no future output."""

    require_rc2_future_outputs_absent(paths)
    if os.path.lexists(paths.capture_manifest):
        raise FileExistsError(f"RC2 artifact already exists: {paths.capture_manifest}")
    payload = canonical_json_bytes(manifest.model_dump(mode="json"))
    try:
        write_exclusive(paths.capture_manifest, payload)
    except FileExistsError as exc:
        raise FileExistsError(f"RC2 artifact already exists: {paths.capture_manifest}") from exc


def write_rc2_registration_v2(
    paths: RC2ArtifactPaths,
    registration: RC2RegistrationV2,
) -> None:
    """Create the revision-2 registration once without touching revision-1 bytes."""

    if not paths.registration_revision_1.is_file():
        raise FileNotFoundError("RC2 registration revision 1 is missing")
    if sha256_file(paths.registration_revision_1) != RC2_REGISTRATION_V1_SHA256:
        raise ValueError("RC2 registration revision 1 checksum changed")
    if os.path.lexists(paths.registration_revision_2):
        raise FileExistsError("RC2 registration revision 2 already exists")
    try:
        write_exclusive(
            paths.registration_revision_2,
            canonical_json_bytes(registration.model_dump(mode="json")),
        )
    except FileExistsError as exc:
        raise FileExistsError("RC2 registration revision 2 already exists") from exc


def prepare_rc2_registration_v2(
    repo_root: Path,
    *,
    implementation_commit_sha: str,
) -> RC2RegistrationPlan:
    """Build revision 2 offline from the committed implementation and governed bytes."""

    paths = RC2ArtifactPaths.from_root(repo_root)
    _require_canonical_paths(paths)
    if os.path.lexists(paths.registration_revision_2):
        raise FileExistsError("RC2 registration revision 2 already exists")
    atomic_temporary_path(paths.registration_revision_2).unlink(missing_ok=True)
    _require_new_revision_2_namespace(paths)
    runtime_cases = require_rc2_governance_identity(paths)
    state = inspect_repository_state(paths.repo_root)
    if state.commit_sha != implementation_commit_sha:
        raise ValueError("implementation commit differs from current HEAD")
    if state.tracked_dirty:
        raise ValueError("tracked worktree must be clean before registration revision 2")
    code_identities = _current_rc2_code_identities(paths)
    registration = RC2RegistrationV2(
        supersedes=RC2SupersededRegistration(
            registration_path=paths.registration_revision_1.relative_to(paths.repo_root).as_posix(),
            registration_sha256=RC2_REGISTRATION_V1_SHA256,
        ),
        parent_artifact_sha256={
            "capture_intent": RC1_CAPTURE_INTENT_SHA256,
            "predictions": RC1_PREDICTIONS_SHA256,
            "snapshot_manifest": RC1_SNAPSHOT_MANIFEST_SHA256,
        },
        frozen_dataset_sha256=RC2_FROZEN_DATASET_SHA256,
        human_review_sha256=RC2_HUMAN_REVIEW_SHA256,
        threshold_sha256=RC2_THRESHOLD_SHA256,
        implementation_commit_sha=implementation_commit_sha,
        registered_untracked_paths=state.untracked_paths,
        code_identities=code_identities,
        generation_config=RC2GenerationConfig(),
        paths=RC2RegisteredPathsV2.from_artifact_paths(paths),
    )
    return RC2RegistrationPlan(registration=registration, runtime_cases=runtime_cases)


def load_rc2_registration_v2(
    paths: RC2ArtifactPaths,
    settings: Settings,
) -> RC2RegistrationPlan:
    """Revalidate every revision-2 identity before capture initialization or resume."""

    plan = load_rc2_registration_v2_offline(paths)
    if RC2GenerationConfig.from_settings(settings) != plan.registration.generation_config:
        raise ValueError("configured generation identity differs from registration revision 2")
    return plan


def load_rc2_registration_v2_offline(
    paths: RC2ArtifactPaths,
) -> RC2RegistrationPlan:
    """Revalidate revision 2 without reading credentials or creating provider clients."""

    _require_canonical_paths(paths)
    if not paths.registration_revision_2.is_file():
        raise FileNotFoundError("RC2 registration revision 2 is missing")
    atomic_temporary_path(paths.registration_revision_2).unlink(missing_ok=True)
    payload = paths.registration_revision_2.read_bytes()
    registration = RC2RegistrationV2.model_validate_json(payload)
    if payload != canonical_json_bytes(registration.model_dump(mode="json")):
        raise ValueError("RC2 registration revision 2 bytes are not canonical")
    if registration.paths != RC2RegisteredPathsV2.from_artifact_paths(paths):
        raise ValueError("RC2 registration revision 2 paths changed")
    runtime_cases = require_rc2_governance_identity(paths)
    if _current_rc2_code_identities(paths) != registration.code_identities:
        raise ValueError("RC2 committed code identity changed after registration revision 2")
    state = inspect_repository_state(paths.repo_root)
    require_registered_git_identity(
        paths.repo_root,
        registered_sha=registration.implementation_commit_sha,
        current_sha=state.commit_sha,
        capture_manifest=paths.registration_revision_2,
    )
    _require_revision_2_worktree_identity(paths, registration, state)
    return RC2RegistrationPlan(registration=registration, runtime_cases=runtime_cases)


def require_rc2_governance_identity(
    paths: RC2ArtifactPaths,
) -> tuple[V11RuntimeCase, ...]:
    """Verify all frozen/governance/RC1/revision-1 bytes without provider use."""

    governed = paths.governed
    required = (
        governed.frozen_dataset,
        governed.freeze_manifest,
        governed.review_packet,
        governed.threshold_spec,
        governed.threshold_approval,
        governed.capture_intent,
        governed.predictions,
        governed.snapshot_manifest,
        paths.registration_revision_1,
    )
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(f"required immutable RC2 input is missing: {path}")
    checks = (
        (governed.frozen_dataset, RC2_FROZEN_DATASET_SHA256, "frozen dataset"),
        (governed.review_packet, RC2_HUMAN_REVIEW_SHA256, "human review"),
        (governed.threshold_spec, RC2_THRESHOLD_SHA256, "threshold specification"),
        (governed.capture_intent, RC1_CAPTURE_INTENT_SHA256, "RC1 capture intent"),
        (governed.predictions, RC1_PREDICTIONS_SHA256, "RC1 predictions"),
        (
            governed.snapshot_manifest,
            RC1_SNAPSHOT_MANIFEST_SHA256,
            "RC1 snapshot manifest",
        ),
        (
            paths.registration_revision_1,
            RC2_REGISTRATION_V1_SHA256,
            "RC2 registration revision 1",
        ),
    )
    for path, expected, name in checks:
        if sha256_file(path) != expected:
            raise ValueError(f"{name} checksum changed")
    freeze_payload = governed.freeze_manifest.read_bytes()
    freeze_manifest = V11FrozenDatasetManifest.model_validate_json(freeze_payload)
    if freeze_payload != canonical_json_bytes(freeze_manifest.model_dump(mode="json")):
        raise ValueError("frozen dataset manifest bytes are not canonical")
    if (
        freeze_manifest.frozen_dataset_sha256 != RC2_FROZEN_DATASET_SHA256
        or freeze_manifest.review_packet_sha256 != RC2_HUMAN_REVIEW_SHA256
        or freeze_manifest.threshold_spec_sha256 != RC2_THRESHOLD_SHA256
        or freeze_manifest.threshold_approval_sha256 != sha256_file(governed.threshold_approval)
        or freeze_manifest.case_count != 26
        or freeze_manifest.review_status != "PASS"
        or freeze_manifest.threshold_approval_decision != "APPROVE_UNCHANGED"
    ):
        raise ValueError("frozen governance manifest identity changed")
    revision_1_payload = paths.registration_revision_1.read_bytes()
    revision_1 = RC2CaptureManifest.model_validate_json(revision_1_payload)
    if revision_1_payload != canonical_json_bytes(revision_1.model_dump(mode="json")):
        raise ValueError("RC2 registration revision 1 bytes are not canonical")
    if (
        revision_1.status != "PREPARED_NOT_CAPTURED"
        or revision_1.capture_started_at is not None
        or revision_1.capture_completed_at is not None
        or revision_1.prediction_checksum is not None
    ):
        raise ValueError("RC2 registration revision 1 was consumed or changed")
    rc1_payload = governed.snapshot_manifest.read_bytes()
    rc1 = V11PredictionSnapshotManifest.model_validate_json(rc1_payload)
    if rc1_payload != canonical_json_bytes(rc1.model_dump(mode="json")):
        raise ValueError("RC1 snapshot manifest bytes are not canonical")
    if rc1.status != "FAILED" or rc1.success_count != 0 or rc1.failure_count != 26:
        raise ValueError("RC1 parent result differs from FAILED_PROVIDER_CAPTURE")
    frozen_cases = load_v1_1_frozen_dataset_bytes(governed.frozen_dataset.read_bytes())
    if len(frozen_cases) != 26 or any(
        not case.human_validated or case.review_status != "PASS" for case in frozen_cases
    ):
        raise ValueError("frozen dataset is not 26/26 human-reviewed PASS")
    return tuple(project_runtime_case(case) for case in frozen_cases)


def _current_rc2_code_identities(paths: RC2ArtifactPaths) -> RC2CodeIdentities:
    required = (
        paths.capture_runner,
        paths.capture_adapter,
        paths.journal_finalizer,
        paths.offline_evaluator,
        paths.extractor_implementation,
    )
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(f"required RC2 implementation file is missing: {path}")
    transport_model = getattr(intake_module, "_ProviderCaseIntakeResult", None)
    if not isinstance(transport_model, type) or not issubclass(transport_model, BaseModel):
        raise ValueError("internal provider transport schema is unavailable")
    transport_type = cast(type[BaseModel], transport_model)
    offline_checksum = sha256_file(paths.offline_evaluator)
    return RC2CodeIdentities(
        registration_sha256=sha256_file(paths.capture_runner),
        capture_runner_sha256=sha256_file(paths.capture_adapter),
        journal_finalizer_sha256=sha256_file(paths.journal_finalizer),
        offline_evaluator_sha256=offline_checksum,
        metrics_producer_sha256=offline_checksum,
        report_producer_sha256=offline_checksum,
        extractor_sha256=sha256_file(paths.extractor_implementation),
        prompt_sha256=sha256_bytes(CASE_INTAKE_SYSTEM_PROMPT.encode("utf-8")),
        canonical_schema_sha256=sha256_bytes(
            canonical_json_bytes(CaseIntakeResult.model_json_schema())
        ),
        transport_schema_sha256=sha256_bytes(
            canonical_json_bytes(transport_type.model_json_schema())
        ),
    )


def _require_new_revision_2_namespace(paths: RC2ArtifactPaths) -> None:
    outputs = (
        paths.capture_started,
        paths.capture_journal,
        paths.capture_completed,
        paths.predictions,
        paths.prediction_metadata,
        paths.metrics,
        paths.failed_samples,
        paths.release_report,
        paths.evaluation_started,
        paths.evaluation_completed,
        paths.release_terminal,
    )
    if any(os.path.lexists(path) for path in outputs):
        raise FileExistsError("RC2 revision-2 lifecycle namespace is already claimed")


def _require_revision_2_worktree_identity(
    paths: RC2ArtifactPaths,
    registration: RC2RegistrationV2,
    state: RepositoryState,
) -> None:
    if state.tracked_dirty:
        raise ValueError("tracked worktree changed after registration revision 2")
    lifecycle_paths = (
        paths.capture_started,
        paths.capture_journal,
        paths.capture_completed,
        paths.predictions,
        paths.prediction_metadata,
        paths.metrics,
        paths.failed_samples,
        paths.release_report,
        paths.evaluation_started,
        paths.evaluation_completed,
        paths.release_terminal,
    )
    permitted = set(registration.registered_untracked_paths)
    permitted.update(
        path.relative_to(paths.repo_root).as_posix()
        for path in lifecycle_paths
        if os.path.lexists(path)
    )
    temporary_paths = tuple(
        atomic_temporary_path(path) for path in (paths.registration_revision_2, *lifecycle_paths)
    )
    journal_probe = paths.capture_journal.with_name(
        f".{paths.capture_journal.name}.availability-probe"
    )
    permitted.update(
        path.relative_to(paths.repo_root).as_posix()
        for path in (*temporary_paths, journal_probe)
        if os.path.lexists(path)
    )
    if set(state.untracked_paths) != permitted:
        raise ValueError("worktree identity differs from registration revision 2")


def require_label_isolated_runtime_cases(runtime_cases: Sequence[object]) -> None:
    """Accept only the exact bookkeeping-plus-production-input runtime boundary."""

    if any(type(runtime_case) is not V11RuntimeCase for runtime_case in runtime_cases):
        raise TypeError("RC2 capture accepts only exact V11RuntimeCase objects")


async def execute_rc2_runtime_cases(
    runtime_cases: Sequence[V11RuntimeCase],
    extractor: _CaseIntakeExtractor,
    *,
    pacing_seconds: float = RC2_INTER_CASE_PACING_SECONDS,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> tuple[V11CaseIntakePredictionRecord, ...]:
    """Run label-free cases sequentially with fixed inter-case pacing."""

    require_label_isolated_runtime_cases(runtime_cases)
    records: list[V11CaseIntakePredictionRecord] = []
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
        except CaseIntakeError as exc:
            try:
                reason = V11PredictionFailureReason(exc.reason)
            except ValueError:
                reason = V11PredictionFailureReason.UNEXPECTED_ERROR
            record = V11CaseIntakePredictionRecord(
                sequence=sequence,
                case_id=runtime_case.case_id,
                status=V11PredictionStatus.ERROR,
                failure_reason=reason,
            )
        except Exception:
            record = V11CaseIntakePredictionRecord(
                sequence=sequence,
                case_id=runtime_case.case_id,
                status=V11PredictionStatus.ERROR,
                failure_reason=V11PredictionFailureReason.UNEXPECTED_ERROR,
            )
        records.append(record)
        if sequence < len(runtime_cases):
            await sleep(pacing_seconds)
    return tuple(records)


def prepare_rc2_capture(
    paths: RC2ArtifactPaths,
    settings: Settings,
    *,
    project_author_name: str,
) -> RC2CapturePlan:
    """Validate immutable governance and construct one unpersisted RC2 registration."""

    _require_canonical_paths(paths)
    if os.path.lexists(paths.capture_manifest):
        raise FileExistsError(f"RC2 artifact already exists: {paths.capture_manifest}")
    require_rc2_future_outputs_absent(paths)
    return _build_rc2_capture_plan(paths, settings, project_author_name=project_author_name)


def load_rc2_capture_plan(
    paths: RC2ArtifactPaths,
    settings: Settings,
    *,
    project_author_name: str,
) -> RC2CapturePlan:
    """Reload and revalidate the exact write-once registration before live use."""

    _require_canonical_paths(paths)
    if not paths.capture_manifest.is_file():
        raise FileNotFoundError("RC2 capture manifest is not registered")
    payload = paths.capture_manifest.read_bytes()
    manifest = RC2CaptureManifest.model_validate_json(payload)
    if payload != canonical_json_bytes(manifest.model_dump(mode="json")):
        raise ValueError("RC2 capture manifest bytes are not canonical")
    repository_state = inspect_repository_state(paths.repo_root)
    require_registered_git_identity(
        paths.repo_root,
        registered_sha=manifest.current_git_sha,
        current_sha=repository_state.commit_sha,
        capture_manifest=paths.capture_manifest,
    )
    require_registered_worktree_identity(repository_state, manifest)
    plan = _build_rc2_capture_plan(
        paths,
        settings,
        project_author_name=project_author_name,
        registered_git_sha=manifest.current_git_sha,
    )
    if plan.manifest != manifest:
        raise ValueError("RC2 registration identity changed after preparation")
    require_rc2_future_outputs_absent(paths)
    return plan


async def capture_rc2_predictions(
    paths: RC2ArtifactPaths,
    settings: Settings,
    *,
    project_author_name: str,
) -> RC2PredictionMetadata:
    """Reject the incomplete revision-1 operational path before any provider use."""

    del paths, settings, project_author_name
    raise RuntimeError(
        "RC2 registration revision 1 is superseded; use the revision-2 crash-safe runner"
    )


def _build_rc2_capture_plan(
    paths: RC2ArtifactPaths,
    settings: Settings,
    *,
    project_author_name: str,
    registered_git_sha: str | None = None,
) -> RC2CapturePlan:
    generation_config = RC2GenerationConfig.from_settings(settings)
    governed = paths.governed
    required_paths = (
        governed.corrected_candidate,
        governed.review_packet,
        governed.threshold_spec,
        governed.threshold_approval,
        governed.frozen_dataset,
        governed.freeze_manifest,
        governed.snapshot_manifest,
        paths.capture_runner,
        paths.capture_adapter,
        paths.extractor_implementation,
    )
    for required_path in required_paths:
        if not required_path.is_file():
            raise FileNotFoundError(f"required RC2 registration input is missing: {required_path}")

    frozen_payload = governed.frozen_dataset.read_bytes()
    review_payload = governed.review_packet.read_bytes()
    threshold_payload = governed.threshold_spec.read_bytes()
    if sha256_bytes(frozen_payload) != RC2_FROZEN_DATASET_SHA256:
        raise ValueError("frozen dataset checksum changed")
    if sha256_bytes(review_payload) != RC2_HUMAN_REVIEW_SHA256:
        raise ValueError("human-review checksum changed")
    if sha256_bytes(threshold_payload) != RC2_THRESHOLD_SHA256:
        raise ValueError("threshold checksum changed")

    freeze_manifest = V11FrozenDatasetManifest.model_validate_json(
        governed.freeze_manifest.read_bytes()
    )
    if (
        freeze_manifest.frozen_dataset_sha256 != RC2_FROZEN_DATASET_SHA256
        or freeze_manifest.review_packet_sha256 != RC2_HUMAN_REVIEW_SHA256
        or freeze_manifest.threshold_spec_sha256 != RC2_THRESHOLD_SHA256
        or freeze_manifest.case_count != 26
        or freeze_manifest.review_status != "PASS"
        or freeze_manifest.threshold_approval_decision != "APPROVE_UNCHANGED"
    ):
        raise ValueError("frozen governance manifest identity changed")

    rc1_predictions = V11PredictionSnapshotManifest.model_validate_json(
        governed.snapshot_manifest.read_bytes()
    )
    if (
        rc1_predictions.status != "FAILED"
        or rc1_predictions.success_count != 0
        or rc1_predictions.failure_count != 26
    ):
        raise ValueError("RC1 parent is not the preserved failed provider capture")

    candidate_payload = governed.corrected_candidate.read_bytes()
    candidate_cases = load_v1_1_candidate_bytes(candidate_payload)
    quality = candidate_quality_report(candidate_cases)
    if (
        len(candidate_cases) != 26
        or quality.schema_validation != "PASS"
        or quality.prediction_label_leakage_case_ids
        or quality.prediction_label_leakage_assessment != "CHECKED_NO_PREDICTION_ARTIFACT_INPUT"
    ):
        raise ValueError("corrected candidate failed canonical validation")

    review = validate_v1_1_review_packet_bytes(
        candidate_cases,
        review_payload,
        project_author_name=project_author_name,
    )
    unresolved = review.pending_count + review.needs_revision_count + review.rejected_count
    if (
        review.status != "PASS"
        or not review.policy_satisfied
        or review.total_rows != 26
        or review.pass_count != 26
        or unresolved != 0
        or review.errors
    ):
        raise ValueError("human review is no longer 26/26 PASS with zero unresolved rows")

    threshold_spec = V11ThresholdSpec.model_validate_json(threshold_payload)
    inherited_path = paths.repo_root / Path(threshold_spec.week3_threshold_source)
    approval_payload = governed.threshold_approval.read_bytes()
    approval = validate_v1_1_threshold_approval_bytes(
        threshold_payload,
        approval_payload,
        inherited_threshold_source_bytes=inherited_path.read_bytes(),
        project_author_name=project_author_name,
        threshold_spec_identity=governed.threshold_spec.relative_to(paths.repo_root).as_posix(),
    )
    if (
        approval.status != "PASS"
        or not approval.policy_satisfied
        or approval.approval_decision != "APPROVE_UNCHANGED"
        or not approval.thresholds_unchanged
        or not approval.registration_approval_state_valid
    ):
        raise ValueError("threshold approval is no longer valid and unchanged")

    frozen_cases = load_v1_1_frozen_dataset_bytes(frozen_payload)
    if len(frozen_cases) != 26 or any(
        not case.human_validated or case.review_status != "PASS" for case in frozen_cases
    ):
        raise ValueError("frozen dataset is not 26 human-reviewed PASS cases")
    runtime_cases = tuple(project_runtime_case(case) for case in frozen_cases)
    require_label_isolated_runtime_cases(runtime_cases)

    extractor_checksum = sha256_file(paths.extractor_implementation)
    remediation_extractor = _git_blob(
        paths.repo_root,
        RC2_REMEDIATION_COMMIT_SHA,
        _EXTRACTOR_RELATIVE_PATH,
    )
    if extractor_checksum != sha256_bytes(remediation_extractor):
        raise ValueError("production extractor differs from the remediation commit")
    canonical_model_path = paths.repo_root / _CANONICAL_MODEL_RELATIVE_PATH
    if canonical_model_path.read_bytes() != _git_blob(
        paths.repo_root,
        RC2_REMEDIATION_COMMIT_SHA,
        _CANONICAL_MODEL_RELATIVE_PATH,
    ):
        raise ValueError("canonical Case Intake models changed after remediation")

    prompt_checksum = sha256_bytes(CASE_INTAKE_SYSTEM_PROMPT.encode("utf-8"))
    if prompt_checksum != RC2_PROMPT_SHA256:
        raise ValueError("Case Intake prompt changed after remediation registration")
    transport_model = getattr(intake_module, "_ProviderCaseIntakeResult", None)
    if not isinstance(transport_model, type) or not issubclass(transport_model, BaseModel):
        raise ValueError("internal provider transport schema is unavailable")
    transport_type = cast(type[BaseModel], transport_model)
    transport_schema_checksum = sha256_bytes(
        canonical_json_bytes(transport_type.model_json_schema())
    )
    canonical_schema_checksum = sha256_bytes(
        canonical_json_bytes(CaseIntakeResult.model_json_schema())
    )

    repository_state = inspect_repository_state(paths.repo_root)
    worktree_clean = not repository_state.tracked_dirty and not repository_state.untracked_paths
    manifest = RC2CaptureManifest(
        release_candidate="v1_1_rc2",
        parent="v1_1_rc1",
        parent_result="FAILED_PROVIDER_CAPTURE",
        frozen_dataset_path=governed.frozen_dataset.relative_to(paths.repo_root).as_posix(),
        frozen_dataset_sha256=RC2_FROZEN_DATASET_SHA256,
        case_count=26,
        human_review_path=governed.review_packet.relative_to(paths.repo_root).as_posix(),
        human_review_sha256=RC2_HUMAN_REVIEW_SHA256,
        human_review_pass_count=26,
        human_review_unresolved_count=0,
        threshold_path=governed.threshold_spec.relative_to(paths.repo_root).as_posix(),
        threshold_sha256=RC2_THRESHOLD_SHA256,
        threshold_approval_valid=True,
        dataset_bytes_unchanged=True,
        expected_labels_unchanged=True,
        thresholds_unchanged=True,
        remediation_commit_sha=RC2_REMEDIATION_COMMIT_SHA,
        current_git_sha=registered_git_sha or repository_state.commit_sha,
        worktree_clean=worktree_clean,
        tracked_worktree_dirty=repository_state.tracked_dirty,
        untracked_worktree_paths=repository_state.untracked_paths,
        capture_runner_code_sha256=sha256_file(paths.capture_runner),
        capture_adapter_code_sha256=sha256_file(paths.capture_adapter),
        extractor_implementation_sha256=extractor_checksum,
        transport_schema_identity=_TRANSPORT_SCHEMA_IDENTITY,
        transport_schema_sha256=transport_schema_checksum,
        canonical_schema_identity=_CANONICAL_SCHEMA_IDENTITY,
        canonical_schema_version="CHECKSUM_BOUND_UNVERSIONED",
        canonical_schema_sha256=canonical_schema_checksum,
        prompt_sha256=prompt_checksum,
        generation_config=generation_config,
        paths=RC2RegisteredPaths.from_artifact_paths(paths),
        label_isolation=True,
        expected_labels_visible_to_extractor=False,
        thresholds_visible_to_extractor=False,
        reviewer_data_visible_to_extractor=False,
        production_extractor_implementation_changed=True,
        legal_semantics_changed=False,
        canonical_case_intake_result_changed=False,
        source_span_invariant_changed=False,
        prompt_semantic_policy_changed=False,
        metric_based_prompt_tuning_performed=False,
        successful_rc1_predictions_existed=False,
        status="PREPARED_NOT_CAPTURED",
    )
    return RC2CapturePlan(manifest=manifest, runtime_cases=runtime_cases)


def require_registered_git_identity(
    repo_root: Path,
    *,
    registered_sha: str,
    current_sha: str,
    capture_manifest: Path,
) -> None:
    """Allow the registered commit or its single manifest-only child commit."""

    if current_sha == registered_sha:
        return
    root = repo_root.resolve()
    manifest_relative_path = capture_manifest.resolve().relative_to(root).as_posix()
    parent_line = subprocess.run(
        ["git", "-C", str(root), "rev-list", "--parents", "-n", "1", current_sha],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    changed_paths = tuple(
        Path(path).as_posix()
        for path in subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                current_sha,
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        if path
    )
    if parent_line != [current_sha, registered_sha] or changed_paths != (manifest_relative_path,):
        raise ValueError("current repository does not match the registered Git identity")


def require_registered_worktree_identity(
    repository_state: RepositoryState,
    manifest: RC2CaptureManifest,
) -> None:
    """Reject any tracked or untracked delta not recorded at registration."""

    if (
        repository_state.tracked_dirty != manifest.tracked_worktree_dirty
        or repository_state.untracked_paths != manifest.untracked_worktree_paths
    ):
        raise ValueError("current repository does not match the registered worktree identity")


def _require_canonical_paths(paths: RC2ArtifactPaths) -> None:
    try:
        root = paths.repo_root.resolve(strict=True)
    except OSError as exc:
        raise ValueError("RC2 repository root does not exist") from exc
    if root != paths.repo_root or paths != RC2ArtifactPaths.from_root(root):
        raise ValueError("RC2 paths differ from the canonical repository contract")
    for path in (
        paths.output_directory,
        paths.registration_revision_1,
        paths.registration_revision_2,
        paths.capture_manifest,
        paths.capture_started,
        paths.capture_journal,
        paths.capture_completed,
        paths.predictions,
        paths.prediction_metadata,
        paths.metrics,
        paths.failed_samples,
        paths.release_report,
        paths.evaluation_started,
        paths.evaluation_completed,
        paths.release_terminal,
    ):
        try:
            path.resolve(strict=False).relative_to(root)
        except ValueError as exc:
            raise ValueError("RC2 output path escapes the repository root") from exc


def _git_blob(repo_root: Path, commit_sha: str, relative_path: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "show", f"{commit_sha}:{relative_path}"],
        check=True,
        capture_output=True,
    )
    return completed.stdout
