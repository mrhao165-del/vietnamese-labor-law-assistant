"""Report protected-scope and test-quality risks in staged and unstaged Git diffs."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

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


def _repository_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / ".git").exists() and (candidate / "pyproject.toml").is_file():
            return candidate
    raise RuntimeError("could not locate repository root")


def _git_output(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", *args), cwd=root, check=True, shell=False, capture_output=True, text=True
    )
    return completed.stdout


def _changed_paths(root: Path, cached: bool) -> set[str]:
    args = ["diff", "--name-only", "--find-renames"]
    if cached:
        args.append("--cached")
    return {line for line in _git_output(root, *args).splitlines() if line}


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
    paths = _changed_paths(root, cached=False) | _changed_paths(root, cached=True)
    diffs = (
        _git_output(root, "diff", "--unified=0"),
        _git_output(root, "diff", "--cached", "--unified=0"),
    )
    added = tuple(line for diff in diffs for line in _added_lines(diff))
    protected_paths = sorted(path for path in paths if path.startswith(PROTECTED_PREFIXES))
    locked_config = [line for line in added if LOCKED_CONFIG in line]
    test_quality = [line for line in added if any(item in line for item in TEST_QUALITY_PATTERNS)]
    coverage_reductions = _coverage_reductions(diffs)
    report = {
        "status": (
            "BLOCKED"
            if protected_paths or locked_config or test_quality or coverage_reductions
            else "CLEAR"
        ),
        "protected_paths": protected_paths,
        "locked_config_added_lines": locked_config,
        "test_quality_added_lines": test_quality,
        "coverage_reductions": coverage_reductions,
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
