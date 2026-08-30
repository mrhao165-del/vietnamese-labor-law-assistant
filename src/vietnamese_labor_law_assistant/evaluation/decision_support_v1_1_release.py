"""Offline-only deterministic v1.1 release evaluation from the production snapshot."""

from __future__ import annotations

import os
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from vietnamese_labor_law_assistant.agent.case_graph import (
    CaseAnalysisErrorCode,
    CaseAnalysisResult,
    CaseAnalysisStatus,
)
from vietnamese_labor_law_assistant.decision_support.clarification import (
    TargetedClarificationBuilder,
)
from vietnamese_labor_law_assistant.decision_support.evidence_requests import (
    EvidenceRequestSkeletonBuilder,
)
from vietnamese_labor_law_assistant.decision_support.missing_facts import MissingFactDetector
from vietnamese_labor_law_assistant.decision_support.refined_issues import RefinedIssueEvaluator
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1 import (
    RefinedIssueLabel,
    V11EvaluationCandidateCase,
    V11EvaluationMetrics,
    V11EvaluationPrediction,
    V11Thresholds,
    load_v1_1_threshold_spec,
    v1_1_metrics,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_artifacts import (
    V11_FREEZE_CODE_RELATIVE_PATHS,
    V11ArtifactPaths,
    canonical_json_bytes,
    inspect_repository_state,
    sha256_bytes,
    write_exclusive,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_capture import (
    V11CaseIntakePredictionRecord,
    V11PredictionSnapshotManifest,
    V11PredictionStatus,
    load_v1_1_prediction_records,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_freeze import (
    V11FrozenDatasetManifest,
    load_v1_1_frozen_dataset,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_week3 import (
    v1_1_registry_for_profile,
)


class V11MetricGate(BaseModel):
    """One measured value compared with its unchanged registered threshold."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    metric: str
    comparator: Literal[">=", "<="]
    measured_value: float | None
    threshold: float
    passed: bool


class V11ReleaseGateResult(BaseModel):
    """Aggregate release decision over all 18 pre-registered metrics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["PASS", "FAIL"]
    gates: tuple[V11MetricGate, ...]
    threshold_modified_after_evaluation: Literal[False] = False


class V11FailedSample(BaseModel):
    """One visible final-evaluation failure with stable typed categories."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    categories: tuple[str, ...]


class V11ReleaseEvaluation(BaseModel):
    """Complete in-memory offline result before write-once materialization."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["PASS", "FAIL"]
    snapshot_complete: bool
    metrics: V11EvaluationMetrics
    gates: V11ReleaseGateResult
    predictions: tuple[V11EvaluationPrediction, ...]
    failed_samples: tuple[V11FailedSample, ...]


@dataclass(frozen=True)
class V11ReleasePaths:
    """Canonical final offline-evaluation outputs for one repository root."""

    repo_root: Path
    derived_predictions: Path
    metrics: Path
    release_manifest: Path
    result_report: Path
    docs_report: Path

    @classmethod
    def from_root(cls, repo_root: Path) -> V11ReleasePaths:
        root = repo_root.resolve()
        results = root / "evaluation/results/decision_support/v1_1"
        return cls(
            repo_root=root,
            derived_predictions=results / "v1_1_final_offline_predictions.jsonl",
            metrics=results / "v1_1_final_metrics.json",
            release_manifest=results / "v1_1_release_evaluation_manifest.json",
            result_report=results / "v1_1_release_evaluation_report.md",
            docs_report=root / "docs/releases/v1_1_week4_release_evaluation.md",
        )


class V11ReleaseProvenance(BaseModel):
    """Frozen inputs and timestamps copied into final release evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    frozen_dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    freeze_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prediction_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prediction_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    threshold_spec_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluation_spec_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_packet_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    git_commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    reviewed_at: datetime
    frozen_at: datetime
    evaluated_at: datetime


class V11ReleaseEvidenceManifest(BaseModel):
    """Checksum-bound final offline release decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["v1_1_release_evaluation_manifest_v1"] = (
        "v1_1_release_evaluation_manifest_v1"
    )
    dataset_id: Literal["decision_support_v1_1_final"] = "decision_support_v1_1_final"
    dataset_version: Literal["v1_1_frozen"] = "v1_1_frozen"
    case_count: Literal[26] = 26
    status: Literal["PASS", "FAIL"]
    provenance: V11ReleaseProvenance
    derived_predictions_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    metrics_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    failed_sample_count: int = Field(ge=0, le=26)
    threshold_modified_after_evaluation: Literal[False] = False
    limitation: Literal[
        "Week 5 EvidencePlan and downstream legal decision execution are NOT part of v1.1 "
        "Week-4 release capability."
    ] = (
        "Week 5 EvidencePlan and downstream legal decision execution are NOT part of v1.1 "
        "Week-4 release capability."
    )


def derive_v1_1_offline_prediction(
    case: V11EvaluationCandidateCase,
    record: V11CaseIntakePredictionRecord,
) -> tuple[V11EvaluationPrediction, tuple[str, ...]]:
    """Run only deterministic Week-3/4 capabilities from one captured intake record."""

    if record.case_id != case.case_id:
        raise ValueError("prediction record case ID differs from the frozen case")
    if record.status is V11PredictionStatus.ERROR:
        failure_reason = (
            record.failure_reason.value
            if record.failure_reason is not None
            else "UNKNOWN_EXTRACTOR_FAILURE"
        )
        terminal = CaseAnalysisResult(
            request_id=f"evaluation:{case.case_id}",
            status=CaseAnalysisStatus.CASE_INTAKE_FAILED,
            message="Captured production Case Intake failed.",
            error_code=_capture_error_code(record),
        )
        return (
            V11EvaluationPrediction(
                case_id=case.case_id,
                graph_status=terminal.status,
                graph_state_payload=terminal.model_dump(mode="json"),
                substantive_ready=False,
            ),
            (f"EXTRACTOR_FAILURE:{failure_reason}",),
        )

    intake = record.result
    if intake is None:
        raise ValueError("successful prediction record is missing its intake result")
    issue_codes = tuple(candidate.issue_code for candidate in intake.candidate_issues)
    if not intake.candidate_issues:
        terminal = CaseAnalysisResult(
            request_id=f"evaluation:{case.case_id}",
            status=CaseAnalysisStatus.UNSUPPORTED_SCOPE,
            message="No supported candidate issue was captured.",
            intake_result=intake,
        )
        return (
            V11EvaluationPrediction(
                case_id=case.case_id,
                case_facts=tuple(intake.facts),
                candidate_issue_codes=issue_codes,
                graph_status=terminal.status,
                graph_state_payload=terminal.model_dump(mode="json"),
                substantive_ready=False,
            ),
            (),
        )

    registry = v1_1_registry_for_profile(case.registry_profile)
    try:
        missing = MissingFactDetector().detect(
            intake.facts,
            intake.candidate_issues,
            registry,
        )
        clarification = TargetedClarificationBuilder().build(
            missing,
            previously_requested_fields=case.previously_requested_fields,
            max_questions=case.max_questions,
        )
        refined = RefinedIssueEvaluator().refine(
            intake.facts,
            intake.candidate_issues,
            missing,
            registry,
        )
    except Exception:
        terminal = CaseAnalysisResult(
            request_id=f"evaluation:{case.case_id}",
            status=CaseAnalysisStatus.CASE_ANALYSIS_FAILED,
            message="Deterministic Case Analysis failed closed.",
            error_code=CaseAnalysisErrorCode.CASE_DOMAIN_CONTRACT_INVALID,
            intake_result=intake,
        )
        return (
            V11EvaluationPrediction(
                case_id=case.case_id,
                case_facts=tuple(intake.facts),
                candidate_issue_codes=issue_codes,
                graph_status=terminal.status,
                graph_state_payload=terminal.model_dump(mode="json"),
                substantive_ready=False,
            ),
            ("DETERMINISTIC_DOMAIN_FAILURE",),
        )

    refined_labels = tuple(
        RefinedIssueLabel(
            issue_code=issue.issue_code,
            status=issue.status,
            reason_code=issue.reason_code,
            remaining_missing_fields=issue.remaining_missing_fields,
            critical_missing_fields=issue.critical_missing_fields,
            conflict_codes=issue.conflict_codes,
        )
        for issue in refined.issues
    )
    try:
        if missing.fields_needed or missing.conflicts:
            terminal = CaseAnalysisResult(
                request_id=f"evaluation:{case.case_id}",
                status=CaseAnalysisStatus.CLARIFICATION_REQUIRED,
                message="Additional facts are required.",
                intake_result=intake,
                missing_facts=missing,
                clarification=clarification,
            )
        else:
            evidence = EvidenceRequestSkeletonBuilder().build(refined, registry)
            terminal = CaseAnalysisResult(
                request_id=f"evaluation:{case.case_id}",
                status=CaseAnalysisStatus.EVIDENCE_REQUEST_READY,
                message="Evidence-request metadata is ready.",
                intake_result=intake,
                missing_facts=missing,
                refined_issues=refined,
                evidence_request=evidence,
            )
    except Exception:
        terminal = CaseAnalysisResult(
            request_id=f"evaluation:{case.case_id}",
            status=CaseAnalysisStatus.CASE_ANALYSIS_FAILED,
            message="The deterministic graph terminal failed its typed contract.",
            error_code=CaseAnalysisErrorCode.CASE_DOMAIN_CONTRACT_INVALID,
            intake_result=intake,
            missing_facts=missing,
            refined_issues=refined,
        )
        return (
            V11EvaluationPrediction(
                case_id=case.case_id,
                case_facts=tuple(intake.facts),
                candidate_issue_codes=issue_codes,
                missing_fields=tuple(field.fact_key for field in missing.fields_needed),
                question_fields=tuple(question.fact_key for question in clarification.questions),
                refined_issues=refined_labels,
                graph_status=terminal.status,
                graph_state_payload=terminal.model_dump(mode="json"),
                substantive_ready=False,
            ),
            ("GRAPH_CONTRACT_FAILURE",),
        )
    return (
        V11EvaluationPrediction(
            case_id=case.case_id,
            case_facts=tuple(intake.facts),
            candidate_issue_codes=issue_codes,
            missing_fields=tuple(field.fact_key for field in missing.fields_needed),
            question_fields=tuple(question.fact_key for question in clarification.questions),
            refined_issues=refined_labels,
            graph_status=terminal.status,
            graph_state_payload=terminal.model_dump(mode="json"),
            substantive_ready=terminal.status is CaseAnalysisStatus.EVIDENCE_REQUEST_READY,
        ),
        (),
    )


def apply_v1_1_release_gates(
    metrics: V11EvaluationMetrics,
    thresholds: V11Thresholds,
) -> V11ReleaseGateResult:
    """Apply every unchanged pre-registered threshold exactly once."""

    applicable_fields = tuple(
        value for value in metrics.fact_field_f1.values() if value is not None
    )
    measurements: tuple[tuple[str, str, float | None, float], ...] = (
        ("overall_fact_f1", ">=", metrics.overall_fact_f1, thresholds.overall_fact_f1_min),
        (
            "minimum_applicable_fact_field_f1",
            ">=",
            min(applicable_fields) if applicable_fields else None,
            thresholds.minimum_applicable_fact_field_f1_min,
        ),
        (
            "critical_field_recall",
            ">=",
            metrics.critical_field_recall,
            thresholds.critical_field_recall_min,
        ),
        ("date_exact_match", ">=", metrics.date_exact_match, thresholds.date_exact_match_min),
        (
            "money_exact_match",
            ">=",
            metrics.money_exact_match,
            thresholds.money_exact_match_min,
        ),
        (
            "source_span_accuracy",
            ">=",
            metrics.source_span_accuracy,
            thresholds.source_span_accuracy_min,
        ),
        (
            "hallucinated_fact_rate",
            "<=",
            metrics.hallucinated_fact_rate,
            thresholds.hallucinated_fact_rate_max,
        ),
        (
            "candidate_issue_macro_f1",
            ">=",
            metrics.candidate_issue_macro_f1,
            thresholds.candidate_issue_macro_f1_min,
        ),
        (
            "critical_issue_recall",
            ">=",
            metrics.critical_issue_recall,
            thresholds.critical_issue_recall_min,
        ),
        (
            "refined_issue_macro_f1",
            ">=",
            metrics.refined_issue_macro_f1,
            thresholds.refined_issue_macro_f1_min,
        ),
        (
            "refined_issue_status_accuracy",
            ">=",
            metrics.refined_issue_status_accuracy,
            thresholds.refined_issue_status_accuracy_min,
        ),
        (
            "refined_issue_payload_accuracy",
            ">=",
            metrics.refined_issue_payload_accuracy,
            thresholds.refined_issue_payload_accuracy_min,
        ),
        (
            "missing_fact_precision",
            ">=",
            metrics.missing_fact_precision,
            thresholds.missing_fact_precision_min,
        ),
        (
            "missing_fact_recall",
            ">=",
            metrics.missing_fact_recall,
            thresholds.missing_fact_recall_min,
        ),
        (
            "duplicate_question_rate",
            "<=",
            metrics.duplicate_question_rate,
            thresholds.duplicate_question_rate_max,
        ),
        (
            "critical_fact_leakage",
            "<=",
            metrics.critical_fact_leakage,
            thresholds.critical_fact_leakage_max,
        ),
        (
            "graph_route_accuracy",
            ">=",
            metrics.graph_route_accuracy,
            thresholds.graph_route_accuracy_min,
        ),
        (
            "graph_state_contract_accuracy",
            ">=",
            metrics.graph_state_contract_accuracy,
            thresholds.graph_state_contract_accuracy_min,
        ),
    )
    gates = tuple(
        V11MetricGate(
            metric=name,
            comparator=comparator,
            measured_value=value,
            threshold=threshold,
            passed=(
                value is not None
                and (value >= threshold if comparator == ">=" else value <= threshold)
            ),
        )
        for name, comparator, value, threshold in measurements
    )
    return V11ReleaseGateResult(
        status="PASS" if all(gate.passed for gate in gates) else "FAIL",
        gates=gates,
    )


def build_v1_1_release_evaluation(
    cases: Sequence[V11EvaluationCandidateCase],
    records: Sequence[V11CaseIntakePredictionRecord],
    thresholds: V11Thresholds,
    *,
    snapshot_complete: bool,
) -> V11ReleaseEvaluation:
    """Derive all offline predictions, metrics, gates, and visible failure categories."""

    if len(cases) != 26 or len(records) != 26:
        raise ValueError("final v1.1 evaluation requires exactly 26 cases and records")
    if tuple(record.case_id for record in records) != tuple(case.case_id for case in cases):
        raise ValueError("prediction records differ from frozen case order")

    predictions: list[V11EvaluationPrediction] = []
    failures: list[V11FailedSample] = []
    for case, record in zip(cases, records, strict=True):
        prediction, technical = derive_v1_1_offline_prediction(case, record)
        predictions.append(prediction)
        categories = _failure_categories(case, prediction, technical)
        if categories:
            failures.append(V11FailedSample(case_id=case.case_id, categories=categories))

    metrics = v1_1_metrics(cases, predictions)
    gates = apply_v1_1_release_gates(metrics, thresholds)
    status: Literal["PASS", "FAIL"] = (
        "PASS" if snapshot_complete and gates.status == "PASS" else "FAIL"
    )
    return V11ReleaseEvaluation(
        status=status,
        snapshot_complete=snapshot_complete,
        metrics=metrics,
        gates=gates,
        predictions=tuple(predictions),
        failed_samples=tuple(failures),
    )


def materialize_v1_1_release_evaluation(
    paths: V11ReleasePaths,
    evaluation: V11ReleaseEvaluation,
    provenance: V11ReleaseProvenance,
) -> V11ReleaseEvidenceManifest:
    """Persist derived predictions, metrics, manifest, and reports without overwriting."""

    outputs = (
        paths.derived_predictions,
        paths.metrics,
        paths.release_manifest,
        paths.result_report,
        paths.docs_report,
    )
    if any(os.path.lexists(path) for path in outputs):
        raise FileExistsError("final v1.1 release-evaluation output already exists")

    prediction_bytes = b"".join(
        canonical_json_bytes(prediction.model_dump(mode="json"))
        for prediction in evaluation.predictions
    )
    metrics_payload = {
        "schema_version": "v1_1_final_metrics_v1",
        "status": evaluation.status,
        "snapshot_complete": evaluation.snapshot_complete,
        "metrics": evaluation.metrics.model_dump(mode="json"),
        "gates": evaluation.gates.model_dump(mode="json"),
        "failed_samples": [sample.model_dump(mode="json") for sample in evaluation.failed_samples],
        "threshold_modified_after_evaluation": False,
    }
    metrics_bytes = canonical_json_bytes(metrics_payload)
    manifest = V11ReleaseEvidenceManifest(
        status=evaluation.status,
        provenance=provenance,
        derived_predictions_sha256=sha256_bytes(prediction_bytes),
        metrics_sha256=sha256_bytes(metrics_bytes),
        failed_sample_count=len(evaluation.failed_samples),
    )
    report_bytes = _release_report(evaluation, provenance).encode("utf-8")

    write_exclusive(paths.derived_predictions, prediction_bytes)
    write_exclusive(paths.metrics, metrics_bytes)
    write_exclusive(
        paths.release_manifest,
        canonical_json_bytes(manifest.model_dump(mode="json")),
    )
    write_exclusive(paths.result_report, report_bytes)
    write_exclusive(paths.docs_report, report_bytes)
    return manifest


def evaluate_frozen_v1_1_release(
    governed: V11ArtifactPaths,
    outputs: V11ReleasePaths,
    *,
    evaluated_at: datetime | None = None,
) -> V11ReleaseEvidenceManifest:
    """Validate frozen/captured identities, evaluate offline, and write final evidence."""

    required = (
        (governed.frozen_dataset, "frozen dataset"),
        (governed.freeze_manifest, "freeze manifest"),
        (governed.predictions, "production prediction snapshot"),
        (governed.snapshot_manifest, "prediction snapshot manifest"),
        (governed.corrected_candidate, "corrected candidate"),
        (governed.review_packet, "human review packet"),
        (governed.threshold_spec, "threshold specification"),
        (governed.threshold_approval, "threshold approval"),
    )
    for path, name in required:
        if not path.is_file():
            raise FileNotFoundError(f"required {name} is missing: {path}")

    frozen_bytes = governed.frozen_dataset.read_bytes()
    freeze_manifest_bytes = governed.freeze_manifest.read_bytes()
    prediction_bytes = governed.predictions.read_bytes()
    prediction_manifest_bytes = governed.snapshot_manifest.read_bytes()
    freeze_manifest = V11FrozenDatasetManifest.model_validate_json(freeze_manifest_bytes)
    snapshot_manifest = V11PredictionSnapshotManifest.model_validate_json(prediction_manifest_bytes)
    if freeze_manifest_bytes != canonical_json_bytes(freeze_manifest.model_dump(mode="json")):
        raise ValueError("freeze manifest bytes are not canonical")
    if prediction_manifest_bytes != canonical_json_bytes(snapshot_manifest.model_dump(mode="json")):
        raise ValueError("prediction snapshot manifest bytes are not canonical")
    if sha256_bytes(frozen_bytes) != freeze_manifest.frozen_dataset_sha256:
        raise ValueError("frozen dataset checksum differs from its manifest")
    if sha256_bytes(prediction_bytes) != snapshot_manifest.predictions_sha256:
        raise ValueError("production prediction checksum differs from its manifest")
    if snapshot_manifest.freeze_manifest_sha256 != sha256_bytes(freeze_manifest_bytes):
        raise ValueError("prediction snapshot binds a different freeze manifest")

    identity_pairs = (
        (
            snapshot_manifest.frozen_dataset_sha256,
            freeze_manifest.frozen_dataset_sha256,
            "frozen dataset",
        ),
        (
            snapshot_manifest.corrected_candidate_sha256,
            freeze_manifest.corrected_candidate_sha256,
            "corrected candidate",
        ),
        (
            snapshot_manifest.review_packet_sha256,
            freeze_manifest.review_packet_sha256,
            "review packet",
        ),
        (
            snapshot_manifest.threshold_spec_sha256,
            freeze_manifest.threshold_spec_sha256,
            "threshold specification",
        ),
        (
            snapshot_manifest.threshold_approval_sha256,
            freeze_manifest.threshold_approval_sha256,
            "threshold approval",
        ),
        (snapshot_manifest.git_commit_sha, freeze_manifest.git_commit_sha, "Git commit"),
    )
    for actual, expected, name in identity_pairs:
        if actual != expected:
            raise ValueError(f"prediction snapshot binds a different {name}")

    governed_payloads = (
        (
            governed.corrected_candidate.read_bytes(),
            freeze_manifest.corrected_candidate_sha256,
            "corrected candidate",
        ),
        (
            governed.review_packet.read_bytes(),
            freeze_manifest.review_packet_sha256,
            "review packet",
        ),
        (
            governed.threshold_spec.read_bytes(),
            freeze_manifest.threshold_spec_sha256,
            "threshold specification",
        ),
        (
            governed.threshold_approval.read_bytes(),
            freeze_manifest.threshold_approval_sha256,
            "threshold approval",
        ),
    )
    for payload, expected, name in governed_payloads:
        if sha256_bytes(payload) != expected:
            raise ValueError(f"{name} changed after freeze")
    for relative in V11_FREEZE_CODE_RELATIVE_PATHS:
        if (
            sha256_bytes((governed.repo_root / relative).read_bytes())
            != (freeze_manifest.code_file_sha256[relative])
        ):
            raise ValueError(f"frozen evaluation code changed: {relative}")

    state = inspect_repository_state(governed.repo_root)
    if state.commit_sha != freeze_manifest.git_commit_sha:
        raise ValueError("Git commit changed after production capture")
    cases = load_v1_1_frozen_dataset(governed.frozen_dataset)
    records = load_v1_1_prediction_records(governed.predictions)
    if tuple(record.case_id for record in records) != tuple(case.case_id for case in cases):
        raise ValueError("prediction record order differs from the frozen dataset")
    threshold_spec = load_v1_1_threshold_spec(
        governed.threshold_spec,
        repo_root=governed.repo_root,
    )
    evaluation = build_v1_1_release_evaluation(
        cases,
        records,
        threshold_spec.thresholds,
        snapshot_complete=snapshot_manifest.status == "COMPLETE",
    )
    timestamp = evaluated_at or datetime.now().astimezone().replace(microsecond=0)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("evaluation timestamp must include a timezone")
    provenance = V11ReleaseProvenance(
        frozen_dataset_sha256=freeze_manifest.frozen_dataset_sha256,
        freeze_manifest_sha256=sha256_bytes(freeze_manifest_bytes),
        prediction_snapshot_sha256=snapshot_manifest.predictions_sha256,
        prediction_manifest_sha256=sha256_bytes(prediction_manifest_bytes),
        threshold_spec_sha256=freeze_manifest.threshold_spec_sha256,
        evaluation_spec_sha256=freeze_manifest.evaluation_spec_sha256,
        review_packet_sha256=freeze_manifest.review_packet_sha256,
        git_commit_sha=freeze_manifest.git_commit_sha,
        reviewed_at=freeze_manifest.reviewed_at,
        frozen_at=freeze_manifest.frozen_at,
        evaluated_at=timestamp,
    )
    return materialize_v1_1_release_evaluation(outputs, evaluation, provenance)


def _capture_error_code(record: V11CaseIntakePredictionRecord) -> CaseAnalysisErrorCode:
    reason = record.failure_reason.value if record.failure_reason is not None else ""
    try:
        return CaseAnalysisErrorCode(reason)
    except ValueError:
        return CaseAnalysisErrorCode.CASE_INTAKE_PROVIDER_ERROR


def _failure_categories(
    case: V11EvaluationCandidateCase,
    prediction: V11EvaluationPrediction,
    technical: tuple[str, ...],
) -> tuple[str, ...]:
    categories = list(technical)
    expected_signatures = Counter(
        (fact.fact_key, fact.fact_type, fact.raw_value) for fact in case.expected_case_facts
    )
    predicted_signatures = Counter(
        (fact.fact_key, fact.fact_type, fact.raw_value) for fact in prediction.case_facts
    )
    if expected_signatures != predicted_signatures:
        categories.append("FACT_SIGNATURE_MISMATCH")
    expected_spans = Counter(
        (
            fact.fact_key,
            fact.fact_type,
            fact.raw_value,
            fact.source_span.start_offset,
            fact.source_span.end_offset,
            fact.source_span.text,
        )
        for fact in case.expected_case_facts
    )
    predicted_spans = Counter(
        (
            fact.fact_key,
            fact.fact_type,
            fact.raw_value,
            fact.source_span.start_offset,
            fact.source_span.end_offset,
            fact.source_span.text,
        )
        for fact in prediction.case_facts
    )
    if expected_spans != predicted_spans:
        categories.append("SOURCE_SPAN_MISMATCH")
    if prediction.candidate_issue_codes != case.expected_candidate_issues:
        categories.append("CANDIDATE_ISSUE_MISMATCH")
    if prediction.refined_issues != case.expected_refined_issues:
        categories.append("REFINED_ISSUE_MISMATCH")
    if prediction.missing_fields != case.expected_missing_fields:
        categories.append("MISSING_FACT_MISMATCH")
    if prediction.question_fields != case.expected_question_fields:
        categories.append("CLARIFICATION_MISMATCH")
    if prediction.graph_status is not case.expected_graph_status:
        categories.append("GRAPH_STATUS_MISMATCH")
    graph_contract = v1_1_metrics((case,), (prediction,)).graph_state_contract_accuracy
    if graph_contract != 1.0:
        categories.append("GRAPH_STATE_CONTRACT_INVALID")
    return tuple(dict.fromkeys(categories))


def _release_report(
    evaluation: V11ReleaseEvaluation,
    provenance: V11ReleaseProvenance,
) -> str:
    metric_lines = "\n".join(
        f"- `{name}`: {value}" for name, value in evaluation.metrics.model_dump(mode="json").items()
    )
    gate_lines = "\n".join(
        f"- `{gate.metric}`: measured={gate.measured_value}, gate {gate.comparator} "
        f"{gate.threshold} — {'PASS' if gate.passed else 'FAIL'}"
        for gate in evaluation.gates.gates
    )
    failure_lines = (
        "\n".join(
            f"- `{sample.case_id}`: {', '.join(sample.categories)}"
            for sample in evaluation.failed_samples
        )
        or "- None"
    )
    limitation = (
        "Week 5 EvidencePlan and downstream legal decision execution are NOT part of v1.1 "
        "Week-4 release capability."
    )
    return (
        "# V1.1 Week-4 frozen release evaluation\n\n"
        f"Release gates: **{evaluation.status}**\n\n"
        "## Frozen identity\n\n"
        f"- Frozen dataset SHA-256: `{provenance.frozen_dataset_sha256}`\n"
        f"- Production prediction SHA-256: `{provenance.prediction_snapshot_sha256}`\n"
        f"- Threshold specification SHA-256: `{provenance.threshold_spec_sha256}`\n"
        f"- Evaluation specification SHA-256: `{provenance.evaluation_spec_sha256}`\n"
        f"- Human-review evidence SHA-256: `{provenance.review_packet_sha256}`\n"
        f"- Git commit: `{provenance.git_commit_sha}`\n"
        f"- Reviewed at: `{provenance.reviewed_at.isoformat()}`\n"
        f"- Frozen at: `{provenance.frozen_at.isoformat()}`\n"
        f"- Evaluated at: `{provenance.evaluated_at.isoformat()}`\n\n"
        "## Metrics\n\n"
        f"{metric_lines}\n\n"
        "## Pre-registered gates\n\n"
        f"{gate_lines}\n\n"
        "Threshold modified after evaluation: **NO**\n\n"
        "## Failed samples and typed categories\n\n"
        f"{failure_lines}\n\n"
        "## Architecture scope and limitation\n\n"
        "V1.1 Week 4 covers production Case Intake extraction followed by deterministic Missing "
        "Facts, Clarification, Refined Issues, and finite CaseGraph evaluation. It does not make "
        "downstream provider calls.\n\n"
        f"{limitation}\n"
    )
