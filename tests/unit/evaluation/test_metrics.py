from typing import Literal

from vietnamese_labor_law_assistant.evaluation.metrics import citation_metrics, retrieval_metrics
from vietnamese_labor_law_assistant.evaluation.models import (
    EvaluationQuestion,
    ExpectedClause,
    RagPrediction,
    RetrievalPrediction,
)

ExpectedBehavior = Literal[
    "answer_with_citations",
    "insufficient_context",
    "clarification_needed",
    "future_calculator",
]


def question(
    behavior: ExpectedBehavior = "answer_with_citations",
) -> EvaluationQuestion:
    return EvaluationQuestion(
        question_id="q",
        question="Câu hỏi",
        category="direct",
        evaluation_scope="retrieval",
        expected_behavior=behavior,
        expected_articles=[1],
        expected_clauses=[ExpectedClause(article_number=1, clause_number=1)],
        expected_chunk_ids=["a"],
        reference_answer="Đáp án",
        reference_answer_source_chunk_ids=["a"],
        difficulty="easy",
        primary_article=1,
        split="dev",
        source_position="beginning",
        dataset_version="v",
    )


def test_retrieval_metrics_rank_denominators_and_errors() -> None:
    qs = [
        question(),
        question("future_calculator").model_copy(
            update={"question_id": "calc", "evaluation_scope": "future_calculator"}
        ),
        question("insufficient_context").model_copy(
            update={
                "question_id": "out",
                "category": "out_of_scope",
                "evaluation_scope": "out_of_scope",
                "expected_articles": [],
                "expected_clauses": [],
                "expected_chunk_ids": [],
            }
        ),
    ]
    p = {
        "q": RetrievalPrediction(
            question_id="q",
            retrieved_chunk_ids=["x", "a", "a"],
            retrieved_articles=[9, 1, 1],
            ranks=[1, 2, 3],
            scores=[0.9, 0.8, 0.7],
            retrieval_source="test",
            latency_ms=10,
        )
    }
    m = retrieval_metrics(qs, p)
    assert m["eligible_count"] == 1 and m["hit_rate_at_1"] == 0 and m["hit_rate_at_3"] == 1
    assert m["mrr"] == 0.5 and m["precision_at_5"] == 0.4


def test_citation_metrics_valid_wrong_and_outside_leakage() -> None:
    answerable, outside = (
        question(),
        question("insufficient_context").model_copy(
            update={
                "question_id": "o",
                "category": "out_of_scope",
                "evaluation_scope": "out_of_scope",
                "expected_articles": [],
                "expected_clauses": [],
                "expected_chunk_ids": [],
            }
        ),
    )
    predictions = {
        "q": RagPrediction(
            question_id="q",
            citation_chunk_ids=["a"],
            citation_articles=[1],
            citation_clauses=[ExpectedClause(article_number=1, clause_number=1)],
        ),
        "o": RagPrediction(question_id="o", insufficient_context=True),
    }
    m = citation_metrics([answerable, outside], predictions)
    assert m["citation_existence_rate"] == 1 and m["article_citation_accuracy"] == 1
    assert m["clause_citation_accuracy"] == 1 and m["out_of_scope_citation_leakage_rate"] == 0
