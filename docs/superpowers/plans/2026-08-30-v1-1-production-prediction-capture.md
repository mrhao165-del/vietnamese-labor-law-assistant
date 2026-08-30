# V1.1 Production Prediction Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an offline freeze boundary and one explicitly live, write-once production Case Intake prediction capture without exposing expected labels to the extractor.

**Architecture:** Three focused evaluation modules own canonical artifact paths/Git identity, frozen-label governance, and production prediction capture. Two scripts remain thin adapters: freeze is offline and separate, while capture defaults to preflight and requires an explicit live confirmation before constructing the same `OpenAIStructuredCaseIntakeExtractor` used by the HTTP runtime.

**Tech Stack:** Python 3.11, Pydantic 2, asyncio, OpenAI Python SDK, pytest/pytest-asyncio, Ruff, Pyright.

**Spec:** `docs/superpowers/specs/2026-08-30-v1-1-production-prediction-capture-design.md`

## Global Constraints

- Production code lives only under `src/vietnamese_labor_law_assistant/`; scripts contain argument parsing and calls into the evaluation package only.
- Do not change the Case Intake prompt, `IssueRegistry`, Missing Facts, Clarification, Refined Issues, CaseGraph, retrieval, MCP, expected labels, reviewer decisions, or threshold values.
- Do not edit or overwrite the corrected candidate, review packet, threshold specification, approval sidecar, or historical Week 2/Week 3 evidence.
- Do not add a runtime dependency or an evaluation-only extractor.
- All tests are offline and use fake/spy extractors; tests must never call a provider.
- Implementation and verification must not run the operational freeze command, live capture command, or Prompt 6.
- The pre-freeze repository must be clean. At capture time, the only permitted worktree delta is the exact frozen dataset and freeze manifest created and checksum-bound after that checkpoint.
- The live extractor receives only `CaseIntakeInput(source_text=raw_user_input, source_ref=source_ref)`; `case_id` stays outside the extractor for bookkeeping.
- Every final artifact is exclusive-create. An intent or partial prediction file is permanent audit evidence and blocks a same-version rerun.
- Commit steps apply only after the user authorizes implementation commits. Stage only listed task paths and never include unrelated worktree changes.

## Planned File Map

- Create `src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1_artifacts.py` for canonical paths, hashes, exclusive writes, and Git policy.
- Create `src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1_freeze.py` for frozen-row and manifest contracts.
- Create `src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1_capture.py` for preflight, label isolation, and write-once capture.
- Modify `src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1_approval.py` only to support canonical repository-relative path identity with absolute file access.
- Create two thin scripts and mirrored evaluation tests.
- Create `docs/evaluation/decision_support_v1_1_production_capture.md` and update repository architecture ownership.

## Shared Offline Test Fixtures

Each test module that needs governed inputs copies them to a temporary repository-shaped tree. It
must never mutate the canonical files:

```python
PROJECT_ROOT = Path(__file__).parents[3]
FROZEN_AT = datetime(2026, 8, 30, 21, 0, tzinfo=timezone(timedelta(hours=7)))
CAPTURED_AT = datetime(2026, 8, 30, 21, 5, tzinfo=timezone(timedelta(hours=7)))
CLEAN_STATE = RepositoryState(commit_sha="b" * 40, tracked_dirty=False, untracked_paths=())


def copy_governed_inputs(tmp_path: Path) -> V11ArtifactPaths:
    source = V11ArtifactPaths.from_root(PROJECT_ROOT)
    target = V11ArtifactPaths.from_root(tmp_path)
    for name in (
        "corrected_candidate",
        "review_packet",
        "threshold_spec",
        "threshold_approval",
    ):
        source_path = getattr(source, name)
        target_path = getattr(target, name)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, target_path)
    return target


@pytest.fixture
def governed_paths(tmp_path: Path) -> V11ArtifactPaths:
    return copy_governed_inputs(tmp_path)


def configured_settings(secret: str = "test-secret") -> Settings:
    return Settings(
        openai_api_key=SecretStr(secret),
        llm_model="test-production-model",
        llm_provider="openai",
        llm_timeout_seconds=60,
        llm_max_retries=2,
        agent_structured_output_max_retries=2,
    )
```

Freeze tests also copy the exact files named by `V11_FREEZE_CODE_RELATIVE_PATHS` before calculating
code hashes. Capture tests create their frozen dataset and manifest from `prepare_v1_1_freeze` in
the temporary tree, then write those prepared bytes with `write_exclusive`; this is test-fixture
materialization, not the canonical operational freeze.

---

### Task 1: Canonical artifacts and repository-state policy

**Files:**

- Create: `src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1_artifacts.py`
- Test: `tests/unit/evaluation/test_decision_support_v1_1_artifacts.py`

**Interfaces:**

- Produces `V11ArtifactPaths.from_root(repo_root: Path) -> V11ArtifactPaths`.
- Produces `RepositoryState(commit_sha: str, tracked_dirty: bool, untracked_paths: tuple[str, ...])`.
- Produces `inspect_repository_state`, `require_pre_freeze_repository_state`, and `require_capture_repository_state`.
- Produces `sha256_file`, `sha256_bytes`, `canonical_json_bytes`, and `write_exclusive`.
- Produces the exact `V11_FREEZE_CODE_RELATIVE_PATHS` tuple used by freeze and capture validation.

- [ ] **Step 1: Write failing path, exclusive-write, and Git-policy tests**

```python
def test_paths_and_write_once_policy(tmp_path: Path) -> None:
    paths = V11ArtifactPaths.from_root(tmp_path)
    assert paths.frozen_dataset.relative_to(tmp_path).as_posix() == (
        "data/evaluation/decision_support/v1_1/v1_1_evaluation_frozen.jsonl"
    )
    assert paths.freeze_manifest.relative_to(tmp_path).as_posix() == (
        "evaluation/results/decision_support/v1_1/v1_1_frozen_dataset_manifest.json"
    )
    output = tmp_path / "evidence.json"
    write_exclusive(output, b"first\n")
    with pytest.raises(FileExistsError):
        write_exclusive(output, b"second\n")
    assert output.read_bytes() == b"first\n"


def test_repository_policy_is_clean_then_allows_only_bound_freeze_outputs(
    tmp_path: Path,
) -> None:
    paths = V11ArtifactPaths.from_root(tmp_path)
    clean = RepositoryState(commit_sha="a" * 40, tracked_dirty=False, untracked_paths=())
    require_pre_freeze_repository_state(clean)
    allowed = RepositoryState(
        commit_sha="a" * 40,
        tracked_dirty=False,
        untracked_paths=(
            paths.frozen_dataset.relative_to(tmp_path).as_posix(),
            paths.freeze_manifest.relative_to(tmp_path).as_posix(),
        ),
    )
    require_capture_repository_state(allowed, paths)
    invalid = allowed.model_copy(
        update={"untracked_paths": (*allowed.untracked_paths, "unrelated.txt")}
    )
    with pytest.raises(ValueError, match="unexpected worktree delta"):
        require_capture_repository_state(invalid, paths)
```

- [ ] **Step 2: Verify the tests fail before implementation**

```powershell
uv run pytest tests/unit/evaluation/test_decision_support_v1_1_artifacts.py -q
```

Expected: collection fails because the module is absent.

- [ ] **Step 3: Implement paths, serialization, writes, and Git inspection**

```python
@dataclass(frozen=True)
class V11ArtifactPaths:
    repo_root: Path
    corrected_candidate: Path
    review_packet: Path
    threshold_spec: Path
    threshold_approval: Path
    frozen_dataset: Path
    freeze_manifest: Path
    capture_intent: Path
    predictions: Path
    snapshot_manifest: Path

    @classmethod
    def from_root(cls, repo_root: Path) -> V11ArtifactPaths:
        root = repo_root.resolve()
        data = root / "data/evaluation/decision_support/v1_1"
        review = root / "evaluation/review/decision_support/v1_1"
        results = root / "evaluation/results/decision_support/v1_1"
        return cls(
            repo_root=root,
            corrected_candidate=data / "v1_1_evaluation_candidate_corrected.jsonl",
            review_packet=review
            / "v1_1_human_review_packet_corrected_prefilled_for_human_review.csv",
            threshold_spec=data / "v1_1_proposed_thresholds.json",
            threshold_approval=review / "v1_1_threshold_approval.json",
            frozen_dataset=data / "v1_1_evaluation_frozen.jsonl",
            freeze_manifest=results / "v1_1_frozen_dataset_manifest.json",
            capture_intent=results / "v1_1_production_case_intake_capture_intent.json",
            predictions=results / "v1_1_production_case_intake_predictions_final.jsonl",
            snapshot_manifest=results
            / "v1_1_production_case_intake_predictions_manifest.json",
        )


class RepositoryState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    tracked_dirty: bool
    untracked_paths: tuple[str, ...]


V11_FREEZE_CODE_RELATIVE_PATHS = (
    "src/vietnamese_labor_law_assistant/decision_support/intake.py",
    "src/vietnamese_labor_law_assistant/decision_support/models.py",
    "src/vietnamese_labor_law_assistant/decision_support/issue_registry.py",
    "src/vietnamese_labor_law_assistant/decision_support/missing_facts.py",
    "src/vietnamese_labor_law_assistant/decision_support/clarification.py",
    "src/vietnamese_labor_law_assistant/decision_support/refined_issues.py",
    "src/vietnamese_labor_law_assistant/agent/case_graph.py",
    "src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1.py",
    "src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1_approval.py",
    "src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1_artifacts.py",
    "src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1_freeze.py",
)


def canonical_json_bytes(payload: object) -> bytes:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return (text + "\n").encode("utf-8")


def write_exclusive(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
```

Use argument-vector Git calls:

```python
commit = subprocess.run(
    ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
    check=True,
    capture_output=True,
    text=True,
).stdout.strip()
tracked_dirty = any(
    subprocess.run(command, check=False, capture_output=True).returncode
    for command in (
        ["git", "-C", str(repo_root), "diff", "--quiet"],
        ["git", "-C", str(repo_root), "diff", "--cached", "--quiet"],
    )
)
untracked = subprocess.run(
    ["git", "-C", str(repo_root), "ls-files", "--others", "--exclude-standard"],
    check=True,
    capture_output=True,
    text=True,
).stdout.splitlines()
```

Sort repository-relative POSIX paths. Pre-freeze accepts no change. Capture accepts no tracked change and exactly the two frozen artifact paths.

- [ ] **Step 4: Run focused checks**

```powershell
uv run pytest tests/unit/evaluation/test_decision_support_v1_1_artifacts.py -q
uv run ruff check src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1_artifacts.py tests/unit/evaluation/test_decision_support_v1_1_artifacts.py
```

Expected: PASS with zero network access.

- [ ] **Step 5: Commit this unit if authorized**

```powershell
git add -- src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1_artifacts.py tests/unit/evaluation/test_decision_support_v1_1_artifacts.py
git diff --cached --check
git commit -m "feat(evaluation): add v1.1 artifact identity policy"
```


---

### Task 2: Offline frozen-dataset governance contract

**Files:**

- Create: `src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1_freeze.py`
- Modify: `src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1_approval.py`
- Test: `tests/unit/evaluation/test_decision_support_v1_1_freeze.py`
- Test: `tests/unit/evaluation/test_decision_support_v1_1_approval.py`

**Interfaces:**

- Consumes the existing candidate, review, leakage, threshold, and approval validators.
- Produces `V11FrozenEvaluationCase`, `V11FrozenDatasetManifest`, and `V11FreezeBundle`.
- Produces `prepare_v1_1_freeze(paths, *, project_author_name, repository_state, frozen_at=None) -> V11FreezeBundle`.
- Produces `freeze_v1_1_evaluation(paths, *, project_author_name, frozen_at=None) -> V11FrozenDatasetManifest`.
- Produces `load_v1_1_frozen_dataset(path) -> list[V11FrozenEvaluationCase]`.
- Extends `validate_v1_1_threshold_approval(..., threshold_spec_identity: str | None = None)`; default behavior remains unchanged.

- [ ] **Step 1: Write the approval identity regression**

```python
def test_threshold_validator_accepts_absolute_bytes_with_registered_identity(
    tmp_path: Path,
) -> None:
    paths = copy_governed_inputs(tmp_path)
    validation = approval.validate_v1_1_threshold_approval(
        paths.threshold_spec,
        paths.threshold_approval,
        project_author_name="mrhao165-del",
        threshold_spec_identity=(
            "data/evaluation/decision_support/v1_1/v1_1_proposed_thresholds.json"
        ),
    )
    assert validation.status == "PASS"
```

Create test approval evidence with that repository-relative path. The optional argument changes only path comparison; checksum, reviewer, and approval-state checks remain required.

- [ ] **Step 2: Write failing freeze tests with copied 26-case inputs**

```python
def test_prepare_freeze_changes_only_validator_owned_state(
    governed_paths: V11ArtifactPaths,
) -> None:
    state = RepositoryState(commit_sha="b" * 40, tracked_dirty=False, untracked_paths=())
    bundle = prepare_v1_1_freeze(
        governed_paths,
        project_author_name="mrhao165-del",
        repository_state=state,
        frozen_at=datetime(2026, 8, 30, 21, 0, tzinfo=timezone(timedelta(hours=7))),
    )
    assert len(bundle.cases) == 26
    assert all(case.human_validated for case in bundle.cases)
    assert all(case.review_status == "PASS" and case.frozen_final for case in bundle.cases)
    assert bundle.manifest.review_status == "PASS"
    assert bundle.manifest.threshold_approval_decision == "APPROVE_UNCHANGED"
    assert bundle.manifest.git_commit_sha == "b" * 40
    assert bundle.manifest.frozen_dataset_sha256 == sha256_bytes(bundle.dataset_bytes)


def test_freeze_rejects_approval_not_earlier_than_freeze(
    governed_paths: V11ArtifactPaths,
) -> None:
    state = RepositoryState(commit_sha="b" * 40, tracked_dirty=False, untracked_paths=())
    with pytest.raises(ValueError, match="threshold approval must precede frozen timestamp"):
        prepare_v1_1_freeze(
            governed_paths,
            project_author_name="mrhao165-del",
            repository_state=state,
            frozen_at=datetime(2026, 8, 30, 19, 0, tzinfo=timezone(timedelta(hours=7))),
        )


def test_freeze_is_separate_write_once_and_preserves_inputs(
    governed_paths: V11ArtifactPaths,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = (
        governed_paths.corrected_candidate,
        governed_paths.review_packet,
        governed_paths.threshold_spec,
        governed_paths.threshold_approval,
    )
    before = {path: path.read_bytes() for path in inputs}
    monkeypatch.setattr(freeze_module, "inspect_repository_state", lambda root: CLEAN_STATE)
    manifest = freeze_v1_1_evaluation(
        governed_paths,
        project_author_name="mrhao165-del",
        frozen_at=FROZEN_AT,
    )
    assert len(load_v1_1_frozen_dataset(governed_paths.frozen_dataset)) == 26
    assert manifest.case_count == 26
    assert before == {path: path.read_bytes() for path in inputs}
    with pytest.raises(FileExistsError):
        freeze_v1_1_evaluation(
            governed_paths,
            project_author_name="mrhao165-del",
            frozen_at=FROZEN_AT,
        )
```

Add mutation cases for review not 26/26 PASS, changed immutable labels, threshold or approval bytes, incomplete reviewer metadata, timezone-free timestamps, duplicate IDs, source-span/schema failure, and prediction-input audit not equal to `CHECKED_NO_PREDICTION_ARTIFACT_INPUT`.

- [ ] **Step 3: Run tests and verify the new contract is missing**

```powershell
uv run pytest tests/unit/evaluation/test_decision_support_v1_1_approval.py tests/unit/evaluation/test_decision_support_v1_1_freeze.py -q
```

Expected: FAIL because the identity extension and freeze module do not exist.

- [ ] **Step 4: Implement frozen rows, manifest, validation, and materialization**

```python
class V11FrozenEvaluationCase(V11EvaluationCandidateCase):
    frozen_schema_version: Literal["v1_1_frozen_case_v1"] = "v1_1_frozen_case_v1"
    human_validated: Literal[True] = True
    review_status: Literal["PASS"] = "PASS"
    frozen_final: Literal[True] = True
    reviewed_at: datetime
    review_evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class V11FrozenDatasetManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["v1_1_frozen_dataset_manifest_v1"]
    dataset_id: Literal["decision_support_v1_1_final"]
    dataset_version: Literal["v1_1_frozen"]
    case_count: Literal[26]
    ordered_case_ids_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    corrected_candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    frozen_dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_packet_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_status: Literal["PASS"]
    reviewed_at: datetime
    threshold_spec_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    threshold_approval_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    threshold_approval_decision: Literal["APPROVE_UNCHANGED"]
    threshold_approved_at: datetime
    evaluation_spec_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_file_sha256: dict[str, str]
    git_commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    pre_freeze_worktree_clean: Literal[True]
    frozen_at: datetime


class V11FreezeBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)
    cases: tuple[V11FrozenEvaluationCase, ...]
    dataset_bytes: bytes
    manifest: V11FrozenDatasetManifest
```

Run `load_v1_1_candidate`, `candidate_quality_report`, `validate_v1_1_review_packet`, and `validate_v1_1_threshold_approval`. Require exactly one timezone-aware review timestamp across the packet, candidate quality PASS, an empty leakage list, explicit no-prediction-input audit, and `threshold_approved_at < frozen_at`. Sort by case ID and serialize one canonical JSON object per line.

Use strict registered identity comparison:

```python
expected_identity = threshold_spec_identity or threshold_spec_path.as_posix()
if evidence.threshold_spec_path != expected_identity:
    errors.append("approval threshold_spec_path differs from the validated proposal")
```

Reject either existing freeze path before writing. Write dataset first and manifest second using `write_exclusive`. Preserve a first-file-only failure as blocking evidence.

- [ ] **Step 5: Run freeze and prerequisite regressions**

```powershell
uv run pytest tests/unit/evaluation/test_decision_support_v1_1_freeze.py tests/unit/evaluation/test_decision_support_v1_1_approval.py tests/unit/evaluation/test_decision_support_v1_1.py -q
uv run ruff check src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1_freeze.py src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1_approval.py tests/unit/evaluation/test_decision_support_v1_1_freeze.py tests/unit/evaluation/test_decision_support_v1_1_approval.py
```

Expected: PASS; test artifacts exist only below pytest temporary directories.

- [ ] **Step 6: Commit the freeze contract if authorized**

```powershell
git add -- src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1_freeze.py src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1_approval.py tests/unit/evaluation/test_decision_support_v1_1_freeze.py tests/unit/evaluation/test_decision_support_v1_1_approval.py
git diff --cached --check
git commit -m "feat(evaluation): add governed v1.1 freeze contract"
```


---

### Task 3: Label-isolated capture preflight

**Files:**

- Create: `src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1_capture.py`
- Test: `tests/unit/evaluation/test_decision_support_v1_1_capture.py`

**Interfaces:**

- Produces `V11RuntimeCase(case_id: str, case_input: CaseIntakeInput)`.
- Produces `V11NonSecretGenerationSettings` and `V11CapturePlan`.
- Produces `project_runtime_case(case: V11FrozenEvaluationCase) -> V11RuntimeCase`.
- Produces `preflight_v1_1_capture(paths, settings, *, project_author_name, repository_state=None) -> V11CapturePlan`.

- [ ] **Step 1: Write failing preflight and negative label-isolation tests**

```python
def test_runtime_projection_contains_only_bookkeeping_and_production_input(
    frozen_case: V11FrozenEvaluationCase,
) -> None:
    runtime = project_runtime_case(frozen_case)
    assert set(runtime.model_dump()) == {"case_id", "case_input"}
    assert runtime.case_input.model_dump(mode="json") == {
        "source_text": frozen_case.raw_user_input,
        "source_ref": frozen_case.source_ref,
        "source_type": "USER_MESSAGE",
    }
    serialized = json.dumps(runtime.model_dump(mode="json"))
    for prohibited in (
        "expected_case_facts",
        "critical_fact_ids",
        "date_fact_ids",
        "money_fact_ids",
        "source_spans",
        "assertion_verification_labels",
        "expected_candidate_issues",
        "critical_issue_codes",
        "expected_missing_fields",
        "expected_refined_issues",
        "expected_refined_issue_status",
        "expected_clarification_behavior",
        "expected_graph_status",
        "reviewer_notes_reasoning",
        "review_decision",
        "thresholds",
    ):
        assert prohibited not in serialized


def test_preflight_binds_governance_and_never_serializes_secret(
    captured_paths: V11ArtifactPaths,
) -> None:
    plan = preflight_v1_1_capture(
        captured_paths,
        configured_settings(secret="secret-value"),
        project_author_name="mrhao165-del",
        repository_state=capture_repository_state(captured_paths),
    )
    assert len(plan.runtime_cases) == 26
    assert plan.extractor_class.endswith(".OpenAIStructuredCaseIntakeExtractor")
    serialized = json.dumps(plan.model_dump(mode="json"))
    assert "OPENAI_API_KEY" not in serialized
    assert "secret-value" not in serialized
    assert plan.generation_settings.temperature == 0


@pytest.mark.parametrize(
    ("mutation", "error"),
    (
        ("candidate_checksum", "corrected candidate checksum changed"),
        ("review_checksum", "human review checksum changed"),
        ("threshold_checksum", "threshold specification checksum changed"),
        ("approval_checksum", "threshold approval checksum changed"),
        ("frozen_checksum", "frozen dataset checksum changed"),
        ("git_commit", "Git source commit changed"),
        ("unrelated_worktree_path", "unexpected worktree delta"),
        ("capture_artifact_exists", "capture artifact already exists"),
    ),
)
def test_preflight_fails_closed_on_bound_state_change(
    tmp_path: Path,
    mutation: str,
    error: str,
) -> None:
    paths, settings, state = governed_capture_fixture(tmp_path, mutation)
    with pytest.raises((ValueError, FileExistsError), match=error):
        preflight_v1_1_capture(
            paths,
            settings,
            project_author_name="mrhao165-del",
            repository_state=state,
        )
```

Add cases for `llm_configured=False`, Gemini without its required base URL, a changed code-file hash, review no longer 26/26, and invalid approval state.

Use these concrete fixture helpers; `prepare_capture_paths` copies the code paths listed in the
shared fixture section, prepares a freeze bundle, and writes its two outputs in the temporary tree:

```python
def prepare_capture_paths(tmp_path: Path) -> V11ArtifactPaths:
    paths = copy_governed_inputs(tmp_path)
    for relative in V11_FREEZE_CODE_RELATIVE_PATHS:
        source = PROJECT_ROOT / relative
        target = paths.repo_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    bundle = prepare_v1_1_freeze(
        paths,
        project_author_name="mrhao165-del",
        repository_state=CLEAN_STATE,
        frozen_at=FROZEN_AT,
    )
    write_exclusive(paths.frozen_dataset, bundle.dataset_bytes)
    write_exclusive(
        paths.freeze_manifest,
        canonical_json_bytes(bundle.manifest.model_dump(mode="json")),
    )
    return paths


def capture_repository_state(paths: V11ArtifactPaths) -> RepositoryState:
    return RepositoryState(
        commit_sha="b" * 40,
        tracked_dirty=False,
        untracked_paths=(
            paths.frozen_dataset.relative_to(paths.repo_root).as_posix(),
            paths.freeze_manifest.relative_to(paths.repo_root).as_posix(),
        ),
    )


@pytest.fixture
def captured_paths(tmp_path: Path) -> V11ArtifactPaths:
    return prepare_capture_paths(tmp_path)


@pytest.fixture
def ready_capture(
    captured_paths: V11ArtifactPaths,
) -> tuple[V11ArtifactPaths, V11CapturePlan, Settings]:
    settings = configured_settings()
    plan = preflight_v1_1_capture(
        captured_paths,
        settings,
        project_author_name="mrhao165-del",
        repository_state=capture_repository_state(captured_paths),
    )
    return captured_paths, plan, settings


def governed_capture_fixture(
    tmp_path: Path,
    mutation: str,
) -> tuple[V11ArtifactPaths, Settings, RepositoryState]:
    paths = prepare_capture_paths(tmp_path)
    state = capture_repository_state(paths)
    checksum_targets = {
        "candidate_checksum": paths.corrected_candidate,
        "review_checksum": paths.review_packet,
        "threshold_checksum": paths.threshold_spec,
        "approval_checksum": paths.threshold_approval,
        "frozen_checksum": paths.frozen_dataset,
    }
    if mutation in checksum_targets:
        with checksum_targets[mutation].open("ab") as handle:
            handle.write(b"\n")
    elif mutation == "git_commit":
        state = state.model_copy(update={"commit_sha": "c" * 40})
    elif mutation == "unrelated_worktree_path":
        state = state.model_copy(
            update={"untracked_paths": (*state.untracked_paths, "unrelated.txt")}
        )
    elif mutation == "capture_artifact_exists":
        write_exclusive(paths.capture_intent, b"{}\n")
    else:
        raise AssertionError(f"unknown mutation fixture: {mutation}")
    return paths, configured_settings(), state
```

- [ ] **Step 2: Run the test and verify the module is missing**

```powershell
uv run pytest tests/unit/evaluation/test_decision_support_v1_1_capture.py -q
```

Expected: FAIL during collection.

- [ ] **Step 3: Implement isolated runtime and sanitized metadata**

```python
class V11RuntimeCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    case_id: str
    case_input: CaseIntakeInput


class V11NonSecretGenerationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    provider: Literal["openai", "gemini_openai_compatible"]
    model: str
    base_url: str | None
    timeout_seconds: float
    transport_max_retries: int
    structured_output_max_retries: int
    temperature: Literal[0] = 0
    nominal_parse_calls: Literal[26] = 26
    maximum_parse_invocations: int
    theoretical_maximum_http_attempts: int


class V11CapturePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    runtime_cases: tuple[V11RuntimeCase, ...]
    dataset_id: Literal["decision_support_v1_1_final"]
    dataset_version: Literal["v1_1_frozen"]
    case_count: Literal[26]
    review_status: Literal["PASS"]
    threshold_approval_decision: Literal["APPROVE_UNCHANGED"]
    frozen_dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    freeze_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    corrected_candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_packet_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    threshold_spec_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    threshold_approval_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    git_commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    extractor_class: Literal[
        "vietnamese_labor_law_assistant.decision_support.intake."
        "OpenAIStructuredCaseIntakeExtractor"
    ]
    extractor_implementation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_identity_method: Literal["BOUND_TO_FULL_INTAKE_MODULE_BYTES"]
    response_schema_identity: Literal[
        "vietnamese_labor_law_assistant.decision_support.models.CaseIntakeResult"
    ]
    generation_settings: V11NonSecretGenerationSettings


def project_runtime_case(case: V11FrozenEvaluationCase) -> V11RuntimeCase:
    return V11RuntimeCase(
        case_id=case.case_id,
        case_input=CaseIntakeInput(source_text=case.raw_user_input, source_ref=case.source_ref),
    )
```

Preflight re-runs all governance validators, validates the frozen manifest/dataset, compares every checksum and ordered case ID, verifies code hashes, requires the same Git commit and allowed-delta worktree, rejects any existing capture artifact, and requires `settings.llm_configured`. It returns only copied runtime inputs and non-secret metadata. Never call `settings.model_dump()`.

Calculate call bounds exactly:

```python
parse_attempts = settings.agent_structured_output_max_retries + 1
http_attempts = settings.llm_max_retries + 1
maximum_parse_invocations = 26 * parse_attempts
theoretical_maximum_http_attempts = maximum_parse_invocations * http_attempts
```

- [ ] **Step 4: Run preflight checks**

```powershell
uv run pytest tests/unit/evaluation/test_decision_support_v1_1_capture.py -q
uv run ruff check src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1_capture.py tests/unit/evaluation/test_decision_support_v1_1_capture.py
```

Expected: PASS with zero provider calls.

- [ ] **Step 5: Commit preflight if authorized**

```powershell
git add -- src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1_capture.py tests/unit/evaluation/test_decision_support_v1_1_capture.py
git diff --cached --check
git commit -m "feat(evaluation): add isolated v1.1 capture preflight"
```

---

### Task 4: Write-once production prediction capture

**Files:**

- Modify: `src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1_capture.py`
- Modify: `tests/unit/evaluation/test_decision_support_v1_1_capture.py`

**Interfaces:**

- Produces `V11PredictionStatus`, `V11PredictionFailureReason`, `V11CaseIntakePredictionRecord`, `V11CaptureIntent`, and `V11PredictionSnapshotManifest`.
- Produces `capture_v1_1_predictions(paths, plan, settings, *, captured_at=None) -> Awaitable[V11PredictionSnapshotManifest]`.
- Produces `load_v1_1_prediction_records(path: Path) -> list[V11CaseIntakePredictionRecord]` for offline post-capture consumers.
- Constructs `OpenAIStructuredCaseIntakeExtractor(settings)` internally. Production has no extractor override; tests monkeypatch that exact imported class.

- [ ] **Step 1: Write failing spy, typed-failure, secret, and interruption tests**

```python
@pytest.mark.asyncio
async def test_capture_constructs_production_extractor_and_passes_only_case_input(
    ready_capture: tuple[V11ArtifactPaths, V11CapturePlan, Settings],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths, plan, settings = ready_capture
    received: list[CaseIntakeInput] = []

    class SpyProductionExtractor:
        def __init__(self, actual_settings: Settings) -> None:
            assert actual_settings is settings

        async def extract(self, case_input: CaseIntakeInput) -> CaseIntakeResult:
            received.append(case_input)
            return CaseIntakeResult()

    monkeypatch.setattr(capture_module, "OpenAIStructuredCaseIntakeExtractor", SpyProductionExtractor)
    manifest = await capture_v1_1_predictions(paths, plan, settings, captured_at=CAPTURED_AT)
    assert len(received) == 26
    assert all(type(item) is CaseIntakeInput for item in received)
    assert manifest.status == "COMPLETE"
    assert manifest.success_count == 26
    assert manifest.failure_count == 0


@pytest.mark.asyncio
async def test_typed_failure_is_recorded_and_final_status_fails(
    ready_capture: tuple[V11ArtifactPaths, V11CapturePlan, Settings],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths, plan, settings = ready_capture

    class FailingExtractor:
        def __init__(self, actual_settings: Settings) -> None:
            assert actual_settings is settings

        async def extract(self, case_input: CaseIntakeInput) -> CaseIntakeResult:
            if case_input is plan.runtime_cases[0].case_input:
                raise CaseIntakeError("CASE_INTAKE_TIMEOUT")
            return CaseIntakeResult()

    monkeypatch.setattr(capture_module, "OpenAIStructuredCaseIntakeExtractor", FailingExtractor)
    manifest = await capture_v1_1_predictions(paths, plan, settings, captured_at=CAPTURED_AT)
    records = load_v1_1_prediction_records(paths.predictions)
    assert manifest.status == "FAILED"
    assert manifest.failure_count == 1
    assert records[0].failure_reason == "CASE_INTAKE_TIMEOUT"
    assert records[0].result is None
```

Add an interruption test that raises `KeyboardInterrupt` on row 2, proves intent and one fsynced row remain, proves snapshot manifest is absent, and proves another attempt is refused. Recursively assert artifacts contain no test secret, `Authorization`, expected-label field names, reviewer notes, or threshold values.

- [ ] **Step 2: Run tests and verify execution is missing**

```powershell
uv run pytest tests/unit/evaluation/test_decision_support_v1_1_capture.py -q
```

Expected: FAIL for missing execution contracts.

- [ ] **Step 3: Implement typed prediction records**

```python
class V11PredictionStatus(StrEnum):
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"


class V11PredictionFailureReason(StrEnum):
    PROVIDER_UNAVAILABLE = "CASE_INTAKE_PROVIDER_UNAVAILABLE"
    EMPTY_OUTPUT = "CASE_INTAKE_EMPTY_OUTPUT"
    SOURCE_INVALID = "CASE_INTAKE_SOURCE_INVALID"
    SCHEMA_INVALID = "CASE_INTAKE_SCHEMA_INVALID"
    TIMEOUT = "CASE_INTAKE_TIMEOUT"
    PROVIDER_ERROR = "CASE_INTAKE_PROVIDER_ERROR"
    UNEXPECTED_ERROR = "CASE_INTAKE_UNEXPECTED_ERROR"


class V11CaseIntakePredictionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    sequence: int = Field(ge=1, le=26)
    case_id: str
    status: V11PredictionStatus
    result: CaseIntakeResult | None = None
    failure_reason: V11PredictionFailureReason | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> V11CaseIntakePredictionRecord:
        if (self.status is V11PredictionStatus.SUCCESS) != (self.result is not None):
            raise ValueError("SUCCESS requires one validated CaseIntakeResult")
        if (self.status is V11PredictionStatus.ERROR) != (self.failure_reason is not None):
            raise ValueError("ERROR requires one typed failure reason")
        return self


def load_v1_1_prediction_records(path: Path) -> list[V11CaseIntakePredictionRecord]:
    records = [
        V11CaseIntakePredictionRecord.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if [record.sequence for record in records] != list(range(1, len(records) + 1)):
        raise ValueError("prediction records must use contiguous frozen order")
    case_ids = [record.case_id for record in records]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("prediction records contain duplicate case IDs")
    return records
```

Intent and manifest contain only the plan checksums, code/schema identity, non-secret provider/model settings, timestamps, total/success/failure counts, and prediction checksum. Intent status is `STARTED`. Final status is `COMPLETE` only for 26 successes; otherwise `FAILED`.

- [ ] **Step 4: Implement durable write-once sequencing**

```python
async def capture_v1_1_predictions(
    paths: V11ArtifactPaths,
    plan: V11CapturePlan,
    settings: Settings,
    *,
    captured_at: datetime | None = None,
) -> V11PredictionSnapshotManifest:
    _require_no_capture_artifacts(paths)
    started_at = _timestamp_value(captured_at)
    write_exclusive(paths.capture_intent, canonical_json_bytes(_intent(plan, started_at)))
    extractor = OpenAIStructuredCaseIntakeExtractor(settings)
    success_count = 0
    failure_count = 0
    paths.predictions.parent.mkdir(parents=True, exist_ok=True)
    with paths.predictions.open("xb") as handle:
        for sequence, runtime_case in enumerate(plan.runtime_cases, start=1):
            try:
                extracted = await extractor.extract(runtime_case.case_input)
                result = validate_case_intake_result(runtime_case.case_input, extracted)
                record = V11CaseIntakePredictionRecord(
                    sequence=sequence,
                    case_id=runtime_case.case_id,
                    status=V11PredictionStatus.SUCCESS,
                    result=result,
                )
                success_count += 1
            except CaseIntakeError as exc:
                record = _failure_record(sequence, runtime_case.case_id, exc.reason)
                failure_count += 1
            except Exception:
                record = _failure_record(
                    sequence,
                    runtime_case.case_id,
                    V11PredictionFailureReason.UNEXPECTED_ERROR.value,
                )
                failure_count += 1
            handle.write(canonical_json_bytes(record.model_dump(mode="json")))
            handle.flush()
            os.fsync(handle.fileno())
    manifest = _snapshot_manifest(
        plan,
        started_at=started_at,
        completed_at=datetime.now().astimezone().replace(microsecond=0),
        predictions_sha256=sha256_file(paths.predictions),
        success_count=success_count,
        failure_count=failure_count,
    )
    write_exclusive(
        paths.snapshot_manifest,
        canonical_json_bytes(manifest.model_dump(mode="json")),
    )
    return manifest
```

Do not catch `BaseException`. Map only allowlisted `CaseIntakeError.reason` values; sanitize all other exceptions to `CASE_INTAKE_UNEXPECTED_ERROR`. Flush and fsync each row before the next provider request.

- [ ] **Step 5: Run capture/intake regressions**

```powershell
uv run pytest tests/unit/evaluation/test_decision_support_v1_1_capture.py tests/unit/decision_support/test_intake.py -q
uv run ruff check src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1_capture.py tests/unit/evaluation/test_decision_support_v1_1_capture.py
```

Expected: PASS with fake/spy extractors only.

- [ ] **Step 6: Commit write-once capture if authorized**

```powershell
git add -- src/vietnamese_labor_law_assistant/evaluation/decision_support_v1_1_capture.py tests/unit/evaluation/test_decision_support_v1_1_capture.py
git diff --cached --check
git commit -m "feat(evaluation): add write-once production capture"
```


---

### Task 5: Thin freeze and capture CLI adapters

**Files:**

- Create: `scripts/freeze_decision_support_v1_1.py`
- Create: `scripts/capture_decision_support_v1_1_predictions.py`
- Create: `tests/unit/evaluation/test_decision_support_v1_1_capture_cli.py`

**Interfaces:**

- Freeze requires `--freeze-reviewed-v1-1` and `--project-author-name`.
- Capture without `--live` performs preflight only.
- Live capture requires `--live --confirm-write-once V1_1_FINAL_CASE_INTAKE_CAPTURE`.
- Neither command accepts dataset/output overrides; `--repo-root` selects only a repository containing canonical relative paths.

- [ ] **Step 1: Write failing adapter safety tests**

```python
def load_script(relative_path: str, module_name: str) -> ModuleType:
    specification = importlib.util.spec_from_file_location(module_name, PROJECT_ROOT / relative_path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


capture_script = load_script(
    "scripts/capture_decision_support_v1_1_predictions.py",
    "capture_decision_support_v1_1_predictions",
)
freeze_script = load_script(
    "scripts/freeze_decision_support_v1_1.py",
    "freeze_decision_support_v1_1",
)
PLAN = object()


def test_capture_cli_without_live_runs_preflight_only(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(capture_script, "get_settings", object)
    monkeypatch.setattr(capture_script, "preflight_v1_1_capture", lambda *args, **kwargs: PLAN)
    monkeypatch.setattr(capture_script, "_preflight_report", lambda plan: {"status": "PASS"})
    monkeypatch.setattr(
        capture_script,
        "capture_v1_1_predictions",
        lambda *args, **kwargs: calls.append("live"),
    )
    assert capture_script.main(["--project-author-name", "mrhao165-del"]) == 0
    assert calls == []


def test_capture_cli_requires_exact_write_once_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(capture_script, "get_settings", object)
    monkeypatch.setattr(capture_script, "preflight_v1_1_capture", lambda *args, **kwargs: PLAN)
    with pytest.raises(SystemExit):
        capture_script.main(["--project-author-name", "mrhao165-del", "--live"])


def test_freeze_cli_requires_explicit_acknowledgement() -> None:
    with pytest.raises(SystemExit):
        freeze_script.main(["--project-author-name", "mrhao165-del"])
```

Also assert imports perform no I/O, parsers expose no artifact-path overrides, and reports contain no credential name/value.

- [ ] **Step 2: Run tests and verify scripts are missing**

```powershell
uv run pytest tests/unit/evaluation/test_decision_support_v1_1_capture_cli.py -q
```

Expected: FAIL during import.

- [ ] **Step 3: Implement the offline freeze adapter**

```python
def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--project-author-name", required=True)
    parser.add_argument("--freeze-reviewed-v1-1", action="store_true")
    args = parser.parse_args(argv)
    if not args.freeze_reviewed_v1_1:
        parser.error("--freeze-reviewed-v1-1 is required")
    manifest = freeze_v1_1_evaluation(
        V11ArtifactPaths.from_root(args.repo_root),
        project_author_name=args.project_author_name,
    )
    print(json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0
```

The freeze adapter imports no settings and exposes no timestamp override.

- [ ] **Step 4: Implement preflight-default and explicit-live capture**

```python
CONFIRMATION = "V1_1_FINAL_CASE_INTAKE_CAPTURE"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--project-author-name", required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--confirm-write-once")
    args = parser.parse_args(argv)
    settings = get_settings()
    paths = V11ArtifactPaths.from_root(args.repo_root)
    plan = preflight_v1_1_capture(
        paths,
        settings,
        project_author_name=args.project_author_name,
    )
    if not args.live:
        print(json.dumps(_preflight_report(plan), ensure_ascii=False, indent=2))
        return 0
    if args.confirm_write_once != CONFIRMATION:
        parser.error(f"--confirm-write-once must equal {CONFIRMATION}")
    manifest = asyncio.run(capture_v1_1_predictions(paths, plan, settings))
    print(json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0 if manifest.status == "COMPLETE" else 1
```

Build `_preflight_report` from checksums, artifact paths, provider/model, and call bounds only. Never serialize `Settings`.

- [ ] **Step 5: Run adapter tests and help-only commands**

```powershell
uv run pytest tests/unit/evaluation/test_decision_support_v1_1_capture_cli.py -q
uv run python scripts/freeze_decision_support_v1_1.py --help
uv run python scripts/capture_decision_support_v1_1_predictions.py --help
uv run ruff check scripts/freeze_decision_support_v1_1.py scripts/capture_decision_support_v1_1_predictions.py tests/unit/evaluation/test_decision_support_v1_1_capture_cli.py
```

Expected: PASS/help output only. Do not use either operational acknowledgement.

- [ ] **Step 6: Commit adapters if authorized**

```powershell
git add -- scripts/freeze_decision_support_v1_1.py scripts/capture_decision_support_v1_1_predictions.py tests/unit/evaluation/test_decision_support_v1_1_capture_cli.py
git diff --cached --check
git commit -m "feat(evaluation): add controlled v1.1 capture commands"
```

---

### Task 6: Documentation, architecture review, and offline verification

**Files:**

- Create: `docs/evaluation/decision_support_v1_1_production_capture.md`
- Modify: `docs/architecture/repository_structure.md`
- Verify only: `.env.example` and governed/historical artifacts.

**Interfaces:**

- Documents exact OpenAI-default and existing Gemini-compatible PowerShell configuration.
- Documents freeze, preflight, one live capture, and offline-after-capture sequence.
- Documents 26 nominal parse requests, 78 maximum structured invocations, 234 theoretical HTTP attempts, and zero downstream LLM calls.

- [ ] **Step 1: Write the operator document with exact configuration**

```markdown
# V1.1 production Case Intake prediction capture

This workflow has one live-provider stage. Freeze and preflight are offline; Missing Facts,
Clarification, Refined Issues, CaseGraph evaluation, metrics, and release gates remain offline after
the snapshot exists.

## OpenAI-default PowerShell configuration

    $env:OPENAI_API_KEY="<YOUR_SECRET>"
    $env:LLM_MODEL="<YOUR_SUPPORTED_MODEL_ID>"
    $env:LLM_PROVIDER="openai"
    $env:LLM_TIMEOUT_SECONDS="60"
    $env:LLM_MAX_RETRIES="2"
    $env:AGENT_STRUCTURED_OUTPUT_MAX_RETRIES="2"
```

Also document the supported Gemini-compatible values already present in `.env.example`, the exact implemented commands, write-once token, every artifact path, typed-failure semantics, partial-attempt blocking, retry bounds, and prohibition on downstream LLM calls.

- [ ] **Step 2: Update repository ownership**

Add this statement to the current v1.1 evaluation paragraph:

```markdown
`evaluation/decision_support_v1_1_artifacts.py`, `_freeze.py`, and `_capture.py` own the canonical
write-once release-evaluation boundary. Freeze validates and binds the reviewed labels and unchanged
threshold approval offline; capture projects only `CaseIntakeInput` into the production extractor.
The scripts are thin adapters, and no downstream evaluation stage may make another provider call.
```

- [ ] **Step 3: Run focused and regression tests offline**

```powershell
uv run pytest tests/unit/evaluation/test_decision_support_v1_1_artifacts.py tests/unit/evaluation/test_decision_support_v1_1_freeze.py tests/unit/evaluation/test_decision_support_v1_1_capture.py tests/unit/evaluation/test_decision_support_v1_1_capture_cli.py tests/unit/evaluation/test_decision_support_v1_1.py tests/unit/evaluation/test_decision_support_v1_1_approval.py tests/unit/decision_support -q
uv run pytest tests/integration/test_week3_decision_support_contracts.py tests/integration/test_week4_case_analysis_workflow.py -q
```

Expected: PASS without network access and without creating canonical frozen/prediction artifacts.

- [ ] **Step 4: Run formatting, lint, typing, and lock checks**

```powershell
uv run ruff format --check src scripts tests
uv run ruff check src scripts tests
uv run pyright
uv lock --check
git diff --check
```

Expected: PASS. Report any pre-existing repository-wide failure exactly and still run focused checks over every task file.

- [ ] **Step 5: Run architecture and protected-artifact reviews**

```powershell
python .agents/skills/protected-artifact-guard/scripts/scan_protected_diff.py
git status --short
git diff -- data/evaluation evaluation/results
```

Apply `architecture-boundary-review` manually: core ownership remains `evaluation`, scripts contain no business/governance logic, imports are absolute, and every new production module has a mirrored unit test. Confirm no frozen dataset, prediction snapshot, threshold change, expected-label change, or historical result modification was introduced.

- [ ] **Step 6: Commit documentation only if authorized and non-overlapping**

```powershell
git add -- docs/evaluation/decision_support_v1_1_production_capture.md
git add -p -- docs/architecture/repository_structure.md
git diff --cached --check
git diff --cached -- docs/architecture/repository_structure.md
git commit -m "docs(evaluation): document v1.1 production capture"
```

If the architecture document has unrelated pre-existing hunks that cannot be staged independently, do not commit it; stop and report the overlap.

- [ ] **Step 7: Report readiness without operational execution**

```text
Frozen artifacts created: NO
Live LLM calls performed: 0
Prompt 6 run: NO
Canonical capture preflight implemented: YES
Ready for clean checkpoint and later explicit freeze: YES/NO
```

Do not claim readiness unless focused tests, label-isolation/write-once tests, Ruff, Pyright, architecture review, and protected-artifact review passed or an external blocker is stated precisely.
