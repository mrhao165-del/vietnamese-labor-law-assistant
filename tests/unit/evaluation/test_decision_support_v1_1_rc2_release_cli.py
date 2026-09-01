from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def load_script() -> ModuleType:
    path = PROJECT_ROOT / "scripts/run_decision_support_v1_1_rc2_evaluation.py"
    specification = importlib.util.spec_from_file_location("rc2_release_script", path)
    if specification is None or specification.loader is None:
        pytest.fail("the RC2 offline release adapter is missing")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_cli_runs_only_offline_evaluator_and_returns_pass(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    script = load_script()
    calls: list[Path] = []
    terminal = SimpleNamespace(
        final_result="PASS",
        model_dump=lambda **_: {"final_result": "PASS", "live_provider_calls": 0},
    )
    monkeypatch.setattr(
        script,
        "evaluate_registered_rc2_release",
        lambda paths: calls.append(paths.repo_root) or terminal,
    )

    result = script.main(
        [
            "--repo-root",
            str(tmp_path),
            "--confirm-write-once",
            "V1_1_RC2_OFFLINE_EVALUATION",
        ]
    )

    assert result == 0
    assert calls == [tmp_path.resolve()]
    assert json.loads(capsys.readouterr().out)["live_provider_calls"] == 0


def test_cli_confirmation_failure_occurs_before_evaluator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = load_script()
    calls: list[str] = []
    monkeypatch.setattr(
        script,
        "evaluate_registered_rc2_release",
        lambda *args, **kwargs: calls.append("evaluate"),
    )

    with pytest.raises(SystemExit):
        script.main([])

    assert calls == []
