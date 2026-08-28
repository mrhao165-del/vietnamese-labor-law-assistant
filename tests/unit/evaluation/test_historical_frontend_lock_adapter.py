"""Offline Git-repository tests for the historical frontend lock adapter."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

HISTORICAL_LOCK_PATH = "frontend/package-lock.json"
QUALIFIED_TAG = "refs/tags/v1.0.0"


def _git(root: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def _initialize_repository(root: Path, lock_bytes: bytes) -> None:
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.name", "Offline Test")
    _git(root, "config", "user.email", "offline-test@example.invalid")
    _git(root, "config", "core.autocrlf", "false")
    _write_lock_commit(root, lock_bytes, "initial lock")


def _write_lock_commit(root: Path, lock_bytes: bytes, message: str) -> None:
    lock_path = root / HISTORICAL_LOCK_PATH
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_bytes(lock_bytes)
    _git(root, "add", "--", HISTORICAL_LOCK_PATH)
    _git(root, "commit", "--no-gpg-sign", "-m", message)


@pytest.fixture(scope="module")
def adapter_module() -> ModuleType:
    script = Path(__file__).resolve().parents[3] / "scripts/historical_frontend_lock.py"
    spec = importlib.util.spec_from_file_location("historical_frontend_lock_adapter", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_branch_named_v1_cannot_substitute_when_exact_tag_is_absent(
    tmp_path: Path,
    adapter_module: ModuleType,
) -> None:
    repository = tmp_path / "branch-only"
    _initialize_repository(repository, b'{"source":"branch-only"}\n')
    _git(repository, "branch", "-M", "v1.0.0")

    with pytest.raises(
        ValueError,
        match=r"historical checksum source is unavailable: refs/tags/v1\.0\.0:",
    ):
        adapter_module.read_historical_frontend_lock_source(repository)


def test_exact_tag_wins_when_same_named_branch_and_worktree_bytes_differ(
    tmp_path: Path,
    adapter_module: ModuleType,
) -> None:
    repository = tmp_path / "tag-and-branch"
    tagged_bytes = b'{"source":"exact-tag"}\n'
    branch_bytes = b'{"source":"same-named-branch"}\n'
    _initialize_repository(repository, tagged_bytes)
    _git(repository, "tag", "v1.0.0")
    _git(repository, "checkout", "-b", "v1.0.0")
    _write_lock_commit(repository, branch_bytes, "current branch lock")

    source = adapter_module.read_historical_frontend_lock_source(repository)[HISTORICAL_LOCK_PATH]

    assert source.revision == QUALIFIED_TAG
    assert source.content == tagged_bytes
    assert (repository / HISTORICAL_LOCK_PATH).read_bytes() == branch_bytes
