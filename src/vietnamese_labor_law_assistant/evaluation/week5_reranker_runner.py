"""Durable service for the staged Week 5 reranker benchmark.

The public CLI delegates here so there is exactly one implementation of
checkpointing, staged DEV selection, TEST gating, and final artifact writing.
"""

from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from vietnamese_labor_law_assistant.common.settings import Settings, get_settings
from vietnamese_labor_law_assistant.evaluation.dataset import load_questions
from vietnamese_labor_law_assistant.evaluation.metrics import retrieval_metrics
from vietnamese_labor_law_assistant.evaluation.models import RetrievalPrediction
from vietnamese_labor_law_assistant.ingestion.identifiers import calculate_file_sha256
from vietnamese_labor_law_assistant.retrieval.bm25_store import Bm25Store
from vietnamese_labor_law_assistant.retrieval.dense import DenseRetriever
from vietnamese_labor_law_assistant.retrieval.embeddings import BgeM3EmbeddingProvider
from vietnamese_labor_law_assistant.retrieval.hybrid import HybridRetriever
from vietnamese_labor_law_assistant.retrieval.lexical_tokenizers import get_lexical_tokenizer
from vietnamese_labor_law_assistant.retrieval.qdrant_store import QdrantStore
from vietnamese_labor_law_assistant.retrieval.reranker import BgeReranker
from vietnamese_labor_law_assistant.retrieval.sparse import SparseRetriever

ROOT = Path(__file__).resolve().parents[3]
DATASET = ROOT / "data/evaluation/labor_law_eval_v1.jsonl"
CORPUS = ROOT / "data/processed/labor_law_clauses.jsonl"
RESULTS = ROOT / "evaluation/results"
PLAN_PATH = RESULTS / "week5_reranker_plan.json"
SELECTION_PATH = RESULTS / "week5_dev_selection.json"
CHECKPOINTS = RESULTS / "week5_reranker_checkpoints"
STAGES = ("A", "B", "C")


def config_id(source: str, candidates: int, output: int, length: int, batch: int) -> str:
    """Return a stable, human-readable reranker configuration identifier."""
    prefix = "R1_DENSE" if source == "dense" else "R2_H2"
    return f"{prefix}_C{candidates}_O{output}_L{length}_B{batch}"


def checkpoint_fingerprint(configuration: dict[str, Any], dataset_checksum: str) -> str:
    """Hash every setting that makes a checkpoint's predictions incompatible."""
    value = {
        "configuration": {
            key: configuration[key] for key in ("source", "candidates", "output", "length", "batch")
        },
        "dataset_checksum": dataset_checksum,
    }
    return sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def rerank_score_fingerprint(configuration: dict[str, Any], dataset_checksum: str) -> str:
    """Hash score-producing inputs; output cutoffs may reuse the same scores."""
    value = {
        "configuration": {
            key: configuration[key] for key in ("source", "candidates", "length", "batch")
        },
        "dataset_checksum": dataset_checksum,
    }
    return sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def atomic_json(path: Path, value: object) -> None:
    """Atomically replace a JSON state file after flushing its content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def load_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    """Load complete JSONL rows keyed by question ID and reject duplicates."""
    records: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        key = value["question_id"]
        if key in records:
            raise ValueError(f"duplicate question prediction: {key}")
        records[key] = value
    return records


def append_prediction(path: Path, value: dict[str, Any]) -> None:
    """Append one complete prediction and flush it before advancing state."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def run_slice(
    questions: list[Any],
    predictions_path: Path,
    state_path: Path,
    budget_seconds: int,
    process: Callable[[Any], dict[str, Any]],
    max_questions: int | None = None,
    fingerprint: str | None = None,
) -> dict[str, object]:
    """Run unfinished questions until the safe time or question limit is reached."""
    if budget_seconds < 1:
        raise ValueError("time budget must be at least one second")
    if max_questions is not None and max_questions < 1:
        raise ValueError("max questions per run must be at least one")
    completed = load_jsonl(predictions_path)
    question_ids = {question.question_id for question in questions}
    unexpected = sorted(set(completed) - question_ids)
    if unexpected:
        raise ValueError(f"checkpoint has question IDs outside this split: {unexpected[0]}")
    started = time.monotonic()
    processed = 0
    for question in questions:
        if question.question_id in completed:
            continue
        if processed == max_questions or time.monotonic() - started >= max(0, budget_seconds - 30):
            break
        result = process(question)
        if result.get("question_id") != question.question_id:
            raise ValueError("checkpoint processor returned the wrong question ID")
        append_prediction(predictions_path, result)
        completed[question.question_id] = result
        processed += 1
        atomic_json(
            state_path,
            _state("RUNNING", completed, questions, started, fingerprint),
        )
    pending = [
        question.question_id for question in questions if question.question_id not in completed
    ]
    result = _state(
        "COMPLETE" if not pending else "PARTIAL", completed, questions, started, fingerprint
    )
    atomic_json(state_path, result)
    return result


def _state(
    status: str,
    completed: dict[str, dict[str, Any]],
    questions: list[Any],
    started: float,
    fingerprint: str | None,
) -> dict[str, object]:
    pending = [
        question.question_id for question in questions if question.question_id not in completed
    ]
    state: dict[str, object] = {
        "status": status,
        "completed": len(completed),
        "total": len(questions),
        "completed_question_ids": sorted(completed),
        "next_question_id": pending[0] if pending else None,
        "elapsed_seconds": time.monotonic() - started,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    if fingerprint is not None:
        state["fingerprint"] = fingerprint
    return state


def execute_week5_command(command: str, **arguments: Any) -> dict[str, Any]:
    """Execute one Week 5 service command and return a JSON-safe report."""
    handlers: dict[str, Callable[..., dict[str, Any]]] = {
        "plan": create_plan,
        "status": status,
        "run-dev": run_dev,
        "select-dev": select_dev,
        "run-test": run_test,
        "validate": validate,
        "finalize": finalize,
    }
    try:
        handler = handlers[command]
    except KeyError as exc:
        raise ValueError(f"unsupported Week 5 command: {command}") from exc
    return handler(**arguments)


def create_plan(**_: Any) -> dict[str, Any]:
    """Write the deterministic staged DEV plan without touching benchmark checkpoints."""
    plan = _load_plan(required=False)
    if plan is None:
        stage_a = [
            _configuration(source, candidate, 5, 512, 1)
            for source in ("dense", "h2")
            for candidate in (10, 20, 30)
        ]
        plan = {
            "status": "PLANNED",
            "created_at": datetime.now(UTC).isoformat(),
            "selection_split": "dev",
            "stages": {
                "A": {"status": "READY", "configurations": stage_a},
                "B": {
                    "status": "WAITING_FOR_STAGE_A",
                    "rule": "best candidate from each pipeline; O5/O8, L512, B1",
                    "configurations": [],
                },
                "C": {
                    "status": "WAITING_FOR_STAGE_B",
                    "rule": "best candidate/output; L512/L768, B1",
                    "configurations": [],
                },
            },
        }
        atomic_json(PLAN_PATH, plan)
    return plan


def status(**_: Any) -> dict[str, Any]:
    """Return checkpoint status without loading retrieval models."""
    plan = _require_plan()
    report = {
        "plan_status": plan["status"],
        "dev_tuning_complete": plan["status"] in {"DEV_TUNING_COMPLETE", "DEV_COMPLETE"},
        "stages": {},
        "test": None,
    }
    for stage in STAGES:
        configurations = _stage_configurations(plan, stage)
        report["stages"][stage] = {
            "status": plan["stages"][stage]["status"],
            "configurations": [_checkpoint_status("dev", item) for item in configurations],
        }
    selection = _load_json(SELECTION_PATH)
    if selection is not None:
        report["dev_selection"] = selection
        final_config = selection.get("final_config")
        if isinstance(final_config, dict):
            report["test"] = _checkpoint_status("test", final_config)
    return report


def run_dev(
    resume: bool = False,
    time_budget_seconds: int = 300,
    max_questions_per_run: int | None = None,
    config_id: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Run one resumable DEV configuration slice from the active plan stage."""
    plan = _require_plan()
    try:
        configuration = _find_runnable_configuration(plan, config_id)
    except RuntimeError:
        if config_id is not None:
            raise
        _advance_dev_tuning(plan)
        if plan["status"] == "DEV_TUNING_COMPLETE":
            return {"status": "DEV_TUNING_COMPLETE"}
        configuration = _find_runnable_configuration(plan, None)
    result = _run_checkpoint(
        "dev",
        configuration,
        resume,
        time_budget_seconds,
        max_questions_per_run,
    )
    return {"configuration": configuration["id"], **result}


def select_dev(**_: Any) -> dict[str, Any]:
    """Select the final DEV configuration after staged tuning is complete."""
    plan = _require_plan()
    if plan["status"] != "DEV_TUNING_COMPLETE":
        raise RuntimeError("DEV staged tuning is not COMPLETE")
    winner, decision = _select_final_dev_configuration(_stage_configurations(plan, "C"))
    plan["status"] = "DEV_COMPLETE"
    atomic_json(PLAN_PATH, plan)
    selection = {
        "status": "DEV_SELECTED",
        "final_config": winner,
        "selection_split": "dev",
        "selection_policy": [
            "recall_at_5_desc",
            "mrr_desc",
            "hit_rate_at_1_desc",
            "p95_latency_ms_asc",
            "peak_rss_bytes_asc_when_available",
            "smaller_configuration_for_exact_metric_ties",
        ],
        "dev_decision": decision,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    atomic_json(SELECTION_PATH, selection)
    return selection


def _advance_dev_tuning(plan: dict[str, Any]) -> None:
    """Open the next DEV stage after the active stage is fully checkpointed."""
    stages = plan["stages"]
    if stages["B"]["status"] == "WAITING_FOR_STAGE_A":
        stage_a = _stage_configurations(plan, "A")
        _require_complete("dev", stage_a, "Stage A")
        winners = {source: _best_configuration(stage_a, source) for source in ("dense", "h2")}
        stages["A"]["status"] = "COMPLETE"
        stages["B"] = {
            "status": "READY",
            "rule": "best candidate from each pipeline; O5/O8, L512, B1",
            "configurations": [
                _configuration(source, winners[source]["candidates"], output, 512, 1)
                for source in ("dense", "h2")
                for output in (5, 8)
            ],
        }
    elif stages["C"]["status"] == "WAITING_FOR_STAGE_B":
        stage_b = _stage_configurations(plan, "B")
        _require_complete("dev", stage_b, "Stage B")
        winners = {source: _best_configuration(stage_b, source) for source in ("dense", "h2")}
        stages["B"]["status"] = "COMPLETE"
        stages["C"] = {
            "status": "READY",
            "rule": "best candidate/output per pipeline; L512/L768, B1",
            "configurations": [
                _configuration(
                    source, winners[source]["candidates"], winners[source]["output"], length, 1
                )
                for source in ("dense", "h2")
                for length in (512, 768)
            ],
        }
    elif stages["C"]["status"] == "READY":
        _require_complete("dev", _stage_configurations(plan, "C"), "Stage C")
        stages["C"]["status"] = "COMPLETE"
        plan["status"] = "DEV_TUNING_COMPLETE"
    atomic_json(PLAN_PATH, plan)


def run_test(
    resume: bool = False,
    time_budget_seconds: int = 300,
    max_questions_per_run: int | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Run TEST exactly for the final DEV-selected configuration."""
    selection = _require_selection()
    configuration = selection.get("final_config")
    if not isinstance(configuration, dict):
        raise RuntimeError("run-test requires a completed DEV selection with final_config")
    result = _run_checkpoint(
        "test", configuration, resume, time_budget_seconds, max_questions_per_run
    )
    return {"configuration": configuration["id"], **result}


def validate(**_: Any) -> dict[str, Any]:
    """Validate JSONL duplicate safety and state totals without running a benchmark."""
    plan = _require_plan()
    questions = load_questions(DATASET)
    validation: list[dict[str, Any]] = []
    for stage in STAGES:
        for configuration in _stage_configurations(plan, stage):
            validation.append(_validate_checkpoint("dev", configuration, questions))
    selection = _load_json(SELECTION_PATH)
    if isinstance(selection, dict) and isinstance(selection.get("final_config"), dict):
        validation.append(_validate_checkpoint("test", selection["final_config"], questions))
    return {"status": "VALID", "checkpoints": validation}


def finalize(**_: Any) -> dict[str, Any]:
    """Write official Week 5 artifacts only after DEV and TEST checkpoints complete."""
    plan = _require_plan()
    if plan["status"] != "DEV_COMPLETE":
        raise RuntimeError("finalize requires DEV to be COMPLETE")
    selection = _require_selection()
    configuration = selection.get("final_config")
    if not isinstance(configuration, dict):
        raise RuntimeError("finalize requires a final DEV selection")
    _require_complete("test", [configuration], "TEST")
    questions = load_questions(DATASET)
    test_questions = [question for question in questions if question.split == "test"]
    predictions = _load_predictions("test", configuration)
    metrics = retrieval_metrics(test_questions, predictions)
    report = {
        "status": "OFFICIAL",
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset_sha256": calculate_file_sha256(DATASET),
        "input_chunk_sha256": calculate_file_sha256(CORPUS),
        "final_retrieval_pipeline": configuration["source"],
        "final_candidate_k": configuration["candidates"],
        "final_rerank_output_k": configuration["output"],
        "final_reranker_max_length": configuration["length"],
        "final_reranker_batch_size": configuration["batch"],
        "reports": [
            {
                "configuration": configuration["id"],
                "selection_split": "test_once",
                "metrics": metrics,
                "by_group": _grouped(test_questions, predictions),
            }
        ],
    }
    atomic_json(RESULTS / "week5_reranker_comparison.json", report)
    _write_final_predictions(configuration)
    atomic_json(
        ROOT / "data/processed/reranker_manifest.json",
        {
            "model": get_settings().reranker_model,
            "device": "cpu",
            "fp16": False,
            "batch_size": configuration["batch"],
            "max_length": configuration["length"],
            "candidate_count": configuration["candidates"],
            "output_count": configuration["output"],
            "dataset_sha256": report["dataset_sha256"],
            "corpus_sha256": report["input_chunk_sha256"],
            "benchmark_status": "OFFICIAL",
            "timestamp": report["generated_at"],
        },
    )
    return {"status": "FINALIZED", "configuration": configuration["id"]}


def _configuration(
    source: str, candidates: int, output: int, length: int, batch: int
) -> dict[str, Any]:
    return {
        "id": config_id(source, candidates, output, length, batch),
        "source": source,
        "candidates": candidates,
        "output": output,
        "length": length,
        "batch": batch,
    }


def _load_plan(required: bool) -> dict[str, Any] | None:
    plan = _load_json(PLAN_PATH)
    if plan is None and required:
        raise RuntimeError("run 'plan' before using this command")
    return plan


def _require_plan() -> dict[str, Any]:
    plan = _load_plan(required=True)
    assert plan is not None
    return plan


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return value


def _require_selection() -> dict[str, Any]:
    selection = _load_json(SELECTION_PATH)
    if selection is None:
        raise RuntimeError("run-test requires week5_dev_selection.json from select-dev")
    return selection


def _stage_configurations(plan: dict[str, Any], stage: str) -> list[dict[str, Any]]:
    configurations = plan["stages"][stage].get("configurations", [])
    if not isinstance(configurations, list):
        raise ValueError(f"invalid {stage} configuration list")
    return configurations


def _checkpoint_paths(split: str, configuration: dict[str, Any]) -> tuple[Path, Path]:
    directory = CHECKPOINTS / split / configuration["id"]
    return directory / "predictions.jsonl", directory / "state.json"


def _checkpoint_status(split: str, configuration: dict[str, Any]) -> dict[str, Any]:
    _, state_path = _checkpoint_paths(split, configuration)
    state = _load_json(state_path) or {"status": "PENDING", "completed": 0}
    return {"configuration": configuration["id"], **state}


def _find_runnable_configuration(plan: dict[str, Any], requested: str | None) -> dict[str, Any]:
    available = [
        configuration
        for stage in STAGES
        if plan["stages"][stage]["status"] == "READY"
        for configuration in _stage_configurations(plan, stage)
    ]
    if requested:
        for configuration in available:
            if configuration["id"] == requested:
                return configuration
        raise RuntimeError("config-id is not an available planned DEV configuration")
    for configuration in available:
        if _checkpoint_status("dev", configuration).get("status") != "COMPLETE":
            return configuration
    raise RuntimeError("no unfinished DEV configuration is available; run select-dev")


def _run_checkpoint(
    split: str,
    configuration: dict[str, Any],
    resume: bool,
    budget_seconds: int,
    max_questions: int | None,
) -> dict[str, Any]:
    predictions_path, state_path = _checkpoint_paths(split, configuration)
    if predictions_path.exists() and not resume:
        raise RuntimeError("checkpoint exists; rerun with --resume")
    fingerprint = checkpoint_fingerprint(configuration, calculate_file_sha256(DATASET))
    existing_state = _load_json(state_path)
    if existing_state is not None and existing_state.get("fingerprint") not in {None, fingerprint}:
        raise RuntimeError(
            "checkpoint fingerprint does not match the current dataset/configuration"
        )
    questions = [question for question in load_questions(DATASET) if question.split == split]
    return run_slice(
        questions,
        predictions_path,
        state_path,
        budget_seconds,
        _question_processor(configuration),
        max_questions=max_questions,
        fingerprint=fingerprint,
    )


def _question_processor(configuration: dict[str, Any]) -> Callable[[Any], dict[str, Any]]:
    settings = _benchmark_settings(configuration)
    dense = DenseRetriever(BgeM3EmbeddingProvider(settings), QdrantStore(settings), settings)
    retriever: DenseRetriever | HybridRetriever = dense
    if configuration["source"] == "h2":
        lexical_path = ROOT / "data/processed/lexical/bm25s_underthesea"
        store = Bm25Store(lexical_path, get_lexical_tokenizer("underthesea"))
        store.load()
        retriever = HybridRetriever(dense, SparseRetriever(store, settings))
    reranker = BgeReranker(settings)

    def process(question: Any) -> dict[str, Any]:
        try:
            retrieved = retriever.search(question.question, configuration["candidates"])
            reranked = reranker.rerank(
                question.question, retrieved.results, configuration["output"]
            )
            return RetrievalPrediction(
                question_id=question.question_id,
                retrieved_chunk_ids=[item.chunk_id for item in reranked.results],
                retrieved_articles=[item.article_number for item in reranked.results],
                ranks=[item.rank for item in reranked.results],
                scores=[item.score for item in reranked.results],
                retrieval_source=configuration["id"],
                latency_ms=retrieved.latency_ms + reranked.latency_ms,
                embedding_latency_ms=getattr(retrieved, "embedding_latency_ms", None),
                backend_latency_ms=getattr(retrieved, "qdrant_latency_ms", None),
            ).model_dump()
        except Exception as exc:
            return RetrievalPrediction(
                question_id=question.question_id,
                retrieved_chunk_ids=[],
                retrieved_articles=[],
                ranks=[],
                scores=[],
                retrieval_source=configuration["id"],
                latency_ms=0,
                error=type(exc).__name__,
            ).model_dump()

    return process


def _benchmark_settings(configuration: dict[str, Any]) -> Settings:
    configured = get_settings()
    return configured.model_copy(
        update={
            "dense_max_top_k": max(configured.dense_max_top_k, configuration["candidates"]),
            "reranker_candidate_k": configuration["candidates"],
            "reranker_output_k": configuration["output"],
            "reranker_max_length": configuration["length"],
            "reranker_batch_size": configuration["batch"],
            "reranker_fallback_mode": "error",
            "reranker_device": "cpu",
        }
    )


def _load_predictions(split: str, configuration: dict[str, Any]) -> dict[str, RetrievalPrediction]:
    predictions_path, _ = _checkpoint_paths(split, configuration)
    return {
        question_id: RetrievalPrediction.model_validate(row)
        for question_id, row in load_jsonl(predictions_path).items()
    }


def _require_complete(split: str, configurations: Iterable[dict[str, Any]], label: str) -> None:
    incomplete = [
        configuration["id"]
        for configuration in configurations
        if _checkpoint_status(split, configuration).get("status") != "COMPLETE"
    ]
    if incomplete:
        raise RuntimeError(f"{label} is not COMPLETE: {', '.join(incomplete)}")


def _best_configuration(
    configurations: Iterable[dict[str, Any]], source: str | None = None
) -> dict[str, Any]:
    candidates = [item for item in configurations if source is None or item["source"] == source]
    if not candidates:
        raise RuntimeError("no completed DEV configuration is available for selection")
    questions = [question for question in load_questions(DATASET) if question.split == "dev"]
    return max(
        candidates,
        key=lambda item: _selection_key(
            retrieval_metrics(questions, _load_predictions("dev", item))
        ),
    )


def _select_final_dev_configuration(
    configurations: Iterable[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Select the final configuration using only DEV metrics and measurements."""
    candidates = list(configurations)
    if not candidates:
        raise RuntimeError("no completed DEV configuration is available for selection")
    questions = [question for question in load_questions(DATASET) if question.split == "dev"]
    rows: list[dict[str, Any]] = []
    for configuration in candidates:
        metrics = retrieval_metrics(questions, _load_predictions("dev", configuration))
        state = _checkpoint_status("dev", configuration)
        peak_rss = state.get("peak_rss_bytes")
        rows.append(
            {
                "configuration": configuration["id"],
                "metrics": {
                    key: metrics.get(key)
                    for key in ("recall_at_5", "mrr", "hit_rate_at_1", "p95_latency_ms")
                },
                "peak_rss_bytes": peak_rss if isinstance(peak_rss, (int, float)) else None,
                "complexity": {
                    key: configuration[key] for key in ("candidates", "output", "length", "batch")
                },
            }
        )

    def ranking(row: dict[str, Any]) -> tuple[float, float, float, float, float, tuple[int, ...]]:
        metrics = row["metrics"]
        p95 = metrics["p95_latency_ms"]
        rss = row["peak_rss_bytes"]
        complexity = row["complexity"]
        return (
            float(metrics["recall_at_5"] or -1),
            float(metrics["mrr"] or -1),
            float(metrics["hit_rate_at_1"] or -1),
            -float(p95) if isinstance(p95, (int, float)) else float("-inf"),
            -float(rss) if isinstance(rss, (int, float)) else 0.0,
            tuple(-int(complexity[key]) for key in ("candidates", "output", "length", "batch")),
        )

    chosen = max(rows, key=ranking)
    winner = next(item for item in candidates if item["id"] == chosen["configuration"])
    return winner, {
        "selection_split": "dev",
        "candidates": rows,
        "winner": chosen["configuration"],
        "peak_rss_note": "not recorded in checkpoints"
        if all(row["peak_rss_bytes"] is None for row in rows)
        else "used when DEV checkpoint measurements were available",
    }


def _selection_key(metrics: dict[str, Any]) -> tuple[float, float]:
    return (float(metrics.get("mrr") or -1), float(metrics.get("hit_rate_at_1") or -1))


def _grouped(
    questions: list[Any], predictions: dict[str, RetrievalPrediction]
) -> dict[str, dict[str, Any]]:
    report: dict[str, dict[str, Any]] = {}
    for attribute in ("category", "difficulty", "split", "source_position"):
        groups: dict[str, list[Any]] = defaultdict(list)
        for question in questions:
            groups[str(getattr(question, attribute))].append(question)
        report[attribute] = {
            name: retrieval_metrics(records, predictions) for name, records in groups.items()
        }
    return report


def _validate_checkpoint(
    split: str, configuration: dict[str, Any], questions: list[Any]
) -> dict[str, Any]:
    split_questions = [question for question in questions if question.split == split]
    predictions_path, state_path = _checkpoint_paths(split, configuration)
    predictions = load_jsonl(predictions_path)
    question_ids = {question.question_id for question in split_questions}
    if unexpected := sorted(set(predictions) - question_ids):
        raise ValueError(f"{configuration['id']} has unexpected question ID: {unexpected[0]}")
    state = _load_json(state_path) or {"status": "PENDING", "completed": 0}
    if state.get("completed", 0) != len(predictions):
        raise ValueError(f"{configuration['id']} state completed count does not match JSONL")
    if state.get("status") == "COMPLETE" and len(predictions) != len(split_questions):
        raise ValueError(f"{configuration['id']} is marked COMPLETE with missing predictions")
    return {
        "split": split,
        "configuration": configuration["id"],
        "status": state.get("status"),
        "completed": len(predictions),
        "total": len(split_questions),
    }


def _write_final_predictions(configuration: dict[str, Any]) -> None:
    predictions_path, _ = _checkpoint_paths("test", configuration)
    target = RESULTS / "week5_reranker_predictions.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for prediction in load_jsonl(predictions_path).values():
            handle.write(
                json.dumps({"configuration": configuration["id"], **prediction}, ensure_ascii=False)
            )
            handle.write("\n")
