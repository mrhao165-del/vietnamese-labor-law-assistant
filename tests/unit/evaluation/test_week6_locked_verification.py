from __future__ import annotations

from vietnamese_labor_law_assistant.evaluation import week6_locked_verification as verification


def test_locked_verification_refuses_invalid_split_or_limit() -> None:
    try:
        verification.run("invalid")
    except ValueError as exc:
        assert "split" in str(exc)
    else:
        raise AssertionError("invalid split must be rejected")
    try:
        verification.run("dev", 0)
    except ValueError as exc:
        assert "positive" in str(exc)
    else:
        raise AssertionError("zero max_questions must be rejected")


def test_locked_configuration_is_immutable_and_not_test_tuned() -> None:
    assert verification.CONFIG == {
        "id": "R2_H2_C10_O5_L512_B1",
        "source": "h2_underthesea",
        "candidate_k": 10,
        "top_k": 5,
        "reranker_max_length": 512,
        "reranker_batch_size": 1,
    }
