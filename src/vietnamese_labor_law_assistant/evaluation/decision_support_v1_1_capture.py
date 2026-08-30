"""Label-isolated preflight contracts for the governed v1.1 prediction capture."""

from __future__ import annotations

from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.decision_support.models import CaseIntakeInput
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1 import (
    candidate_quality_report,
    load_v1_1_candidate,
    validate_v1_1_review_packet,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_approval import (
    validate_v1_1_threshold_approval,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_artifacts import (
    V11_FREEZE_CODE_RELATIVE_PATHS,
    RepositoryState,
    V11ArtifactPaths,
    canonical_json_bytes,
    inspect_repository_state,
    require_capture_repository_state,
    sha256_bytes,
    sha256_file,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_freeze import (
    V11FrozenDatasetManifest,
    V11FrozenEvaluationCase,
    load_v1_1_frozen_dataset,
    prepare_v1_1_freeze,
)

_EXTRACTOR_CLASS = (
    "vietnamese_labor_law_assistant.decision_support.intake.OpenAIStructuredCaseIntakeExtractor"
)
_INTAKE_IMPLEMENTATION_PATH = "src/vietnamese_labor_law_assistant/decision_support/intake.py"
_RESPONSE_SCHEMA_IDENTITY = (
    "vietnamese_labor_law_assistant.decision_support.models.CaseIntakeResult"
)


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
    _require_capture_inputs(paths)
    generation_settings = _non_secret_generation_settings(settings)

    manifest = V11FrozenDatasetManifest.model_validate_json(
        paths.freeze_manifest.read_text(encoding="utf-8")
    )
    if paths.freeze_manifest.read_bytes() != canonical_json_bytes(manifest.model_dump(mode="json")):
        raise ValueError("freeze manifest bytes are not canonical")

    state = repository_state or inspect_repository_state(paths.repo_root)
    require_capture_repository_state(state, paths)
    if state.commit_sha != manifest.git_commit_sha:
        raise ValueError("Git source commit changed after the governed freeze")

    _require_checksum(
        paths.corrected_candidate,
        manifest.corrected_candidate_sha256,
        "corrected candidate checksum changed",
    )
    _require_checksum(
        paths.review_packet,
        manifest.review_packet_sha256,
        "human review checksum changed",
    )
    _require_checksum(
        paths.threshold_spec,
        manifest.threshold_spec_sha256,
        "threshold specification checksum changed",
    )
    _require_checksum(
        paths.threshold_approval,
        manifest.threshold_approval_sha256,
        "threshold approval checksum changed",
    )
    _require_checksum(
        paths.frozen_dataset,
        manifest.frozen_dataset_sha256,
        "frozen dataset checksum changed",
    )

    candidate_cases = load_v1_1_candidate(paths.corrected_candidate)
    quality = candidate_quality_report(candidate_cases)
    if (
        len(candidate_cases) != 26
        or quality.schema_validation != "PASS"
        or quality.prediction_label_leakage_case_ids
        or quality.prediction_label_leakage_assessment != "CHECKED_NO_PREDICTION_ARTIFACT_INPUT"
    ):
        raise ValueError("corrected candidate failed canonical capture validation")

    review = validate_v1_1_review_packet(
        candidate_cases,
        paths.review_packet,
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
    approval = validate_v1_1_threshold_approval(
        paths.threshold_spec,
        paths.threshold_approval,
        project_author_name=project_author_name,
        threshold_spec_identity=threshold_identity,
        repo_root=paths.repo_root,
    )
    if (
        not approval.policy_satisfied
        or approval.status != "PASS"
        or approval.approval_decision != "APPROVE_UNCHANGED"
        or not approval.thresholds_unchanged
        or not approval.registration_approval_state_valid
    ):
        raise ValueError("threshold approval state is invalid")

    frozen_cases = load_v1_1_frozen_dataset(paths.frozen_dataset)
    ordered_case_ids = [case.case_id for case in frozen_cases]
    ordered_case_ids_sha256 = sha256_bytes(canonical_json_bytes(ordered_case_ids))
    if ordered_case_ids_sha256 != manifest.ordered_case_ids_sha256:
        raise ValueError("ordered frozen case IDs changed")
    if ordered_case_ids != sorted(case.case_id for case in candidate_cases):
        raise ValueError("frozen case IDs differ from the corrected candidate")

    _require_code_identity(paths, manifest)
    regenerated = prepare_v1_1_freeze(
        paths,
        project_author_name=project_author_name,
        repository_state=RepositoryState(
            commit_sha=manifest.git_commit_sha,
            tracked_dirty=False,
            untracked_paths=(),
        ),
        frozen_at=manifest.frozen_at,
    )
    if regenerated.dataset_bytes != paths.frozen_dataset.read_bytes():
        raise ValueError("frozen dataset differs from the governed freeze inputs")
    if regenerated.manifest != manifest:
        raise ValueError("freeze manifest differs from revalidated governance state")

    runtime_cases = tuple(project_runtime_case(case) for case in frozen_cases)
    return V11CapturePlan(
        runtime_cases=runtime_cases,
        dataset_id=manifest.dataset_id,
        dataset_version=manifest.dataset_version,
        case_count=manifest.case_count,
        review_status=manifest.review_status,
        threshold_approval_decision=manifest.threshold_approval_decision,
        frozen_dataset_sha256=manifest.frozen_dataset_sha256,
        freeze_manifest_sha256=sha256_file(paths.freeze_manifest),
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


def _require_canonical_paths(paths: V11ArtifactPaths) -> None:
    expected = V11ArtifactPaths.from_root(paths.repo_root)
    if paths != expected:
        raise ValueError("capture paths differ from the canonical v1.1 artifact contract")


def _require_no_existing_capture_artifact(paths: V11ArtifactPaths) -> None:
    for path in (paths.capture_intent, paths.predictions, paths.snapshot_manifest):
        if path.exists():
            raise FileExistsError(f"capture artifact already exists: {path}")


def _require_capture_inputs(paths: V11ArtifactPaths) -> None:
    for path in (
        paths.corrected_candidate,
        paths.review_packet,
        paths.threshold_spec,
        paths.threshold_approval,
        paths.frozen_dataset,
        paths.freeze_manifest,
    ):
        if not path.is_file():
            raise FileNotFoundError(f"required capture preflight artifact is missing: {path}")


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
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("provider base URL must not embed credentials")

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


def _require_checksum(path: Path, expected: str, error: str) -> None:
    if sha256_file(path) != expected:
        raise ValueError(error)


def _require_code_identity(
    paths: V11ArtifactPaths,
    manifest: V11FrozenDatasetManifest,
) -> None:
    if set(manifest.code_file_sha256) != set(V11_FREEZE_CODE_RELATIVE_PATHS):
        raise ValueError("freeze manifest code-file identity set changed")
    for relative_path in V11_FREEZE_CODE_RELATIVE_PATHS:
        code_path = paths.repo_root / relative_path
        if (
            not code_path.is_file()
            or sha256_file(code_path) != manifest.code_file_sha256[relative_path]
        ):
            raise ValueError(f"code file checksum changed: {relative_path}")
