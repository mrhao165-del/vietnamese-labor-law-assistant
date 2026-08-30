from __future__ import annotations

from pathlib import Path

import pytest

from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_artifacts import (
    RepositoryState,
    V11ArtifactPaths,
    canonical_json_bytes,
    require_capture_repository_state,
    require_pre_freeze_repository_state,
    sha256_bytes,
    sha256_file,
    write_exclusive,
)


def test_paths_and_write_once_policy(tmp_path: Path) -> None:
    paths = V11ArtifactPaths.from_root(tmp_path)

    assert paths.frozen_dataset.relative_to(tmp_path).as_posix() == (
        "data/evaluation/decision_support/v1_1/v1_1_evaluation_frozen.jsonl"
    )
    assert paths.freeze_manifest.relative_to(tmp_path).as_posix() == (
        "evaluation/results/decision_support/v1_1/v1_1_frozen_dataset_manifest.json"
    )
    output = tmp_path / "evidence.json"
    write_exclusive(output, b"first\n")
    with pytest.raises(FileExistsError):
        write_exclusive(output, b"second\n")
    assert output.read_bytes() == b"first\n"


def test_repository_policy_is_clean_then_allows_only_bound_freeze_outputs(
    tmp_path: Path,
) -> None:
    paths = V11ArtifactPaths.from_root(tmp_path)
    clean = RepositoryState(commit_sha="a" * 40, tracked_dirty=False, untracked_paths=())

    require_pre_freeze_repository_state(clean)

    allowed = RepositoryState(
        commit_sha="a" * 40,
        tracked_dirty=False,
        untracked_paths=(
            paths.frozen_dataset.relative_to(tmp_path).as_posix(),
            paths.freeze_manifest.relative_to(tmp_path).as_posix(),
        ),
    )
    require_capture_repository_state(allowed, paths)
    invalid = allowed.model_copy(
        update={"untracked_paths": (*allowed.untracked_paths, "unrelated.txt")}
    )
    with pytest.raises(ValueError, match="unexpected worktree delta"):
        require_capture_repository_state(invalid, paths)


def test_hashing_and_canonical_json_are_byte_deterministic(tmp_path: Path) -> None:
    payload = {"z": "tiếng Việt", "a": [2, 1]}
    encoded = canonical_json_bytes(payload)
    file_path = tmp_path / "payload.json"
    file_path.write_bytes(encoded)

    assert encoded == b'{"a":[2,1],"z":"ti\xe1\xba\xbfng Vi\xe1\xbb\x87t"}\n'
    assert sha256_file(file_path) == sha256_bytes(encoded)
