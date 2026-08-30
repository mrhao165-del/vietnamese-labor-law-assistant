from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _load_script(relative_path: str, module_name: str) -> ModuleType:
    specification = importlib.util.spec_from_file_location(
        module_name,
        PROJECT_ROOT / relative_path,
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_capture_defaults_to_offline_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_script(
        "scripts/capture_decision_support_v1_1_predictions.py",
        "capture_decision_support_v1_1_predictions_preflight",
    )
    calls: list[str] = []
    plan = SimpleNamespace(
        case_count=26,
        frozen_dataset_sha256="a" * 64,
        freeze_manifest_sha256="b" * 64,
        git_commit_sha="c" * 40,
        extractor_class="production.Extractor",
        generation_settings=SimpleNamespace(
            provider="openai",
            model="model-id",
            nominal_parse_calls=26,
            maximum_parse_invocations=78,
            theoretical_maximum_http_attempts=234,
        ),
    )
    monkeypatch.setattr(module, "get_settings", lambda: object())
    monkeypatch.setattr(module, "preflight_v1_1_capture", lambda *args, **kwargs: plan)

    async def fail_if_live(*args: object, **kwargs: object) -> object:
        calls.append("live")
        raise AssertionError("offline preflight must not execute capture")

    monkeypatch.setattr(module, "capture_v1_1_predictions", fail_if_live)

    assert module.main(["--project-author-name", "mrhao165-del"]) == 0
    assert calls == []


def test_capture_requires_exact_write_once_confirmation_before_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script(
        "scripts/capture_decision_support_v1_1_predictions.py",
        "capture_decision_support_v1_1_predictions_confirmation",
    )
    calls: list[str] = []
    monkeypatch.setattr(module, "get_settings", lambda: calls.append("settings"))
    monkeypatch.setattr(
        module,
        "preflight_v1_1_capture",
        lambda *args, **kwargs: calls.append("preflight"),
    )

    with pytest.raises(SystemExit):
        module.main(["--project-author-name", "mrhao165-del", "--live"])

    assert calls == []


def test_freeze_requires_explicit_acknowledgement_before_writing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script(
        "scripts/freeze_decision_support_v1_1.py",
        "freeze_decision_support_v1_1_confirmation",
    )
    calls: list[str] = []
    monkeypatch.setattr(
        module,
        "freeze_v1_1_evaluation",
        lambda *args, **kwargs: calls.append("freeze"),
    )

    with pytest.raises(SystemExit):
        module.main(["--project-author-name", "mrhao165-del"])

    assert calls == []


def test_final_evaluation_requires_explicit_acknowledgement_before_writing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script(
        "scripts/run_decision_support_v1_1_final_evaluation.py",
        "run_decision_support_v1_1_final_evaluation_confirmation",
    )
    calls: list[str] = []
    monkeypatch.setattr(
        module,
        "evaluate_frozen_v1_1_release",
        lambda *args, **kwargs: calls.append("evaluate"),
    )

    with pytest.raises(SystemExit):
        module.main([])

    assert calls == []


def test_final_evaluation_uses_only_canonical_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_script(
        "scripts/run_decision_support_v1_1_final_evaluation.py",
        "run_decision_support_v1_1_final_evaluation_paths",
    )
    calls: list[tuple[Any, Any]] = []
    result = SimpleNamespace(status="FAIL", failed_sample_count=1)
    monkeypatch.setattr(
        module,
        "evaluate_frozen_v1_1_release",
        lambda governed, outputs: calls.append((governed, outputs)) or result,
    )

    assert (
        module.main(
            [
                "--repo-root",
                str(tmp_path),
                "--evaluate-frozen-v1-1",
            ]
        )
        == 0
    )
    assert len(calls) == 1
    governed, outputs = calls[0]
    assert governed.repo_root == tmp_path.resolve()
    assert outputs.repo_root == tmp_path.resolve()


def test_preflight_report_contains_only_non_secret_capture_metadata() -> None:
    module = _load_script(
        "scripts/capture_decision_support_v1_1_predictions.py",
        "capture_decision_support_v1_1_predictions_report",
    )
    plan = SimpleNamespace(
        case_count=26,
        frozen_dataset_sha256="a" * 64,
        freeze_manifest_sha256="b" * 64,
        git_commit_sha="c" * 40,
        extractor_class="production.Extractor",
        generation_settings=SimpleNamespace(
            provider="gemini_openai_compatible",
            model="gemini-model",
            nominal_parse_calls=26,
            maximum_parse_invocations=78,
            theoretical_maximum_http_attempts=234,
        ),
    )

    serialized = json.dumps(module._preflight_report(plan), sort_keys=True)

    assert "secret" not in serialized.casefold()
    assert "api_key" not in serialized.casefold()
    assert "authorization" not in serialized.casefold()
    assert '"case_count": 26' in serialized
    assert '"maximum_parse_invocations": 78' in serialized


@pytest.mark.parametrize(
    "unsupported_option",
    ("--candidate", "--predictions", "--output", "--threshold-spec"),
)
def test_capture_exposes_no_governed_artifact_path_override(
    unsupported_option: str,
) -> None:
    module = _load_script(
        "scripts/capture_decision_support_v1_1_predictions.py",
        f"capture_decision_support_v1_1_predictions_{unsupported_option[2:]}",
    )

    with pytest.raises(SystemExit):
        module.main(
            [
                "--project-author-name",
                "mrhao165-del",
                unsupported_option,
                "elsewhere.json",
            ]
        )
