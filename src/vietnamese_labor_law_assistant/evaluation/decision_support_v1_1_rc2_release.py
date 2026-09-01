"""Provider-free RC2 evaluator and write-once release artifact producers."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1 import (
    V11EvaluationCandidateCase,
    V11EvaluationMetrics,
    V11Thresholds,
    load_v1_1_threshold_spec,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_artifacts import (
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_capture import (
    V11CaseIntakePredictionRecord,
    V11PredictionStatus,
    load_v1_1_prediction_records,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_freeze import (
    load_v1_1_frozen_dataset,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2 import (
    RC2ArtifactPaths,
    RC2CodeIdentities,
    RC2GenerationConfig,
    RC2RegisteredPathsV2,
    RC2RegistrationV2,
    load_rc2_registration_v2_offline,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2_capture import (
    RC2CaptureCompleted,
    RC2CaptureStarted,
    RC2PredictionMetadataV2,
    load_rc2_capture_started,
    load_rc2_journal,
    publish_atomic_write_once,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_release import (
    V11MetricGate,
    apply_v1_1_release_gates,
    build_v1_1_release_evaluation,
)

ModelT = TypeVar("ModelT", bound=BaseModel)


class RC2ReleaseProvenance(BaseModel):
    """Capture and evaluator identities safe to copy into offline release evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    release_candidate: Literal["v1_1_rc2"] = "v1_1_rc2"
    rc1_parent: Literal["v1_1_rc1"] = "v1_1_rc1"
    rc1_result: Literal["FAILED_PROVIDER_CAPTURE"] = "FAILED_PROVIDER_CAPTURE"
    rc1_preserved: Literal[True] = True
    registration_revision: Literal[2] = 2
    capture_run_id: str
    implementation_commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    code_identities: RC2CodeIdentities
    generation_config: RC2GenerationConfig
    frozen_dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    human_review_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    threshold_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prediction_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    registration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    capture_completed_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    capture_started_at: datetime
    capture_completed_at: datetime
    success_count: int = Field(ge=0, le=26)
    typed_failure_count: int = Field(ge=0, le=26)
    evaluated_at: datetime

    @model_validator(mode="after")
    def validate_provenance(self) -> RC2ReleaseProvenance:
        for value, name in (
            (self.capture_started_at, "capture start timestamp"),
            (self.capture_completed_at, "capture completion timestamp"),
            (self.evaluated_at, "evaluation timestamp"),
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must include a timezone")
        if self.capture_completed_at < self.capture_started_at:
            raise ValueError("capture completion timestamp precedes capture start")
        if self.evaluated_at < self.capture_completed_at:
            raise ValueError("evaluation timestamp precedes capture completion")
        if self.success_count + self.typed_failure_count != 26:
            raise ValueError("capture counts must total 26")
        return self


class RC2MetricsArtifact(BaseModel):
    """All measured values and 18 unchanged gates for one finalized snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["v1_1_rc2_metrics_v1"] = "v1_1_rc2_metrics_v1"
    release_candidate: Literal["v1_1_rc2"] = "v1_1_rc2"
    metric_definitions: dict[str, str]
    measured_metrics: V11EvaluationMetrics
    thresholds: V11Thresholds
    gates: tuple[V11MetricGate, ...]
    passed_gate_count: int = Field(ge=0, le=18)
    failed_gate_count: int = Field(ge=0, le=18)
    release_gate_result: Literal["PASS", "FAIL"]
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prediction_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    threshold_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluator_code_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluated_at: datetime
    threshold_modified_after_evaluation: Literal[False] = False

    @model_validator(mode="after")
    def validate_gate_counts(self) -> RC2MetricsArtifact:
        if len(self.gates) != 18:
            raise ValueError("RC2 metrics artifact requires all 18 gates")
        if self.passed_gate_count + self.failed_gate_count != 18:
            raise ValueError("RC2 gate counts must total 18")
        observed_passes = sum(gate.passed for gate in self.gates)
        if observed_passes != self.passed_gate_count:
            raise ValueError("RC2 passed-gate count differs from gate results")
        expected_result = "PASS" if self.failed_gate_count == 0 else "FAIL"
        if self.release_gate_result != expected_result:
            raise ValueError("RC2 release-gate result differs from mandatory gates")
        return self


class RC2FailedSample(BaseModel):
    """One failing case with canonical categories and affected metric families."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    categories: tuple[str, ...] = Field(min_length=1)
    metric_families: tuple[str, ...] = Field(min_length=1)
    extractor_failure_reason: str | None = None


class RC2OfflineEvaluation(BaseModel):
    """Provider-free in-memory result ready for write-once materialization."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["PASS", "FAIL"]
    metrics: RC2MetricsArtifact
    failed_samples: tuple[RC2FailedSample, ...]
    provenance: RC2ReleaseProvenance | None = None
    live_provider_calls: Literal[0] = 0
    downstream_llm_calls: Literal[0] = 0

    @model_validator(mode="after")
    def validate_status(self) -> RC2OfflineEvaluation:
        if self.status == "PASS" and self.metrics.release_gate_result != "PASS":
            raise ValueError("RC2 PASS requires all mandatory gates to pass")
        return self


class RC2EvaluationStarted(BaseModel):
    """Stable identity and timestamp for resumable offline materialization."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["v1_1_rc2_evaluation_started_v1"] = "v1_1_rc2_evaluation_started_v1"
    release_candidate: Literal["v1_1_rc2"] = "v1_1_rc2"
    registration_revision: Literal[2] = 2
    lifecycle_state: Literal["OFFLINE_EVALUATION_STARTED"] = "OFFLINE_EVALUATION_STARTED"
    capture_run_id: str
    registration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    capture_completed_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prediction_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluator_code_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluated_at: datetime
    live_provider_calls: Literal[0] = 0

    @model_validator(mode="after")
    def validate_timestamp(self) -> RC2EvaluationStarted:
        if self.evaluated_at.tzinfo is None or self.evaluated_at.utcoffset() is None:
            raise ValueError("evaluation start timestamp must include a timezone")
        return self


class RC2EvaluationCompleted(BaseModel):
    """Immutable OFFLINE_EVALUATED transition bound to all release products."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["v1_1_rc2_evaluation_completed_v1"] = "v1_1_rc2_evaluation_completed_v1"
    release_candidate: Literal["v1_1_rc2"] = "v1_1_rc2"
    registration_revision: Literal[2] = 2
    lifecycle_state: Literal["OFFLINE_EVALUATED"] = "OFFLINE_EVALUATED"
    capture_run_id: str
    evaluation_started_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    capture_completed_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prediction_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    metrics_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    failed_samples_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    release_report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluator_code_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluated_at: datetime
    release_gate_result: Literal["PASS", "FAIL"]
    live_provider_calls: Literal[0] = 0
    downstream_llm_calls: Literal[0] = 0


class RC2ReleaseTerminal(BaseModel):
    """Final immutable release decision whose parent is OFFLINE_EVALUATED."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["v1_1_rc2_release_terminal_v1"] = "v1_1_rc2_release_terminal_v1"
    release_candidate: Literal["v1_1_rc2"] = "v1_1_rc2"
    registration_revision: Literal[2] = 2
    lifecycle_state: Literal["RELEASE_PASS", "RELEASE_FAIL"]
    final_result: Literal["PASS", "FAIL"]
    evaluation_completed_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    passed_gate_count: int = Field(ge=0, le=18)
    failed_gate_count: int = Field(ge=0, le=18)
    failing_case_ids: tuple[str, ...]
    threshold_modified_after_evaluation: Literal[False] = False
    live_provider_calls_after_snapshot: Literal[0] = 0

    @model_validator(mode="after")
    def validate_terminal_status(self) -> RC2ReleaseTerminal:
        if (self.lifecycle_state == "RELEASE_PASS") != (self.final_result == "PASS"):
            raise ValueError("release lifecycle state differs from final result")
        if self.final_result == "PASS" and self.failed_gate_count:
            raise ValueError("RELEASE_PASS cannot contain failed mandatory gates")
        return self


def build_rc2_metrics_artifact(
    metrics: V11EvaluationMetrics,
    thresholds: V11Thresholds,
    *,
    metric_definitions: Mapping[str, str],
    provenance: RC2ReleaseProvenance,
) -> RC2MetricsArtifact:
    """Apply the existing registered N/A/failure semantics to all 18 metrics."""

    gates = apply_v1_1_release_gates(metrics, thresholds)
    passed = sum(gate.passed for gate in gates.gates)
    return RC2MetricsArtifact(
        metric_definitions=dict(metric_definitions),
        measured_metrics=metrics,
        thresholds=thresholds,
        gates=gates.gates,
        passed_gate_count=passed,
        failed_gate_count=18 - passed,
        release_gate_result=gates.status,
        dataset_sha256=provenance.frozen_dataset_sha256,
        prediction_sha256=provenance.prediction_sha256,
        threshold_sha256=provenance.threshold_sha256,
        evaluator_code_sha256=provenance.code_identities.offline_evaluator_sha256,
        evaluated_at=provenance.evaluated_at,
    )


def build_rc2_offline_evaluation(
    cases: Sequence[V11EvaluationCandidateCase],
    records: Sequence[V11CaseIntakePredictionRecord],
    thresholds: V11Thresholds,
    *,
    metric_definitions: Mapping[str, str],
    provenance: RC2ReleaseProvenance,
    snapshot_complete: bool,
) -> RC2OfflineEvaluation:
    """Run Case Intake snapshot through deterministic downstream capabilities only."""

    success_count = sum(record.status is V11PredictionStatus.SUCCESS for record in records)
    if (
        success_count != provenance.success_count
        or len(records) - success_count != provenance.typed_failure_count
    ):
        raise ValueError("prediction counts differ from capture-completion provenance")
    base = build_v1_1_release_evaluation(
        cases,
        records,
        thresholds,
        snapshot_complete=snapshot_complete,
    )
    metrics = build_rc2_metrics_artifact(
        base.metrics,
        thresholds,
        metric_definitions=metric_definitions,
        provenance=provenance,
    )
    failed_samples = tuple(
        RC2FailedSample(
            case_id=sample.case_id,
            categories=_normalized_failure_categories(sample.categories),
            metric_families=_metric_families(sample.categories),
            extractor_failure_reason=_extractor_failure_reason(sample.categories),
        )
        for sample in base.failed_samples
    )
    status: Literal["PASS", "FAIL"] = (
        "PASS" if snapshot_complete and metrics.release_gate_result == "PASS" else "FAIL"
    )
    return RC2OfflineEvaluation(
        status=status,
        metrics=metrics,
        failed_samples=failed_samples,
        provenance=provenance,
    )


def materialize_rc2_release(
    paths: RC2ArtifactPaths,
    evaluation: RC2OfflineEvaluation,
) -> RC2ReleaseTerminal:
    """Atomically create each RC2 final result once, with the terminal identity last."""

    if evaluation.provenance is None:
        raise ValueError("RC2 release materialization requires provenance")
    terminal_preexisting = os.path.lexists(paths.release_terminal)
    metrics_bytes = canonical_json_bytes(evaluation.metrics.model_dump(mode="json"))
    failed_bytes = b"".join(
        canonical_json_bytes(sample.model_dump(mode="json")) for sample in evaluation.failed_samples
    )
    report_bytes = _release_report(evaluation).encode("utf-8")

    provenance = evaluation.provenance
    started = RC2EvaluationStarted(
        capture_run_id=provenance.capture_run_id,
        registration_sha256=provenance.registration_sha256,
        capture_completed_sha256=provenance.capture_completed_sha256,
        prediction_sha256=provenance.prediction_sha256,
        evaluator_code_sha256=provenance.code_identities.offline_evaluator_sha256,
        evaluated_at=provenance.evaluated_at,
    )
    started_bytes = canonical_json_bytes(started.model_dump(mode="json"))
    evaluated = RC2EvaluationCompleted(
        capture_run_id=provenance.capture_run_id,
        evaluation_started_sha256=sha256_bytes(started_bytes),
        capture_completed_sha256=provenance.capture_completed_sha256,
        prediction_sha256=provenance.prediction_sha256,
        metrics_sha256=sha256_bytes(metrics_bytes),
        failed_samples_sha256=sha256_bytes(failed_bytes),
        release_report_sha256=sha256_bytes(report_bytes),
        evaluator_code_sha256=provenance.code_identities.offline_evaluator_sha256,
        evaluated_at=provenance.evaluated_at,
        release_gate_result=evaluation.metrics.release_gate_result,
    )
    evaluated_bytes = canonical_json_bytes(evaluated.model_dump(mode="json"))
    terminal = RC2ReleaseTerminal(
        lifecycle_state="RELEASE_PASS" if evaluation.status == "PASS" else "RELEASE_FAIL",
        final_result=evaluation.status,
        evaluation_completed_sha256=sha256_bytes(evaluated_bytes),
        passed_gate_count=evaluation.metrics.passed_gate_count,
        failed_gate_count=evaluation.metrics.failed_gate_count,
        failing_case_ids=tuple(sample.case_id for sample in evaluation.failed_samples),
    )
    terminal_bytes = canonical_json_bytes(terminal.model_dump(mode="json"))
    for path, payload in (
        (paths.evaluation_started, started_bytes),
        (paths.metrics, metrics_bytes),
        (paths.failed_samples, failed_bytes),
        (paths.release_report, report_bytes),
        (paths.evaluation_completed, evaluated_bytes),
        (paths.release_terminal, terminal_bytes),
    ):
        _publish_or_verify_release_artifact(path, payload)
    if terminal_preexisting:
        raise FileExistsError("RC2 release is already finalized")
    return terminal


def evaluate_registered_rc2_release(
    paths: RC2ArtifactPaths,
    *,
    evaluated_at: datetime | None = None,
) -> RC2ReleaseTerminal:
    """Evaluate the real finalized RC2 snapshot offline; this API has no provider input."""

    required_before_labels = (
        paths.registration_revision_2,
        paths.capture_started,
        paths.capture_journal,
        paths.predictions,
        paths.prediction_metadata,
        paths.capture_completed,
    )
    for path in required_before_labels:
        if not path.is_file():
            raise FileNotFoundError(f"required finalized RC2 capture artifact is missing: {path}")
    registration = _load_canonical_model(paths.registration_revision_2, RC2RegistrationV2)
    started = _load_canonical_model(paths.capture_started, RC2CaptureStarted)
    metadata = _load_canonical_model(paths.prediction_metadata, RC2PredictionMetadataV2)
    completed = _load_canonical_model(paths.capture_completed, RC2CaptureCompleted)
    prediction_sha256 = sha256_file(paths.predictions)
    _validate_prelabel_capture_chain(
        paths,
        registration,
        started,
        metadata,
        completed,
        prediction_sha256,
    )

    # This full loader validates Git/worktree/code/governance identity. It is called only
    # after the finalized prediction chain is proven, so labels cannot affect capture.
    plan = load_rc2_registration_v2_offline(paths)
    if plan.registration != registration:
        raise ValueError("offline registration identity differs from capture registration")
    verified_started = load_rc2_capture_started(paths, registration, plan.runtime_cases)
    if verified_started != started:
        raise ValueError("validated CAPTURE_STARTED identity changed")
    journal_entries = load_rc2_journal(paths, started, plan.runtime_cases)
    if len(journal_entries) != 26:
        raise ValueError("offline evaluation requires 26 terminal journal entries")
    journal_successes = sum(entry.terminal_result == "SUCCESS" for entry in journal_entries)
    if (
        journal_successes != completed.success_count
        or 26 - journal_successes != completed.typed_failure_count
    ):
        raise ValueError("capture completion counts differ from durable journal")

    cases = load_v1_1_frozen_dataset(paths.governed.frozen_dataset)
    records = load_v1_1_prediction_records(paths.predictions)
    threshold_spec = load_v1_1_threshold_spec(
        paths.governed.threshold_spec,
        repo_root=paths.repo_root,
    )
    timestamp = _resolve_evaluation_timestamp(
        paths,
        registration,
        completed,
        prediction_sha256,
        evaluated_at,
    )
    provenance = RC2ReleaseProvenance(
        capture_run_id=completed.capture_run_id,
        implementation_commit_sha=registration.implementation_commit_sha,
        code_identities=registration.code_identities,
        generation_config=registration.generation_config,
        frozen_dataset_sha256=registration.frozen_dataset_sha256,
        human_review_sha256=registration.human_review_sha256,
        threshold_sha256=registration.threshold_sha256,
        prediction_sha256=prediction_sha256,
        registration_sha256=sha256_file(paths.registration_revision_2),
        capture_completed_sha256=sha256_file(paths.capture_completed),
        capture_started_at=completed.capture_started_at,
        capture_completed_at=completed.capture_completed_at,
        success_count=completed.success_count,
        typed_failure_count=completed.typed_failure_count,
        evaluated_at=timestamp,
    )
    evaluation = build_rc2_offline_evaluation(
        cases,
        records,
        threshold_spec.thresholds,
        metric_definitions=threshold_spec.metric_definitions,
        provenance=provenance,
        snapshot_complete=True,
    )
    return materialize_rc2_release(paths, evaluation)


def _validate_prelabel_capture_chain(
    paths: RC2ArtifactPaths,
    registration: RC2RegistrationV2,
    started: RC2CaptureStarted,
    metadata: RC2PredictionMetadataV2,
    completed: RC2CaptureCompleted,
    prediction_sha256: str,
) -> None:
    """Prove every capture parent/checksum before expected labels are reachable."""

    registration_sha256 = sha256_file(paths.registration_revision_2)
    started_sha256 = sha256_file(paths.capture_started)
    metadata_sha256 = sha256_file(paths.prediction_metadata)
    journal_sha256 = sha256_file(paths.capture_journal)
    if registration.paths != RC2RegisteredPathsV2.from_artifact_paths(paths):
        raise ValueError("RC2 registration paths differ from the canonical namespace")
    if any(
        value != registration_sha256
        for value in (
            started.registration_sha256,
            metadata.registration_sha256,
            completed.registration_sha256,
        )
    ):
        raise ValueError("capture chain binds a different registration revision 2")
    if any(
        value != started_sha256
        for value in (metadata.capture_started_sha256, completed.capture_started_sha256)
    ):
        raise ValueError("capture chain binds a different CAPTURE_STARTED identity")
    if completed.prediction_metadata_sha256 != metadata_sha256:
        raise ValueError("capture completion binds different prediction metadata")
    if any(
        value != journal_sha256 for value in (metadata.journal_sha256, completed.journal_sha256)
    ):
        raise ValueError("capture chain binds a different durable journal")
    if any(
        value != prediction_sha256
        for value in (metadata.predictions_sha256, completed.prediction_snapshot_sha256)
    ):
        raise ValueError("capture chain binds a different prediction snapshot")
    if not (
        started.capture_run_id == metadata.capture_run_id == completed.capture_run_id
        and started.capture_started_at
        == metadata.capture_started_at
        == completed.capture_started_at
        and metadata.capture_completed_at == completed.capture_completed_at
        and metadata.success_count == completed.success_count
        and metadata.typed_failure_count == completed.typed_failure_count
        and metadata.capture_outcome == completed.capture_outcome
    ):
        raise ValueError("capture lifecycle identities or counts differ")
    if not (
        started.frozen_dataset_sha256
        == completed.frozen_dataset_sha256
        == registration.frozen_dataset_sha256
        and started.human_review_sha256
        == completed.human_review_sha256
        == registration.human_review_sha256
        and started.threshold_sha256 == completed.threshold_sha256 == registration.threshold_sha256
        and started.implementation_commit_sha
        == completed.implementation_commit_sha
        == registration.implementation_commit_sha
        and started.code_identities == completed.code_identities == registration.code_identities
        and started.generation_config
        == completed.generation_config
        == registration.generation_config
    ):
        raise ValueError(
            "capture code, governance, or generation identity differs from registration"
        )


def _resolve_evaluation_timestamp(
    paths: RC2ArtifactPaths,
    registration: RC2RegistrationV2,
    completed: RC2CaptureCompleted,
    prediction_sha256: str,
    requested: datetime | None,
) -> datetime:
    if paths.evaluation_started.is_file():
        started = _load_canonical_model(paths.evaluation_started, RC2EvaluationStarted)
        expected = RC2EvaluationStarted(
            capture_run_id=completed.capture_run_id,
            registration_sha256=sha256_file(paths.registration_revision_2),
            capture_completed_sha256=sha256_file(paths.capture_completed),
            prediction_sha256=prediction_sha256,
            evaluator_code_sha256=registration.code_identities.offline_evaluator_sha256,
            evaluated_at=started.evaluated_at,
        )
        if started != expected:
            raise ValueError("existing offline-evaluation start identity changed")
        if requested is not None and requested != started.evaluated_at:
            raise ValueError(
                "requested evaluation timestamp differs from existing evaluation start"
            )
        return started.evaluated_at
    downstream = (
        paths.metrics,
        paths.failed_samples,
        paths.release_report,
        paths.evaluation_completed,
        paths.release_terminal,
    )
    if any(os.path.lexists(path) for path in downstream):
        raise ValueError("release output exists without offline-evaluation start identity")
    return requested or datetime.now().astimezone().replace(microsecond=0)


def _metric_families(categories: Sequence[str]) -> tuple[str, ...]:
    families: list[str] = []
    for category in categories:
        prefix = category.split(":", 1)[0]
        mapped = {
            "EXTRACTOR_FAILURE": (
                "CASE_INTAKE",
                "CANDIDATE_ISSUES",
                "REFINED_ISSUES",
                "MISSING_FACTS",
                "CLARIFICATION",
                "CASE_GRAPH",
            ),
            "FACT_SIGNATURE_MISMATCH": ("CASE_INTAKE",),
            "SOURCE_SPAN_MISMATCH": ("SOURCE_SPANS",),
            "CANDIDATE_ISSUE_MISMATCH": ("CANDIDATE_ISSUES",),
            "REFINED_ISSUE_MISMATCH": ("REFINED_ISSUES",),
            "MISSING_FACT_MISMATCH": ("MISSING_FACTS",),
            "CLARIFICATION_MISMATCH": ("CLARIFICATION",),
            "GRAPH_STATUS_MISMATCH": ("CASE_GRAPH",),
            "GRAPH_STATE_CONTRACT_INVALID": ("CASE_GRAPH",),
            "GRAPH_CONTRACT_FAILURE": ("CASE_GRAPH",),
            "DETERMINISTIC_DOMAIN_FAILURE": ("DETERMINISTIC_DOWNSTREAM",),
        }.get(prefix, ())
        families.extend(mapped)
    return tuple(dict.fromkeys(families or ("DETERMINISTIC_DOWNSTREAM",)))


def _normalized_failure_categories(categories: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(category.split(":", 1)[0] for category in categories))


def _extractor_failure_reason(categories: Sequence[str]) -> str | None:
    return next(
        (
            category.split(":", 1)[1]
            for category in categories
            if category.startswith("EXTRACTOR_FAILURE:")
        ),
        None,
    )


def _load_canonical_model(path: Path, model_type: type[ModelT]) -> ModelT:
    payload = path.read_bytes()
    model = model_type.model_validate_json(payload)
    if payload != canonical_json_bytes(model.model_dump(mode="json")):
        raise ValueError(f"artifact bytes are not canonical: {path}")
    return model


def _publish_or_verify_release_artifact(path: Path, payload: bytes) -> None:
    if os.path.lexists(path):
        if not path.is_file() or path.read_bytes() != payload:
            raise ValueError(f"existing release artifact differs from evaluation: {path}")
        return
    publish_atomic_write_once(path, payload)


def _release_report(evaluation: RC2OfflineEvaluation) -> str:
    provenance = evaluation.provenance
    if provenance is None:
        raise ValueError("RC2 report requires release provenance")
    metric_lines = "\n".join(
        f"- `{name}`: {json.dumps(value, ensure_ascii=False, sort_keys=True)}"
        for name, value in evaluation.metrics.measured_metrics.model_dump(mode="json").items()
    )
    gate_lines = "\n".join(
        f"- `{gate.metric}`: measured={gate.measured_value}, gate {gate.comparator} "
        f"{gate.threshold} — {'PASS' if gate.passed else 'FAIL'}"
        for gate in evaluation.metrics.gates
    )
    failures = (
        "\n".join(
            f"- `{sample.case_id}`: {', '.join(sample.categories)}"
            f"{f' [{sample.extractor_failure_reason}]' if sample.extractor_failure_reason else ''} "
            f"(families: {', '.join(sample.metric_families)})"
            for sample in evaluation.failed_samples
        )
        or "- None"
    )
    code_lines = "\n".join(
        f"- `{name}`: `{value}`"
        for name, value in provenance.code_identities.model_dump(mode="json").items()
    )
    config = provenance.generation_config
    return (
        "# RC2 release evaluation\n\n"
        f"Final result: **{evaluation.status}**\n\n"
        "## Release identity\n\n"
        "- Release candidate: `v1_1_rc2`\n"
        "- RC1 parent/result: `v1_1_rc1` / `FAILED_PROVIDER_CAPTURE`\n"
        "- RC1 preservation: immutable and unchanged\n"
        "- Registration revision: `2`\n"
        f"- Capture run ID: `{provenance.capture_run_id}`\n"
        f"- Implementation Git commit: `{provenance.implementation_commit_sha}`\n"
        f"- Frozen dataset SHA-256: `{provenance.frozen_dataset_sha256}`\n"
        f"- Human-review SHA-256: `{provenance.human_review_sha256}`\n"
        f"- Threshold SHA-256: `{provenance.threshold_sha256}`\n"
        f"- Prediction SHA-256: `{provenance.prediction_sha256}`\n"
        f"- Capture started at: `{provenance.capture_started_at.isoformat()}`\n"
        f"- Capture completed at: `{provenance.capture_completed_at.isoformat()}`\n"
        f"- Evaluated at: `{provenance.evaluated_at.isoformat()}`\n"
        f"- Success count: `{provenance.success_count}`\n"
        f"- Typed failure count: `{provenance.typed_failure_count}`\n\n"
        "## Code identities\n\n"
        f"{code_lines}\n\n"
        "## Provider configuration\n\n"
        f"- Provider: `{config.provider}`\n"
        f"- Model: `{config.model}`\n"
        f"- Base URL: `{config.base_url}`\n"
        f"- Temperature: `{config.temperature}`\n"
        f"- Timeout seconds: `{config.timeout_seconds}`\n"
        f"- SDK retries: `{config.sdk_max_retries}`\n"
        f"- Structured retries: `{config.structured_max_retries}`\n"
        f"- Concurrency: `{config.concurrency}`\n"
        f"- Inter-case pacing: `{config.inter_case_pacing_seconds}` seconds\n\n"
        "## Metrics\n\n"
        f"{metric_lines}\n\n"
        "## All 18 pre-registered gates\n\n"
        f"{gate_lines}\n\n"
        f"- Passed gates: `{evaluation.metrics.passed_gate_count}`\n"
        f"- Failed gates: `{evaluation.metrics.failed_gate_count}`\n\n"
        "Threshold modified after evaluation: **NO**\n\n"
        "Expected labels hidden during provider capture: **YES**\n\n"
        "Live LLM calls after snapshot: **0**\n\n"
        "## Failed samples and typed categories\n\n"
        f"{failures}\n\n"
        "## Known limitations\n\n"
        "Week 5 EvidencePlan, MCP efficiency optimization, legal application, recommendations, "
        "and what-if analysis are NOT part of this Week-4 release capability.\n"
    )
