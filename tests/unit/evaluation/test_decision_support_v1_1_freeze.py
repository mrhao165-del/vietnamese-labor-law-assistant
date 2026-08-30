from __future__ import annotations

import csv
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_freeze as freeze_module
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_artifacts import (
    V11_FREEZE_CODE_RELATIVE_PATHS,
    RepositoryState,
    V11ArtifactPaths,
    sha256_bytes,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_freeze import (
    freeze_v1_1_evaluation,
    load_v1_1_frozen_dataset,
    prepare_v1_1_freeze,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SOURCE_PATHS = V11ArtifactPaths.from_root(REPOSITORY_ROOT)
FROZEN_AT = datetime(2026, 8, 30, 21, 0, tzinfo=timezone(timedelta(hours=7)))
CLEAN_STATE = RepositoryState(commit_sha="b" * 40, tracked_dirty=False, untracked_paths=())


@pytest.fixture
def governed_paths(tmp_path: Path) -> V11ArtifactPaths:
    paths = V11ArtifactPaths.from_root(tmp_path)
    for source, destination in (
        (SOURCE_PATHS.corrected_candidate, paths.corrected_candidate),
        (SOURCE_PATHS.review_packet, paths.review_packet),
        (SOURCE_PATHS.threshold_spec, paths.threshold_spec),
        (SOURCE_PATHS.threshold_approval, paths.threshold_approval),
        (
            REPOSITORY_ROOT / "data/evaluation/decision_support/v1_1/week3_evaluation_spec.json",
            tmp_path / "data/evaluation/decision_support/v1_1/week3_evaluation_spec.json",
        ),
    ):
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    for relative_path in V11_FREEZE_CODE_RELATIVE_PATHS:
        destination = tmp_path / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY_ROOT / relative_path, destination)
    return paths


def test_prepare_freeze_changes_only_validator_owned_state(
    governed_paths: V11ArtifactPaths,
) -> None:
    bundle = prepare_v1_1_freeze(
        governed_paths,
        project_author_name="mrhao165-del",
        repository_state=CLEAN_STATE,
        frozen_at=FROZEN_AT,
    )

    assert len(bundle.cases) == 26
    assert all(case.human_validated for case in bundle.cases)
    assert all(case.review_status == "PASS" and case.frozen_final for case in bundle.cases)
    assert bundle.manifest.review_status == "PASS"
    assert bundle.manifest.threshold_approval_decision == "APPROVE_UNCHANGED"
    assert bundle.manifest.git_commit_sha == "b" * 40
    assert bundle.manifest.frozen_dataset_sha256 == sha256_bytes(bundle.dataset_bytes)


def test_freeze_rejects_approval_not_earlier_than_freeze(
    governed_paths: V11ArtifactPaths,
) -> None:
    with pytest.raises(ValueError, match="threshold approval must precede frozen timestamp"):
        prepare_v1_1_freeze(
            governed_paths,
            project_author_name="mrhao165-del",
            repository_state=CLEAN_STATE,
            frozen_at=datetime(2026, 8, 30, 19, 0, tzinfo=timezone(timedelta(hours=7))),
        )


def test_prepare_freeze_rejects_mutated_temp_root_inherited_threshold_source(
    governed_paths: V11ArtifactPaths,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    week3_spec = governed_paths.repo_root / (
        "data/evaluation/decision_support/v1_1/week3_evaluation_spec.json"
    )
    payload = json.loads(week3_spec.read_text(encoding="utf-8"))
    payload["thresholds"]["missing_fact_precision_min"] = 0.5
    week3_spec.write_text(json.dumps(payload), encoding="utf-8")
    non_root_cwd = governed_paths.repo_root / "outside-repository"
    non_root_cwd.mkdir()
    monkeypatch.chdir(non_root_cwd)

    with pytest.raises(ValueError, match="v1.1 proposal changed the Week-3 threshold"):
        prepare_v1_1_freeze(
            governed_paths,
            project_author_name="mrhao165-del",
            repository_state=CLEAN_STATE,
            frozen_at=FROZEN_AT,
        )


def test_freeze_is_separate_write_once_and_preserves_inputs(
    governed_paths: V11ArtifactPaths,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = (
        governed_paths.corrected_candidate,
        governed_paths.review_packet,
        governed_paths.threshold_spec,
        governed_paths.threshold_approval,
    )
    before = {path: path.read_bytes() for path in inputs}
    monkeypatch.setattr(freeze_module, "inspect_repository_state", lambda root: CLEAN_STATE)

    manifest = freeze_v1_1_evaluation(
        governed_paths,
        project_author_name="mrhao165-del",
        frozen_at=FROZEN_AT,
    )

    assert len(load_v1_1_frozen_dataset(governed_paths.frozen_dataset)) == 26
    assert manifest.case_count == 26
    assert before == {path: path.read_bytes() for path in inputs}
    with pytest.raises(FileExistsError):
        freeze_v1_1_evaluation(
            governed_paths,
            project_author_name="mrhao165-del",
            frozen_at=FROZEN_AT,
        )


def test_prepare_freeze_rejects_non_pass_review(
    governed_paths: V11ArtifactPaths,
) -> None:
    _update_review_row(governed_paths.review_packet, review_decision="NEEDS_REVISION")

    with pytest.raises(ValueError, match="review packet failed canonical validation"):
        prepare_v1_1_freeze(
            governed_paths,
            project_author_name="mrhao165-del",
            repository_state=CLEAN_STATE,
            frozen_at=FROZEN_AT,
        )


def test_prepare_freeze_rejects_changed_immutable_review_label(
    governed_paths: V11ArtifactPaths,
) -> None:
    _update_review_row(governed_paths.review_packet, raw_user_input="changed")

    with pytest.raises(ValueError, match="review packet failed canonical validation"):
        prepare_v1_1_freeze(
            governed_paths,
            project_author_name="mrhao165-del",
            repository_state=CLEAN_STATE,
            frozen_at=FROZEN_AT,
        )


@pytest.mark.parametrize("path_name", ("threshold_spec", "threshold_approval"))
def test_prepare_freeze_rejects_changed_threshold_governance_bytes(
    governed_paths: V11ArtifactPaths,
    path_name: str,
) -> None:
    path = getattr(governed_paths, path_name)
    path.write_bytes(path.read_bytes() + b" \n")

    with pytest.raises(ValueError, match="threshold approval failed canonical validation"):
        prepare_v1_1_freeze(
            governed_paths,
            project_author_name="mrhao165-del",
            repository_state=CLEAN_STATE,
            frozen_at=FROZEN_AT,
        )


def test_prepare_freeze_rejects_incomplete_reviewer_metadata(
    governed_paths: V11ArtifactPaths,
) -> None:
    _update_review_row(governed_paths.review_packet, reviewer_identifier="")

    with pytest.raises(ValueError, match="review packet failed canonical validation"):
        prepare_v1_1_freeze(
            governed_paths,
            project_author_name="mrhao165-del",
            repository_state=CLEAN_STATE,
            frozen_at=FROZEN_AT,
        )


def test_prepare_freeze_rejects_timezone_free_review_timestamp(
    governed_paths: V11ArtifactPaths,
) -> None:
    _update_all_review_rows(governed_paths.review_packet, reviewed_at="2026-08-30T19:59:16")

    with pytest.raises(ValueError, match="reviewed_at timestamps must include a timezone"):
        prepare_v1_1_freeze(
            governed_paths,
            project_author_name="mrhao165-del",
            repository_state=CLEAN_STATE,
            frozen_at=FROZEN_AT,
        )


def test_prepare_freeze_rejects_duplicate_candidate_ids(
    governed_paths: V11ArtifactPaths,
) -> None:
    first = governed_paths.corrected_candidate.read_text(encoding="utf-8").splitlines()[0]
    governed_paths.corrected_candidate.write_text(first + "\n" + first + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unique non-empty case IDs"):
        prepare_v1_1_freeze(
            governed_paths,
            project_author_name="mrhao165-del",
            repository_state=CLEAN_STATE,
            frozen_at=FROZEN_AT,
        )


def test_prepare_freeze_rejects_source_span_schema_failure(
    governed_paths: V11ArtifactPaths,
) -> None:
    rows = governed_paths.corrected_candidate.read_text(encoding="utf-8").splitlines()
    payload = json.loads(rows[0])
    payload["expected_case_facts"][0]["source_span"]["text"] = "not from input"
    rows[0] = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    governed_paths.corrected_candidate.write_text("\n".join(rows) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="source span"):
        prepare_v1_1_freeze(
            governed_paths,
            project_author_name="mrhao165-del",
            repository_state=CLEAN_STATE,
            frozen_at=FROZEN_AT,
        )


def test_prepare_freeze_rejects_pending_prediction_input_audit(
    governed_paths: V11ArtifactPaths,
) -> None:
    rows = governed_paths.corrected_candidate.read_text(encoding="utf-8").splitlines()
    payload = json.loads(rows[0])
    payload["candidate_generation_input_audit"] = (
        "PENDING_HUMAN_PROVENANCE_CONFIRMATION_NO_PREDICTION_INPUT"
    )
    rows[0] = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    governed_paths.corrected_candidate.write_text("\n".join(rows) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="completed prediction-input audit"):
        prepare_v1_1_freeze(
            governed_paths,
            project_author_name="mrhao165-del",
            repository_state=CLEAN_STATE,
            frozen_at=FROZEN_AT,
        )


def _update_review_row(path: Path, **changes: str) -> None:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fields = list(reader.fieldnames or ())
    rows[0].update(changes)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _update_all_review_rows(path: Path, **changes: str) -> None:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fields = list(reader.fieldnames or ())
    for row in rows:
        row.update(changes)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
