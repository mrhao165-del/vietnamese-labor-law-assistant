from pathlib import Path

from vietnamese_labor_law_assistant.evaluation.dataset import (
    load_questions,
    normalise_question,
    write_json,
    write_questions,
)
from vietnamese_labor_law_assistant.evaluation.models import EvaluationQuestion, ExpectedClause


def make_question(question_id: str = "q") -> EvaluationQuestion:
    return EvaluationQuestion(
        question_id=question_id,
        question="Người lao động",
        category="direct",
        evaluation_scope="retrieval",
        expected_behavior="answer_with_citations",
        expected_articles=[1],
        expected_clauses=[ExpectedClause(article_number=1, clause_number=1)],
        expected_chunk_ids=["chunk"],
        reference_answer="Đáp án",
        reference_answer_source_chunk_ids=["chunk"],
        difficulty="easy",
        primary_article=1,
        split="dev",
        source_position="beginning",
        dataset_version="v1",
    )


def test_dataset_jsonl_round_trip_and_normalization(tmp_path: Path) -> None:
    path = tmp_path / "questions.jsonl"
    write_questions(path, [make_question(), make_question("q2")])
    assert [q.question_id for q in load_questions(path)] == ["q", "q2"]
    assert normalise_question("  NGƯỜI   lao động ") == "người lao động"


def test_write_json_is_utf8_and_deterministic_shape(tmp_path: Path) -> None:
    path = tmp_path / "report.json"
    write_json(path, {"điều": 35, "ok": True})
    assert '"điều": 35' in path.read_text(encoding="utf-8")
