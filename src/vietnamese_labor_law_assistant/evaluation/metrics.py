"""Deterministic retrieval, citation and latency metrics without LLM judging."""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence

from .models import EvaluationQuestion, RagPrediction, RetrievalPrediction


def percentile95(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return sorted(values)[max(0, math.ceil(len(values) * 0.95) - 1)]


def retrieval_metrics(
    questions: Sequence[EvaluationQuestion], predictions: dict[str, RetrievalPrediction]
) -> dict[str, float | int | None]:
    # Retrieval relevance is evaluated only where the dataset expects a cited legal
    # answer.  Clarification, out-of-scope, and future-calculator records have
    # separate behavioural metrics and must not dilute retrieval accuracy.
    eligible = [
        question
        for question in questions
        if question.expected_behavior == "answer_with_citations" and question.expected_chunk_ids
    ]
    ranks: list[int | None] = []
    precisions: list[float] = []
    latencies: list[float] = []
    errors = 0
    for question in eligible:
        prediction = predictions.get(question.question_id)
        if prediction is None or prediction.error:
            errors += 1
            continue
        latencies.append(prediction.latency_ms)
        expected = set(question.expected_chunk_ids)
        found = [chunk_id for chunk_id in prediction.retrieved_chunk_ids]
        ranks.append(
            next((index + 1 for index, chunk_id in enumerate(found) if chunk_id in expected), None)
        )
        precisions.append(sum(chunk_id in expected for chunk_id in found[:5]) / 5)

    def hit(k: int) -> float | None:
        return (
            sum(rank is not None and rank <= k for rank in ranks) / len(eligible)
            if eligible
            else None
        )

    return {
        "eligible_count": len(eligible),
        "hit_rate_at_1": hit(1),
        "hit_rate_at_3": hit(3),
        "hit_rate_at_5": hit(5),
        "hit_rate_at_10": hit(10),
        "recall_at_5": hit(5),
        "recall_at_10": hit(10),
        "precision_at_5": statistics.fmean(precisions) if precisions else None,
        "mrr": statistics.fmean(1 / rank if rank else 0 for rank in ranks) if ranks else None,
        "mean_latency_ms": statistics.fmean(latencies) if latencies else None,
        "median_latency_ms": statistics.median(latencies) if latencies else None,
        "p95_latency_ms": percentile95(latencies),
        "error_rate": errors / len(eligible) if eligible else None,
    }


def citation_metrics(
    questions: Sequence[EvaluationQuestion], predictions: dict[str, RagPrediction]
) -> dict[str, float | int | None]:
    answerable = [q for q in questions if q.expected_behavior == "answer_with_citations"]
    out_of_scope = [q for q in questions if q.category == "out_of_scope"]
    existence = []
    article_accuracy = []
    clause_accuracy = []
    rejections = []
    leakage = []
    for question in answerable:
        prediction = predictions.get(question.question_id)
        if prediction and not prediction.error:
            existence.append(bool(prediction.citation_chunk_ids))
            article_accuracy.append(
                bool(set(prediction.citation_articles) & set(question.expected_articles))
            )
            expected_clauses = {
                (item.article_number, item.clause_number) for item in question.expected_clauses
            }
            if expected_clauses:
                actual = {
                    (item.article_number, item.clause_number)
                    for item in prediction.citation_clauses
                }
                clause_accuracy.append(bool(actual & expected_clauses))
    for question in out_of_scope:
        prediction = predictions.get(question.question_id)
        if prediction and not prediction.error:
            rejections.append(prediction.insufficient_context)
            leakage.append(bool(prediction.citation_chunk_ids))

    def rate(values: list[bool]) -> float | None:
        return sum(values) / len(values) if values else None

    return {
        "citation_existence_rate": rate(existence),
        "article_citation_accuracy": rate(article_accuracy),
        "clause_citation_accuracy": rate(clause_accuracy),
        "out_of_scope_rejection_rate": rate(rejections),
        "out_of_scope_citation_leakage_rate": rate(leakage),
    }
