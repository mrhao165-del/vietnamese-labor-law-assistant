from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def load_script() -> ModuleType:
    path = PROJECT_ROOT / "scripts/run_decision_support_atomic_development.py"
    specification = importlib.util.spec_from_file_location("atomic_development_script", path)
    if specification is None or specification.loader is None:
        pytest.fail("the atomic development adapter is missing")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_cli_requires_explicit_synthetic_non_release_acknowledgement_before_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = load_script()
    calls: list[str] = []
    monkeypatch.setattr(script, "get_settings", lambda: calls.append("settings"))

    with pytest.raises(SystemExit):
        script.main([])

    assert calls == []


def test_cli_uses_fixed_matrix_and_prints_no_secret(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    script = load_script()
    calls: list[object] = []
    fake_report = SimpleNamespace(
        metrics=SimpleNamespace(live_development_passed=True),
        model_dump=lambda **_: {
            "mode": "SYNTHETIC_DEVELOPMENT_NOT_RELEASE",
            "metrics": {"live_development_passed": True},
        },
    )
    monkeypatch.setattr(script, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(script, "validate_development_provider_settings", lambda settings: None)
    monkeypatch.setattr(script, "load_atomic_synthetic_cases", lambda path: tuple(range(20)))
    monkeypatch.setattr(script, "OpenAIStructuredCaseIntakeExtractor", lambda settings: object())

    async def fake_run(*args: object, **kwargs: object) -> object:
        calls.extend((args, kwargs))
        return fake_report

    monkeypatch.setattr(script, "run_atomic_synthetic_development", fake_run)

    result = script.main(
        [
            "--repo-root",
            str(tmp_path),
            "--run-id",
            "synthetic-live-1",
            "--live-development",
            "--acknowledge-not-release",
            "SYNTHETIC_DEVELOPMENT_NOT_RELEASE",
        ]
    )

    assert result == 0
    assert calls
    output = capsys.readouterr().out
    assert json.loads(output)["mode"] == "SYNTHETIC_DEVELOPMENT_NOT_RELEASE"
    assert "api_key" not in output.casefold()
    assert "authorization" not in output.casefold()
