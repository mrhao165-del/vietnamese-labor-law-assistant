from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from vietnamese_labor_law_assistant.evaluation.decision_support_fact_issue_development import (
    FactIssueArtifactPaths,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def load_script() -> ModuleType:
    path = PROJECT_ROOT / "scripts/run_decision_support_fact_issue_development.py"
    specification = importlib.util.spec_from_file_location("fact_issue_development_script", path)
    if specification is None or specification.loader is None:
        pytest.fail("the fact-vs-issue synthetic development adapter is missing")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_cli_requires_explicit_non_release_acknowledgement_before_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = load_script()
    calls: list[str] = []
    monkeypatch.setattr(script, "get_settings", lambda: calls.append("settings"))

    with pytest.raises(SystemExit):
        script.main([])

    assert calls == []


@pytest.mark.parametrize("run_id", ["../rc2", "x" * 121])
def test_cli_rejects_invalid_run_id_before_settings(
    monkeypatch: pytest.MonkeyPatch,
    run_id: str,
) -> None:
    script = load_script()
    calls: list[str] = []
    monkeypatch.setattr(script, "get_settings", lambda: calls.append("settings"))

    with pytest.raises(SystemExit):
        script.main(
            [
                "--run-id",
                run_id,
                "--live-development",
                "--acknowledge-not-release",
                "FACT_ISSUE_EVIDENCE_SYNTHETIC_NOT_RELEASE",
            ]
        )

    assert calls == []


def test_cli_uses_fixed_matrix_development_namespace_and_prints_no_secret(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    script = load_script()
    calls: list[object] = []
    fake_report = SimpleNamespace(
        gates=SimpleNamespace(overall_passed=True),
        metrics=SimpleNamespace(live_development_passed=True),
        model_dump=lambda **_: {
            "mode": "FACT_ISSUE_EVIDENCE_SYNTHETIC_NOT_RELEASE",
            "gates": {"overall_passed": True},
        },
    )
    monkeypatch.setattr(script, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(script, "validate_development_provider_settings", lambda settings: None)
    monkeypatch.setattr(script, "load_fact_issue_matrix", lambda path: tuple(range(16)))
    monkeypatch.setattr(script, "OpenAIStructuredCaseIntakeExtractor", lambda settings: object())

    async def fake_run(*args: object, **kwargs: object) -> object:
        calls.extend((args, kwargs))
        return fake_report

    monkeypatch.setattr(script, "run_fact_issue_development_cycle", fake_run)

    result = script.main(
        [
            "--repo-root",
            str(tmp_path),
            "--run-id",
            "fact-issue-live-1",
            "--live-development",
            "--acknowledge-not-release",
            "FACT_ISSUE_EVIDENCE_SYNTHETIC_NOT_RELEASE",
        ]
    )

    assert result == 0
    assert calls
    run_args = calls[0]
    assert isinstance(run_args, tuple)
    paths = run_args[2]
    assert isinstance(paths, FactIssueArtifactPaths)
    assert paths.output_dir == (
        tmp_path.resolve()
        / "evaluation/development/decision_support/v1_1/post_rc2/runs/fact-issue-live-1"
    )
    assert run_args[0] == tuple(range(16))
    output = capsys.readouterr().out
    assert json.loads(output)["mode"] == "FACT_ISSUE_EVIDENCE_SYNTHETIC_NOT_RELEASE"
    assert "api_key" not in output.casefold()
    assert "authorization" not in output.casefold()
