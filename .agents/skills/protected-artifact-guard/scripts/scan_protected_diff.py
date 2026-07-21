"""Report protected-scope and test-quality risks in staged and unstaged Git diffs."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Iterable
from fnmatch import fnmatch
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

PROTECTED_PREFIXES = ("data/raw/", "data/processed/", "data/evaluation/", "evaluation/results/")
LOCKED_CONFIG = "R2_H2_C10_O5_L512_B1"
TEST_QUALITY_PATTERNS = (
    "pytest.mark.skip",
    "pytest.mark.skipif",
    "pytest.skip(",
    "unittest.skip",
    "# pragma: no cover",
    "omit =",
    "omit=",
)
FAIL_UNDER_PATTERN = re.compile(r"^\s*fail_under\s*=\s*(\d+(?:\.\d+)?)\s*$")
LOCAL_RUNTIME_PATHS = (
    ".env",
    ".cache",
    "data/runtime/app.sqlite3",
    "frontend/node_modules",
    "frontend/dist",
)
LOCKED_CONFIG_RUNTIME_PREFIXES = ("src/", "scripts/")
LOCKED_CONFIG_RUNTIME_FILES = {".env.example", "compose.yaml", "pyproject.toml"}


def _repository_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / ".git").exists() and (candidate / "pyproject.toml").is_file():
            return candidate
    raise RuntimeError("could not locate repository root")


def _git_output(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", *args),
        cwd=root,
        check=True,
        shell=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.stdout


def _is_ignored(root: Path, path: str) -> bool:
    return (
        subprocess.run(
            ("git", "check-ignore", "-q", "--", path),
            cwd=root,
            check=False,
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )


def _dockerignore_excludes(path: str, dockerignore: Path) -> bool:
    if not dockerignore.is_file():
        return False
    for raw_line in dockerignore.read_text(encoding="utf-8").splitlines():
        pattern = raw_line.strip()
        if not pattern or pattern.startswith("#") or pattern.startswith("!"):
            continue
        normalized = pattern.rstrip("/")
        if path == normalized or path.startswith(f"{normalized}/"):
            return True
        if fnmatch(path, pattern) or fnmatch(Path(path).name, pattern):
            return True
    return False


def _local_runtime_report(root: Path) -> tuple[list[str], list[str], list[str]]:
    ignored: list[str] = []
    unignored: list[str] = []
    docker_context_risks: list[str] = []
    tracked = set(_git_output(root, "ls-files", "--", *LOCAL_RUNTIME_PATHS).splitlines())
    for path in LOCAL_RUNTIME_PATHS:
        candidate = root / path
        if path in tracked:
            unignored.append(path)
            continue
        if not candidate.exists():
            continue
        if _is_ignored(root, path):
            ignored.append(path)
        else:
            unignored.append(path)
        dockerignore = root / (
            "frontend/.dockerignore" if path.startswith("frontend/") else ".dockerignore"
        )
        docker_path = path.removeprefix("frontend/") if path.startswith("frontend/") else path
        if not _dockerignore_excludes(docker_path, dockerignore):
            docker_context_risks.append(path)
    return sorted(ignored), sorted(unignored), sorted(docker_context_risks)


def _changed_paths(root: Path, cached: bool) -> set[str]:
    args = ["diff", "--name-only", "--find-renames"]
    if cached:
        args.append("--cached")
    return {line for line in _git_output(root, *args).splitlines() if line}


def _locked_config_added_lines(root: Path, cached: bool) -> list[str]:
    paths = _changed_paths(root, cached)
    runtime_paths = sorted(
        path
        for path in paths
        if path.startswith(LOCKED_CONFIG_RUNTIME_PREFIXES) or path in LOCKED_CONFIG_RUNTIME_FILES
    )
    if not runtime_paths:
        return []
    args = ["diff", "--unified=0"]
    if cached:
        args.append("--cached")
    args.extend(("--", *runtime_paths))
    return [line for line in _added_lines(_git_output(root, *args)) if LOCKED_CONFIG in line]


def _added_lines(diff: str) -> Iterable[str]:
    for line in diff.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            yield line[1:]


def _removed_lines(diff: str) -> Iterable[str]:
    for line in diff.splitlines():
        if line.startswith("-") and not line.startswith("---"):
            yield line[1:]


def _coverage_reductions(diffs: Iterable[str]) -> list[dict[str, float]]:
    reductions: list[dict[str, float]] = []
    for diff in diffs:
        removed = [
            float(match.group(1))
            for line in _removed_lines(diff)
            if (match := FAIL_UNDER_PATTERN.match(line)) is not None
        ]
        added = [
            float(match.group(1))
            for line in _added_lines(diff)
            if (match := FAIL_UNDER_PATTERN.match(line)) is not None
        ]
        for old in removed:
            for new in added:
                if new < old:
                    reductions.append({"from": old, "to": new})
    return reductions


def main() -> int:
    root = _repository_root()
    ignored_local_runtime, unignored_local_runtime, docker_context_risks = _local_runtime_report(
        root
    )
    paths = _changed_paths(root, cached=False) | _changed_paths(root, cached=True)
    diffs = (
        _git_output(root, "diff", "--unified=0"),
        _git_output(root, "diff", "--cached", "--unified=0"),
    )
    added = tuple(line for diff in diffs for line in _added_lines(diff))
    protected_paths = sorted(path for path in paths if path.startswith(PROTECTED_PREFIXES))
    locked_config = _locked_config_added_lines(root, cached=False) + _locked_config_added_lines(
        root, cached=True
    )
    test_quality = [line for line in added if any(item in line for item in TEST_QUALITY_PATTERNS)]
    coverage_reductions = _coverage_reductions(diffs)
    report = {
        "status": (
            "BLOCKED"
            if (
                protected_paths
                or locked_config
                or test_quality
                or coverage_reductions
                or unignored_local_runtime
                or docker_context_risks
            )
            else "CLEAR"
        ),
        "protected_paths": protected_paths,
        "locked_config_added_lines": locked_config,
        "test_quality_added_lines": test_quality,
        "coverage_reductions": coverage_reductions,
        "ignored_local_runtime_artifacts": ignored_local_runtime,
        "unignored_or_tracked_local_runtime_artifacts": unignored_local_runtime,
        "docker_context_risks": docker_context_risks,
        "untracked_paths": sorted(
            line[3:]
            for line in _git_output(root, "status", "--short").splitlines()
            if line.startswith("?? ")
        ),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    sys.exit(main())
