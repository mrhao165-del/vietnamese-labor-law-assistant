"""Build immutable Week 5 reports from completed checkpoints and Week 4 provenance."""

from __future__ import annotations

import csv
import json
import math
import statistics
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil
import torch
from FlagEmbedding import FlagReranker
from transformers import AutoTokenizer

from vietnamese_labor_law_assistant.evaluation.dataset import load_questions
from vietnamese_labor_law_assistant.evaluation.metrics import retrieval_metrics
from vietnamese_labor_law_assistant.evaluation.models import RetrievalPrediction
from vietnamese_labor_law_assistant.ingestion.identifiers import calculate_file_sha256
from vietnamese_labor_law_assistant.retrieval.models import RetrievedChunk
from vietnamese_labor_law_assistant.retrieval.rerank_text import build_rerank_passage

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evaluation/results"
CHECKPOINTS = RESULTS / "week5_reranker_checkpoints"
DATASET = ROOT / "data/evaluation/labor_law_eval_v1.jsonl"
CORPUS = ROOT / "data/processed/labor_law_clauses.jsonl"
MODEL = "BAAI/bge-reranker-v2-m3"
SELECTED_ID = "R2_H2_C10_O5_L512_B1"
R1_ID = "R1_DENSE_C10_O5_L512_B1"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def checkpoint_predictions(split: str, config_id: str) -> dict[str, RetrievalPrediction]:
    records = read_jsonl(CHECKPOINTS / split / config_id / "predictions.jsonl")
    return {row["question_id"]: RetrievalPrediction.model_validate(row) for row in records}


def checkpoint_records(split: str, config_id: str) -> dict[str, dict[str, Any]]:
    return {
        row["question_id"]: row
        for row in read_jsonl(CHECKPOINTS / split / config_id / "predictions.jsonl")
    }


def percentile(values: list[int], fraction: float) -> int | None:
    if not values:
        return None
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)]


class RssSampler:
    """Sample process RSS while loading the already-selected CPU model."""

    def __init__(self) -> None:
        self.process = psutil.Process()
        self.peak = self.process.memory_info().rss
        self.running = False
        self.thread = threading.Thread(target=self._sample, daemon=True)

    def _sample(self) -> None:
        while self.running:
            self.peak = max(self.peak, self.process.memory_info().rss)
            time.sleep(0.02)

    def __enter__(self) -> RssSampler:
        self.running = True
        self.thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.running = False
        self.thread.join()
        self.peak = max(self.peak, self.process.memory_info().rss)


def resource_report() -> dict[str, object]:
    with RssSampler() as sampler:
        FlagReranker(MODEL, use_fp16=False, devices="cpu", batch_size=1, max_length=512)
    return {
        "device": "cpu",
        "fp16": False,
        "peak_rss_bytes": sampler.peak,
        "peak_rss_mib": round(sampler.peak / (1024 * 1024), 2),
        "cuda": bool(torch.cuda.is_available()),
        "peak_vram": None,
        "gpu_benchmark_status": "NOT_AVAILABLE_IN_CURRENT_ENVIRONMENT",
        "measurement": (
            "RSS sampled during selected BAAI/bge-reranker-v2-m3 CPU model initialization; "
            "no benchmark questions rerun."
        ),
    }


def rerank_passage(chunk: dict[str, Any]) -> str:
    return build_rerank_passage(
        RetrievedChunk(
            rank=1,
            score=0.0,
            **{
                key: chunk[key]
                for key in (
                    "chunk_id",
                    "document_id",
                    "document_name",
                    "chapter_number",
                    "chapter_title",
                    "section_number",
                    "section_title",
                    "article_number",
                    "article_title",
                    "clause_number",
                    "point_label",
                    "point_labels",
                    "content",
                    "source_file",
                    "source_url",
                    "source_block_start",
                    "source_block_end",
                    "content_sha256",
                )
            },
        )
    )


def token_report(
    questions: dict[str, Any], records: dict[str, dict[str, Any]], corpus: dict[str, dict[str, Any]]
) -> dict[str, object]:
    tokenizer = AutoTokenizer.from_pretrained(MODEL)
    counts: list[int] = []
    for question_id, record in records.items():
        for chunk_id in record["retrieved_chunk_ids"]:
            counts.append(
                len(
                    tokenizer(
                        questions[question_id].question,
                        rerank_passage(corpus[chunk_id]),
                        add_special_tokens=True,
                        truncation=False,
                    )["input_ids"]
                )
            )
    over_512 = sum(value > 512 for value in counts)
    over_768 = sum(value > 768 for value in counts)
    return {
        "model": MODEL,
        "tokenizer": MODEL,
        "tokenization": "query/passage pair, add_special_tokens=True, truncation=False",
        "pair_count": len(counts),
        "min": min(counts) if counts else None,
        "max": max(counts) if counts else None,
        "mean": statistics.fmean(counts) if counts else None,
        "median": statistics.median(counts) if counts else None,
        "p95": percentile(counts, 0.95),
        "p99": percentile(counts, 0.99),
        "over_512": over_512,
        "over_768": over_768,
        "selected_max_length": 512,
        "selected_truncation_count": over_512,
        "selected_truncation_rate": over_512 / len(counts) if counts else 0.0,
        "sample_scope": (
            "five retained reranked passages for every completed selected R2 DEV and TEST "
            "checkpoint question"
        ),
    }


def first_rank(record: dict[str, Any], expected: set[str]) -> int | None:
    return next(
        (
            index + 1
            for index, chunk_id in enumerate(record["retrieved_chunk_ids"])
            if chunk_id in expected
        ),
        None,
    )


def error_analysis(
    questions: dict[str, Any],
    b0: dict[str, dict[str, Any]],
    b1: dict[str, dict[str, Any]],
    l1: dict[str, dict[str, Any]],
    r2: dict[str, dict[str, Any]],
    truncation: dict[str, object],
) -> str:
    rows: list[tuple[str, str]] = []
    for question_id, question in questions.items():
        if question_id not in r2:
            continue
        expected = set(question.expected_chunk_ids)
        before = first_rank(b1[question_id], expected)
        after = first_rank(r2[question_id], expected)
        prefix = f"`{question_id}` ({question.category})"
        if before and after and after < before:
            rows.append(("rank tăng", f"{prefix}: expected rank {before} → {after}."))
        elif before and after and after > before:
            rows.append(("rank giảm", f"{prefix}: expected rank {before} → {after}."))
        elif before and after and after == before:
            rows.append(("không đổi", f"{prefix}: expected rank giữ ở {after}."))
        if b0[question_id]["retrieved_chunk_ids"][:5] != b1[question_id]["retrieved_chunk_ids"][:5]:
            rows.append(("Dense và H2 khác nhau", f"{prefix}: top-5 Dense và H2 khác nhau."))
        if question.category == "legal_keyword" and before and after:
            rows.append(
                (
                    "keyword sai ngữ cảnh",
                    f"{prefix}: kiểm tra keyword; expected {before} → {after}.",
                )
            )
        if question.category == "natural_paraphrase" and before and after:
            rows.append(
                ("paraphrase", f"{prefix}: paraphrase giữ/đổi expected rank {before} → {after}.")
            )
        if question.expected_clauses:
            rows.append(
                (
                    "query Điều/Khoản",
                    f"{prefix}: có expected clause; expected rank {before} → {after}.",
                )
            )
    missing_h2 = [
        question_id
        for question_id, question in questions.items()
        if question.expected_chunk_ids
        and not set(question.expected_chunk_ids).intersection(
            b1[question_id]["retrieved_chunk_ids"]
        )
    ]
    missing_l1 = [
        question_id
        for question_id, question in questions.items()
        if question.expected_chunk_ids
        and not set(question.expected_chunk_ids).intersection(
            l1[question_id]["retrieved_chunk_ids"]
        )
    ]
    rows.append(
        (
            "candidate pool thiếu expected chunk",
            f"`{missing_l1[0]}`: L1 BM25 candidate pool thiếu expected chunk; "
            f"selected H2 has {len(missing_h2)}/60 such cases.",
        )
        if not missing_h2
        else (
            "candidate pool thiếu expected chunk",
            f"`{missing_h2[0]}`: expected chunk không có trong selected H2 pool.",
        ),
    )
    rows.append(
        (
            "truncation",
            "Selected 512 truncates "
            f"{truncation['selected_truncation_count']}/{truncation['pair_count']} measured pairs.",
        )
    )
    required = [
        "rank tăng",
        "rank giảm",
        "không đổi",
        "Dense và H2 khác nhau",
        "keyword sai ngữ cảnh",
        "paraphrase",
        "query Điều/Khoản",
    ]
    selected: list[tuple[str, str]] = []
    for category in required:
        candidates = [row for row in rows if row[0] == category]
        if category == "keyword sai ngữ cảnh":
            candidates.sort(key=lambda row: "expected 1 → 1" in row[1])
        selected.extend(candidates[:1])
    selected.extend([row for row in rows if row[0] == "rank tăng"][:1])
    selected.extend([row for row in rows if row[0] == "candidate pool thiếu expected chunk"])
    selected.extend([row for row in rows if row[0] == "truncation"])
    lines = [
        "# Week 5 reranker error analysis",
        "",
        "All examples are completed checkpoint/provenance records; no synthetic cases.",
        "",
        "| Type | Actual case |",
        "|---|---|",
    ]
    lines.extend(f"| {category} | {detail} |" for category, detail in selected)
    lines.extend(["", f"Case count: {len(selected)}."])
    return "\n".join(lines) + "\n"


def main() -> int:
    selection = read_json(RESULTS / "week5_dev_selection.json")
    if selection["final_config"]["id"] != SELECTED_ID:
        raise RuntimeError("selected configuration changed; refusing to build official reports")
    dataset_hash = calculate_file_sha256(DATASET)
    corpus_hash = calculate_file_sha256(CORPUS)
    week4 = read_json(RESULTS / "week4_retrieval_comparison.json")
    if week4["dataset_sha256"] != dataset_hash or week4["input_chunk_sha256"] != corpus_hash:
        raise RuntimeError("Week 4 provenance checksum does not match the official inputs")
    questions = load_questions(DATASET)
    question_by_id = {question.question_id: question for question in questions}
    corpus = {row["chunk_id"]: row for row in read_jsonl(CORPUS)}
    b0 = {
        row["question_id"]: row
        for row in read_jsonl(RESULTS / "week4_retrieval_predictions.jsonl")
        if row["configuration"] == "L0_DENSE"
    }
    b1 = {
        row["question_id"]: row
        for row in read_jsonl(RESULTS / "week4_retrieval_predictions.jsonl")
        if row["configuration"] == "H2_DENSE_UNDERTHESEA_RRF"
    }
    l1 = {
        row["question_id"]: row
        for row in read_jsonl(RESULTS / "week4_retrieval_predictions.jsonl")
        if row["configuration"] == "L1_BM25_WHITESPACE"
    }
    r1_dev = checkpoint_predictions("dev", R1_ID)
    r2_test = checkpoint_predictions("test", SELECTED_ID)
    r2_all = checkpoint_records("dev", SELECTED_ID) | checkpoint_records("test", SELECTED_ID)
    provenance = {row["configuration"]: row for row in week4["results"]}
    reports = [
        {
            "configuration": "B0_DENSE_NO_RERANK",
            "selection_split": "week4_provenance_all",
            "evidence": "Week 4 L0_DENSE official provenance; matching dataset/corpus checksums.",
            "metrics": provenance["L0_DENSE"]["metrics"],
        },
        {
            "configuration": "B1_H2_NO_RERANK",
            "selection_split": "week4_provenance_all",
            "evidence": (
                "Week 4 H2_DENSE_UNDERTHESEA_RRF official provenance; "
                "matching dataset/corpus checksums."
            ),
            "metrics": provenance["H2_DENSE_UNDERTHESEA_RRF"]["metrics"],
        },
        {
            "configuration": "R1_DENSE_RERANK",
            "selection_split": "dev",
            "evidence": f"Real model checkpoint: dev/{R1_ID}.",
            "metrics": retrieval_metrics([q for q in questions if q.split == "dev"], r1_dev),
        },
        {
            "configuration": "R2_H2_RERANK",
            "selection_split": "test_once",
            "evidence": (
                f"Real model checkpoint: test/{SELECTED_ID}; single selected-config TEST run."
            ),
            "metrics": retrieval_metrics([q for q in questions if q.split == "test"], r2_test),
        },
    ]
    tokens = token_report(question_by_id, r2_all, corpus)
    resources = resource_report()
    report = {
        "status": "PROVISIONAL_PENDING_INDEPENDENT_HUMAN_LABEL_CONFIRMATION",
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset_sha256": dataset_hash,
        "input_chunk_sha256": corpus_hash,
        "selection_artifact": "evaluation/results/week5_dev_selection.json",
        "final_retrieval_pipeline": "R2_H2_RERANK",
        "final_candidate_k": 10,
        "final_rerank_output_k": 5,
        "final_reranker_max_length": 512,
        "final_reranker_batch_size": 1,
        "resource_report": resources,
        "reports": reports,
    }
    write_json(RESULTS / "week5_reranker_comparison.json", report)
    with (RESULTS / "week5_reranker_comparison.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        fields = [
            "configuration",
            "selection_split",
            "recall_at_5",
            "mrr",
            "hit_rate_at_1",
            "mean_latency_ms",
            "p95_latency_ms",
            "error_rate",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in reports:
            row = {
                "configuration": item["configuration"],
                "selection_split": item["selection_split"],
            }
            row.update({field: item["metrics"].get(field) for field in fields[2:]})
            writer.writerow(row)
    markdown = [
        "# Week 5 official reranker comparison",
        "",
        "| Pipeline | Split | Recall@5 | MRR | Hit@1 | Mean ms | P95 ms |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for item in reports:
        metric = item["metrics"]
        markdown.append(
            f"| {item['configuration']} | {item['selection_split']} | "
            f"{metric['recall_at_5']:.4f} | {metric['mrr']:.4f} | "
            f"{metric['hit_rate_at_1']:.4f} | {metric['mean_latency_ms']:.2f} | "
            f"{metric['p95_latency_ms']:.2f} |"
        )
    markdown.extend(
        [
            "",
            "B0/B1 are checksum-matched Week 4 provenance; "
            "R1/R2 are real reranker model checkpoints.",
        ]
    )
    (RESULTS / "week5_reranker_comparison.md").write_text(
        "\n".join(markdown) + "\n", encoding="utf-8"
    )
    tokens.update(
        {
            "dataset_sha256": dataset_hash,
            "corpus_sha256": corpus_hash,
            "generated_at": report["generated_at"],
        }
    )
    write_json(ROOT / "data/processed/reranker_token_report.json", tokens)
    (RESULTS / "week5_reranker_error_analysis.md").write_text(
        error_analysis(question_by_id, b0, b1, l1, r2_all, tokens), encoding="utf-8"
    )
    (ROOT / "docs/week5_reranker.md").write_text(
        "# Week 5 reranker\n\n"
        "`R2_H2_C10_O5_L512_B1` is the DEV-selected configuration. "
        "TEST was run once only for that selected configuration. "
        "The official comparison distinguishes Week 4 baseline provenance "
        "from real reranker checkpoints.\n\n"
        "## Final configuration\n\n"
        "- `FINAL_RETRIEVAL_PIPELINE=R2_H2_RERANK`\n"
        "- `FINAL_CANDIDATE_K=10`\n"
        "- `FINAL_RERANK_OUTPUT_K=5`\n"
        "- `FINAL_RERANKER_MAX_LENGTH=512`\n"
        "- `FINAL_RERANKER_BATCH_SIZE=1`\n\n"
        "Reranking is not made the application default by this benchmark; "
        "runtime default remains independently controlled by settings.\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "PROVISIONAL_REPORTS_WRITTEN",
                "resource_report": resources,
                "token_report": tokens,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
