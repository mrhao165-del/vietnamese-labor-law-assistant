from __future__ import annotations

from pathlib import Path

import pytest

from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_artifacts import (
    canonical_json_bytes,
    sha256_file,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
REVISION_1_SHA256 = "7561fad80e75d0cea84f144471596cb7ae31cd70b6786ac4e410fe814e3e30ac"


def test_revision_2_paths_leave_revision_1_as_historical_evidence(tmp_path: Path) -> None:
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2 import (
        RC2ArtifactPaths,
    )

    paths = RC2ArtifactPaths.from_root(tmp_path)

    assert paths.registration_revision_1.name == "rc2_capture_manifest.json"
    assert paths.registration_revision_2.name == "rc2_registration_v2.json"
    assert paths.capture_started.name == "rc2_capture_started.json"
    assert paths.capture_journal.name == "rc2_capture_journal.jsonl"
    assert paths.capture_completed.name == "rc2_capture_completed.json"
    assert paths.evaluation_completed.name == "rc2_evaluation_completed.json"
    assert paths.release_terminal.name == "rc2_release_terminal.json"


def test_revision_2_records_zero_call_supersession_without_rewriting_revision_1() -> None:
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2 import (
        RC2_REGISTRATION_V1_SHA256,
        RC2RegistrationV2,
    )

    revision_1 = (
        PROJECT_ROOT / "evaluation/results/decision_support/v1_1/rc2/rc2_capture_manifest.json"
    )
    before = revision_1.read_bytes()

    registration = RC2RegistrationV2.model_validate(registration_payload(PROJECT_ROOT))

    assert RC2_REGISTRATION_V1_SHA256 == REVISION_1_SHA256
    assert sha256_file(revision_1) == REVISION_1_SHA256
    assert revision_1.read_bytes() == before
    assert registration.release_candidate == "v1_1_rc2"
    assert registration.registration_revision == 2
    assert registration.status == "PREPARED_NOT_CAPTURED"
    assert registration.capture_started_at is None
    assert registration.prediction_checksum is None
    assert registration.frozen_provider_calls == 0
    assert registration.rc2_capture_started is False
    assert registration.supersedes.registration_revision == 1
    assert registration.supersedes.registration_sha256 == REVISION_1_SHA256
    assert registration.supersedes.state == "SUPERSEDED_BEFORE_CAPTURE"
    assert registration.supersedes.reason == "INCOMPLETE_CLOSEOUT_CAPABILITY"
    assert registration.supersedes.frozen_provider_calls == 0


def test_revision_2_writer_is_canonical_and_write_once(tmp_path: Path) -> None:
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2 import (
        RC2ArtifactPaths,
        RC2RegistrationV2,
        write_rc2_registration_v2,
    )

    paths = RC2ArtifactPaths.from_root(tmp_path)
    paths.registration_revision_1.parent.mkdir(parents=True)
    source = PROJECT_ROOT / "evaluation/results/decision_support/v1_1/rc2/rc2_capture_manifest.json"
    paths.registration_revision_1.write_bytes(source.read_bytes())
    registration = RC2RegistrationV2.model_validate(registration_payload(tmp_path))

    write_rc2_registration_v2(paths, registration)

    assert paths.registration_revision_2.read_bytes() == canonical_json_bytes(
        registration.model_dump(mode="json")
    )
    with pytest.raises(FileExistsError, match="registration revision 2"):
        write_rc2_registration_v2(paths, registration)


def test_prepare_revision_2_entrypoint_binds_the_committed_implementation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.unit.evaluation.test_decision_support_v1_1_rc2_capture_lifecycle import (
        runtime_cases,
    )
    from vietnamese_labor_law_assistant.evaluation import (
        decision_support_v1_1_rc2 as rc2_module,
    )
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_artifacts import (
        RepositoryState,
    )

    paths = rc2_module.RC2ArtifactPaths.from_root(tmp_path)
    identities = rc2_module.RC2CodeIdentities.model_validate(
        registration_payload(tmp_path)["code_identities"]
    )
    commit_sha = "a" * 40
    monkeypatch.setattr(
        rc2_module,
        "require_rc2_governance_identity",
        lambda _: runtime_cases(),
    )
    monkeypatch.setattr(
        rc2_module,
        "inspect_repository_state",
        lambda _: RepositoryState(
            commit_sha=commit_sha,
            tracked_dirty=False,
            untracked_paths=("synthetic-user-plan.md",),
            git_top_level=tmp_path,
        ),
    )
    monkeypatch.setattr(rc2_module, "_current_rc2_code_identities", lambda _: identities)

    plan = rc2_module.prepare_rc2_registration_v2(
        tmp_path,
        implementation_commit_sha=commit_sha,
    )

    assert plan.registration.implementation_commit_sha == commit_sha
    assert plan.registration.registered_untracked_paths == ("synthetic-user-plan.md",)
    assert plan.registration.code_identities == identities
    assert plan.registration.supersedes.registration_sha256 == REVISION_1_SHA256
    assert plan.registration.frozen_provider_calls == 0
    assert plan.runtime_cases == runtime_cases()
    assert not paths.registration_revision_2.exists()


def test_offline_registration_loader_enforces_full_identity_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.unit.evaluation.test_decision_support_v1_1_rc2_capture_lifecycle import (
        runtime_cases,
    )
    from vietnamese_labor_law_assistant.evaluation import (
        decision_support_v1_1_rc2 as rc2_module,
    )
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_artifacts import (
        RepositoryState,
    )

    paths = rc2_module.RC2ArtifactPaths.from_root(tmp_path)
    paths.registration_revision_2.parent.mkdir(parents=True)
    registered = rc2_module.RC2RegistrationV2.model_validate(registration_payload(tmp_path))
    paths.registration_revision_2.write_bytes(
        canonical_json_bytes(registered.model_dump(mode="json"))
    )
    monkeypatch.setattr(
        rc2_module,
        "require_rc2_governance_identity",
        lambda _: runtime_cases(),
    )
    monkeypatch.setattr(
        rc2_module,
        "_current_rc2_code_identities",
        lambda _: registered.code_identities,
    )
    monkeypatch.setattr(
        rc2_module,
        "inspect_repository_state",
        lambda _: RepositoryState(
            commit_sha=registered.implementation_commit_sha,
            tracked_dirty=False,
            untracked_paths=(),
            git_top_level=tmp_path,
        ),
    )

    plan = rc2_module.load_rc2_registration_v2_offline(paths)
    assert plan.registration == registered
    assert plan.runtime_cases == runtime_cases()

    monkeypatch.setattr(
        rc2_module,
        "_current_rc2_code_identities",
        lambda _: registered.code_identities.model_copy(
            update={"offline_evaluator_sha256": "f" * 64}
        ),
    )
    with pytest.raises(ValueError, match="committed code identity changed"):
        rc2_module.load_rc2_registration_v2_offline(paths)


@pytest.mark.parametrize(
    ("target_name", "error"),
    (
        ("frozen_dataset", "frozen dataset checksum changed"),
        ("review_packet", "human review checksum changed"),
        ("threshold_spec", "threshold specification checksum changed"),
    ),
)
def test_governance_checksum_mismatch_blocks_before_capture(
    target_name: str,
    error: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vietnamese_labor_law_assistant.evaluation import (
        decision_support_v1_1_rc2 as rc2_module,
    )

    paths = synthetic_governance_inputs(tmp_path)
    monkeypatch.setattr(
        rc2_module,
        "RC2_FROZEN_DATASET_SHA256",
        sha256_file(paths.governed.frozen_dataset),
    )
    monkeypatch.setattr(
        rc2_module,
        "RC2_HUMAN_REVIEW_SHA256",
        sha256_file(paths.governed.review_packet),
    )
    monkeypatch.setattr(
        rc2_module,
        "RC2_THRESHOLD_SHA256",
        sha256_file(paths.governed.threshold_spec),
    )
    target = getattr(paths.governed, target_name)
    target.write_bytes(target.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match=error):
        rc2_module.require_rc2_governance_identity(paths)


@pytest.mark.asyncio
async def test_revision_1_unsafe_capture_entrypoint_is_disabled(tmp_path: Path) -> None:
    from pydantic import SecretStr

    from vietnamese_labor_law_assistant.common.settings import Settings
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2 import (
        RC2ArtifactPaths,
        capture_rc2_predictions,
    )

    configured = Settings(
        openai_api_key=SecretStr("offline-test-secret"),
        llm_provider="openai",
        llm_model="mistral-small-2603",
        openai_base_url="https://api.mistral.ai/v1",
        llm_timeout_seconds=60,
        llm_max_retries=2,
        agent_structured_output_max_retries=2,
    )

    with pytest.raises(RuntimeError, match="revision 1 is superseded"):
        await capture_rc2_predictions(
            RC2ArtifactPaths.from_root(tmp_path),
            configured,
            project_author_name="mrhao165-del",
        )


def registration_payload(repo_root: Path) -> dict[str, object]:
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2 import (
        RC2ArtifactPaths,
        RC2GenerationConfig,
        RC2RegisteredPathsV2,
    )

    paths = RC2ArtifactPaths.from_root(repo_root)
    return {
        "release_candidate": "v1_1_rc2",
        "registration_revision": 2,
        "status": "PREPARED_NOT_CAPTURED",
        "supersedes": {
            "release_candidate": "v1_1_rc2",
            "registration_revision": 1,
            "registration_path": (
                "evaluation/results/decision_support/v1_1/rc2/rc2_capture_manifest.json"
            ),
            "registration_sha256": REVISION_1_SHA256,
            "state": "SUPERSEDED_BEFORE_CAPTURE",
            "reason": "INCOMPLETE_CLOSEOUT_CAPABILITY",
            "frozen_provider_calls": 0,
        },
        "parent": "v1_1_rc1",
        "parent_result": "FAILED_PROVIDER_CAPTURE",
        "parent_immutable": True,
        "parent_successful_predictions": 0,
        "parent_artifact_sha256": {
            "capture_intent": "37ac396778226f84efdb655003e2cd738def7650c0904f65c142fd28cfe4e0f9",
            "predictions": "d59815facf4c3360dba5c8471f446de3262ddeca42f6e25adad3268a60a44d9a",
            "snapshot_manifest": (
                "4ea2d90d03eff5db5b4d972d487508b07b88ef1274050641973089ba11a86415"
            ),
        },
        "frozen_dataset_sha256": (
            "5f726893300176d1c3b4e915253682b70ef343376903e3e7e243d838e245c29e"
        ),
        "case_count": 26,
        "human_review_sha256": ("bae5fe6826c0d92ec4f85f433e7fdd640bc182bcaefaaf93ee3d4d0b1a2068d6"),
        "human_review_pass_count": 26,
        "human_review_unresolved_count": 0,
        "threshold_sha256": ("373aa3d4512e6d5cb75e7bcba3dbcc6ef2541ced8603b67b18e6bcd80b31ad5c"),
        "threshold_decision": "APPROVE_UNCHANGED",
        "implementation_commit_sha": "a" * 40,
        "registered_untracked_paths": (),
        "code_identities": {
            "registration_sha256": "1" * 64,
            "capture_runner_sha256": "2" * 64,
            "journal_finalizer_sha256": "3" * 64,
            "offline_evaluator_sha256": "4" * 64,
            "metrics_producer_sha256": "4" * 64,
            "report_producer_sha256": "4" * 64,
            "extractor_sha256": "5" * 64,
            "prompt_sha256": "6" * 64,
            "canonical_schema_sha256": "7" * 64,
            "transport_schema_sha256": "8" * 64,
        },
        "generation_config": RC2GenerationConfig(),
        "paths": RC2RegisteredPathsV2.from_artifact_paths(paths),
        "label_isolation": True,
        "expected_labels_visible_during_capture": False,
        "frozen_provider_calls": 0,
        "rc2_capture_started": False,
        "capture_started_at": None,
        "prediction_checksum": None,
        "expected_labels_unchanged": True,
        "legal_semantics_changed": False,
        "case_intake_semantics_changed": False,
        "source_span_validation_weakened": False,
        "week5_functionality_added": False,
    }


def synthetic_governance_inputs(tmp_path: Path):
    from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2 import (
        RC2ArtifactPaths,
    )

    target = RC2ArtifactPaths.from_root(tmp_path)
    inputs = (
        target.governed.frozen_dataset,
        target.governed.freeze_manifest,
        target.governed.review_packet,
        target.governed.threshold_spec,
        target.governed.threshold_approval,
        target.governed.capture_intent,
        target.governed.predictions,
        target.governed.snapshot_manifest,
        target.registration_revision_1,
    )
    for index, target_path in enumerate(inputs, start=1):
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(f"synthetic-governance-{index}\n".encode())
    return target
