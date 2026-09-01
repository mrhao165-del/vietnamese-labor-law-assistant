from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from vietnamese_labor_law_assistant.evaluation import (
    decision_support_split_inference_development as split_development,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ACKNOWLEDGEMENT = "SPLIT_INFERENCE_SYNTHETIC_NOT_RELEASE"


def load_script() -> ModuleType:
    path = PROJECT_ROOT / "scripts/run_decision_support_split_inference_development.py"
    specification = importlib.util.spec_from_file_location("split_inference_script", path)
    if specification is None or specification.loader is None:
        pytest.fail("the split-inference development adapter is missing")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_cli_requires_non_release_acknowledgement_before_loading_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = load_script()
    calls: list[str] = []
    monkeypatch.setattr(script, "get_settings", lambda: calls.append("settings"))

    with pytest.raises(SystemExit):
        script.main([])

    assert calls == []


def test_cli_uses_only_the_fixed_split_development_namespace(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    script = load_script()
    calls: list[object] = []
    fake_report = SimpleNamespace(
        gates=SimpleNamespace(overall_passed=True),
        model_dump=lambda **_: {
            "mode": ACKNOWLEDGEMENT,
            "old26_executed": False,
            "gates": {"overall_passed": True},
        },
    )
    monkeypatch.setattr(script, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(script, "validate_development_provider_settings", lambda settings: None)
    monkeypatch.setattr(
        script.split_development,
        "load_split_inference_synthetic_cases",
        lambda path: tuple(range(28)),
    )
    monkeypatch.setattr(script, "OpenAIStructuredCaseIntakeExtractor", lambda settings: object())

    async def fake_run(*args: object, **kwargs: object) -> object:
        calls.extend((args, kwargs))
        return fake_report

    monkeypatch.setattr(
        script.split_development,
        "run_split_inference_synthetic_development",
        fake_run,
    )

    result = script.main(
        [
            "--repo-root",
            str(tmp_path),
            "--run-id",
            "split-live-1",
            "--live-development",
            "--acknowledge-not-release",
            ACKNOWLEDGEMENT,
        ]
    )

    assert result == 0
    run_args = calls[0]
    assert isinstance(run_args, tuple)
    paths = run_args[2]
    assert isinstance(paths, split_development.SplitInferenceArtifactPaths)
    assert paths.output_dir == (
        tmp_path.resolve()
        / "evaluation/development/decision_support/v1_1/post_rc2/runs/split-live-1"
    )
    run_kwargs = calls[1]
    assert isinstance(run_kwargs, dict)
    assert run_kwargs["matrix_path"] == (
        tmp_path.resolve() / "evaluation/development/decision_support/v1_1/post_rc2/"
        "split_inference_synthetic_v1.jsonl"
    )
    output = capsys.readouterr().out
    assert json.loads(output)["old26_executed"] is False
    assert "api_key" not in output.casefold()
