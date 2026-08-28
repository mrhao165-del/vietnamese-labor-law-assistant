"""Deterministic Week 12 portfolio aggregation and review-packet contracts."""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PORTFOLIO_SCHEMA_VERSION = "1.0"
SELECTED_RETRIEVAL_CONFIG = "R2_H2_C10_O5_L512_B1"
PHASE_MANIFEST_NAMES = {
    "historical": "release_manifest.json",
    "remediation": "remediation_manifest.json",
    "final": "final_release_manifest.json",
}
HISTORICAL_FRONTEND_LOCK_PATH = "frontend/package-lock.json"
HISTORICAL_FRONTEND_LOCK_REF = "v1.0.0"

REQUIRED_BENCHMARK_FIELDS = {
    "tier",
    "metric",
    "definition",
    "split",
    "sample_count",
    "source_result_file",
    "config",
    "value",
    "unit",
    "applicability",
    "provenance",
    "notes",
}

TIER_ORDER = {
    "V1_DENSE": 1,
    "V2_HYBRID": 2,
    "V3_HYBRID_RERANKER": 3,
    "V4_MCP_AGENT_GUARDRAIL": 4,
}


@dataclass(frozen=True)
class MetricSpec:
    name: str
    definition: str
    unit: str


@dataclass(frozen=True)
class VersionedChecksumSource:
    """Exact bytes read by an adapter from one named repository revision."""

    revision: str
    content: bytes


RETRIEVAL_METRICS = (
    MetricSpec("hit_rate_at_1", "Eligible questions with a relevant chunk at rank 1.", "ratio"),
    MetricSpec("recall_at_5", "Mean relevant-chunk recall within the first five results.", "ratio"),
    MetricSpec("mrr", "Mean reciprocal rank of the first relevant result.", "ratio"),
    MetricSpec("mean_latency_ms", "Arithmetic mean measured query latency.", "ms"),
    MetricSpec("p95_latency_ms", "95th percentile measured query latency.", "ms"),
    MetricSpec("error_rate", "Fraction of evaluated questions ending in an error.", "ratio"),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_checksum_digests(
    root: Path,
    relative_paths: Iterable[str],
    *,
    versioned_sources: Mapping[str, VersionedChecksumSource] | None = None,
) -> dict[str, str]:
    """Resolve exact-byte digests under the allowlisted historical-source policy."""

    paths = tuple(relative_paths)
    sources = dict(versioned_sources or {})
    for relative_path in sources:
        if relative_path != HISTORICAL_FRONTEND_LOCK_PATH:
            raise ValueError(f"versioned checksum source is not allowed: {relative_path}")
        if relative_path not in paths:
            raise ValueError(f"versioned checksum source is unused: {relative_path}")

    resolved: dict[str, str] = {}
    for relative_path in paths:
        if relative_path == HISTORICAL_FRONTEND_LOCK_PATH:
            source = sources.get(relative_path)
            if source is None:
                raise ValueError(
                    "versioned checksum source is missing: "
                    f"{relative_path}@{HISTORICAL_FRONTEND_LOCK_REF}"
                )
            if source.revision != HISTORICAL_FRONTEND_LOCK_REF:
                raise ValueError(f"versioned checksum revision mismatch: {relative_path}")
            resolved[relative_path] = hashlib.sha256(source.content).hexdigest()
            continue

        path = root / relative_path
        resolved[relative_path] = sha256_file(path) if path.is_file() else "MISSING"
    return resolved


def validate_checksum_contract(
    root: Path,
    checksums: Mapping[str, object],
    *,
    versioned_sources: Mapping[str, VersionedChecksumSource] | None = None,
    context: str,
) -> None:
    """Validate historical lock bytes by policy and every other target in the worktree."""

    for relative_path, expected in checksums.items():
        if (
            not isinstance(relative_path, str)
            or not isinstance(expected, str)
            or len(expected) != 64
            or any(character not in "0123456789abcdef" for character in expected)
        ):
            raise ValueError(f"invalid checksum digest: {relative_path}")

    actual_by_path = resolve_checksum_digests(
        root,
        checksums,
        versioned_sources=versioned_sources,
    )
    for relative_path, expected in checksums.items():
        actual = actual_by_path[relative_path]
        if actual != expected:
            raise ValueError(f"{context} checksum mismatch: {relative_path}")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def select_phase_manifest(result_dir: Path, phase: str = "auto") -> Path:
    """Select an explicit release phase, preferring the current final candidate for auto."""

    if phase == "auto":
        for candidate in ("final", "remediation", "historical"):
            path = result_dir / PHASE_MANIFEST_NAMES[candidate]
            if path.exists():
                return path
        raise ValueError("no Week 12 phase manifest exists")
    try:
        path = result_dir / PHASE_MANIFEST_NAMES[phase]
    except KeyError as exc:
        raise ValueError(f"unsupported manifest phase: {phase}") from exc
    if not path.exists():
        raise ValueError(f"manifest for phase {phase} does not exist")
    return path


def validate_final_candidate_manifest(
    root: Path,
    manifest: Mapping[str, Any],
    *,
    versioned_sources: Mapping[str, VersionedChecksumSource] | None = None,
) -> None:
    """Validate current candidate inputs without mutating historical phase evidence."""

    if manifest.get("phase") != "POST_ROUND3_FINAL_RELEASE_CANDIDATE":
        raise ValueError("invalid final release manifest phase")
    if manifest.get("selected_retrieval_config") != SELECTED_RETRIEVAL_CONFIG:
        raise ValueError("final release manifest selected configuration changed")
    checksums = manifest.get("checksums")
    if not isinstance(checksums, Mapping):
        raise ValueError("final release manifest checksums must be an object")
    validate_checksum_contract(
        root,
        checksums,
        versioned_sources=versioned_sources,
        context="final release manifest",
    )
    thresholds = manifest.get("guardrail_thresholds")
    if thresholds != {"lower": 0.35, "high": 0.75}:
        raise ValueError("final release manifest guardrail thresholds changed")
    historical = manifest.get("historical_manifests")
    if not isinstance(historical, Mapping) or set(historical) != {
        "release_manifest.json",
        "remediation_manifest.json",
    }:
        raise ValueError("final release manifest historical references are incomplete")
    result_dir = root / "evaluation/results/week12"
    for name, expected in historical.items():
        if not isinstance(expected, str) or sha256_file(result_dir / name) != expected:
            raise ValueError(f"historical manifest checksum mismatch: {name}")


def _row(
    *,
    tier: str,
    metric: MetricSpec,
    split: str,
    sample_count: int,
    source: str,
    config: str,
    value: int | float | None,
    notes: str = "",
) -> dict[str, Any]:
    applicable = value is not None
    return {
        "tier": tier,
        "metric": metric.name,
        "definition": metric.definition,
        "split": split,
        "sample_count": sample_count,
        "source_result_file": source,
        "config": config,
        "value": value,
        "unit": metric.unit,
        "applicability": "APPLICABLE" if applicable else "N/A",
        "provenance": "REUSED_CHECKSUM_ALIGNED_LOCKED_ARTEFACT",
        "notes": notes if applicable else notes or "Metric was not recorded by the source runner.",
    }


def _retrieval_rows(
    tier: str,
    source: str,
    config: str,
    split: str,
    sample_count: int,
    metrics: Mapping[str, Any],
) -> list[dict[str, Any]]:
    return [
        _row(
            tier=tier,
            metric=metric,
            split=split,
            sample_count=sample_count,
            source=source,
            config=config,
            value=metrics.get(metric.name),
        )
        for metric in RETRIEVAL_METRICS
    ]


def build_benchmark_summary(root: Path) -> dict[str, Any]:
    dense_path = root / "evaluation/results/week2_dense_current_baseline.json"
    hybrid_path = root / "evaluation/results/week4_current_retrieval_comparison.json"
    reranker_path = root / "evaluation/results/week5_current_reranker_comparison.json"
    agent_path = root / "evaluation/results/week9_agent_metrics.json"
    guardrail_path = root / "evaluation/results/week10_guardrail_metrics.json"

    dense = load_json(dense_path)
    hybrid = load_json(hybrid_path)
    reranker = load_json(reranker_path)
    agent = load_json(agent_path)
    guardrail = load_json(guardrail_path)

    expected_dataset = dense["dataset_sha256"]
    expected_corpus = dense["corpus_sha256"]
    aligned = (hybrid["dataset_sha256"], reranker["dataset_sha256"]) == (
        expected_dataset,
        expected_dataset,
    ) and (hybrid["corpus_sha256"], reranker["corpus_sha256"]) == (
        expected_corpus,
        expected_corpus,
    )
    if not aligned:
        raise ValueError("V1-V3 source artefacts are not checksum aligned")
    if reranker["selected_config"] != SELECTED_RETRIEVAL_CONFIG:
        raise ValueError("selected retrieval configuration changed")

    hybrid_pipeline = next(
        item for item in hybrid["pipelines"] if item["pipeline_id"] == "H2_DENSE_UNDERTHESEA_RRF"
    )
    reranker_dev = next(
        item
        for item in reranker["dev_results"]
        if item["configuration"]["id"] == SELECTED_RETRIEVAL_CONFIG
    )

    rows = _retrieval_rows(
        "V1_DENSE",
        dense_path.relative_to(root).as_posix(),
        dense["pipeline_id"],
        dense["dataset_split"].upper(),
        dense["question_count"],
        dense["metrics"],
    )
    rows += _retrieval_rows(
        "V2_HYBRID",
        hybrid_path.relative_to(root).as_posix(),
        hybrid_pipeline["pipeline_id"],
        "DEV",
        hybrid["question_count"],
        hybrid_pipeline["metrics"],
    )
    rows += _retrieval_rows(
        "V3_HYBRID_RERANKER",
        reranker_path.relative_to(root).as_posix(),
        SELECTED_RETRIEVAL_CONFIG,
        "DEV",
        reranker_dev["prediction_count"],
        reranker_dev["metrics"],
    )

    v4_agent_specs = (
        MetricSpec("intent_accuracy", "Exact expected Agent route match.", "ratio"),
        MetricSpec("tool_selection_accuracy", "Exact expected tool-set match.", "ratio"),
        MetricSpec("parameter_exact_match", "Exact expected tool-parameter match.", "ratio"),
        MetricSpec("tool_call_success_rate", "Successful expected tool calls.", "ratio"),
        MetricSpec("out_of_scope_accuracy", "Correct out-of-scope handling.", "ratio"),
        MetricSpec("clarification_accuracy", "Correct clarification-required handling.", "ratio"),
        MetricSpec(
            "error_handling_success_rate", "Expected error contracts handled safely.", "ratio"
        ),
        MetricSpec("average_tool_calls", "Mean tool calls per evaluated request.", "calls/request"),
        MetricSpec("mean_latency_ms", "Mean offline contract-workflow latency.", "ms"),
        MetricSpec("p95_latency_ms", "P95 offline contract-workflow latency.", "ms"),
        MetricSpec("timeout_rate", "Fraction of requests ending in timeout.", "ratio"),
    )
    for metric in v4_agent_specs:
        rows.append(
            _row(
                tier="V4_MCP_AGENT_GUARDRAIL",
                metric=metric,
                split="OFFLINE_AGENT_CONTRACT",
                sample_count=agent["case_count"],
                source=agent_path.relative_to(root).as_posix(),
                config="finite-langgraph+project-mcp-stdio",
                value=agent["metrics"].get(metric.name),
                notes="Dataset-driven fake router/MCP envelopes; not live LLM latency."
                if metric.name in {"mean_latency_ms", "p95_latency_ms"}
                else "",
            )
        )

    guardrail_specs = (
        MetricSpec(
            "citation_existence_accuracy",
            "Correct detection of required citation presence.",
            "ratio",
        ),
        MetricSpec(
            "retrieved_membership_accuracy",
            "Citation IDs correctly checked against bounded evidence.",
            "ratio",
        ),
        MetricSpec(
            "citation_support_rate",
            "Supported outcomes divided by evaluated guardrail cases.",
            "ratio",
        ),
        MetricSpec(
            "unsupported_detection_recall", "Recall for expected unsupported cases.", "ratio"
        ),
        MetricSpec(
            "insufficient_context_detection_recall",
            "Recall for expected insufficient-context cases.",
            "ratio",
        ),
        MetricSpec(
            "out_of_scope_refusal_accuracy",
            "Correct safe refusal for out-of-scope fixture.",
            "ratio",
        ),
        MetricSpec(
            "mean_verification_latency_ms",
            "Mean deterministic guardrail verification latency.",
            "ms",
        ),
        MetricSpec(
            "p95_verification_latency_ms", "P95 deterministic guardrail verification latency.", "ms"
        ),
    )
    for metric in guardrail_specs:
        rows.append(
            _row(
                tier="V4_MCP_AGENT_GUARDRAIL",
                metric=metric,
                split="OFFLINE_GUARDRAIL_CONTRACT",
                sample_count=guardrail["case_count"],
                source=guardrail_path.relative_to(root).as_posix(),
                config="week10-fail-closed-lower0.35-high0.75",
                value=guardrail["metrics"].get(metric.name),
            )
        )

    rows = deterministic_metric_order(rows)
    summary = {
        "schema_version": PORTFOLIO_SCHEMA_VERSION,
        "status": "PASS",
        "classification": "PORTFOLIO_AGGREGATION_OF_EXISTING_EVIDENCE",
        "dataset_sha256": expected_dataset,
        "corpus_sha256": expected_corpus,
        "selected_retrieval_config": SELECTED_RETRIEVAL_CONFIG,
        "test_used_for_tuning": False,
        "rows": rows,
        "limitations": [
            "V1-V3 are aligned DEV retrieval comparisons; the locked V3 TEST result remains "
            "in its source artefact.",
            "V4 combines two separately labelled 40-case offline contract suites and is not "
            "a retrieval-only comparison.",
            "Faithfulness, response relevancy, and answer correctness are N/A because no "
            "reproducible judge-backed metric exists.",
        ],
    }
    validate_benchmark_summary(summary)
    return summary


def deterministic_metric_order(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        (dict(row) for row in rows),
        key=lambda row: (
            TIER_ORDER.get(str(row.get("tier")), 99),
            str(row.get("split")),
            str(row.get("metric")),
            str(row.get("source_result_file")),
        ),
    )


def validate_benchmark_summary(summary: Mapping[str, Any]) -> None:
    rows = summary.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("benchmark summary rows must be a non-empty list")
    seen: set[tuple[str, str, str, str]] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"row {index} must be an object")
        missing = REQUIRED_BENCHMARK_FIELDS - set(row)
        if missing:
            raise ValueError(f"row {index} missing fields: {sorted(missing)}")
        key = (
            str(row["tier"]),
            str(row["split"]),
            str(row["metric"]),
            str(row["source_result_file"]),
        )
        if key in seen:
            raise ValueError(f"duplicate metric row: {key}")
        seen.add(key)
        value = row["value"]
        if value is None and row["applicability"] != "N/A":
            raise ValueError(f"missing metric {key} must be marked N/A")
        if value is not None and row["applicability"] != "APPLICABLE":
            raise ValueError(f"recorded metric {key} must be applicable")
    if [dict(row) for row in rows] != deterministic_metric_order(rows):
        raise ValueError("benchmark rows are not deterministically ordered")


def validate_final_agent_guardrail(report: Mapping[str, Any]) -> None:
    """Validate the bounded V4 result schema without inventing missing metrics."""

    if report.get("schema_version") != "4.0" or report.get("status") != "PASS":
        raise ValueError("invalid final Agent/guardrail report header")
    sample_count = report.get("sample_count")
    metrics = report.get("metrics")
    if not isinstance(sample_count, int) or sample_count <= 0 or not isinstance(metrics, dict):
        raise ValueError("invalid final Agent/guardrail sample schema")
    required = {
        "route_tool_selection_accuracy",
        "parameter_accuracy",
        "tool_call_success",
        "clarification_accuracy",
        "out_of_scope_accuracy",
        "insufficient_context_accuracy",
        "citation_existence",
        "citation_validity",
        "citation_support",
        "timeout_rate",
        "error_rate",
        "mean_latency_ms",
        "p95_latency_ms",
    }
    if set(metrics) != required:
        raise ValueError("final Agent/guardrail metric set mismatch")
    for name in required - {"mean_latency_ms", "p95_latency_ms", "citation_support"}:
        metric = metrics[name]
        if not isinstance(metric, dict) or not {
            "value",
            "numerator",
            "denominator",
        }.issubset(metric):
            raise ValueError(f"invalid final metric schema: {name}")
        denominator = metric["denominator"]
        numerator = metric["numerator"]
        if not isinstance(denominator, int) or denominator <= 0:
            raise ValueError(f"invalid final metric denominator: {name}")
        if not isinstance(numerator, int) or not 0 <= numerator <= denominator:
            raise ValueError(f"invalid final metric numerator: {name}")
    if report.get("provenance") != "LIVE_DOCKER_CPU_LLM":
        raise ValueError("final Agent/guardrail provenance is not live Docker CPU/LLM")
    if metrics["mean_latency_ms"] < 0 or metrics["p95_latency_ms"] < 0:
        raise ValueError("final Agent/guardrail latency must be non-negative")


def write_benchmark_files(summary: Mapping[str, Any], json_path: Path, csv_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    fieldnames = list(next(iter(summary["rows"])).keys())
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summary["rows"])


def bounded_excerpt(value: str, limit: int = 500) -> str:
    normalized = " ".join(value.split())
    return normalized if len(normalized) <= limit else normalized[: limit - 1] + "…"


def review_row(
    case: Mapping[str, Any], response: Mapping[str, Any], review_id: str
) -> dict[str, Any]:
    citations = response.get("citations") or []
    traces = response.get("tool_trace") or []
    verification = response.get("verification") or {}
    expected_articles = case.get("expected_article_arguments") or []
    if not expected_articles and case.get("expected_article_number") is not None:
        expected_articles = [case["expected_article_number"]]
    return {
        "review_id": review_id,
        "question_id": case["fixture_id"],
        "category": case["review_category"],
        "question": case["question"],
        "expected_route": case["expected_route"],
        "expected_tool_calls": json.dumps(case.get("expected_tools", []), ensure_ascii=False),
        "expected_article_clause_point": json.dumps(expected_articles, ensure_ascii=False),
        "system_answer": response.get("answer_text") or response.get("answer") or "",
        "citations": json.dumps(citations, ensure_ascii=False),
        "retrieved_contexts_or_bounded_excerpts": json.dumps(
            [
                {
                    "chunk_id": citation.get("chunk_id"),
                    "article": citation.get("article_number"),
                    "clause": citation.get("clause_number"),
                    "point": citation.get("point_label"),
                    "excerpt": bounded_excerpt(str(citation.get("excerpt") or "")),
                }
                for citation in citations
            ],
            ensure_ascii=False,
        ),
        "verification_result": json.dumps(verification, ensure_ascii=False),
        "warnings": json.dumps(response.get("warnings") or [], ensure_ascii=False),
        "latency_ms": response.get("latency_ms"),
        "observed_tool_calls": json.dumps(
            [trace.get("tool_name") for trace in traces], ensure_ascii=False
        ),
        "provenance": "LIVE_HTTP_AGENT_RESPONSE",
        "reviewer_decision": "",
        "reviewer_name": "",
        "reviewer_role": "",
        "reviewed_at": "",
        "evidence_note": "",
    }


def validate_review_rows(
    rows: Sequence[Mapping[str, Any]],
    expected_count: int = 24,
    *,
    reviewer_fields_must_be_blank: bool = True,
) -> None:
    if len(rows) != expected_count:
        raise ValueError(f"expected {expected_count} manual-review rows, got {len(rows)}")
    ids = [str(row["review_id"]) for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate review_id")
    if reviewer_fields_must_be_blank:
        for row in rows:
            for field in (
                "reviewer_decision",
                "reviewer_name",
                "reviewer_role",
                "reviewed_at",
                "evidence_note",
            ):
                if row.get(field):
                    raise ValueError(f"{field} must remain blank")
