from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def load_script() -> ModuleType:
    path = PROJECT_ROOT / "scripts/run_decision_support_v1_1_development.py"
    specification = importlib.util.spec_from_file_location("post_rc2_development_script", path)
    if specification is None or specification.loader is None:
        pytest.fail("the post-RC2 development adapter is missing")
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


def test_cli_runs_development_service_and_prints_no_secret(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    script = load_script()
    calls: list[object] = []
    fake_report = SimpleNamespace(
        pipeline_exit_criteria_passed=True,
        model_dump=lambda **_: {
            "mode": "DEVELOPMENT_REGRESSION_NOT_RELEASE",
            "pipeline_exit_criteria_passed": True,
        },
    )
    monkeypatch.setattr(script, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(script, "validate_development_provider_settings", lambda settings: None)
    monkeypatch.setattr(script, "load_v1_1_frozen_dataset", lambda path: tuple(range(26)))
    monkeypatch.setattr(
        script,
        "load_v1_1_threshold_spec",
        lambda *args, **kwargs: SimpleNamespace(thresholds=object()),
    )
    monkeypatch.setattr(script, "sha256_file", lambda path: "a" * 64)
    monkeypatch.setattr(script, "OpenAIStructuredCaseIntakeExtractor", lambda settings: object())

    async def fake_run(*args: object, **kwargs: object) -> object:
        calls.extend((args, kwargs))
        return fake_report

    monkeypatch.setattr(script, "run_post_rc2_development_regression", fake_run)

    result = script.main(
        [
            "--repo-root",
            str(tmp_path),
            "--run-id",
            "dev-run-1",
            "--live-development",
            "--acknowledge-not-release",
            "RC2_REGRESSION_DIAGNOSTIC_SET",
        ]
    )

    assert result == 0
    assert calls
    output = capsys.readouterr().out
    assert json.loads(output)["mode"] == "DEVELOPMENT_REGRESSION_NOT_RELEASE"
    assert "api_key" not in output.casefold()
    assert "authorization" not in output.casefold()
