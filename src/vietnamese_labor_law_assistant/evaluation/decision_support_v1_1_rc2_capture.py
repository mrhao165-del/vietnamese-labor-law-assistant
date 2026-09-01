"""Crash-safe, resumable capture lifecycle for the unconsumed v1.1 RC2."""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.decision_support.intake import (
    CaseIntakeError,
    OpenAIStructuredCaseIntakeExtractor,
    validate_case_intake_result,
)
from vietnamese_labor_law_assistant.decision_support.models import (
    CaseIntakeInput,
    CaseIntakeResult,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_artifacts import (
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
    write_exclusive,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_capture import (
    V11CaseIntakePredictionRecord,
    V11PredictionFailureReason,
    V11PredictionStatus,
    V11RuntimeCase,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2 import (
    RC2ArtifactPaths,
    RC2CodeIdentities,
    RC2GenerationConfig,
    RC2RegisteredPathsV2,
    RC2RegistrationV2,
    load_rc2_registration_v2,
)


class _CaseIntakeExtractor(Protocol):
    async def extract(self, case_input: CaseIntakeInput) -> CaseIntakeResult: ...


ExtractorFactory = Callable[[Settings], _CaseIntakeExtractor]
Clock = Callable[[], datetime]
RunIdFactory = Callable[[], str]
ModelT = TypeVar("ModelT", bound=BaseModel)


class RC2CaptureStarted(BaseModel):
    """Immutable start identity created only after successful runtime construction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["v1_1_rc2_capture_started_v1"] = "v1_1_rc2_capture_started_v1"
    release_candidate: Literal["v1_1_rc2"] = "v1_1_rc2"
    registration_revision: Literal[2] = 2
    lifecycle_state: Literal["CAPTURE_STARTED"] = "CAPTURE_STARTED"
    capture_run_id: str = Field(min_length=1, max_length=100)
    capture_started_at: datetime
    registration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    ordered_case_ids_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    frozen_dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    human_review_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    threshold_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    implementation_commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    code_identities: RC2CodeIdentities
    generation_config: RC2GenerationConfig
    label_isolation: Literal[True] = True
    expected_labels_visible_during_capture: Literal[False] = False

    @model_validator(mode="after")
    def validate_start_timestamp(self) -> RC2CaptureStarted:
        _require_timezone_aware(self.capture_started_at, "capture start timestamp")
        return self


class RC2CaptureJournalEntry(BaseModel):
    """One append-only terminal case attempt with no label or secret fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["v1_1_rc2_capture_journal_entry_v1"] = (
        "v1_1_rc2_capture_journal_entry_v1"
    )
    capture_run_id: str = Field(min_length=1, max_length=100)
    sequence: int = Field(ge=1, le=26)
    case_id: str = Field(min_length=1, max_length=100)
    attempt_state: Literal["TERMINAL"] = "TERMINAL"
    terminal_result: Literal["SUCCESS", "FAILURE"]
    prediction: CaseIntakeResult | None = None
    failure_category: V11PredictionFailureReason | None = None
    provider: Literal["openai"]
    model: Literal["mistral-small-2603"]
    attempted_at: datetime

    @model_validator(mode="after")
    def validate_terminal_payload(self) -> RC2CaptureJournalEntry:
        if self.terminal_result == "SUCCESS":
            if self.prediction is None or self.failure_category is not None:
                raise ValueError("SUCCESS requires one canonical prediction and no failure")
        elif self.prediction is not None or self.failure_category is None:
            raise ValueError("FAILURE requires one typed failure and no prediction")
        _require_timezone_aware(self.attempted_at, "case attempt timestamp")
        return self


class RC2PredictionMetadataV2(BaseModel):
    """Write-once metadata for the deterministic journal-derived snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["v1_1_rc2_prediction_metadata_v2"] = "v1_1_rc2_prediction_metadata_v2"
    release_candidate: Literal["v1_1_rc2"] = "v1_1_rc2"
    registration_revision: Literal[2] = 2
    lifecycle_state: Literal["CAPTURE_COMPLETED"] = "CAPTURE_COMPLETED"
    capture_outcome: Literal["ALL_SUCCESS", "COMPLETED_WITH_TYPED_FAILURES"]
    capture_run_id: str
    capture_started_at: datetime
    capture_completed_at: datetime
    registration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    capture_started_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    journal_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    predictions_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    total_count: Literal[26] = 26
    success_count: int = Field(ge=0, le=26)
    typed_failure_count: int = Field(ge=0, le=26)

    @model_validator(mode="after")
    def validate_metadata(self) -> RC2PredictionMetadataV2:
        _require_timezone_aware(self.capture_started_at, "capture start timestamp")
        _require_timezone_aware(self.capture_completed_at, "capture completion timestamp")
        if self.capture_completed_at < self.capture_started_at:
            raise ValueError("capture completion timestamp precedes capture start")
        if self.success_count + self.typed_failure_count != self.total_count:
            raise ValueError("capture counts must total 26")
        all_success = self.success_count == 26 and self.typed_failure_count == 0
        if (self.capture_outcome == "ALL_SUCCESS") != all_success:
            raise ValueError("ALL_SUCCESS requires exactly 26 successful cases")
        return self


class RC2CaptureCompleted(BaseModel):
    """Immutable terminal capture identity bound to start, journal, and snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["v1_1_rc2_capture_completed_v1"] = "v1_1_rc2_capture_completed_v1"
    release_candidate: Literal["v1_1_rc2"] = "v1_1_rc2"
    registration_revision: Literal[2] = 2
    lifecycle_state: Literal["CAPTURE_COMPLETED"] = "CAPTURE_COMPLETED"
    capture_outcome: Literal["ALL_SUCCESS", "COMPLETED_WITH_TYPED_FAILURES"]
    capture_run_id: str
    capture_started_at: datetime
    capture_completed_at: datetime
    registration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    capture_started_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prediction_metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    frozen_dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    human_review_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    threshold_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    implementation_commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    code_identities: RC2CodeIdentities
    generation_config: RC2GenerationConfig
    total_cases: Literal[26] = 26
    success_count: int = Field(ge=0, le=26)
    typed_failure_count: int = Field(ge=0, le=26)
    prediction_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    journal_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    label_isolation_confirmed: Literal[True] = True
    expected_labels_visible_during_capture: Literal[False] = False

    @model_validator(mode="after")
    def validate_completion(self) -> RC2CaptureCompleted:
        _require_timezone_aware(self.capture_started_at, "capture start timestamp")
        _require_timezone_aware(self.capture_completed_at, "capture completion timestamp")
        if self.capture_completed_at < self.capture_started_at:
            raise ValueError("capture completion timestamp precedes capture start")
        if self.success_count + self.typed_failure_count != self.total_cases:
            raise ValueError("capture counts must total 26")
        return self


@dataclass(frozen=True)
class RC2CaptureContext:
    """Validated same-attempt state plus the initialized production extractor."""

    started: RC2CaptureStarted
    runtime_cases: tuple[V11RuntimeCase, ...]
    journal_entries: tuple[RC2CaptureJournalEntry, ...]
    extractor: _CaseIntakeExtractor


def initialize_rc2_capture(
    paths: RC2ArtifactPaths,
    registration: RC2RegistrationV2,
    runtime_cases: Sequence[V11RuntimeCase],
    settings: Settings,
    *,
    extractor_factory: ExtractorFactory = OpenAIStructuredCaseIntakeExtractor,
    now: Clock = lambda: datetime.now().astimezone(),
    run_id_factory: RunIdFactory = lambda: str(uuid.uuid4()),
) -> RC2CaptureContext:
    """Validate identity and initialize or resume without claiming the final snapshot."""

    cases = _validate_capture_inputs(paths, registration, runtime_cases, settings)
    if paths.capture_started.is_file():
        started = load_rc2_capture_started(paths, registration, cases)
        entries = load_rc2_journal(paths, started, cases)
        _probe_journal_availability(paths.capture_journal)
        extractor = extractor_factory(settings)
        return RC2CaptureContext(started, cases, entries, extractor)

    _require_new_capture_namespace(paths)
    _probe_journal_availability(paths.capture_journal)
    extractor = extractor_factory(settings)
    started = RC2CaptureStarted(
        capture_run_id=run_id_factory(),
        capture_started_at=now(),
        registration_sha256=sha256_file(paths.registration_revision_2),
        ordered_case_ids_sha256=_ordered_case_ids_sha256(cases),
        frozen_dataset_sha256=registration.frozen_dataset_sha256,
        human_review_sha256=registration.human_review_sha256,
        threshold_sha256=registration.threshold_sha256,
        implementation_commit_sha=registration.implementation_commit_sha,
        code_identities=registration.code_identities,
        generation_config=registration.generation_config,
    )
    write_exclusive(
        paths.capture_started,
        canonical_json_bytes(started.model_dump(mode="json")),
    )
    return RC2CaptureContext(started, cases, (), extractor)


def load_rc2_capture_started(
    paths: RC2ArtifactPaths,
    registration: RC2RegistrationV2,
    runtime_cases: Sequence[V11RuntimeCase],
) -> RC2CaptureStarted:
    """Load and fail closed on any start/registration/case identity difference."""

    payload = paths.capture_started.read_bytes()
    started = RC2CaptureStarted.model_validate_json(payload)
    if payload != canonical_json_bytes(started.model_dump(mode="json")):
        raise ValueError("RC2 capture-start bytes are not canonical")
    expected = {
        "registration_sha256": sha256_file(paths.registration_revision_2),
        "ordered_case_ids_sha256": _ordered_case_ids_sha256(runtime_cases),
        "frozen_dataset_sha256": registration.frozen_dataset_sha256,
        "human_review_sha256": registration.human_review_sha256,
        "threshold_sha256": registration.threshold_sha256,
        "implementation_commit_sha": registration.implementation_commit_sha,
        "code_identities": registration.code_identities,
        "generation_config": registration.generation_config,
    }
    for field_name, expected_value in expected.items():
        if getattr(started, field_name) != expected_value:
            raise ValueError(f"capture-start {field_name} differs from registration revision 2")
    return started


def load_rc2_journal(
    paths: RC2ArtifactPaths,
    started: RC2CaptureStarted,
    runtime_cases: Sequence[V11RuntimeCase],
) -> tuple[RC2CaptureJournalEntry, ...]:
    """Validate the canonical append-only journal as an ordered terminal prefix."""

    if not paths.capture_journal.exists():
        return ()
    payload = paths.capture_journal.read_bytes()
    if not payload:
        return ()
    lines = payload.splitlines(keepends=True)
    if any(not line.endswith(b"\n") for line in lines):
        raise ValueError("RC2 capture journal contains an incomplete record")
    entries: list[RC2CaptureJournalEntry] = []
    expected_cases = tuple(runtime_cases)
    for index, line in enumerate(lines, start=1):
        entry = RC2CaptureJournalEntry.model_validate_json(line)
        if line != canonical_json_bytes(entry.model_dump(mode="json")):
            raise ValueError("RC2 capture journal bytes are not canonical")
        if entry.capture_run_id != started.capture_run_id:
            raise ValueError("journal capture run ID differs from CAPTURE_STARTED")
        if entry.provider != started.generation_config.provider:
            raise ValueError("journal provider differs from CAPTURE_STARTED")
        if entry.model != started.generation_config.model:
            raise ValueError("journal model differs from CAPTURE_STARTED")
        if index > len(expected_cases):
            raise ValueError("journal contains more than 26 terminal cases")
        expected_case = expected_cases[index - 1]
        if entry.sequence != index or entry.case_id != expected_case.case_id:
            raise ValueError("journal is not the ordered frozen-case terminal prefix")
        entries.append(entry)
    return tuple(entries)


def append_rc2_journal_entry(
    paths: RC2ArtifactPaths,
    started: RC2CaptureStarted,
    runtime_cases: Sequence[V11RuntimeCase],
    entry: RC2CaptureJournalEntry,
) -> None:
    """Append and fsync exactly one previously unseen terminal case record."""

    known_ids = tuple(case.case_id for case in runtime_cases)
    if entry.case_id not in known_ids:
        raise ValueError("journal entry contains an unknown case ID")
    existing = load_rc2_journal(paths, started, runtime_cases)
    if any(item.case_id == entry.case_id for item in existing):
        raise ValueError("terminal journal entry already exists for case ID")
    next_sequence = len(existing) + 1
    if entry.sequence != next_sequence or entry.case_id != known_ids[next_sequence - 1]:
        raise ValueError("journal entry differs from the next registered case")
    if entry.capture_run_id != started.capture_run_id:
        raise ValueError("journal capture run ID differs from CAPTURE_STARTED")
    if (
        entry.provider != started.generation_config.provider
        or entry.model != started.generation_config.model
    ):
        raise ValueError("journal provider/model differs from CAPTURE_STARTED")
    payload = canonical_json_bytes(entry.model_dump(mode="json"))
    mode = "ab" if paths.capture_journal.exists() else "xb"
    with paths.capture_journal.open(mode) as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


async def run_or_resume_rc2_capture(
    paths: RC2ArtifactPaths,
    registration: RC2RegistrationV2,
    runtime_cases: Sequence[V11RuntimeCase],
    settings: Settings,
    *,
    extractor_factory: ExtractorFactory = OpenAIStructuredCaseIntakeExtractor,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    now: Clock = lambda: datetime.now().astimezone(),
    run_id_factory: RunIdFactory = lambda: str(uuid.uuid4()),
) -> RC2CaptureCompleted:
    """Resume one run, never re-call a terminal case, then finalize from its journal."""

    cases = _validate_capture_inputs(paths, registration, runtime_cases, settings)
    if paths.capture_completed.is_file():
        started = load_rc2_capture_started(paths, registration, cases)
        return finalize_rc2_capture(paths, registration, started, cases, completed_at=now())
    if paths.capture_started.is_file():
        started = load_rc2_capture_started(paths, registration, cases)
        if len(load_rc2_journal(paths, started, cases)) == 26:
            return finalize_rc2_capture(
                paths,
                registration,
                started,
                cases,
                completed_at=now(),
            )
    context = initialize_rc2_capture(
        paths,
        registration,
        cases,
        settings,
        extractor_factory=extractor_factory,
        now=now,
        run_id_factory=run_id_factory,
    )
    pending = cases[len(context.journal_entries) :]
    for pending_index, runtime_case in enumerate(pending):
        sequence = len(context.journal_entries) + pending_index + 1
        entry = await _attempt_case(
            context.started,
            context.extractor,
            runtime_case,
            sequence=sequence,
            attempted_at=now(),
        )
        append_rc2_journal_entry(paths, context.started, cases, entry)
        if pending_index + 1 < len(pending):
            await sleep(registration.generation_config.inter_case_pacing_seconds)
    return finalize_rc2_capture(
        paths,
        registration,
        context.started,
        cases,
        completed_at=now(),
    )


async def capture_registered_rc2(
    paths: RC2ArtifactPaths,
    settings: Settings,
    *,
    extractor_factory: ExtractorFactory = OpenAIStructuredCaseIntakeExtractor,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    now: Clock = lambda: datetime.now().astimezone(),
    run_id_factory: RunIdFactory = lambda: str(uuid.uuid4()),
) -> RC2CaptureCompleted:
    """Revalidate revision 2 and run/resume its only frozen capture attempt."""

    plan = load_rc2_registration_v2(paths, settings)
    return await run_or_resume_rc2_capture(
        paths,
        plan.registration,
        plan.runtime_cases,
        settings,
        extractor_factory=extractor_factory,
        sleep=sleep,
        now=now,
        run_id_factory=run_id_factory,
    )


def finalize_rc2_capture(
    paths: RC2ArtifactPaths,
    registration: RC2RegistrationV2,
    started: RC2CaptureStarted,
    runtime_cases: Sequence[V11RuntimeCase],
    *,
    completed_at: datetime,
) -> RC2CaptureCompleted:
    """Materialize a complete deterministic snapshot and immutable completion identity."""

    cases = tuple(runtime_cases)
    entries = load_rc2_journal(paths, started, cases)
    if len(cases) != 26 or len(entries) != 26:
        raise ValueError("snapshot finalization requires all 26 terminal cases")
    records = tuple(_prediction_record(entry) for entry in entries)
    prediction_bytes = b"".join(
        canonical_json_bytes(record.model_dump(mode="json")) for record in records
    )
    prediction_sha256 = sha256_bytes(prediction_bytes)
    _publish_or_verify_snapshot(paths.predictions, prediction_bytes)
    _validate_prediction_snapshot(paths.predictions, cases, prediction_sha256)

    registration_sha256 = sha256_file(paths.registration_revision_2)
    started_sha256 = sha256_file(paths.capture_started)
    journal_sha256 = sha256_file(paths.capture_journal)
    success_count = sum(entry.terminal_result == "SUCCESS" for entry in entries)
    typed_failure_count = 26 - success_count
    outcome: Literal["ALL_SUCCESS", "COMPLETED_WITH_TYPED_FAILURES"] = (
        "ALL_SUCCESS" if typed_failure_count == 0 else "COMPLETED_WITH_TYPED_FAILURES"
    )
    if paths.prediction_metadata.is_file():
        metadata = _load_canonical_model(paths.prediction_metadata, RC2PredictionMetadataV2)
        if (
            metadata.capture_run_id != started.capture_run_id
            or metadata.registration_sha256 != registration_sha256
            or metadata.capture_started_sha256 != started_sha256
            or metadata.journal_sha256 != journal_sha256
            or metadata.predictions_sha256 != prediction_sha256
            or metadata.success_count != success_count
            or metadata.typed_failure_count != typed_failure_count
        ):
            raise ValueError("existing prediction metadata differs from journal finalization")
    else:
        metadata = RC2PredictionMetadataV2(
            capture_outcome=outcome,
            capture_run_id=started.capture_run_id,
            capture_started_at=started.capture_started_at,
            capture_completed_at=completed_at,
            registration_sha256=registration_sha256,
            capture_started_sha256=started_sha256,
            journal_sha256=journal_sha256,
            predictions_sha256=prediction_sha256,
            success_count=success_count,
            typed_failure_count=typed_failure_count,
        )
        write_exclusive(
            paths.prediction_metadata,
            canonical_json_bytes(metadata.model_dump(mode="json")),
        )
    completion = RC2CaptureCompleted(
        capture_outcome=metadata.capture_outcome,
        capture_run_id=started.capture_run_id,
        capture_started_at=started.capture_started_at,
        capture_completed_at=metadata.capture_completed_at,
        registration_sha256=registration_sha256,
        capture_started_sha256=started_sha256,
        prediction_metadata_sha256=sha256_file(paths.prediction_metadata),
        frozen_dataset_sha256=registration.frozen_dataset_sha256,
        human_review_sha256=registration.human_review_sha256,
        threshold_sha256=registration.threshold_sha256,
        implementation_commit_sha=registration.implementation_commit_sha,
        code_identities=registration.code_identities,
        generation_config=registration.generation_config,
        success_count=success_count,
        typed_failure_count=typed_failure_count,
        prediction_snapshot_sha256=prediction_sha256,
        journal_sha256=journal_sha256,
    )
    if paths.capture_completed.is_file():
        existing = _load_canonical_model(paths.capture_completed, RC2CaptureCompleted)
        if existing != completion:
            raise ValueError("existing capture completion differs from finalized identity")
        return existing
    write_exclusive(
        paths.capture_completed,
        canonical_json_bytes(completion.model_dump(mode="json")),
    )
    return completion


async def _attempt_case(
    started: RC2CaptureStarted,
    extractor: _CaseIntakeExtractor,
    runtime_case: V11RuntimeCase,
    *,
    sequence: int,
    attempted_at: datetime,
) -> RC2CaptureJournalEntry:
    try:
        extracted = await extractor.extract(runtime_case.case_input)
        prediction = validate_case_intake_result(runtime_case.case_input, extracted)
        return RC2CaptureJournalEntry(
            capture_run_id=started.capture_run_id,
            sequence=sequence,
            case_id=runtime_case.case_id,
            terminal_result="SUCCESS",
            prediction=prediction,
            provider=started.generation_config.provider,
            model=started.generation_config.model,
            attempted_at=attempted_at,
        )
    except CaseIntakeError as exc:
        try:
            failure = V11PredictionFailureReason(exc.reason)
        except ValueError:
            failure = V11PredictionFailureReason.UNEXPECTED_ERROR
    except Exception:
        failure = V11PredictionFailureReason.UNEXPECTED_ERROR
    return RC2CaptureJournalEntry(
        capture_run_id=started.capture_run_id,
        sequence=sequence,
        case_id=runtime_case.case_id,
        terminal_result="FAILURE",
        failure_category=failure,
        provider=started.generation_config.provider,
        model=started.generation_config.model,
        attempted_at=attempted_at,
    )


def _validate_capture_inputs(
    paths: RC2ArtifactPaths,
    registration: RC2RegistrationV2,
    runtime_cases: Sequence[V11RuntimeCase],
    settings: Settings,
) -> tuple[V11RuntimeCase, ...]:
    cases = tuple(runtime_cases)
    if len(cases) != 26:
        raise ValueError("RC2 capture requires exactly 26 runtime cases")
    if any(type(case) is not V11RuntimeCase for case in cases):
        raise TypeError("RC2 capture accepts only exact V11RuntimeCase objects")
    case_ids = tuple(case.case_id for case in cases)
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("RC2 runtime case IDs must be unique")
    if registration.paths != RC2RegisteredPathsV2.from_artifact_paths(paths):
        raise ValueError("registration output paths differ from the canonical RC2 namespace")
    if not paths.registration_revision_2.is_file():
        raise FileNotFoundError("RC2 registration revision 2 is missing")
    payload = paths.registration_revision_2.read_bytes()
    persisted = RC2RegistrationV2.model_validate_json(payload)
    if payload != canonical_json_bytes(persisted.model_dump(mode="json")):
        raise ValueError("RC2 registration revision 2 bytes are not canonical")
    if persisted != registration:
        raise ValueError("RC2 registration revision 2 identity changed")
    configured = RC2GenerationConfig.from_settings(settings)
    if configured != registration.generation_config:
        raise ValueError("configured generation identity differs from registration revision 2")
    if paths.capture_journal.exists() and not paths.capture_started.exists():
        raise ValueError("capture journal exists without CAPTURE_STARTED identity")
    return cases


def _require_new_capture_namespace(paths: RC2ArtifactPaths) -> None:
    claimed = (
        paths.capture_started,
        paths.capture_journal,
        paths.capture_completed,
        paths.predictions,
        paths.prediction_metadata,
        paths.metrics,
        paths.failed_samples,
        paths.release_report,
        paths.evaluation_started,
        paths.evaluation_completed,
        paths.release_terminal,
    )
    if any(os.path.lexists(path) for path in claimed):
        raise FileExistsError("RC2 output namespace is already claimed")


def _probe_journal_availability(journal_path: Path) -> None:
    """Prove the registered journal can be durably opened before capture starts."""

    if journal_path.exists():
        if not journal_path.is_file():
            raise OSError("RC2 capture journal is not a regular file")
        with journal_path.open("ab") as handle:
            handle.flush()
            os.fsync(handle.fileno())
        return

    probe_path = journal_path.with_name(f".{journal_path.name}.availability-probe")
    probe_path.unlink(missing_ok=True)
    try:
        with probe_path.open("xb") as handle:
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        probe_path.unlink(missing_ok=True)


def _ordered_case_ids_sha256(runtime_cases: Sequence[V11RuntimeCase]) -> str:
    return sha256_bytes(canonical_json_bytes([case.case_id for case in runtime_cases]))


def _prediction_record(entry: RC2CaptureJournalEntry) -> V11CaseIntakePredictionRecord:
    if entry.terminal_result == "SUCCESS":
        return V11CaseIntakePredictionRecord(
            sequence=entry.sequence,
            case_id=entry.case_id,
            status=V11PredictionStatus.SUCCESS,
            result=entry.prediction,
        )
    return V11CaseIntakePredictionRecord(
        sequence=entry.sequence,
        case_id=entry.case_id,
        status=V11PredictionStatus.ERROR,
        failure_reason=entry.failure_category,
    )


def _publish_or_verify_snapshot(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError("final prediction snapshot changed from journal materialization")
        return
    _atomic_publish_once(path, payload)


def _atomic_publish_once(path: Path, payload: bytes) -> None:
    write_exclusive(path, payload)


def publish_atomic_write_once(path: Path, payload: bytes) -> None:
    """Durably publish complete bytes under a previously absent final name."""

    _atomic_publish_once(path, payload)


def _validate_prediction_snapshot(
    path: Path,
    runtime_cases: Sequence[V11RuntimeCase],
    expected_sha256: str,
) -> None:
    payload = path.read_bytes()
    if sha256_bytes(payload) != expected_sha256:
        raise ValueError("final prediction snapshot checksum changed")
    lines = payload.splitlines(keepends=True)
    if len(lines) != 26 or any(not line.endswith(b"\n") for line in lines):
        raise ValueError("final prediction snapshot must contain 26 canonical rows")
    records = tuple(V11CaseIntakePredictionRecord.model_validate_json(line) for line in lines)
    if any(
        line != canonical_json_bytes(record.model_dump(mode="json"))
        for line, record in zip(lines, records, strict=True)
    ):
        raise ValueError("final prediction snapshot rows are not canonical")
    if tuple(record.case_id for record in records) != tuple(case.case_id for case in runtime_cases):
        raise ValueError("final prediction snapshot case IDs differ from registered order")


def _load_canonical_model(path: Path, model_type: type[ModelT]) -> ModelT:
    payload = path.read_bytes()
    model = model_type.model_validate_json(payload)
    if payload != canonical_json_bytes(model.model_dump(mode="json")):
        raise ValueError(f"artifact bytes are not canonical: {path}")
    return model


def _require_timezone_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
