"""Offline regression checks for the pre-Week-6 source and benchmark provenance."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vietnamese_labor_law_assistant.evaluation.dataset import load_questions
from vietnamese_labor_law_assistant.ingestion.identifiers import calculate_file_sha256
from vietnamese_labor_law_assistant.ingestion.models import SourceMetadata
from vietnamese_labor_law_assistant.ingestion.writers import (
    read_articles_jsonl,
    read_chunks_jsonl,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data/raw/labor_law.docx"
METADATA = ROOT / "data/raw/source_metadata.json"
ARTICLES = ROOT / "data/processed/labor_law_articles.jsonl"
CHUNKS = ROOT / "data/processed/labor_law_clauses.jsonl"
DATASET = ROOT / "data/evaluation/labor_law_eval_v1.jsonl"
MANIFEST = ROOT / "data/evaluation/labor_law_eval_v1_manifest.json"
SELECTION = ROOT / "evaluation/results/week5_dev_selection.json"
WEEK5 = ROOT / "evaluation/results/week5_reranker_comparison.json"
LEXICAL_MANIFEST = ROOT / "data/processed/lexical/bm25s_underthesea/manifest.json"
WHITESPACE_LEXICAL_MANIFEST = ROOT / "data/processed/lexical/bm25s_whitespace/manifest.json"
DENSE_MANIFEST = ROOT / "data/processed/dense_index_manifest.json"
RERANKER_MANIFEST = ROOT / "data/processed/reranker_manifest.json"
INDEPENDENT_PACKET = ROOT / "data/evaluation/labor_law_eval_v1_independent_review_packet.csv"


@pytest.mark.integration
def test_canonical_source_dataset_and_week5_provenance_are_consistent() -> None:
    metadata = SourceMetadata.model_validate_json(METADATA.read_text(encoding="utf-8"))
    source_sha256 = calculate_file_sha256(SOURCE)
    assert metadata.source_file == "data/raw/labor_law.docx"
    assert metadata.sha256 == source_sha256

    articles = read_articles_jsonl(ARTICLES)
    chunks = read_chunks_jsonl(CHUNKS)
    assert len(articles) == 220
    assert len(chunks) == 682
    assert len({article.article_number for article in articles}) == len(articles)
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)
    assert all(chunk.source_paragraph_indexes for chunk in chunks)

    questions = load_questions(DATASET)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    chunk_ids = {chunk.chunk_id for chunk in chunks}
    dev_ids = {question.question_id for question in questions if question.split == "dev"}
    test_ids = {question.question_id for question in questions if question.split == "test"}
    assert len(questions) == 60
    assert len({question.question_id for question in questions}) == len(questions)
    assert not dev_ids & test_ids
    assert all(
        set(question.expected_chunk_ids + question.reference_answer_source_chunk_ids) <= chunk_ids
        for question in questions
    )
    assert manifest["dataset_sha256"] == calculate_file_sha256(DATASET)
    assert manifest["source_chunks_sha256"] == calculate_file_sha256(CHUNKS)
    assert manifest["split_status"] == "FROZEN"
    assert manifest["official_status"] == "INDEPENDENT_HUMAN_REVIEWED"
    independent = manifest["independent_review"]
    assert (
        independent["packet_path"]
        == "data/evaluation/labor_law_eval_v1_independent_review_packet.csv"
    )
    assert independent["packet_sha256"] == calculate_file_sha256(INDEPENDENT_PACKET)
    assert independent["policy_satisfied"] is True

    selection = json.loads(SELECTION.read_text(encoding="utf-8"))
    week5 = json.loads(WEEK5.read_text(encoding="utf-8"))
    lexical = json.loads(LEXICAL_MANIFEST.read_text(encoding="utf-8"))
    whitespace_lexical = json.loads(WHITESPACE_LEXICAL_MANIFEST.read_text(encoding="utf-8"))
    dense = json.loads(DENSE_MANIFEST.read_text(encoding="utf-8"))
    reranker = json.loads(RERANKER_MANIFEST.read_text(encoding="utf-8"))
    assert selection["selection_split"] == "dev"
    assert selection["final_config"] == {
        "id": "R2_H2_C10_O5_L512_B1",
        "source": "h2",
        "candidates": 10,
        "output": 5,
        "length": 512,
        "batch": 1,
    }
    assert week5["status"] == "HISTORICAL_PROVISIONAL_PRIOR_DATASET"
    assert week5["dataset_sha256"] == reranker["dataset_sha256"]
    assert week5["input_chunk_sha256"] == reranker["corpus_sha256"]
    assert lexical["tokenizer_name"] == "underthesea"
    assert lexical["source_jsonl_sha256"] == manifest["source_chunks_sha256"]
    assert lexical["chunk_count"] == len(chunks)
    assert whitespace_lexical["source_jsonl_sha256"] == manifest["source_chunks_sha256"]
    assert whitespace_lexical["chunk_count"] == len(chunks)
    assert dense["source_jsonl_sha256"] == manifest["source_chunks_sha256"]
    assert dense["point_count_after_index"] == len(chunks)
    assert reranker["model"] == "BAAI/bge-reranker-v2-m3"
    assert reranker["batch_size"] == 1
    assert reranker["max_length"] == 512
    assert reranker["candidate_count"] == 10
    assert reranker["output_count"] == 5
    assert reranker["benchmark_status"] == "HISTORICAL_PROVISIONAL_PRIOR_DATASET"
