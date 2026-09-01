"""Post-RC2 development regression stays separate from immutable release evidence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import SecretStr

from tests.unit.evaluation.rc2_synthetic_support import (
    perfect_records,
    registered_thresholds,
    synthetic_cases,
)
from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.decision_support.models import (
    CaseIntakeInput,
    CaseIntakeResult,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_development import (
    DevelopmentArtifactPaths,
    build_rc2_regression_identity,
    run_post_rc2_development_regression,
    validate_development_provider_settings,
)

NOW = datetime(2026, 9, 1, 18, 0, tzinfo=timezone(timedelta(hours=7)))


def exact_settings(**updates: object) -> Settings:
    payload: dict[str, object] = {
        "openai_api_key": SecretStr("development-test-key"),
        "openai_base_url": "https://api.mistral.ai/v1",
        "llm_model": "mistral-small-2603",
        "llm_provider": "openai",
        "llm_timeout_seconds": 60,
        "llm_max_retries": 2,
        "agent_structured_output_max_retries": 2,
    }
    payload.update(updates)
    return Settings.model_validate(payload)


class RecordingExtractor:
    def __init__(self, results: dict[str, CaseIntakeResult]) -> None:
        self.results = results
        self.calls: list[CaseIntakeInput] = []

    async def extract(self, case_input: CaseIntakeInput) -> CaseIntakeResult:
        self.calls.append(case_input)
        return self.results[case_input.source_ref]


def test_regression_identity_marks_old_cases_as_development_not_holdout() -> None:
    identity = build_rc2_regression_identity("a" * 64)

    assert identity.case_count == 26
    assert identity.governance_classification == "RC2_REGRESSION_DIAGNOSTIC_SET"
    assert identity.blind_holdout is False
    assert identity.regression_use_allowed is True
    assert identity.historical_rc2_artifacts_mutable is False
    assert identity.historical_prediction_sha256 == (
        "6f2c113afc7270135c519ebebf265f866e2e38518d26a8cacb281a6570ce1d76"
    )


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        (
            {
                "llm_provider": "gemini_openai_compatible",
                "openai_base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
            },
            "provider",
        ),
        ({"llm_model": "mistral-small-latest"}, "model"),
        ({"openai_base_url": "https://api.openai.com/v1"}, "base URL"),
        ({"llm_timeout_seconds": 61}, "timeout"),
        ({"llm_max_retries": 1}, "SDK retries"),
        ({"agent_structured_output_max_retries": 1}, "structured retries"),
    ],
)
def test_development_provider_settings_are_exact_and_fail_closed(
    updates: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_development_provider_settings(exact_settings(**updates))


def test_development_provider_requires_a_configured_key_without_exposing_it() -> None:
    with pytest.raises(ValueError, match="API key"):
        validate_development_provider_settings(exact_settings(openai_api_key=None))


@pytest.mark.asyncio
async def test_development_runner_is_label_isolated_paced_and_writes_no_release_claim(
    tmp_path: Path,
) -> None:
    cases = synthetic_cases()
    records = perfect_records(cases)
    extractor = RecordingExtractor(
        {
            case.source_ref: record.result
            for case, record in zip(cases, records, strict=True)
            if record.result is not None
        }
    )
    pauses: list[float] = []
    paths = DevelopmentArtifactPaths.from_output_dir(tmp_path / "development-run")

    report = await run_post_rc2_development_regression(
        cases,
        exact_settings(),
        registered_thresholds(),
        paths,
        extractor=extractor,
        dataset_sha256="a" * 64,
        run_id="post-rc2-synthetic-pass",
        started_at=NOW,
        completed_at=None,
        now=lambda: NOW + timedelta(minutes=1),
        sleep=lambda seconds: _record_pause(pauses, seconds),
    )

    assert len(extractor.calls) == 26
    assert all(type(item) is CaseIntakeInput for item in extractor.calls)
    assert pauses == [1.0] * 25
    assert report.mode == "DEVELOPMENT_REGRESSION_NOT_RELEASE"
    assert report.governance_classification == "RC2_REGRESSION_DIAGNOSTIC_SET"
    assert report.release_decision_emitted is False
    assert report.success_count == 26
    assert report.failure_count == 0
    assert report.completed_at == NOW + timedelta(minutes=1)
    assert len(report.prompt_sha256) == 64
    assert report.compliance.canonical_fact_key_compliance == 1.0
    assert report.compliance.canonical_fact_type_compliance == 1.0
    assert report.compliance.invalid_unregistered_key_rate == 0.0
    assert report.compliance.source_grounding_accuracy == 1.0
    assert report.compliance.zero_expected_fact_cases_with_positive_facts == ()
    assert report.intake_subset_metrics.overall_fact_f1 == 1.0
    assert report.full_metrics.candidate_issue_macro_f1 == 1.0
    assert report.pipeline_exit_criteria_passed is True
    assert paths.predictions.is_file()
    assert paths.derived_predictions.is_file()
    assert paths.report.is_file()
    prediction_bytes = paths.predictions.read_text(encoding="utf-8")
    assert "expected_case_facts" not in prediction_bytes
    assert "critical_fact_ids" not in prediction_bytes
    assert "threshold" not in prediction_bytes
    assert "RELEASE_PASS" not in paths.report.read_text(encoding="utf-8")

    with pytest.raises(FileExistsError):
        await run_post_rc2_development_regression(
            cases,
            exact_settings(),
            registered_thresholds(),
            paths,
            extractor=extractor,
            dataset_sha256="a" * 64,
            run_id="post-rc2-synthetic-pass",
            started_at=NOW,
            completed_at=NOW + timedelta(minutes=1),
            sleep=lambda seconds: _record_pause(pauses, seconds),
        )


@pytest.mark.asyncio
async def test_development_runner_rejects_historical_release_namespace_before_calls(
    tmp_path: Path,
) -> None:
    cases = synthetic_cases()
    records = perfect_records(cases)
    extractor = RecordingExtractor(
        {
            case.source_ref: record.result
            for case, record in zip(cases, records, strict=True)
            if record.result is not None
        }
    )
    paths = DevelopmentArtifactPaths.from_output_dir(
        tmp_path
        / "evaluation"
        / "results"
        / "decision_support"
        / "v1_1"
        / "rc2"
        / "development-run"
    )

    with pytest.raises(ValueError, match="historical release namespace"):
        await run_post_rc2_development_regression(
            cases,
            exact_settings(),
            registered_thresholds(),
            paths,
            extractor=extractor,
            dataset_sha256="a" * 64,
            run_id="post-rc2-protected-path",
            started_at=NOW,
            completed_at=NOW + timedelta(minutes=1),
            sleep=lambda _: _no_pause(),
        )
    assert extractor.calls == []


async def _record_pause(pauses: list[float], seconds: float) -> None:
    pauses.append(seconds)


async def _no_pause() -> None:
    return None
