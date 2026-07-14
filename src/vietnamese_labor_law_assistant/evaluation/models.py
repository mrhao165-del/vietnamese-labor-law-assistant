"""Typed contracts for evaluation records and retrieval predictions."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class ExpectedClause(BaseModel):
    article_number: int = Field(gt=0)
    clause_number: int = Field(gt=0)
    point_label: str | None = None


class EvaluationQuestion(BaseModel):
    question_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    category: Literal[
        "direct", "natural_paraphrase", "legal_keyword", "ambiguous", "out_of_scope", "calculation"
    ]
    evaluation_scope: Literal["retrieval", "rag", "out_of_scope", "future_calculator"]
    expected_behavior: Literal[
        "answer_with_citations", "insufficient_context", "clarification_needed", "future_calculator"
    ]
    expected_articles: list[int] = Field(default_factory=list)
    expected_clauses: list[ExpectedClause] = Field(default_factory=list)
    expected_chunk_ids: list[str] = Field(default_factory=list)
    reference_answer: str | None = None
    reference_answer_source_chunk_ids: list[str] = Field(default_factory=list)
    difficulty: Literal["easy", "medium", "hard"]
    primary_article: int | None = Field(default=None, gt=0)
    split: Literal["dev", "test"]
    source_position: Literal["beginning", "middle", "end", "outside"]
    human_validated: bool = False
    review_status: Literal["PENDING", "PASS", "NEEDS_REVISION", "REJECTED"] = "PENDING"
    reviewer: str | None = None
    review_notes: str | None = None
    required_clarifications: list[str] = Field(default_factory=list)
    dataset_version: str

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_scope_rules(self) -> EvaluationQuestion:
        if self.category == "out_of_scope":
            if self.expected_articles or self.expected_clauses or self.expected_chunk_ids:
                raise ValueError("out_of_scope records must not contain expected citations")
            if self.expected_behavior != "insufficient_context":
                raise ValueError("out_of_scope records require insufficient_context")
        if self.expected_behavior == "answer_with_citations" and not self.expected_chunk_ids:
            raise ValueError("answerable records require expected source chunks")
        if self.human_validated and self.review_status != "PASS":
            raise ValueError("human_validated records require PASS review status")
        return self


class RetrievalPrediction(BaseModel):
    question_id: str
    retrieved_chunk_ids: list[str]
    retrieved_articles: list[int]
    retrieved_clauses: list[ExpectedClause] = Field(default_factory=list)
    ranks: list[int]
    scores: list[float]
    retrieval_source: str
    latency_ms: float = Field(ge=0)
    embedding_latency_ms: float | None = Field(default=None, ge=0)
    backend_latency_ms: float | None = Field(default=None, ge=0)
    error: str | None = None


class RagPrediction(BaseModel):
    question_id: str
    answer: str | None = None
    citation_chunk_ids: list[str] = Field(default_factory=list)
    citation_articles: list[int] = Field(default_factory=list)
    citation_clauses: list[ExpectedClause] = Field(default_factory=list)
    insufficient_context: bool = False
    retrieval_latency_ms: float | None = Field(default=None, ge=0)
    generation_latency_ms: float | None = Field(default=None, ge=0)
    total_latency_ms: float | None = Field(default=None, ge=0)
    error: str | None = None
