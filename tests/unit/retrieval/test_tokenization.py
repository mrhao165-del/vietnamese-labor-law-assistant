from vietnamese_labor_law_assistant.retrieval.tokenization import (
    TokenCount,
    build_token_report,
    count_embedding_tokens,
)


class FakeTokenizer:
    def __call__(
        self, text: str, *, add_special_tokens: bool, truncation: bool
    ) -> dict[str, list[int]]:
        assert add_special_tokens and not truncation
        return {"input_ids": list(range(len(text.split()) + 2))}


def test_token_count_and_report() -> None:
    assert count_embedding_tokens(FakeTokenizer(), "một hai") == 4
    report = build_token_report(
        [TokenCount("a", 1, None, 0, 4), TokenCount("b", 2, 1, 1, 9)], 5, "model"
    )
    assert report["over_limit_count"] == 1
    assert report["status"] == "FAIL"
