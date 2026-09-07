"""Write-once four-case provider transport probe; never a quality or release evaluation."""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.decision_support.intake import (
    CANDIDATE_ISSUE_SYSTEM_PROMPT,
    FACT_EXTRACTION_SYSTEM_PROMPT,
    CaseIntakeError,
    OpenAIStructuredCaseIntakeExtractor,
)
from vietnamese_labor_law_assistant.decision_support.models import CaseIntakeInput
from vietnamese_labor_law_assistant.evaluation.decision_support_hybrid_fact_development import (
    HybridFactGenerationConfig,
    production_pipeline_sha256,
    validate_hybrid_provider_settings,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_provider_pacing import (
    DevelopmentRequestPacer,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_split_inference_development import (
    load_split_inference_synthetic_cases,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_artifacts import (
    canonical_json_bytes,
    sha256_bytes,
    write_exclusive,
)

_DEVELOPMENT_ROOT = Path(__file__).resolve().parents[3] / (
    "evaluation/development/decision_support/v1_1/post_rc2"
)
_RUNS_ROOT = _DEVELOPMENT_ROOT / "runs"
_CASE_IDS = tuple(f"split-inference-dev-{n}" for n in ("004", "008", "012", "006"))


async def run_transport_probe(
    settings: Settings,
    output_dir: Path,
    *,
    request_pacing_seconds: float = 10,
    inter_case_pacing_seconds: float = 1,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> dict[str, object]:
    """Project only four source inputs, record each observation, and stop on terminal failure."""

    if (
        output_dir.resolve().parent != _RUNS_ROOT.resolve()
        or re.fullmatch(r"transport-probe-hybrid-fact-v2-[A-Za-z0-9._-]{1,80}", output_dir.name)
        is None
    ):
        raise ValueError("transport probe requires a new direct development run namespace")
    if output_dir.exists():
        raise FileExistsError("transport probe namespace already exists")
    if settings.llm_provider != "gemini_openai_compatible":
        raise ValueError("this probe is authorized for Gemini only")
    config = HybridFactGenerationConfig.model_validate(
        {
            **validate_hybrid_provider_settings(settings).model_dump(),
            "request_pacing_seconds": request_pacing_seconds,
            "inter_case_pacing_seconds": inter_case_pacing_seconds,
        }
    )
    pacer = DevelopmentRequestPacer(request_pacing_seconds, sleep=sleep)
    DevelopmentRequestPacer(inter_case_pacing_seconds)  # Reuse finite pacing validation.
    matrix_path = _DEVELOPMENT_ROOT / "split_inference_synthetic_v1.jsonl"
    cases = {case.case_id: case for case in load_split_inference_synthetic_cases(matrix_path)}
    claim = {
        "schema_version": "case_intake_transport_probe_v1",
        "mode": "CASE_INTAKE_TRANSPORT_PROBE_NOT_QUALITY",
        "started_at": datetime.now(UTC).isoformat(),
        "case_ids": _CASE_IDS,
        "generation_config": config.model_dump(mode="json"),
        "request_pacing_seconds": request_pacing_seconds,
        "inter_case_pacing_seconds": inter_case_pacing_seconds,
        "matrix_sha256": sha256_bytes(matrix_path.read_bytes()),
        "fact_prompt_sha256": sha256_bytes(FACT_EXTRACTION_SYSTEM_PROMPT.encode()),
        "issue_prompt_sha256": sha256_bytes(CANDIDATE_ISSUE_SYSTEM_PROMPT.encode()),
        "production_pipeline_sha256": production_pipeline_sha256(),
        "old26_executed": False,
        "release_holdout_accessed": False,
    }
    write_exclusive(output_dir / "transport_probe_claim.json", canonical_json_bytes(claim))
    events: list[dict[str, object]] = []

    def observe(event: dict[str, object]) -> None:
        events.append(event)
        write_exclusive(
            output_dir / f"transport_attempt_{len(events):03}.json", canonical_json_bytes(event)
        )

    extractor = OpenAIStructuredCaseIntakeExtractor(
        settings,
        before_request=pacer.before_request,
        transport_observer=observe,
    )
    records: list[dict[str, object]] = []
    started = time.perf_counter()
    for case_id in _CASE_IDS:
        case = cases[case_id]
        case_input = CaseIntakeInput(source_text=case.source_text, source_ref=case.source_ref)
        try:
            result, audit = await extractor.extract_with_transport_audit(case_input)
            record: dict[str, object] = {
                "case_id": case_id,
                "status": "SUCCESS",
                "result": result.model_dump(mode="json"),
                "audit": audit.model_dump(mode="json"),
            }
        except CaseIntakeError as exc:
            record = {
                "case_id": case_id,
                "status": "ERROR",
                "reason": exc.reason,
                "boundary": exc.boundary,
            }
        records.append(record)
        write_exclusive(output_dir / f"{case_id}.json", canonical_json_bytes(record))
        if record["status"] != "SUCCESS":
            break
        if case_id != _CASE_IDS[-1]:
            await sleep(inter_case_pacing_seconds)
    completed = len(records) == 4 and all(r["status"] == "SUCCESS" for r in records)
    report = {
        **claim,
        "completed_at": datetime.now(UTC).isoformat(),
        "total_duration_seconds": time.perf_counter() - started,
        "status": "PASS" if completed else "BLOCKED_EXTERNAL",
        "all_four_cases_completed": completed,
        "logical_boundary_calls": len({(e["case_id"], e["boundary"]) for e in events}),
        "observed_application_transport_attempts": len(events),
        "rate_limit_errors": sum(e["status"] == 429 for e in events),
        "rate_limit_events": [e for e in events if e["status"] == 429],
        "records": records,
    }
    write_exclusive(output_dir / "transport_probe_report.json", canonical_json_bytes(report))
    return report
