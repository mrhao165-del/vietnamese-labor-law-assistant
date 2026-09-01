from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from vietnamese_labor_law_assistant.evaluation import (
    decision_support_fact_value_eligibility_development as fact_value_development,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ACKNOWLEDGEMENT = "FACT_VALUE_ELIGIBILITY_SYNTHETIC_NOT_RELEASE"


def load_script() -> ModuleType:
    path = PROJECT_ROOT / "scripts/run_decision_support_fact_value_eligibility_development.py"
    specification = importlib.util.spec_from_file_location("fact_value_eligibility_script", path)
    if specification is None or specification.loader is None:
        pytest.fail("the fact-value eligibility development adapter is missing")
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
                ACKNOWLEDGEMENT,
            ]
        )

    assert calls == []


def test_cli_reports_invalid_provider_configuration_without_its_detail(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = load_script()
    monkeypatch.setattr(script, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(
        script,
        "validate_development_provider_settings",
        lambda settings: (_ for _ in ()).throw(ValueError("api_key=secret-value")),
    )

    with pytest.raises(SystemExit):
        script.main(
            [
                "--run-id",
                "invalid-config",
                "--live-development",
                "--acknowledge-not-release",
                ACKNOWLEDGEMENT,
            ]
        )

    error = capsys.readouterr().err
    assert "development provider configuration is invalid" in error
    assert "secret-value" not in error


def test_cli_uses_fixed_matrix_development_namespace_and_prints_no_secret(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    script = load_script()
    calls: list[object] = []
    fake_report = SimpleNamespace(
        gates=SimpleNamespace(overall_passed=True),
        metrics=SimpleNamespace(),
        model_dump=lambda **_: {
            "mode": ACKNOWLEDGEMENT,
            "gates": {"overall_passed": True},
        },
    )
    monkeypatch.setattr(script, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(script, "validate_development_provider_settings", lambda settings: None)
    monkeypatch.setattr(
        script.fact_value_development,
        "load_fact_value_eligibility_synthetic_cases",
        lambda path: tuple(range(28)),
    )
    monkeypatch.setattr(script, "OpenAIStructuredCaseIntakeExtractor", lambda settings: object())

    async def fake_run(*args: object, **kwargs: object) -> object:
        calls.extend((args, kwargs))
        return fake_report

    monkeypatch.setattr(
        script.fact_value_development,
        "run_fact_value_eligibility_synthetic_development",
        fake_run,
    )

    result = script.main(
        [
            "--repo-root",
            str(tmp_path),
            "--run-id",
            "fact-value-live-1",
            "--live-development",
            "--acknowledge-not-release",
            ACKNOWLEDGEMENT,
        ]
    )

    assert result == 0
    assert calls
    run_args = calls[0]
    assert isinstance(run_args, tuple)
    paths = run_args[2]
    assert isinstance(paths, fact_value_development.FactValueEligibilityArtifactPaths)
    assert paths.output_dir == (
        tmp_path.resolve()
        / "evaluation/development/decision_support/v1_1/post_rc2/runs/fact-value-live-1"
    )
    assert run_args[0] == tuple(range(28))
    run_kwargs = calls[1]
    assert isinstance(run_kwargs, dict)
    assert run_kwargs["matrix_path"] == (
        tmp_path.resolve() / "evaluation/development/decision_support/v1_1/post_rc2/"
        "fact_value_eligibility_synthetic_v1.jsonl"
    )
    output = capsys.readouterr().out
    assert json.loads(output)["mode"] == ACKNOWLEDGEMENT
    assert "api_key" not in output.casefold()
    assert "authorization" not in output.casefold()
