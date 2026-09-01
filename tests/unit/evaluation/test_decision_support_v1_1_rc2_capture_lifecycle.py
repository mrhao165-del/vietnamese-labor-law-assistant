from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NoReturn

import pytest
from pydantic import SecretStr

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.decision_support.models import (
    CaseIntakeInput,
    CaseIntakeResult,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_artifacts import (
    sha256_bytes,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_capture import (
    V11PredictionFailureReason,
    V11RuntimeCase,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2 import (
    RC2ArtifactPaths,
    RC2CodeIdentities,
    RC2GenerationConfig,
    RC2RegisteredPathsV2,
    RC2RegistrationV2,
    RC2SupersededRegistration,
    write_rc2_registration_v2,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 9, 1, 9, 0, tzinfo=timezone(timedelta(hours=7)))


def settings(*, model: str = "mistral-small-2603") -> Settings:
    return Settings(
        openai_api_key=SecretStr("offline-test-secret"),
        llm_provider="openai",
        llm_model=model,
        openai_base_url="https://api.mistral.ai/v1",
        llm_timeout_seconds=60,
        llm_max_retries=2,
        agent_structured_output_max_retries=2,
    )


def runtime_cases() -> tuple[V11RuntimeCase, ...]:
    return tuple(
        V11RuntimeCase(
            case_id=f"synthetic-{sequence:03d}",
            case_input=CaseIntakeInput(
                source_text=f"Synthetic non-frozen case {sequence}.",
                source_ref=f"user_message:synthetic_{sequence:03d}",
            ),
        )
        for sequence in range(1, 27)
    )


def registration(paths: RC2ArtifactPaths) -> RC2RegistrationV2:
    return RC2RegistrationV2(
        supersedes=RC2SupersededRegistration(
            registration_path=paths.registration_revision_1.relative_to(paths.repo_root).as_posix(),
            registration_sha256=(
                "7561fad80e75d0cea84f144471596cb7ae31cd70b6786ac4e410fe814e3e30ac"
            ),
        ),
        implementation_commit_sha="a" * 40,
        frozen_dataset_sha256="9" * 64,
        human_review_sha256="a" * 64,
        threshold_sha256="b" * 64,
        parent_artifact_sha256={
            "capture_intent": "37ac396778226f84efdb655003e2cd738def7650c0904f65c142fd28cfe4e0f9",
            "predictions": "d59815facf4c3360dba5c8471f446de3262ddeca42f6e25adad3268a60a44d9a",
            "snapshot_manifest": (
                "4ea2d90d03eff5db5b4d972d487508b07b88ef1274050641973089ba11a86415"
            ),
        },
        code_identities=RC2CodeIdentities(
            registration_sha256="1" * 64,
            capture_runner_sha256="2" * 64,
            journal_finalizer_sha256="3" * 64,
            offline_evaluator_sha256="4" * 64,
            metrics_producer_sha256="4" * 64,
            report_producer_sha256="4" * 64,
            extractor_sha256="5" * 64,
            prompt_sha256="6" * 64,
            canonical_schema_sha256="7" * 64,
            transport_schema_sha256="8" * 64,
        ),
        generation_config=RC2GenerationConfig(),
        paths=RC2RegisteredPathsV2.from_artifact_paths(paths),
    )


def prepared_paths(tmp_path: Path) -> tuple[RC2ArtifactPaths, RC2RegistrationV2]:
    paths = RC2ArtifactPaths.from_root(tmp_path)
    paths.registration_revision_1.parent.mkdir(parents=True)
    revision_1 = (
        PROJECT_ROOT / "evaluation/results/decision_support/v1_1/rc2/rc2_capture_manifest.json"
    )
    paths.registration_revision_1.write_bytes(revision_1.read_bytes())
    registered = registration(paths)
    write_rc2_registration_v2(paths, registered)
    return paths, registered


class SuccessfulExtractor:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    async def extract(self, case_input: CaseIntakeInput) -> CaseIntakeResult:
        self.calls.append(case_input.source_ref)
        return CaseIntakeResult()


def test_extractor_construction_failure_precedes_start_and_final_paths(tmp_path: Path) -> None:
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2_capture import (
        initialize_rc2_capture,
    )

    paths, registered = prepared_paths(tmp_path)

    def fail_construction(_: Settings) -> NoReturn:
        raise RuntimeError("synthetic constructor failure")

    with pytest.raises(RuntimeError, match="constructor failure"):
        initialize_rc2_capture(
            paths,
            registered,
            runtime_cases(),
            settings(),
            extractor_factory=fail_construction,
            now=lambda: NOW,
            run_id_factory=lambda: "run-synthetic-001",
        )

    assert not paths.capture_started.exists()
    assert not paths.capture_journal.exists()
    assert not paths.predictions.exists()
    assert not paths.prediction_metadata.exists()
    assert not paths.capture_completed.exists()


def test_output_namespace_conflict_blocks_before_extractor_construction(tmp_path: Path) -> None:
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2_capture import (
        initialize_rc2_capture,
    )

    paths, registered = prepared_paths(tmp_path)
    paths.predictions.write_bytes(b"claimed")
    constructed: list[str] = []

    def construct(_: Settings) -> SuccessfulExtractor:
        constructed.append("constructed")
        return SuccessfulExtractor([])

    with pytest.raises(FileExistsError, match="output namespace"):
        initialize_rc2_capture(
            paths,
            registered,
            runtime_cases(),
            settings(),
            extractor_factory=construct,
        )

    assert constructed == []


def test_journal_availability_is_probed_before_extractor_and_capture_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vietnamese_labor_law_assistant.evaluation import (
        decision_support_v1_1_rc2_capture as capture_module,
    )

    paths, registered = prepared_paths(tmp_path)
    constructed: list[str] = []

    def unavailable(_: Path) -> NoReturn:
        raise OSError("synthetic journal unavailable")

    def construct(_: Settings) -> SuccessfulExtractor:
        constructed.append("constructed")
        return SuccessfulExtractor([])

    monkeypatch.setattr(
        capture_module,
        "_probe_journal_availability",
        unavailable,
        raising=False,
    )
    with pytest.raises(OSError, match="journal unavailable"):
        capture_module.initialize_rc2_capture(
            paths,
            registered,
            runtime_cases(),
            settings(),
            extractor_factory=construct,
        )

    assert constructed == []
    assert not paths.capture_started.exists()
    assert not paths.capture_journal.exists()
    assert not paths.predictions.exists()


def test_capture_start_publication_interruption_leaves_no_final_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vietnamese_labor_law_assistant.evaluation import (
        decision_support_v1_1_artifacts as artifacts_module,
    )
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2_capture import (
        initialize_rc2_capture,
    )

    paths, registered = prepared_paths(tmp_path)
    link = artifacts_module.os.link

    def interrupt(_: Path, destination: Path) -> None:
        if Path(destination) == paths.capture_started:
            raise OSError("synthetic capture-start interruption")
        link(_, destination)

    monkeypatch.setattr(artifacts_module.os, "link", interrupt)
    with pytest.raises(OSError, match="capture-start interruption"):
        initialize_rc2_capture(
            paths,
            registered,
            runtime_cases(),
            settings(),
            extractor_factory=lambda _: SuccessfulExtractor([]),
            now=lambda: NOW,
            run_id_factory=lambda: "run-atomic-start",
        )
    assert not paths.capture_started.exists()
    assert not paths.predictions.exists()

    monkeypatch.setattr(artifacts_module.os, "link", link)
    context = initialize_rc2_capture(
        paths,
        registered,
        runtime_cases(),
        settings(),
        extractor_factory=lambda _: SuccessfulExtractor([]),
        now=lambda: NOW,
        run_id_factory=lambda: "run-atomic-start",
    )
    assert context.started.capture_run_id == "run-atomic-start"


@pytest.mark.asyncio
async def test_journal_appends_success_and_typed_failure_without_labels(tmp_path: Path) -> None:
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2_capture import (
        RC2CaptureJournalEntry,
        append_rc2_journal_entry,
        initialize_rc2_capture,
        load_rc2_journal,
    )

    paths, registered = prepared_paths(tmp_path)
    cases = runtime_cases()
    context = initialize_rc2_capture(
        paths,
        registered,
        cases,
        settings(),
        extractor_factory=lambda _: SuccessfulExtractor([]),
        now=lambda: NOW,
        run_id_factory=lambda: "run-synthetic-001",
    )
    success = RC2CaptureJournalEntry(
        capture_run_id=context.started.capture_run_id,
        sequence=1,
        case_id=cases[0].case_id,
        terminal_result="SUCCESS",
        prediction=CaseIntakeResult(),
        provider="openai",
        model="mistral-small-2603",
        attempted_at=NOW,
    )
    failure = RC2CaptureJournalEntry(
        capture_run_id=context.started.capture_run_id,
        sequence=2,
        case_id=cases[1].case_id,
        terminal_result="FAILURE",
        failure_category=V11PredictionFailureReason.TIMEOUT,
        provider="openai",
        model="mistral-small-2603",
        attempted_at=NOW,
    )

    append_rc2_journal_entry(paths, context.started, cases, success)
    append_rc2_journal_entry(paths, context.started, cases, failure)

    observed = load_rc2_journal(paths, context.started, cases)
    assert observed == (success, failure)
    payload = paths.capture_journal.read_text(encoding="utf-8")
    assert "CASE_INTAKE_TIMEOUT" in payload
    for prohibited in (
        "expected_case_facts",
        "expected_candidate_issues",
        "expected_refined_issues",
        "reviewer_notes_reasoning",
        "thresholds",
        "offline-test-secret",
    ):
        assert prohibited not in payload

    with pytest.raises(ValueError, match="terminal journal entry already exists"):
        append_rc2_journal_entry(paths, context.started, cases, success)
    unknown = success.model_copy(update={"sequence": 3, "case_id": "synthetic-unknown"})
    with pytest.raises(ValueError, match="unknown case ID"):
        append_rc2_journal_entry(paths, context.started, cases, unknown)


class SimulatedCrash(BaseException):
    pass


class CrashAfterExtractor:
    def __init__(self, completed_before_crash: int, calls: list[str]) -> None:
        self.completed_before_crash = completed_before_crash
        self.calls = calls

    async def extract(self, case_input: CaseIntakeInput) -> CaseIntakeResult:
        if len(self.calls) == self.completed_before_crash:
            raise SimulatedCrash
        self.calls.append(case_input.source_ref)
        return CaseIntakeResult()


@pytest.mark.asyncio
@pytest.mark.parametrize("completed_before_crash", (1, 7, 25))
async def test_resume_retains_run_id_and_calls_only_unseen_cases(
    completed_before_crash: int,
    tmp_path: Path,
) -> None:
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2_capture import (
        load_rc2_capture_started,
        load_rc2_journal,
        run_or_resume_rc2_capture,
    )

    paths, registered = prepared_paths(tmp_path)
    cases = runtime_cases()
    first_calls: list[str] = []
    with pytest.raises(SimulatedCrash):
        await run_or_resume_rc2_capture(
            paths,
            registered,
            cases,
            settings(),
            extractor_factory=lambda _: CrashAfterExtractor(completed_before_crash, first_calls),
            sleep=lambda _: _no_sleep(),
            now=lambda: NOW,
            run_id_factory=lambda: "run-synthetic-001",
        )
    started_before = load_rc2_capture_started(paths, registered, cases)
    journal_before = load_rc2_journal(paths, started_before, cases)
    assert len(journal_before) == completed_before_crash

    resumed_calls: list[str] = []
    completed = await run_or_resume_rc2_capture(
        paths,
        registered,
        cases,
        settings(),
        extractor_factory=lambda _: SuccessfulExtractor(resumed_calls),
        sleep=lambda _: _no_sleep(),
        now=lambda: NOW + timedelta(minutes=1),
        run_id_factory=lambda: "must-not-replace-run-id",
    )

    assert completed.capture_run_id == started_before.capture_run_id == "run-synthetic-001"
    assert len(resumed_calls) == 26 - completed_before_crash
    assert set(resumed_calls).isdisjoint(first_calls)
    assert len(load_rc2_journal(paths, started_before, cases)) == 26


@pytest.mark.asyncio
async def test_crash_before_first_case_resumes_all_cases_with_same_run_id(tmp_path: Path) -> None:
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2_capture import (
        initialize_rc2_capture,
        run_or_resume_rc2_capture,
    )

    paths, registered = prepared_paths(tmp_path)
    cases = runtime_cases()
    context = initialize_rc2_capture(
        paths,
        registered,
        cases,
        settings(),
        extractor_factory=lambda _: SuccessfulExtractor([]),
        now=lambda: NOW,
        run_id_factory=lambda: "run-before-case-1",
    )
    assert not paths.capture_journal.exists()

    calls: list[str] = []
    completed = await run_or_resume_rc2_capture(
        paths,
        registered,
        cases,
        settings(),
        extractor_factory=lambda _: SuccessfulExtractor(calls),
        sleep=lambda _: _no_sleep(),
        now=lambda: NOW + timedelta(minutes=1),
    )

    assert completed.capture_run_id == context.started.capture_run_id
    assert len(calls) == 26


def test_changed_config_prevents_resume_before_extractor_construction(tmp_path: Path) -> None:
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2_capture import (
        initialize_rc2_capture,
    )

    paths, registered = prepared_paths(tmp_path)
    cases = runtime_cases()
    initialize_rc2_capture(
        paths,
        registered,
        cases,
        settings(),
        extractor_factory=lambda _: SuccessfulExtractor([]),
        now=lambda: NOW,
        run_id_factory=lambda: "run-synthetic-001",
    )
    constructed: list[str] = []

    def construct(_: Settings) -> SuccessfulExtractor:
        constructed.append("constructed")
        return SuccessfulExtractor([])

    with pytest.raises(ValueError, match="exact RC2 model"):
        initialize_rc2_capture(
            paths,
            registered,
            cases,
            settings(model="changed-model"),
            extractor_factory=construct,
        )

    assert constructed == []


@pytest.mark.asyncio
async def test_snapshot_requires_all_cases_and_is_atomic_stable_and_write_once(
    tmp_path: Path,
) -> None:
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2_capture import (
        finalize_rc2_capture,
        initialize_rc2_capture,
        run_or_resume_rc2_capture,
    )

    paths, registered = prepared_paths(tmp_path)
    cases = runtime_cases()
    context = initialize_rc2_capture(
        paths,
        registered,
        cases,
        settings(),
        extractor_factory=lambda _: SuccessfulExtractor([]),
        now=lambda: NOW,
        run_id_factory=lambda: "run-synthetic-001",
    )
    with pytest.raises(ValueError, match="all 26 terminal cases"):
        finalize_rc2_capture(paths, registered, context.started, cases, completed_at=NOW)
    assert not paths.predictions.exists()

    calls: list[str] = []
    completed = await run_or_resume_rc2_capture(
        paths,
        registered,
        cases,
        settings(),
        extractor_factory=lambda _: SuccessfulExtractor(calls),
        sleep=lambda _: _no_sleep(),
        now=lambda: NOW + timedelta(minutes=1),
    )
    first_bytes = paths.predictions.read_bytes()
    assert sha256_bytes(first_bytes) == completed.prediction_snapshot_sha256
    assert len(first_bytes.splitlines()) == 26
    assert not tuple(paths.output_directory.glob("*.tmp"))

    second = finalize_rc2_capture(
        paths,
        registered,
        context.started,
        cases,
        completed_at=NOW + timedelta(minutes=2),
    )
    assert second == completed
    assert paths.predictions.read_bytes() == first_bytes

    paths.predictions.write_bytes(first_bytes + b"tampered")
    with pytest.raises(ValueError, match="final prediction snapshot changed"):
        finalize_rc2_capture(
            paths,
            registered,
            context.started,
            cases,
            completed_at=NOW + timedelta(minutes=3),
        )


@pytest.mark.asyncio
async def test_complete_journal_recovery_finalizes_without_extractor_construction(
    tmp_path: Path,
) -> None:
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2_capture import (
        RC2CaptureJournalEntry,
        append_rc2_journal_entry,
        initialize_rc2_capture,
        run_or_resume_rc2_capture,
    )

    paths, registered = prepared_paths(tmp_path)
    cases = runtime_cases()
    context = initialize_rc2_capture(
        paths,
        registered,
        cases,
        settings(),
        extractor_factory=lambda _: SuccessfulExtractor([]),
        now=lambda: NOW,
        run_id_factory=lambda: "run-finalizer-recovery",
    )
    for sequence, case in enumerate(cases, start=1):
        append_rc2_journal_entry(
            paths,
            context.started,
            cases,
            RC2CaptureJournalEntry(
                capture_run_id=context.started.capture_run_id,
                sequence=sequence,
                case_id=case.case_id,
                terminal_result="SUCCESS",
                prediction=CaseIntakeResult(),
                provider="openai",
                model="mistral-small-2603",
                attempted_at=NOW,
            ),
        )

    def construction_must_not_run(_: Settings) -> NoReturn:
        raise AssertionError("complete-journal recovery constructed an extractor")

    completed = await run_or_resume_rc2_capture(
        paths,
        registered,
        cases,
        settings(),
        extractor_factory=construction_must_not_run,
        now=lambda: NOW + timedelta(minutes=1),
    )

    assert completed.capture_run_id == "run-finalizer-recovery"
    assert paths.predictions.is_file()
    assert paths.capture_completed.is_file()


@pytest.mark.parametrize("interrupted_artifact", ("prediction_metadata", "capture_completed"))
def test_finalizer_recovers_after_atomic_lifecycle_publication_interruption(
    interrupted_artifact: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vietnamese_labor_law_assistant.evaluation import (
        decision_support_v1_1_artifacts as artifacts_module,
    )
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2_capture import (
        RC2CaptureJournalEntry,
        append_rc2_journal_entry,
        finalize_rc2_capture,
        initialize_rc2_capture,
    )

    paths, registered = prepared_paths(tmp_path)
    cases = runtime_cases()
    context = initialize_rc2_capture(
        paths,
        registered,
        cases,
        settings(),
        extractor_factory=lambda _: SuccessfulExtractor([]),
        now=lambda: NOW,
        run_id_factory=lambda: "run-finalizer-atomic-recovery",
    )
    for sequence, case in enumerate(cases, start=1):
        append_rc2_journal_entry(
            paths,
            context.started,
            cases,
            RC2CaptureJournalEntry(
                capture_run_id=context.started.capture_run_id,
                sequence=sequence,
                case_id=case.case_id,
                terminal_result="SUCCESS",
                prediction=CaseIntakeResult(),
                provider="openai",
                model="mistral-small-2603",
                attempted_at=NOW,
            ),
        )
    target = getattr(paths, interrupted_artifact)
    link = artifacts_module.os.link

    def interrupt(source: Path, destination: Path) -> None:
        if Path(destination) == target:
            raise OSError("synthetic finalizer interruption")
        link(source, destination)

    monkeypatch.setattr(artifacts_module.os, "link", interrupt)
    with pytest.raises(OSError, match="finalizer interruption"):
        finalize_rc2_capture(
            paths,
            registered,
            context.started,
            cases,
            completed_at=NOW + timedelta(minutes=1),
        )
    assert paths.predictions.is_file()
    assert not target.exists()
    assert not paths.capture_completed.exists()

    monkeypatch.setattr(artifacts_module.os, "link", link)
    completed = finalize_rc2_capture(
        paths,
        registered,
        context.started,
        cases,
        completed_at=NOW + timedelta(minutes=1),
    )
    assert completed.capture_run_id == context.started.capture_run_id
    assert paths.prediction_metadata.is_file()
    assert paths.capture_completed.is_file()


async def _no_sleep() -> None:
    return None
