from pathlib import Path

import pytest

from vietnamese_labor_law_assistant.evaluation.week5_reranker_runner import (
    append_prediction,
    atomic_json,
    checkpoint_fingerprint,
    config_id,
    load_jsonl,
    rerank_score_fingerprint,
    run_slice,
)


class Question:
    def __init__(self, question_id: str) -> None:
        self.question_id = question_id


def test_config_id_and_atomic_state_are_deterministic(tmp_path: Path) -> None:
    assert config_id("dense", 10, 5, 512, 1) == "R1_DENSE_C10_O5_L512_B1"
    assert config_id("h2", 20, 8, 768, 1) == "R2_H2_C20_O8_L768_B1"
    state = tmp_path / "state.json"
    atomic_json(state, {"status": "PARTIAL"})
    assert state.read_text(encoding="utf-8").strip().endswith("}")


def test_atomic_json_replaces_complete_document(tmp_path: Path) -> None:
    state = tmp_path / "state.json"
    atomic_json(state, {"status": "PARTIAL", "completed": 1})
    assert state.read_text(encoding="utf-8") == '{\n  "status": "PARTIAL",\n  "completed": 1\n}\n'
    assert not state.with_suffix(".json.tmp").exists()


def test_slice_resumes_without_duplicate_prediction(tmp_path: Path) -> None:
    questions = [Question("q1"), Question("q2")]
    path, state = tmp_path / "predictions.jsonl", tmp_path / "state.json"
    append_prediction(path, {"question_id": "q1", "score": 1})
    seen: list[str] = []
    result = run_slice(
        questions,
        path,
        state,
        60,
        lambda question: seen.append(question.question_id) or {"question_id": question.question_id},
    )
    assert result["status"] == "COMPLETE" and seen == ["q2"]
    assert sorted(load_jsonl(path)) == ["q1", "q2"]


def test_duplicate_checkpoint_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "predictions.jsonl"
    append_prediction(path, {"question_id": "q1"})
    append_prediction(path, {"question_id": "q1"})
    with pytest.raises(ValueError, match="duplicate"):
        load_jsonl(path)


def test_append_preserves_all_valid_jsonl_rows(tmp_path: Path) -> None:
    path = tmp_path / "predictions.jsonl"
    append_prediction(path, {"question_id": "q1", "score": 1})
    append_prediction(path, {"question_id": "q2", "score": 2})
    assert load_jsonl(path) == {
        "q1": {"question_id": "q1", "score": 1},
        "q2": {"question_id": "q2", "score": 2},
    }


def test_corrupt_final_jsonl_line_is_detected_without_truncating_valid_rows(tmp_path: Path) -> None:
    path = tmp_path / "predictions.jsonl"
    append_prediction(path, {"question_id": "q1"})
    path.write_text(path.read_text(encoding="utf-8") + '{"question_id":\n', encoding="utf-8")

    with pytest.raises(ValueError, match="Expecting value"):
        load_jsonl(path)

    assert path.read_text(encoding="utf-8").startswith('{"question_id": "q1"}')


def test_slice_stops_safely_when_time_budget_has_no_work_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from vietnamese_labor_law_assistant.evaluation import week5_reranker_runner as runner

    monkeypatch.setattr(runner.time, "monotonic", lambda: 0.0)
    seen: list[str] = []
    result = run_slice(
        [Question("q1")],
        tmp_path / "predictions.jsonl",
        tmp_path / "state.json",
        30,
        lambda question: seen.append(question.question_id) or {"question_id": question.question_id},
    )
    assert result["status"] == "PARTIAL"
    assert result["next_question_id"] == "q1"
    assert seen == []


def test_slice_honours_max_questions_per_run(tmp_path: Path) -> None:
    seen: list[str] = []
    result = run_slice(
        [Question("q1"), Question("q2"), Question("q3")],
        tmp_path / "predictions.jsonl",
        tmp_path / "state.json",
        60,
        lambda question: seen.append(question.question_id) or {"question_id": question.question_id},
        max_questions=2,
    )
    assert result["status"] == "PARTIAL"
    assert result["next_question_id"] == "q3"
    assert seen == ["q1", "q2"]


def test_checkpoint_fingerprint_changes_for_max_length_and_dataset_checksum() -> None:
    base = {"source": "dense", "candidates": 20, "output": 5, "length": 512, "batch": 1}
    longer = {**base, "length": 768}
    assert checkpoint_fingerprint(base, "dataset-a") != checkpoint_fingerprint(longer, "dataset-a")
    assert checkpoint_fingerprint(base, "dataset-a") != checkpoint_fingerprint(base, "dataset-b")


def test_score_fingerprint_shares_output_cutoffs_but_not_max_length() -> None:
    base = {"source": "h2", "candidates": 20, "output": 5, "length": 512, "batch": 1}
    output_eight = {**base, "output": 8}
    longer = {**base, "length": 768}
    assert rerank_score_fingerprint(base, "dataset") == rerank_score_fingerprint(
        output_eight, "dataset"
    )
    assert rerank_score_fingerprint(base, "dataset") != rerank_score_fingerprint(longer, "dataset")
