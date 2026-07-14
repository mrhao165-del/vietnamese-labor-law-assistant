"""Offline guardrails for the repository's architectural boundaries."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
PACKAGE = SRC / "vietnamese_labor_law_assistant"
GENERATED_DIRECTORY_NAMES = {"__pycache__"}
# This is the only permitted non-package file directly under src. Add an exception
# here with a reason if packaging metadata is deliberately introduced later.
ALLOWED_SRC_METADATA = {"py.typed"}


def python_files(directory: Path) -> list[Path]:
    return [
        path
        for path in directory.rglob("*.py")
        if not any(part in GENERATED_DIRECTORY_NAMES for part in path.parts)
    ]


def parse_module(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_src_contains_only_primary_package_and_documented_metadata() -> None:
    unexpected = [
        path.name
        for path in SRC.iterdir()
        if path.name not in GENERATED_DIRECTORY_NAMES
        and path.name != PACKAGE.name
        and path.name not in ALLOWED_SRC_METADATA
    ]

    assert not unexpected, f"Unexpected top-level entries in src/: {unexpected}"
    assert PACKAGE.is_dir()


def test_non_code_directories_do_not_contain_python() -> None:
    protected_directories = [ROOT / "data", ROOT / "docs", ROOT / "evaluation" / "results"]
    violations = [
        path.relative_to(ROOT)
        for directory in protected_directories
        for path in python_files(directory)
    ]

    assert not violations, f"Python files are not allowed in data/docs/results: {violations}"


def test_production_modules_do_not_depend_on_tests_or_src_package() -> None:
    violations: list[str] = []
    for path in python_files(PACKAGE):
        for node in ast.walk(parse_module(path)):
            module = None
            if isinstance(node, ast.Import):
                module = next(
                    (
                        name.name
                        for name in node.names
                        if name.name == "src" or name.name.startswith("src.")
                    ),
                    None,
                )
                module = module or next(
                    (
                        name.name
                        for name in node.names
                        if name.name == "tests" or name.name.startswith("tests.")
                    ),
                    None,
                )
            elif isinstance(node, ast.ImportFrom):
                module = node.module

            if module and (
                module == "src"
                or module.startswith("src.")
                or module == "tests"
                or module.startswith("tests.")
            ):
                violations.append(f"{path.relative_to(ROOT)}: {module}")

    assert not violations, "Production imports must not depend on src or tests: " + ", ".join(
        violations
    )


def test_root_package_init_is_inert() -> None:
    tree = parse_module(PACKAGE / "__init__.py")
    allowed_nodes = (ast.Expr, ast.Assign, ast.AnnAssign)
    unexpected_nodes = [
        type(node).__name__ for node in tree.body if not isinstance(node, allowed_nodes)
    ]
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]

    assert not unexpected_nodes, f"Root __init__.py must stay declarative: {unexpected_nodes}"
    assert not calls, "Root __init__.py must not perform runtime initialization or print output"
