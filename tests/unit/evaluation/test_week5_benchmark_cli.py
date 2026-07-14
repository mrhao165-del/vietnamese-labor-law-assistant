"""Offline tests for the Week 5 CLI service and its completion gates."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from vietnamese_labor_law_assistant.evaluation import week5_reranker_runner as runner


def _question(question_id: str, split: str) -> dict[str, object]:
    return {
        "question_id": question_id,
        "question": f"Question {question_id}",
        "category": "direct",
        "evaluation_scope": "retrieval",
        "expected_behavior": "answer_with_citations",
        "expected_articles": [1],
        "expected_clauses": [{"article_number": 1, "clause_number": 1}],
        "expected_chunk_ids": ["chunk-1"],
        "difficulty": "easy",
        "primary_article": 1,
        "split": split,
        "source_position": "beginning",
        "human_validated": True,
        "review_status": "PASS",
        "dataset_version": "v1",
    }


@pytest.fixture
def isolated_week5(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    results = tmp_path / "evaluation/results"
    dataset = tmp_path / "data/evaluation/labor_law_eval_v1.jsonl"
    corpus = tmp_path / "data/processed/labor_law_clauses.jsonl"
    dataset.parent.mkdir(parents=True)
    corpus.parent.mkdir(parents=True)
    dataset.write_text(
        "\n".join(json.dumps(_question("dev-1", "dev")) for _ in range(1))
        + "\n"
        + json.dumps(_question("test-1", "test"))
        + "\n",
        encoding="utf-8",
    )
    corpus.write_text('{"chunk_id": "chunk-1"}\n', encoding="utf-8")
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "DATASET", dataset)
    monkeypatch.setattr(runner, "CORPUS", corpus)
    monkeypatch.setattr(runner, "RESULTS", results)
    monkeypatch.setattr(runner, "PLAN_PATH", results / "week5_reranker_plan.json")
    monkeypatch.setattr(runner, "SELECTION_PATH", results / "week5_dev_selection.json")
    monkeypatch.setattr(runner, "CHECKPOINTS", results / "week5_reranker_checkpoints")
    return tmp_path


def _prediction(question_id: str, source: str) -> dict[str, object]:
    return {
        "question_id": question_id,
        "retrieved_chunk_ids": ["chunk-1"],
        "retrieved_articles": [1],
        "ranks": [1],
        "scores": [1.0],
        "retrieval_source": source,
        "latency_ms": 1.0,
    }


def _complete_checkpoint(split: str, configuration: dict[str, object], question_id: str) -> None:
    predictions_path, state_path = runner._checkpoint_paths(split, configuration)
    runner.append_prediction(predictions_path, _prediction(question_id, str(configuration["id"])))
    runner.atomic_json(
        state_path,
        {"status": "COMPLETE", "completed": 1, "total": 1, "next_question_id": None},
    )


def test_plan_writes_exact_stage_a_configurations(isolated_week5: Path) -> None:
    plan = runner.create_plan()
    configurations = plan["stages"]["A"]["configurations"]
    assert [item["id"] for item in configurations] == [
        "R1_DENSE_C10_O5_L512_B1",
        "R1_DENSE_C20_O5_L512_B1",
        "R1_DENSE_C30_O5_L512_B1",
        "R2_H2_C10_O5_L512_B1",
        "R2_H2_C20_O5_L512_B1",
        "R2_H2_C30_O5_L512_B1",
    ]
    assert runner.PLAN_PATH.exists()


def test_status_reads_checkpoint_state(isolated_week5: Path) -> None:
    plan = runner.create_plan()
    configuration = plan["stages"]["A"]["configurations"][0]
    _, state_path = runner._checkpoint_paths("dev", configuration)
    runner.atomic_json(
        state_path, {"status": "PARTIAL", "completed": 1, "next_question_id": "dev-2"}
    )

    report = runner.status()

    assert report["stages"]["A"]["configurations"][0]["status"] == "PARTIAL"
    assert report["stages"]["A"]["configurations"][0]["next_question_id"] == "dev-2"


def test_select_dev_refuses_incomplete_stage_a(isolated_week5: Path) -> None:
    runner.create_plan()
    with pytest.raises(RuntimeError, match="staged tuning is not COMPLETE"):
        runner.select_dev()


def test_run_dev_resume_skips_completed_question(
    isolated_week5: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = runner.create_plan()
    configuration = plan["stages"]["A"]["configurations"][0]
    predictions_path, _ = runner._checkpoint_paths("dev", configuration)
    runner.append_prediction(predictions_path, _prediction("dev-1", str(configuration["id"])))
    questions = [
        SimpleNamespace(question_id="dev-1", split="dev"),
        SimpleNamespace(question_id="dev-2", split="dev"),
    ]
    seen: list[str] = []
    monkeypatch.setattr(runner, "load_questions", lambda _: questions)
    monkeypatch.setattr(
        runner,
        "_question_processor",
        lambda _: (
            lambda question: (
                seen.append(question.question_id)
                or _prediction(question.question_id, str(configuration["id"]))
            )
        ),
    )

    result = runner.run_dev(resume=True, config_id=str(configuration["id"]))

    assert result["status"] == "COMPLETE"
    assert seen == ["dev-2"]


def test_run_test_refuses_without_selection_artifact(isolated_week5: Path) -> None:
    with pytest.raises(RuntimeError, match="week5_dev_selection.json"):
        runner.run_test()


def test_run_test_uses_only_selected_configuration(
    isolated_week5: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected = runner._configuration("h2", 20, 8, 512, 1)
    runner.atomic_json(runner.SELECTION_PATH, {"status": "DEV_SELECTED", "final_config": selected})
    received: dict[str, object] = {}

    def fake_run(
        split: str, configuration: dict[str, object], *_: object, **__: object
    ) -> dict[str, object]:
        received["split"] = split
        received["configuration"] = configuration
        return {"status": "PARTIAL", "completed": 0, "total": 1}

    monkeypatch.setattr(runner, "_run_checkpoint", fake_run)
    result = runner.run_test()

    assert result["configuration"] == selected["id"]
    assert received == {"split": "test", "configuration": selected}


def test_finalize_refuses_when_dev_or_test_is_incomplete(isolated_week5: Path) -> None:
    runner.create_plan()
    with pytest.raises(RuntimeError, match="DEV to be COMPLETE"):
        runner.finalize()


def test_finalize_refuses_partial_test_and_never_writes_official_output(
    isolated_week5: Path,
) -> None:
    plan = runner.create_plan()
    plan["status"] = "DEV_COMPLETE"
    runner.atomic_json(runner.PLAN_PATH, plan)
    selected = plan["stages"]["A"]["configurations"][0]
    runner.atomic_json(runner.SELECTION_PATH, {"status": "DEV_SELECTED", "final_config": selected})
    _, state_path = runner._checkpoint_paths("test", selected)
    runner.atomic_json(state_path, {"status": "PARTIAL", "completed": 0, "total": 1})

    with pytest.raises(RuntimeError, match="TEST is not COMPLETE"):
        runner.finalize()

    assert not (runner.RESULTS / "week5_reranker_comparison.json").exists()


def test_finalize_writes_official_output_from_complete_test_only(
    isolated_week5: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = runner.create_plan()
    plan["status"] = "DEV_COMPLETE"
    runner.atomic_json(runner.PLAN_PATH, plan)
    selected = plan["stages"]["A"]["configurations"][0]
    runner.atomic_json(runner.SELECTION_PATH, {"status": "DEV_SELECTED", "final_config": selected})
    _complete_checkpoint("test", selected, "test-1")
    monkeypatch.setattr(
        runner, "get_settings", lambda: SimpleNamespace(reranker_model="fake-reranker")
    )

    result = runner.finalize()
    official = json.loads(
        (runner.RESULTS / "week5_reranker_comparison.json").read_text(encoding="utf-8")
    )
    final_rows = (runner.RESULTS / "week5_reranker_predictions.jsonl").read_text(encoding="utf-8")

    assert result == {"status": "FINALIZED", "configuration": selected["id"]}
    assert official["status"] == "OFFICIAL"
    assert "PARTIAL" not in final_rows
    assert "dev-1" not in final_rows
    assert '"question_id": "test-1"' in final_rows


def test_validate_rejects_test_question_in_dev_checkpoint(isolated_week5: Path) -> None:
    plan = runner.create_plan()
    configuration = plan["stages"]["A"]["configurations"][0]
    predictions_path, state_path = runner._checkpoint_paths("dev", configuration)
    runner.append_prediction(predictions_path, _prediction("test-1", str(configuration["id"])))
    runner.atomic_json(state_path, {"status": "PARTIAL", "completed": 1, "total": 1})

    with pytest.raises(ValueError, match="unexpected question ID"):
        runner.validate()


@pytest.fixture(scope="module")
def cli_module() -> ModuleType:
    script = Path(__file__).resolve().parents[3] / "scripts/run_week5_reranker_benchmark.py"
    spec = importlib.util.spec_from_file_location("week5_benchmark_cli", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_parser_exposes_all_checkpoint_commands(cli_module: ModuleType) -> None:
    parser = cli_module.build_parser()
    assert parser.parse_args(["plan"]).command == "plan"
    assert parser.parse_args(["status"]).command == "status"
    assert (
        parser.parse_args(["run-dev", "--resume", "--max-questions-per-run", "1"]).command
        == "run-dev"
    )
    assert parser.parse_args(["select-dev"]).command == "select-dev"
    assert parser.parse_args(["run-test", "--time-budget-seconds", "31"]).command == "run-test"
    assert parser.parse_args(["validate"]).command == "validate"
    assert parser.parse_args(["finalize"]).command == "finalize"


def test_cli_main_delegates_command_and_returns_service_exit_code(
    cli_module: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    received: dict[str, object] = {}

    def fake_execute(command: str, **arguments: object) -> dict[str, str]:
        received["command"] = command
        received["arguments"] = arguments
        return {"status": "OK"}

    monkeypatch.setattr(cli_module, "execute_week5_command", fake_execute)
    monkeypatch.setattr("sys.argv", ["week5", "run-dev", "--config-id", "R1_DENSE_C10_O5_L512_B1"])

    assert cli_module.main() == 0
    assert received["command"] == "run-dev"
    assert received["arguments"] == {
        "resume": False,
        "time_budget_seconds": 300,
        "max_questions_per_run": None,
        "config_id": "R1_DENSE_C10_O5_L512_B1",
    }
