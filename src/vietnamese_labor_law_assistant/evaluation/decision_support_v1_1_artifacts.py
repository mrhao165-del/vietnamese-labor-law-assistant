"""Canonical artifact paths and repository-state checks for v1.1 capture."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True)
class V11ArtifactPaths:
    """The fixed locations for v1.1 decision-support evidence artifacts."""

    repo_root: Path
    corrected_candidate: Path
    review_packet: Path
    threshold_spec: Path
    threshold_approval: Path
    frozen_dataset: Path
    freeze_manifest: Path
    capture_intent: Path
    predictions: Path
    snapshot_manifest: Path

    @classmethod
    def from_root(cls, repo_root: Path) -> V11ArtifactPaths:
        root = repo_root.resolve()
        data = root / "data/evaluation/decision_support/v1_1"
        review = root / "evaluation/review/decision_support/v1_1"
        results = root / "evaluation/results/decision_support/v1_1"
        return cls(
            repo_root=root,
            corrected_candidate=data / "v1_1_evaluation_candidate_corrected.jsonl",
            review_packet=(
                review / "v1_1_human_review_packet_corrected_prefilled_for_human_review.csv"
            ),
            threshold_spec=data / "v1_1_proposed_thresholds.json",
            threshold_approval=review / "v1_1_threshold_approval.json",
            frozen_dataset=data / "v1_1_evaluation_frozen.jsonl",
            freeze_manifest=results / "v1_1_frozen_dataset_manifest.json",
            capture_intent=results / "v1_1_production_case_intake_capture_intent.json",
            predictions=results / "v1_1_production_case_intake_predictions_final.jsonl",
            snapshot_manifest=(results / "v1_1_production_case_intake_predictions_manifest.json"),
        )


class RepositoryState(BaseModel):
    """The Git state that is permitted around an evidence transition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    tracked_dirty: bool
    untracked_paths: tuple[str, ...]
    git_top_level: Path | None = None


V11_FREEZE_CODE_RELATIVE_PATHS = (
    "src/vietnamese_labor_law_assistant/decision_support/intake.py",
    "src/vietnamese_labor_law_assistant/decision_support/models.py",
    "src/vietnamese_labor_law_assistant/decision_support/issue_registry.py",
    "src/vietnamese_labor_law_assistant/decision_support/missing_facts.py",
    "src/vietnamese_labor_law_assistant/decision_support/clarification.py",
    "src/vietnamese_labor_law_assistant/decision_support/refined_issues.py",
    "src/vietnamese_labor_law_assistant/decision_support/evidence_requests.py",
    "src/vietnamese_labor_law_assistant/agent/case_graph.py",
    "src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1.py",
    "src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1_approval.py",
    "src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1_artifacts.py",
    "src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1_freeze.py",
    "src/vietnamese_labor_law_assistant/evaluation/decision_support_week3.py",
    "src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1_release.py",
)


def sha256_bytes(payload: bytes) -> str:
    """Return the lowercase SHA-256 checksum for raw artifact bytes."""

    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    """Return the lowercase SHA-256 checksum for a file without text decoding."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(payload: object) -> bytes:
    """Serialize JSON in the canonical, UTF-8, newline-terminated artifact form."""

    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return (text + "\n").encode("utf-8")


def write_exclusive(path: Path, payload: bytes) -> None:
    """Atomically publish complete bytes once under an absent final name."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if os.path.lexists(path):
        raise FileExistsError(f"final artifact already exists: {path}")
    temporary = atomic_temporary_path(path)
    if os.path.lexists(temporary):
        temporary.unlink()
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if temporary.read_bytes() != payload:
            raise OSError("temporary artifact changed before atomic publication")
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise FileExistsError(f"final artifact already exists: {path}") from exc
        fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_temporary_path(path: Path) -> Path:
    """Return the fixed recoverable temporary name for a write-once artifact."""

    return path.with_name(f".{path.name}.atomic-write.tmp")


def fsync_directory(path: Path) -> None:
    """Durably persist a directory entry on platforms that expose directory fsync."""

    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def inspect_repository_state(repo_root: Path) -> RepositoryState:
    """Inspect the current commit and worktree without changing repository state."""

    root = repo_root.resolve()
    git_top_level = Path(
        subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    ).resolve()
    commit = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    tracked_dirty = any(
        subprocess.run(command, check=False, capture_output=True).returncode
        for command in (
            ["git", "-C", str(root), "diff", "--quiet"],
            ["git", "-C", str(root), "diff", "--cached", "--quiet"],
        )
    )
    untracked = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--others", "--exclude-standard"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    return RepositoryState(
        commit_sha=commit,
        tracked_dirty=tracked_dirty,
        untracked_paths=tuple(sorted(Path(item).as_posix() for item in untracked)),
        git_top_level=git_top_level,
    )


def require_pre_freeze_repository_state(state: RepositoryState) -> None:
    """Fail closed unless freezing starts from a completely clean worktree."""

    if state.tracked_dirty or state.untracked_paths:
        raise ValueError("unexpected worktree delta before freeze")


def require_capture_repository_state(state: RepositoryState, paths: V11ArtifactPaths) -> None:
    """Allow capture only after the two frozen artifacts are the sole worktree delta."""

    expected_paths = tuple(
        sorted(
            (
                paths.frozen_dataset.relative_to(paths.repo_root).as_posix(),
                paths.freeze_manifest.relative_to(paths.repo_root).as_posix(),
            )
        )
    )
    if state.tracked_dirty or tuple(sorted(state.untracked_paths)) != expected_paths:
        raise ValueError("unexpected worktree delta for capture")
