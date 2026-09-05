"""Offline CLI contracts for Hybrid Fact V2 development runs."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from vietnamese_labor_law_assistant.evaluation import (
    decision_support_hybrid_fact_development as hybrid_development,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ACKNOWLEDGEMENT = "HYBRID_FACT_V2_SYNTHETIC_NOT_RELEASE"


def load_script() -> ModuleType:
    path = PROJECT_ROOT / "scripts/run_decision_support_hybrid_fact_development.py"
    specification = importlib.util.spec_from_file_location("hybrid_fact_script", path)
    if specification is None or specification.loader is None:
        pytest.fail("the Hybrid Fact V2 development adapter is missing")
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


def test_cli_uses_only_fixed_matrix_and_new_hybrid_run_namespace(
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
            "release_holdout_accessed": False,
            "gates": {"overall_passed": True},
        },
    )
    monkeypatch.setattr(script, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(
        script.hybrid_development, "validate_hybrid_provider_settings", lambda _: None
    )
    monkeypatch.setattr(
        script.split_development,
        "load_split_inference_synthetic_cases",
        lambda _: tuple(range(28)),
    )
    monkeypatch.setattr(script, "OpenAIStructuredCaseIntakeExtractor", lambda _: object())

    async def fake_run(*args: object, **kwargs: object) -> object:
        calls.extend((args, kwargs))
        return fake_report

    monkeypatch.setattr(script.hybrid_development, "run_hybrid_fact_development", fake_run)

    result = script.main(
        [
            "--repo-root",
            str(tmp_path),
            "--run-id",
            "hybrid-fact-v2-live-1",
            "--live-development",
            "--acknowledge-not-release",
            ACKNOWLEDGEMENT,
        ]
    )

    assert result == 0
    run_args = calls[0]
    assert isinstance(run_args, tuple)
    paths = run_args[2]
    assert isinstance(paths, hybrid_development.HybridFactArtifactPaths)
    assert paths.output_dir == (
        tmp_path.resolve() / "evaluation/development/decision_support/v1_1/post_rc2/runs/"
        "hybrid-fact-v2-live-1"
    )
    run_kwargs = calls[1]
    assert isinstance(run_kwargs, dict)
    assert run_kwargs["matrix_path"] == (
        tmp_path.resolve() / "evaluation/development/decision_support/v1_1/post_rc2/"
        "split_inference_synthetic_v1.jsonl"
    )
    output = json.loads(capsys.readouterr().out)
    assert output["old26_executed"] is False
    assert output["release_holdout_accessed"] is False
    assert "api_key" not in str(output).casefold()
