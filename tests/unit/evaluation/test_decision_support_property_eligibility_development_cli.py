from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from vietnamese_labor_law_assistant.evaluation.decision_support_atomic_development import (
    PropertyEligibilityArtifactPaths,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def load_script() -> ModuleType:
    path = PROJECT_ROOT / "scripts/run_decision_support_property_eligibility_development.py"
    specification = importlib.util.spec_from_file_location("property_development_script", path)
    if specification is None or specification.loader is None:
        pytest.fail("the property-eligibility development adapter is missing")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_cli_requires_explicit_property_non_release_acknowledgement_before_settings(
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
                "PROPERTY_ELIGIBILITY_SYNTHETIC_NOT_RELEASE",
            ]
        )

    assert calls == []


def test_cli_uses_fixed_thirty_case_matrix_and_prints_no_secret(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    script = load_script()
    calls: list[object] = []
    fake_report = SimpleNamespace(
        metrics=SimpleNamespace(live_development_passed=True),
        model_dump=lambda **_: {
            "mode": "PROPERTY_ELIGIBILITY_SYNTHETIC_NOT_RELEASE",
            "metrics": {"live_development_passed": True},
        },
    )
    monkeypatch.setattr(script, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(script, "validate_development_provider_settings", lambda settings: None)
    monkeypatch.setattr(
        script,
        "load_property_eligibility_synthetic_cases",
        lambda path: tuple(range(30)),
    )
    monkeypatch.setattr(script, "OpenAIStructuredCaseIntakeExtractor", lambda settings: object())

    async def fake_run(*args: object, **kwargs: object) -> object:
        calls.extend((args, kwargs))
        return fake_report

    monkeypatch.setattr(script, "run_property_eligibility_synthetic_development", fake_run)

    result = script.main(
        [
            "--repo-root",
            str(tmp_path),
            "--run-id",
            "property-live-1",
            "--live-development",
            "--acknowledge-not-release",
            "PROPERTY_ELIGIBILITY_SYNTHETIC_NOT_RELEASE",
        ]
    )

    assert result == 0
    assert calls
    run_args = calls[0]
    assert isinstance(run_args, tuple)
    paths = run_args[2]
    assert isinstance(paths, PropertyEligibilityArtifactPaths)
    assert paths.output_dir == (
        tmp_path.resolve()
        / "evaluation/development/decision_support/v1_1/post_rc2/runs/property-live-1"
    )
    output = capsys.readouterr().out
    assert json.loads(output)["mode"] == "PROPERTY_ELIGIBILITY_SYNTHETIC_NOT_RELEASE"
    assert "api_key" not in output.casefold()
    assert "authorization" not in output.casefold()
