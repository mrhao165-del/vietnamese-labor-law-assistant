from __future__ import annotations

import csv
import json
import os
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import SecretStr

import vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_capture as capture_module
from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_artifacts import (
    V11_FREEZE_CODE_RELATIVE_PATHS,
    RepositoryState,
    V11ArtifactPaths,
    canonical_json_bytes,
    sha256_file,
    write_exclusive,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_capture import (
    V11CapturePlan,
    preflight_v1_1_capture,
    project_runtime_case,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_freeze import (
    V11FrozenEvaluationCase,
    load_v1_1_frozen_dataset,
    prepare_v1_1_freeze,
)

PROJECT_ROOT = Path(__file__).parents[3]
FROZEN_AT = datetime(2026, 8, 30, 21, 0, tzinfo=timezone(timedelta(hours=7)))
CLEAN_STATE = RepositoryState(commit_sha="b" * 40, tracked_dirty=False, untracked_paths=())
WEEK3_SPEC_RELATIVE_PATH = Path("data/evaluation/decision_support/v1_1/week3_evaluation_spec.json")


def copy_governed_inputs(tmp_path: Path) -> V11ArtifactPaths:
    source = V11ArtifactPaths.from_root(PROJECT_ROOT)
    target = V11ArtifactPaths.from_root(tmp_path)
    for name in (
        "corrected_candidate",
        "review_packet",
        "threshold_spec",
        "threshold_approval",
    ):
        source_path = getattr(source, name)
        target_path = getattr(target, name)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, target_path)
    week3_target = target.repo_root / WEEK3_SPEC_RELATIVE_PATH
    week3_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PROJECT_ROOT / WEEK3_SPEC_RELATIVE_PATH, week3_target)
    return target


def configured_settings(secret: str = "test-secret") -> Settings:
    return Settings(
        openai_api_key=SecretStr(secret),
        llm_model="test-production-model",
        llm_provider="openai",
        llm_timeout_seconds=60,
        llm_max_retries=2,
        agent_structured_output_max_retries=2,
    )


def prepare_capture_paths(tmp_path: Path) -> V11ArtifactPaths:
    paths = copy_governed_inputs(tmp_path)
    for relative in V11_FREEZE_CODE_RELATIVE_PATHS:
        source = PROJECT_ROOT / relative
        target = paths.repo_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    bundle = prepare_v1_1_freeze(
        paths,
        project_author_name="mrhao165-del",
        repository_state=CLEAN_STATE,
        frozen_at=FROZEN_AT,
    )
    write_exclusive(paths.frozen_dataset, bundle.dataset_bytes)
    write_exclusive(
        paths.freeze_manifest,
        canonical_json_bytes(bundle.manifest.model_dump(mode="json")),
    )
    return paths


def capture_repository_state(paths: V11ArtifactPaths) -> RepositoryState:
    return RepositoryState(
        commit_sha="b" * 40,
        tracked_dirty=False,
        untracked_paths=(
            paths.frozen_dataset.relative_to(paths.repo_root).as_posix(),
            paths.freeze_manifest.relative_to(paths.repo_root).as_posix(),
        ),
        git_top_level=paths.repo_root,
    )


@pytest.fixture
def captured_paths(tmp_path: Path) -> V11ArtifactPaths:
    return prepare_capture_paths(tmp_path)


@pytest.fixture
def frozen_case(captured_paths: V11ArtifactPaths) -> V11FrozenEvaluationCase:
    return load_v1_1_frozen_dataset(captured_paths.frozen_dataset)[0]


@pytest.fixture
def ready_capture(
    captured_paths: V11ArtifactPaths,
) -> tuple[V11ArtifactPaths, V11CapturePlan, Settings]:
    settings = configured_settings()
    plan = preflight_v1_1_capture(
        captured_paths,
        settings,
        project_author_name="mrhao165-del",
        repository_state=capture_repository_state(captured_paths),
    )
    return captured_paths, plan, settings


def governed_capture_fixture(
    tmp_path: Path,
    mutation: str,
) -> tuple[V11ArtifactPaths, Settings, RepositoryState]:
    paths = prepare_capture_paths(tmp_path)
    state = capture_repository_state(paths)
    checksum_targets = {
        "candidate_checksum": paths.corrected_candidate,
        "review_checksum": paths.review_packet,
        "threshold_checksum": paths.threshold_spec,
        "approval_checksum": paths.threshold_approval,
        "frozen_checksum": paths.frozen_dataset,
    }
    if mutation in checksum_targets:
        with checksum_targets[mutation].open("ab") as handle:
            handle.write(b"\n")
    elif mutation == "git_commit":
        state = state.model_copy(update={"commit_sha": "c" * 40})
    elif mutation == "unrelated_worktree_path":
        state = state.model_copy(
            update={"untracked_paths": (*state.untracked_paths, "unrelated.txt")}
        )
    elif mutation == "capture_artifact_exists":
        write_exclusive(paths.capture_intent, b"{}\n")
    else:
        raise AssertionError(f"unknown mutation fixture: {mutation}")
    return paths, configured_settings(), state


def test_runtime_projection_contains_only_bookkeeping_and_production_input(
    frozen_case: V11FrozenEvaluationCase,
) -> None:
    runtime = project_runtime_case(frozen_case)
    assert set(runtime.model_dump()) == {"case_id", "case_input"}
    assert runtime.case_input.model_dump(mode="json") == {
        "source_text": frozen_case.raw_user_input,
        "source_ref": frozen_case.source_ref,
        "source_type": "USER_MESSAGE",
    }
    serialized = json.dumps(runtime.model_dump(mode="json"))
    for prohibited in (
        "expected_case_facts",
        "critical_fact_ids",
        "date_fact_ids",
        "money_fact_ids",
        "source_spans",
        "assertion_verification_labels",
        "expected_candidate_issues",
        "critical_issue_codes",
        "expected_missing_fields",
        "expected_refined_issues",
        "expected_refined_issue_status",
        "expected_clarification_behavior",
        "expected_graph_status",
        "reviewer_notes_reasoning",
        "review_decision",
        "thresholds",
    ):
        assert prohibited not in serialized


def test_preflight_binds_governance_and_never_serializes_secret(
    captured_paths: V11ArtifactPaths,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_settings_dump(*args: object, **kwargs: object) -> None:
        raise AssertionError("preflight must copy non-secret settings field-by-field")

    monkeypatch.setattr(Settings, "model_dump", reject_settings_dump)
    plan = preflight_v1_1_capture(
        captured_paths,
        configured_settings(secret="secret-value"),
        project_author_name="mrhao165-del",
        repository_state=capture_repository_state(captured_paths),
    )

    assert len(plan.runtime_cases) == 26
    assert plan.extractor_class.endswith(".OpenAIStructuredCaseIntakeExtractor")
    assert [case.case_id for case in plan.runtime_cases] == sorted(
        case.case_id for case in plan.runtime_cases
    )
    serialized = json.dumps(plan.model_dump(mode="json"))
    assert "OPENAI_API_KEY" not in serialized
    assert "secret-value" not in serialized
    assert plan.generation_settings.temperature == 0
    assert plan.generation_settings.nominal_parse_calls == 26
    assert plan.generation_settings.maximum_parse_invocations == 78
    assert plan.generation_settings.theoretical_maximum_http_attempts == 234


@pytest.mark.parametrize(
    ("mutation", "error"),
    (
        ("candidate_checksum", "corrected candidate checksum changed"),
        ("review_checksum", "human review checksum changed"),
        ("threshold_checksum", "threshold specification checksum changed"),
        ("approval_checksum", "threshold approval checksum changed"),
        ("frozen_checksum", "frozen dataset checksum changed"),
        ("git_commit", "Git source commit changed"),
        ("unrelated_worktree_path", "unexpected worktree delta"),
        ("capture_artifact_exists", "capture artifact already exists"),
    ),
)
def test_preflight_fails_closed_on_bound_state_change(
    tmp_path: Path,
    mutation: str,
    error: str,
) -> None:
    paths, settings, state = governed_capture_fixture(tmp_path, mutation)
    with pytest.raises((ValueError, FileExistsError), match=error):
        preflight_v1_1_capture(
            paths,
            settings,
            project_author_name="mrhao165-del",
            repository_state=state,
        )


def test_preflight_rejects_unconfigured_provider(captured_paths: V11ArtifactPaths) -> None:
    settings = Settings(
        openai_api_key=None,
        llm_model=None,
        llm_provider="openai",
    )

    with pytest.raises(ValueError, match="production LLM provider is not configured"):
        preflight_v1_1_capture(
            captured_paths,
            settings,
            project_author_name="mrhao165-del",
            repository_state=capture_repository_state(captured_paths),
        )


def test_preflight_rejects_gemini_without_required_base_url(
    captured_paths: V11ArtifactPaths,
) -> None:
    settings = Settings(
        openai_api_key=SecretStr("test-secret"),
        llm_model="gemini-test-model",
        llm_provider="gemini_openai_compatible",
        openai_base_url=None,
    )

    with pytest.raises(ValueError, match="Gemini provider requires a configured base URL"):
        preflight_v1_1_capture(
            captured_paths,
            settings,
            project_author_name="mrhao165-del",
            repository_state=capture_repository_state(captured_paths),
        )


@pytest.mark.parametrize(
    "base_url",
    (
        "https://user:secret-value@provider.test/v1",
        "https://provider.test/v1?key=secret-value",
        "https://provider.test/v1#token=secret-value",
    ),
)
def test_preflight_rejects_secret_bearing_base_url_components(
    captured_paths: V11ArtifactPaths,
    base_url: str,
) -> None:
    settings = Settings(
        openai_api_key=SecretStr("test-secret"),
        llm_model="test-production-model",
        llm_provider="openai",
        openai_base_url=base_url,
    )

    with pytest.raises(ValueError, match="provider base URL contains non-persistable components"):
        preflight_v1_1_capture(
            captured_paths,
            settings,
            project_author_name="mrhao165-del",
            repository_state=capture_repository_state(captured_paths),
        )


def test_preflight_rejects_changed_code_file_hash(captured_paths: V11ArtifactPaths) -> None:
    intake_path = captured_paths.repo_root / V11_FREEZE_CODE_RELATIVE_PATHS[0]
    with intake_path.open("ab") as handle:
        handle.write(b"\n")

    with pytest.raises(ValueError, match="code file checksum changed"):
        preflight_v1_1_capture(
            captured_paths,
            configured_settings(),
            project_author_name="mrhao165-del",
            repository_state=capture_repository_state(captured_paths),
        )


def test_preflight_revalidates_review_as_26_of_26_pass(
    captured_paths: V11ArtifactPaths,
) -> None:
    with captured_paths.review_packet.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fields = list(reader.fieldnames or ())
    rows[0]["review_decision"] = "NEEDS_REVISION"
    rows[0]["disagreement_correction"] = "Requires correction before capture."
    with captured_paths.review_packet.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    _update_manifest_checksum(
        captured_paths,
        "review_packet_sha256",
        sha256_file(captured_paths.review_packet),
    )

    with pytest.raises(ValueError, match="human review is no longer 26/26 PASS"):
        preflight_v1_1_capture(
            captured_paths,
            configured_settings(),
            project_author_name="mrhao165-del",
            repository_state=capture_repository_state(captured_paths),
        )


def test_preflight_revalidates_threshold_approval_state(
    captured_paths: V11ArtifactPaths,
) -> None:
    approval = json.loads(captured_paths.threshold_approval.read_text(encoding="utf-8"))
    approval["reviewer_name"] = "mrhao165-del"
    captured_paths.threshold_approval.write_text(
        json.dumps(approval, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _update_manifest_checksum(
        captured_paths,
        "threshold_approval_sha256",
        sha256_file(captured_paths.threshold_approval),
    )

    with pytest.raises(ValueError, match="threshold approval state is invalid"):
        preflight_v1_1_capture(
            captured_paths,
            configured_settings(),
            project_author_name="mrhao165-del",
            repository_state=capture_repository_state(captured_paths),
        )


def test_preflight_rejects_changed_ordered_case_identity(
    captured_paths: V11ArtifactPaths,
) -> None:
    rows = captured_paths.frozen_dataset.read_bytes().splitlines(keepends=True)
    captured_paths.frozen_dataset.write_bytes(b"".join(reversed(rows)))
    _update_manifest_checksum(
        captured_paths,
        "frozen_dataset_sha256",
        sha256_file(captured_paths.frozen_dataset),
    )

    with pytest.raises(ValueError, match="ordered frozen case IDs changed"):
        preflight_v1_1_capture(
            captured_paths,
            configured_settings(),
            project_author_name="mrhao165-del",
            repository_state=capture_repository_state(captured_paths),
        )


@pytest.mark.parametrize("artifact_name", ("capture_intent", "predictions", "snapshot_manifest"))
def test_preflight_rechecks_capture_artifact_absence_before_return(
    captured_paths: V11ArtifactPaths,
    artifact_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = capture_module.candidate_quality_report
    created = False

    def create_capture_artifact(cases: object) -> object:
        nonlocal created
        if not created:
            created = True
            write_exclusive(getattr(captured_paths, artifact_name), b"{}\n")
        return original(cases)  # type: ignore[arg-type]

    monkeypatch.setattr(capture_module, "candidate_quality_report", create_capture_artifact)

    with pytest.raises(FileExistsError, match="capture artifact already exists"):
        preflight_v1_1_capture(
            captured_paths,
            configured_settings(),
            project_author_name="mrhao165-del",
            repository_state=capture_repository_state(captured_paths),
        )


@pytest.mark.parametrize("artifact_name", ("capture_intent", "predictions", "snapshot_manifest"))
def test_preflight_makes_output_absence_the_final_check(
    captured_paths: V11ArtifactPaths,
    artifact_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clean = capture_repository_state(captured_paths)
    observations = 0

    def observe_repository_state(root: Path) -> RepositoryState:
        nonlocal observations
        assert root == captured_paths.repo_root
        observations += 1
        if observations == 2:
            write_exclusive(getattr(captured_paths, artifact_name), b"{}\n")
        return clean

    monkeypatch.setattr(
        capture_module,
        "inspect_repository_state",
        observe_repository_state,
    )

    with pytest.raises(FileExistsError, match="capture artifact already exists"):
        preflight_v1_1_capture(
            captured_paths,
            configured_settings(),
            project_author_name="mrhao165-del",
        )


@pytest.mark.parametrize("target_kind", ("frozen_dataset", "freeze_manifest", "code_file"))
def test_preflight_rejects_file_mutated_and_restored_during_validation(
    captured_paths: V11ArtifactPaths,
    target_kind: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = (
        captured_paths.repo_root / V11_FREEZE_CODE_RELATIVE_PATHS[0]
        if target_kind == "code_file"
        else getattr(captured_paths, target_kind)
    )
    original_bytes = target.read_bytes()
    original = capture_module.candidate_quality_report
    mutated = False

    def mutate_and_restore(cases: object) -> object:
        nonlocal mutated
        if not mutated:
            mutated = True
            target.write_bytes(original_bytes + b"\n")
            target.write_bytes(original_bytes)
        return original(cases)  # type: ignore[arg-type]

    monkeypatch.setattr(capture_module, "candidate_quality_report", mutate_and_restore)

    with pytest.raises(ValueError, match="governed file identity changed"):
        preflight_v1_1_capture(
            captured_paths,
            configured_settings(),
            project_author_name="mrhao165-del",
            repository_state=capture_repository_state(captured_paths),
        )


def test_preflight_rejects_metadata_preserving_same_size_mutation(
    captured_paths: V11ArtifactPaths,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = captured_paths.frozen_dataset
    original_bytes = target.read_bytes()
    original_stat = target.stat()
    original = capture_module.candidate_quality_report
    mutated = False

    def mutate_with_restored_metadata(cases: object) -> object:
        nonlocal mutated
        if not mutated:
            mutated = True
            replacement = bytes((original_bytes[0] ^ 1,)) + original_bytes[1:]
            target.write_bytes(replacement)
            os.utime(
                target,
                ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
            )
        return original(cases)  # type: ignore[arg-type]

    monkeypatch.setattr(
        capture_module,
        "candidate_quality_report",
        mutate_with_restored_metadata,
    )

    with pytest.raises(ValueError, match="governed file bytes changed"):
        preflight_v1_1_capture(
            captured_paths,
            configured_settings(),
            project_author_name="mrhao165-del",
            repository_state=capture_repository_state(captured_paths),
        )


def test_preflight_performs_only_reads_and_in_memory_reconstruction(
    captured_paths: V11ArtifactPaths,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_open = Path.open
    original_os_open = os.open

    def reject_temporary_directory(*args: object, **kwargs: object) -> object:
        raise AssertionError("preflight must not create a temporary directory")

    def reject_directory_creation(*args: object, **kwargs: object) -> None:
        raise AssertionError("preflight must not create directories")

    def allow_os_reads_only(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
        if flags & write_flags:
            raise AssertionError("preflight must not open files for writing")
        return original_os_open(path, flags, mode, dir_fd=dir_fd)

    def allow_reads_only(
        path: Path,
        mode: str = "r",
        *args: object,
        **kwargs: object,
    ) -> object:
        if any(flag in mode for flag in "wax+"):
            raise AssertionError("preflight must not open files for writing")
        return original_open(path, mode, *args, **kwargs)  # type: ignore

    monkeypatch.setattr(tempfile, "TemporaryDirectory", reject_temporary_directory)
    monkeypatch.setattr(Path, "mkdir", reject_directory_creation)
    monkeypatch.setattr(Path, "open", allow_reads_only)
    monkeypatch.setattr(os, "open", allow_os_reads_only)

    plan = preflight_v1_1_capture(
        captured_paths,
        configured_settings(),
        project_author_name="mrhao165-del",
        repository_state=capture_repository_state(captured_paths),
    )

    assert len(plan.runtime_cases) == 26


def test_preflight_rechecks_repository_state_before_return(
    captured_paths: V11ArtifactPaths,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clean = capture_repository_state(captured_paths)
    dirty = clean.model_copy(update={"untracked_paths": (*clean.untracked_paths, "late.txt")})
    states = iter((clean, dirty))
    monkeypatch.setattr(capture_module, "inspect_repository_state", lambda root: next(states))

    with pytest.raises(ValueError, match="unexpected worktree delta"):
        preflight_v1_1_capture(
            captured_paths,
            configured_settings(),
            project_author_name="mrhao165-del",
        )


def test_preflight_rejects_external_governed_input_symlink(
    captured_paths: V11ArtifactPaths,
    tmp_path: Path,
) -> None:
    external = tmp_path.parent / f"{tmp_path.name}-external-candidate.jsonl"
    external.write_bytes(captured_paths.corrected_candidate.read_bytes())
    captured_paths.corrected_candidate.unlink()
    captured_paths.corrected_candidate.symlink_to(external)

    with pytest.raises(ValueError, match="governed paths must not contain symlinks"):
        preflight_v1_1_capture(
            captured_paths,
            configured_settings(),
            project_author_name="mrhao165-del",
            repository_state=capture_repository_state(captured_paths),
        )


def test_preflight_rejects_governed_code_symlink(
    captured_paths: V11ArtifactPaths,
    tmp_path: Path,
) -> None:
    code_path = captured_paths.repo_root / V11_FREEZE_CODE_RELATIVE_PATHS[0]
    external = tmp_path.parent / f"{tmp_path.name}-external-intake.py"
    external.write_bytes(code_path.read_bytes())
    code_path.unlink()
    code_path.symlink_to(external)

    with pytest.raises(ValueError, match="governed paths must not contain symlinks"):
        preflight_v1_1_capture(
            captured_paths,
            configured_settings(),
            project_author_name="mrhao165-del",
            repository_state=capture_repository_state(captured_paths),
        )


def test_preflight_rejects_dangling_capture_output_symlink(
    captured_paths: V11ArtifactPaths,
) -> None:
    captured_paths.capture_intent.parent.mkdir(parents=True, exist_ok=True)
    captured_paths.capture_intent.symlink_to(captured_paths.capture_intent.parent / "missing.json")

    with pytest.raises(FileExistsError, match="capture artifact already exists"):
        preflight_v1_1_capture(
            captured_paths,
            configured_settings(),
            project_author_name="mrhao165-del",
            repository_state=capture_repository_state(captured_paths),
        )


def test_preflight_rejects_repo_root_that_differs_from_git_top_level(tmp_path: Path) -> None:
    paths = prepare_capture_paths(tmp_path / "nested")
    state = capture_repository_state(paths).model_copy(update={"git_top_level": tmp_path})

    with pytest.raises(ValueError, match="repository root differs from Git top-level"):
        preflight_v1_1_capture(
            paths,
            configured_settings(),
            project_author_name="mrhao165-del",
            repository_state=state,
        )


@pytest.mark.parametrize("artifact_name", ("capture_intent", "predictions", "snapshot_manifest"))
def test_preflight_rejects_every_existing_capture_artifact(
    captured_paths: V11ArtifactPaths,
    artifact_name: str,
) -> None:
    write_exclusive(getattr(captured_paths, artifact_name), b"{}\n")

    with pytest.raises(FileExistsError, match="capture artifact already exists"):
        preflight_v1_1_capture(
            captured_paths,
            configured_settings(),
            project_author_name="mrhao165-del",
            repository_state=capture_repository_state(captured_paths),
        )


def _update_manifest_checksum(paths: V11ArtifactPaths, field: str, checksum: str) -> None:
    manifest = json.loads(paths.freeze_manifest.read_text(encoding="utf-8"))
    manifest[field] = checksum
    paths.freeze_manifest.write_bytes(canonical_json_bytes(manifest))
