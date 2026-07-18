"""Run canonical checks and discovered production MCP demos."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path


def _repository_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise RuntimeError("could not locate repository root")


def _run(command: Sequence[str], root: Path) -> int:
    print("+", " ".join(command), flush=True)
    return subprocess.run(command, cwd=root, check=False, shell=False).returncode


def main() -> int:
    root = _repository_root()
    commands: tuple[tuple[str, ...], ...] = (
        ("uv", "lock", "--check"),
        ("uv", "run", "ruff", "format", "--check", "."),
        ("uv", "run", "ruff", "check", "."),
        ("uv", "run", "pyright"),
        ("uv", "run", "pytest", "--cov=vietnamese_labor_law_assistant"),
    )
    for command in commands:
        if _run(command, root):
            return 1
    demos = sorted((root / "scripts").glob("demo_*_mcp*_client.py"))
    for demo in demos:
        if _run(("uv", "run", "python", str(demo.relative_to(root))), root):
            return 1
    print(f"PASS: {len(commands)} canonical checks and {len(demos)} production MCP demos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
