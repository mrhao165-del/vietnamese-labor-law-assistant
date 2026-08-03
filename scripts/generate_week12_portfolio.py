"""Generate checksum-backed Week 12 benchmark and release provenance artefacts."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vietnamese_labor_law_assistant.evaluation.week12_portfolio import (
    PORTFOLIO_SCHEMA_VERSION,
    SELECTED_RETRIEVAL_CONFIG,
    build_benchmark_summary,
    sha256_file,
    validate_benchmark_summary,
    write_benchmark_files,
)


def command_output(*args: str) -> str:
    return subprocess.run(
        args,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


def build_release_manifest(root: Path) -> dict[str, Any]:
    dataset_manifest = json.loads(
        (root / "data/evaluation/labor_law_eval_v1_manifest.json").read_text(encoding="utf-8")
    )
    dense_manifest = json.loads(
        (root / "data/processed/dense_index_manifest.json").read_text(encoding="utf-8")
    )
    lexical_manifest = json.loads(
        (root / "data/processed/lexical/bm25s_underthesea/manifest.json").read_text(
            encoding="utf-8"
        )
    )
    reranker_manifest = json.loads(
        (root / "data/processed/reranker_manifest.json").read_text(encoding="utf-8")
    )
    return {
        "schema_version": PORTFOLIO_SCHEMA_VERSION,
        "status": "PASS",
        "generated_at": datetime.now(UTC).isoformat(),
        "source_commit": command_output("git", "rev-parse", "HEAD"),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "corpus": {
            "path": "data/processed/labor_law_clauses.jsonl",
            "sha256": sha256_file(root / "data/processed/labor_law_clauses.jsonl"),
        },
        "evaluation_dataset": {
            "path": "data/evaluation/labor_law_eval_v1.jsonl",
            "sha256": sha256_file(root / "data/evaluation/labor_law_eval_v1.jsonl"),
            "manifest_path": "data/evaluation/labor_law_eval_v1_manifest.json",
            "manifest_sha256": sha256_file(
                root / "data/evaluation/labor_law_eval_v1_manifest.json"
            ),
            "split_status": dataset_manifest["split_status"],
            "total_questions": dataset_manifest["total_questions"],
            "dev_questions": 42,
            "test_questions": 18,
        },
        "retrieval": {
            "selected_config": SELECTED_RETRIEVAL_CONFIG,
            "dense_model": dense_manifest.get("model_name", "BAAI/bge-m3"),
            "lexical_tokenizer": lexical_manifest.get("tokenizer", "underthesea"),
            "lexical_index": "BM25S",
            "fusion": "Reciprocal Rank Fusion (rrf_k=60)",
            "reranker": reranker_manifest.get("model_name", "BAAI/bge-reranker-v2-m3"),
            "candidate_k": 10,
            "output_k": 5,
            "reranker_max_length": 512,
            "reranker_batch_size": 1,
        },
        "agent": {
            "workflow": "finite LangGraph",
            "mcp_transport": "project-owned stdio child processes",
            "llm_provider": "gemini_openai_compatible",
            "llm_model": "gemini-3.1-flash-lite",
        },
        "guardrail": {
            "semantic_model": "BAAI/bge-m3",
            "lower_threshold": 0.35,
            "high_threshold": 0.75,
            "llm_judge_enabled": False,
            "fail_closed": True,
        },
        "lockfiles": {
            "uv.lock": sha256_file(root / "uv.lock"),
            "frontend/package-lock.json": sha256_file(root / "frontend/package-lock.json"),
            "compose.yaml": sha256_file(root / "compose.yaml"),
        },
        "benchmark_runners": {
            "portfolio": "week12-portfolio-v1",
            "dense": "scripts/run_week2_current_dense_baseline.py",
            "hybrid": "scripts/run_week4_current_retrieval_benchmark.py",
            "reranker": "scripts/run_week5_current_reranker_benchmark.py",
            "agent": "scripts/run_week9_agent_evaluation.py",
            "guardrail": "scripts/run_week10_guardrail_evaluation.py",
        },
        "secrets_recorded": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output_dir = root / "evaluation/results/week12"
    benchmark = build_benchmark_summary(root)
    validate_benchmark_summary(benchmark)
    if args.check:
        recorded = json.loads((output_dir / "benchmark_summary.json").read_text(encoding="utf-8"))
        validate_benchmark_summary(recorded)
        if recorded != benchmark:
            raise SystemExit("benchmark_summary.json is not reproducible from source artefacts")
        print("PASS: Week 12 benchmark schema and reproducibility")
        return
    write_benchmark_files(
        benchmark,
        output_dir / "benchmark_summary.json",
        output_dir / "benchmark_summary.csv",
    )
    manifest = build_release_manifest(root)
    (output_dir / "release_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print("PASS: generated Week 12 benchmark summary and release manifest")


if __name__ == "__main__":
    main()
