from __future__ import annotations

import importlib
import importlib.util
import json
import subprocess
from datetime import datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from pydantic import SecretStr, ValidationError

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.decision_support.models import (
    CaseIntakeInput,
    CaseIntakeResult,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_capture import (
    V11RuntimeCase,
)

PROJECT_ROOT = Path(__file__).parents[3]


def rc2_module() -> ModuleType:
    try:
        return importlib.import_module(
            "vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2"
        )
    except ModuleNotFoundError:
        pytest.fail("the dedicated RC2 registration module is missing")


def configured_settings(*, model: str = "mistral-small-2603") -> Settings:
    return Settings(
        openai_api_key=SecretStr("test-secret"),
        openai_base_url="https://api.mistral.ai/v1",
        llm_provider="openai",
        llm_model=model,
        llm_timeout_seconds=60,
        llm_max_retries=2,
        agent_structured_output_max_retries=2,
    )


def initialize_git_repository(repo_root: Path) -> str:
    subprocess.run(["git", "init", "--quiet", str(repo_root)], check=True)
    subprocess.run(
        ["git", "-C", str(repo_root), "config", "user.name", "RC2 Test"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_root), "config", "user.email", "rc2@example.invalid"],
        check=True,
    )
    (repo_root / "capture_runner.py").write_text("# registered code\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(repo_root), "add", "capture_runner.py"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_root), "commit", "--quiet", "-m", "register code"],
        check=True,
    )
    return subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def commit_paths(repo_root: Path, *relative_paths: str) -> str:
    subprocess.run(
        ["git", "-C", str(repo_root), "add", "--", *relative_paths],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_root), "commit", "--quiet", "-m", "record manifest"],
        check=True,
    )
    return subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_registered_git_identity_accepts_one_manifest_only_child(tmp_path: Path) -> None:
    module = rc2_module()
    registered_sha = initialize_git_repository(tmp_path)
    manifest_path = module.RC2ArtifactPaths.from_root(tmp_path).capture_manifest
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text("{}\n", encoding="utf-8")
    current_sha = commit_paths(
        tmp_path,
        manifest_path.relative_to(tmp_path).as_posix(),
    )

    module.require_registered_git_identity(
        tmp_path,
        registered_sha=registered_sha,
        current_sha=current_sha,
        capture_manifest=manifest_path,
    )


def test_registered_git_identity_rejects_child_with_unrelated_path(tmp_path: Path) -> None:
    module = rc2_module()
    registered_sha = initialize_git_repository(tmp_path)
    manifest_path = module.RC2ArtifactPaths.from_root(tmp_path).capture_manifest
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text("{}\n", encoding="utf-8")
    (tmp_path / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")
    current_sha = commit_paths(
        tmp_path,
        manifest_path.relative_to(tmp_path).as_posix(),
        "unexpected.txt",
    )

    with pytest.raises(ValueError, match="registered Git identity"):
        module.require_registered_git_identity(
            tmp_path,
            registered_sha=registered_sha,
            current_sha=current_sha,
            capture_manifest=manifest_path,
        )


def test_load_rc2_capture_plan_rejects_unrelated_commit_after_registration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = rc2_module()
    registered_sha = initialize_git_repository(tmp_path)
    paths = module.RC2ArtifactPaths.from_root(tmp_path)
    payload = {**manifest_payload(tmp_path), "current_git_sha": registered_sha}
    manifest = module.RC2CaptureManifest.model_validate(payload)
    paths.capture_manifest.parent.mkdir(parents=True)
    paths.capture_manifest.write_bytes(
        module.canonical_json_bytes(manifest.model_dump(mode="json"))
    )
    (tmp_path / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")
    commit_paths(
        tmp_path,
        paths.capture_manifest.relative_to(tmp_path).as_posix(),
        "unexpected.txt",
    )
    plan = module.RC2CapturePlan(manifest=manifest, runtime_cases=())
    monkeypatch.setattr(module, "_build_rc2_capture_plan", lambda *args, **kwargs: plan)

    with pytest.raises(ValueError, match="registered Git identity"):
        module.load_rc2_capture_plan(
            paths,
            configured_settings(),
            project_author_name="mrhao165-del",
        )


def test_registered_worktree_identity_rejects_extra_untracked_path(tmp_path: Path) -> None:
    module = rc2_module()
    allowed_path = "docs/superpowers/plans/user-plan.md"
    payload = {
        **manifest_payload(tmp_path),
        "tracked_worktree_dirty": False,
        "untracked_worktree_paths": [allowed_path],
    }
    manifest = module.RC2CaptureManifest.model_validate(payload)
    state = module.RepositoryState(
        commit_sha="e" * 40,
        tracked_dirty=False,
        untracked_paths=(allowed_path, "unexpected.txt"),
        git_top_level=tmp_path,
    )

    with pytest.raises(ValueError, match="registered worktree identity"):
        module.require_registered_worktree_identity(state, manifest)


def manifest_payload(tmp_path: Path) -> dict[str, object]:
    paths = rc2_module().RC2ArtifactPaths.from_root(tmp_path)
    return {
        "release_candidate": "v1_1_rc2",
        "parent": "v1_1_rc1",
        "parent_result": "FAILED_PROVIDER_CAPTURE",
        "frozen_dataset_path": "data/evaluation/decision_support/v1_1/v1_1_evaluation_frozen.jsonl",
        "frozen_dataset_sha256": "a" * 64,
        "case_count": 26,
        "human_review_path": (
            "evaluation/review/decision_support/v1_1/"
            "v1_1_human_review_packet_corrected_prefilled_for_human_review.csv"
        ),
        "human_review_sha256": "b" * 64,
        "human_review_pass_count": 26,
        "human_review_unresolved_count": 0,
        "threshold_path": "data/evaluation/decision_support/v1_1/v1_1_proposed_thresholds.json",
        "threshold_sha256": "c" * 64,
        "threshold_approval_valid": True,
        "dataset_bytes_unchanged": True,
        "expected_labels_unchanged": True,
        "thresholds_unchanged": True,
        "remediation_commit_sha": "6b846de192aff26ae8ac1f84e12365868f9c3971",
        "current_git_sha": "d" * 40,
        "worktree_clean": False,
        "tracked_worktree_dirty": False,
        "untracked_worktree_paths": [],
        "capture_runner_code_sha256": "e" * 64,
        "capture_adapter_code_sha256": "f" * 64,
        "extractor_implementation_sha256": "1" * 64,
        "transport_schema_identity": (
            "vietnamese_labor_law_assistant.decision_support.intake._ProviderCaseIntakeResult"
        ),
        "transport_schema_sha256": "2" * 64,
        "canonical_schema_identity": (
            "vietnamese_labor_law_assistant.decision_support.models.CaseIntakeResult"
        ),
        "canonical_schema_version": "CHECKSUM_BOUND_UNVERSIONED",
        "canonical_schema_sha256": "3" * 64,
        "prompt_sha256": "4" * 64,
        "generation_config": rc2_module().RC2GenerationConfig.from_settings(configured_settings()),
        "paths": rc2_module().RC2RegisteredPaths.from_artifact_paths(paths),
        "label_isolation": True,
        "expected_labels_visible_to_extractor": False,
        "thresholds_visible_to_extractor": False,
        "reviewer_data_visible_to_extractor": False,
        "production_extractor_implementation_changed": True,
        "legal_semantics_changed": False,
        "canonical_case_intake_result_changed": False,
        "source_span_invariant_changed": False,
        "prompt_semantic_policy_changed": False,
        "metric_based_prompt_tuning_performed": False,
        "successful_rc1_predictions_existed": False,
        "capture_started_at": None,
        "capture_completed_at": None,
        "prediction_checksum": None,
        "status": "PREPARED_NOT_CAPTURED",
    }


def test_rc2_paths_are_distinct_and_do_not_create_future_outputs(tmp_path: Path) -> None:
    module = rc2_module()

    paths = module.RC2ArtifactPaths.from_root(tmp_path)

    assert paths.output_directory == (
        tmp_path.resolve() / "evaluation/results/decision_support/v1_1/rc2"
    )
    assert paths.capture_manifest.name == "rc2_capture_manifest.json"
    assert paths.predictions.name == "rc2_production_predictions.jsonl"
    assert paths.prediction_metadata.name == "rc2_prediction_metadata.json"
    assert paths.metrics.name == "rc2_metrics.json"
    assert paths.failed_samples.name == "rc2_failed_samples.jsonl"
    assert paths.release_report.name == "rc2_release_evaluation.md"
    assert not paths.output_directory.exists()


def test_rc2_generation_config_requires_exact_pinned_values() -> None:
    module = rc2_module()

    config = module.RC2GenerationConfig.from_settings(configured_settings())

    assert config.model == "mistral-small-2603"
    assert config.model_alias_used is False
    assert config.temperature == 0
    assert config.timeout_seconds == 60
    assert config.sdk_max_retries == 2
    assert config.structured_max_retries == 2
    assert config.concurrency == 1
    assert config.inter_case_pacing_seconds == 1.0

    with pytest.raises(ValueError, match="exact RC2 model"):
        module.RC2GenerationConfig.from_settings(configured_settings(model="mistral-small-latest"))


def test_prepared_manifest_requires_null_capture_fields(tmp_path: Path) -> None:
    module = rc2_module()
    payload = manifest_payload(tmp_path)

    manifest = module.RC2CaptureManifest.model_validate(payload)

    assert manifest.status == "PREPARED_NOT_CAPTURED"
    assert manifest.capture_started_at is None
    assert manifest.capture_completed_at is None
    assert manifest.prediction_checksum is None
    with pytest.raises(ValidationError):
        module.RC2CaptureManifest.model_validate(
            {**payload, "capture_started_at": datetime.now().astimezone()}
        )


def test_manifest_and_all_future_outputs_are_write_once(tmp_path: Path) -> None:
    module = rc2_module()
    paths = module.RC2ArtifactPaths.from_root(tmp_path)
    manifest = module.RC2CaptureManifest.model_validate(manifest_payload(tmp_path))

    module.write_rc2_manifest(paths, manifest)

    assert paths.capture_manifest.exists()
    assert not paths.predictions.exists()
    assert not paths.prediction_metadata.exists()
    assert not paths.metrics.exists()
    assert not paths.failed_samples.exists()
    assert not paths.release_report.exists()
    with pytest.raises(FileExistsError, match="RC2 artifact already exists"):
        module.write_rc2_manifest(paths, manifest)
    paths.predictions.write_bytes(b"claimed")
    with pytest.raises(FileExistsError, match="RC2 artifact already exists"):
        module.require_rc2_future_outputs_absent(paths)


@pytest.mark.asyncio
async def test_runtime_executor_is_label_isolated_sequential_and_paced() -> None:
    module = rc2_module()
    runtime_cases = tuple(
        V11RuntimeCase(
            case_id=f"synthetic-{index}",
            case_input=CaseIntakeInput(
                source_text=f"Nội dung tổng hợp {index}.",
                source_ref=f"user_message:synthetic-{index}",
            ),
        )
        for index in (1, 2)
    )
    observed: list[tuple[str, object]] = []

    class Extractor:
        async def extract(self, case_input: CaseIntakeInput) -> CaseIntakeResult:
            observed.append(("extract", case_input))
            return CaseIntakeResult(facts=[], candidate_issues=[])

    async def pace(seconds: float) -> None:
        observed.append(("pace", seconds))

    records = await module.execute_rc2_runtime_cases(
        runtime_cases,
        Extractor(),
        pacing_seconds=1.0,
        sleep=pace,
    )

    assert [item[0] for item in observed] == ["extract", "pace", "extract"]
    assert type(observed[0][1]) is CaseIntakeInput
    assert type(observed[2][1]) is CaseIntakeInput
    assert observed[1] == ("pace", 1.0)
    assert [record.case_id for record in records] == ["synthetic-1", "synthetic-2"]
    serialized = "".join(record.model_dump_json() for record in records)
    for prohibited in (
        "expected_case_facts",
        "expected_candidate_issues",
        "expected_refined_issues",
        "expected_missing_fields",
        "reviewer_notes_reasoning",
        "review_decision",
        "thresholds",
    ):
        assert prohibited not in serialized


def test_runtime_executor_rejects_non_runtime_case_objects() -> None:
    module = rc2_module()

    with pytest.raises(TypeError, match="exact V11RuntimeCase"):
        module.require_label_isolated_runtime_cases((object(),))


def test_prediction_metadata_rejects_inconsistent_status_and_counts() -> None:
    module = rc2_module()
    now = datetime.now().astimezone()

    with pytest.raises(ValidationError, match="prediction counts must total 26"):
        module.RC2PredictionMetadata(
            status="FAILED",
            started_at=now,
            completed_at=now,
            predictions_sha256="a" * 64,
            success_count=1,
            failure_count=1,
            capture_manifest_sha256="b" * 64,
        )
    with pytest.raises(ValidationError, match="COMPLETE requires 26 successful"):
        module.RC2PredictionMetadata(
            status="COMPLETE",
            started_at=now,
            completed_at=now,
            predictions_sha256="a" * 64,
            success_count=25,
            failure_count=1,
            capture_manifest_sha256="b" * 64,
        )


def test_prepare_rc2_capture_binds_exact_governance_and_remediation_identity() -> None:
    module = rc2_module()
    paths = module.RC2ArtifactPaths.from_root(PROJECT_ROOT)

    if paths.capture_manifest.exists():
        plan = module.load_rc2_capture_plan(
            paths,
            configured_settings(),
            project_author_name="mrhao165-del",
        )
    else:
        plan = module.prepare_rc2_capture(
            paths,
            configured_settings(),
            project_author_name="mrhao165-del",
        )

    manifest = plan.manifest
    assert manifest.release_candidate == "v1_1_rc2"
    assert manifest.parent == "v1_1_rc1"
    assert manifest.parent_result == "FAILED_PROVIDER_CAPTURE"
    assert manifest.remediation_commit_sha == ("6b846de192aff26ae8ac1f84e12365868f9c3971")
    assert manifest.worktree_clean is (
        not manifest.tracked_worktree_dirty and not manifest.untracked_worktree_paths
    )
    assert manifest.frozen_dataset_sha256 == (
        "5f726893300176d1c3b4e915253682b70ef343376903e3e7e243d838e245c29e"
    )
    assert manifest.threshold_sha256 == (
        "373aa3d4512e6d5cb75e7bcba3dbcc6ef2541ced8603b67b18e6bcd80b31ad5c"
    )
    assert manifest.human_review_sha256 == (
        "bae5fe6826c0d92ec4f85f433e7fdd640bc182bcaefaaf93ee3d4d0b1a2068d6"
    )
    assert manifest.human_review_pass_count == 26
    assert manifest.human_review_unresolved_count == 0
    assert manifest.threshold_approval_valid is True
    assert manifest.prompt_sha256 == (
        "64e75d2491f1832bd1aabbb92fea58b786965912d7f1fb588bd946327edae935"
    )
    assert len(manifest.extractor_implementation_sha256) == 64
    assert len(manifest.transport_schema_sha256) == 64
    assert len(manifest.canonical_schema_sha256) == 64
    assert len(plan.runtime_cases) == 26
    assert all(type(runtime) is V11RuntimeCase for runtime in plan.runtime_cases)
    assert all(
        set(runtime.model_dump(mode="json")) == {"case_id", "case_input"}
        for runtime in plan.runtime_cases
    )


def load_capture_script() -> ModuleType:
    path = PROJECT_ROOT / "scripts/capture_decision_support_v1_1_rc2.py"
    specification = importlib.util.spec_from_file_location("rc2_capture_script", path)
    if specification is None or specification.loader is None:
        pytest.fail("the RC2 capture adapter is missing")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_rc2_capture_adapter_defaults_to_offline_preparation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    script = load_capture_script()
    calls: list[str] = []
    manifest = rc2_module().RC2CaptureManifest.model_validate(manifest_payload(PROJECT_ROOT))
    plan = SimpleNamespace(manifest=manifest, runtime_cases=tuple())
    monkeypatch.setattr(script, "get_settings", lambda: configured_settings())
    monkeypatch.setattr(
        script,
        "prepare_rc2_capture",
        lambda *args, **kwargs: calls.append("prepare") or plan,
    )
    monkeypatch.setattr(
        script,
        "write_rc2_manifest",
        lambda *args, **kwargs: calls.append("write"),
    )
    monkeypatch.setattr(
        script,
        "capture_rc2_predictions",
        lambda *args, **kwargs: calls.append("live"),
    )

    assert (
        script.main(
            [
                "--repo-root",
                str(tmp_path),
                "--project-author-name",
                "mrhao165-del",
            ]
        )
        == 0
    )

    report = json.loads(capsys.readouterr().out)
    assert calls == ["prepare"]
    assert report["status"] == "PREPARED_NOT_WRITTEN"
    assert report["provider_calls_performed"] == 0


@pytest.mark.parametrize("mode", ("--register", "--live"))
def test_rc2_capture_adapter_requires_confirmation_before_settings(
    mode: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = load_capture_script()
    calls: list[str] = []
    monkeypatch.setattr(script, "get_settings", lambda: calls.append("settings"))

    with pytest.raises(SystemExit):
        script.main(["--project-author-name", "mrhao165-del", mode])

    assert calls == []
