from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.unit.evaluation.rc2_synthetic_support import (
    perfect_records,
    registered_thresholds,
    synthetic_cases,
)
from tests.unit.evaluation.test_decision_support_v1_1_rc2_capture_lifecycle import (
    registration,
    settings,
)
from tests.unit.evaluation.test_decision_support_v1_1_rc2_release import (
    METRIC_DEFINITIONS,
)
from vietnamese_labor_law_assistant.decision_support.intake import CaseIntakeError
from vietnamese_labor_law_assistant.decision_support.models import (
    CandidateIssue,
    CaseIntakeInput,
    CaseIntakeResult,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_capture import (
    V11RuntimeCase,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2 import (
    RC2ArtifactPaths,
    RC2RegistrationPlan,
    write_rc2_registration_v2,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2_capture import (
    run_or_resume_rc2_capture,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 9, 1, 15, 0, tzinfo=timezone(timedelta(hours=7)))


class SyntheticExtractor:
    def __init__(
        self,
        results: dict[str, CaseIntakeResult],
        *,
        fail_source_ref: str | None = None,
    ) -> None:
        self.results = results
        self.fail_source_ref = fail_source_ref

    async def extract(self, case_input: CaseIntakeInput) -> CaseIntakeResult:
        if case_input.source_ref == self.fail_source_ref:
            raise CaseIntakeError("CASE_INTAKE_PROVIDER_ERROR")
        return self.results[case_input.source_ref]


@pytest.mark.asyncio
@pytest.mark.parametrize(("fail_first", "expected"), ((False, "PASS"), (True, "FAIL")))
async def test_complete_synthetic_release_dry_run_is_offline_and_temporary(
    fail_first: bool,
    expected: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vietnamese_labor_law_assistant.evaluation import (
        decision_support_v1_1_rc2_release as release_module,
    )

    paths = RC2ArtifactPaths.from_root(tmp_path)
    paths.registration_revision_1.parent.mkdir(parents=True)
    revision_1 = (
        PROJECT_ROOT / "evaluation/results/decision_support/v1_1/rc2/rc2_capture_manifest.json"
    )
    paths.registration_revision_1.write_bytes(revision_1.read_bytes())
    registered = registration(paths)
    write_rc2_registration_v2(paths, registered)

    cases = synthetic_cases()
    runtime = tuple(
        V11RuntimeCase(
            case_id=case.case_id,
            case_input=CaseIntakeInput(
                source_text=case.raw_user_input,
                source_ref=case.source_ref,
            ),
        )
        for case in cases
    )
    perfect = perfect_records(cases)
    results = {
        case.source_ref: CaseIntakeResult(
            facts=list(record.result.facts if record.result is not None else ()),
            candidate_issues=[
                CandidateIssue(issue_code=issue.issue_code)
                for issue in (record.result.candidate_issues if record.result is not None else ())
            ],
        )
        for case, record in zip(cases, perfect, strict=True)
    }
    extractor = SyntheticExtractor(
        results,
        fail_source_ref=cases[0].source_ref if fail_first else None,
    )
    await run_or_resume_rc2_capture(
        paths,
        registered,
        runtime,
        settings(),
        extractor_factory=lambda _: extractor,
        sleep=lambda _: _no_sleep(),
        now=lambda: NOW,
        run_id_factory=lambda: "run-synthetic-e2e",
    )
    monkeypatch.setattr(
        release_module,
        "load_rc2_registration_v2_offline",
        lambda _: RC2RegistrationPlan(registration=registered, runtime_cases=runtime),
    )
    monkeypatch.setattr(release_module, "load_v1_1_frozen_dataset", lambda _: cases)
    monkeypatch.setattr(
        release_module,
        "load_v1_1_threshold_spec",
        lambda *_, **__: SimpleNamespace(
            thresholds=registered_thresholds(),
            metric_definitions=METRIC_DEFINITIONS,
        ),
    )
    terminal = release_module.evaluate_registered_rc2_release(
        paths,
        evaluated_at=NOW + timedelta(minutes=1),
    )

    assert terminal.final_result == expected
    assert terminal.lifecycle_state == f"RELEASE_{expected}"
    assert paths.release_report.is_file()
    assert paths.evaluation_completed.is_file()
    assert paths.release_terminal.is_file()
    assert not (
        PROJECT_ROOT
        / "evaluation/results/decision_support/v1_1/rc2/rc2_production_predictions.jsonl"
    ).exists()


@pytest.mark.asyncio
async def test_registered_release_facade_enforces_full_identity_before_labels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vietnamese_labor_law_assistant.evaluation import (
        decision_support_v1_1_rc2_release as release_module,
    )

    paths = RC2ArtifactPaths.from_root(tmp_path)
    paths.registration_revision_1.parent.mkdir(parents=True)
    revision_1 = (
        PROJECT_ROOT / "evaluation/results/decision_support/v1_1/rc2/rc2_capture_manifest.json"
    )
    paths.registration_revision_1.write_bytes(revision_1.read_bytes())
    registered = registration(paths)
    write_rc2_registration_v2(paths, registered)
    cases = synthetic_cases()
    runtime = tuple(
        V11RuntimeCase(
            case_id=case.case_id,
            case_input=CaseIntakeInput(
                source_text=case.raw_user_input,
                source_ref=case.source_ref,
            ),
        )
        for case in cases
    )
    perfect = perfect_records(cases)
    results = {
        case.source_ref: CaseIntakeResult(
            facts=list(record.result.facts if record.result is not None else ()),
            candidate_issues=[
                CandidateIssue(issue_code=issue.issue_code)
                for issue in (record.result.candidate_issues if record.result is not None else ())
            ],
        )
        for case, record in zip(cases, perfect, strict=True)
    }
    await run_or_resume_rc2_capture(
        paths,
        registered,
        runtime,
        settings(),
        extractor_factory=lambda _: SyntheticExtractor(results),
        sleep=lambda _: _no_sleep(),
        now=lambda: NOW,
        run_id_factory=lambda: "run-synthetic-facade",
    )
    labels_loaded: list[bool] = []
    full_loader_called: list[bool] = []

    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_artifacts import (
        canonical_json_bytes,
    )
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2_capture import (
        RC2CaptureCompleted,
    )

    original_completion = paths.capture_completed.read_bytes()
    completion = RC2CaptureCompleted.model_validate_json(original_completion)
    paths.capture_completed.write_bytes(
        canonical_json_bytes(
            completion.model_copy(update={"prediction_metadata_sha256": "0" * 64}).model_dump(
                mode="json"
            )
        )
    )

    def loader_must_not_run(_: RC2ArtifactPaths):
        full_loader_called.append(True)
        raise AssertionError("full loader ran before capture-chain validation")

    monkeypatch.setattr(
        release_module,
        "load_rc2_registration_v2_offline",
        loader_must_not_run,
    )
    with pytest.raises(ValueError, match="different prediction metadata"):
        release_module.evaluate_registered_rc2_release(paths, evaluated_at=NOW)
    assert full_loader_called == []
    paths.capture_completed.write_bytes(original_completion)

    def reject_changed_code(_: RC2ArtifactPaths):
        raise ValueError("synthetic registered code identity changed")

    def forbidden_label_load(_: Path):
        labels_loaded.append(True)
        raise AssertionError("labels became reachable before full identity validation")

    monkeypatch.setattr(
        release_module,
        "load_rc2_registration_v2_offline",
        reject_changed_code,
        raising=False,
    )
    monkeypatch.setattr(
        release_module,
        "load_v1_1_frozen_dataset",
        forbidden_label_load,
    )

    with pytest.raises(ValueError, match="registered code identity changed"):
        release_module.evaluate_registered_rc2_release(paths, evaluated_at=NOW)
    assert labels_loaded == []


async def _no_sleep() -> None:
    return None
