from collections.abc import Sequence
from pathlib import Path

import pytest

from vietnamese_labor_law_assistant.guardrails.citation_parser import parse_legal_citation
from vietnamese_labor_law_assistant.guardrails.enums import ReasonCode, VerificationStatus
from vietnamese_labor_law_assistant.guardrails.judge import (
    JudgeDecision,
    JudgeInvalidOutputError,
    JudgeUnavailableError,
)
from vietnamese_labor_law_assistant.guardrails.models import (
    AtomicClaim,
    EvidenceContext,
    LegalReference,
)
from vietnamese_labor_law_assistant.guardrails.policy import guarded_answer
from vietnamese_labor_law_assistant.guardrails.service import CitationGuardrailService
from vietnamese_labor_law_assistant.guardrails.similarity import BgeM3SemanticScorer
from vietnamese_labor_law_assistant.guardrails.source_registry import CanonicalSourceRegistry

SOURCE = Path("data/processed/labor_law_clauses.jsonl")
CHUNK = "ll_6af59ba448952c1c927978713d34d984"


def service() -> CitationGuardrailService:
    return CitationGuardrailService(CanonicalSourceRegistry(SOURCE))


def evidence(content: str = "người lao động báo trước 45 ngày") -> EvidenceContext:
    return EvidenceContext(chunk_id=CHUNK, content=content, article_number=35, clause_number=1)


def test_parser_normalizes_order_unicode_and_rejects_malformed() -> None:
    parsed = parse_legal_citation("Điểm A  Khoản 1  Điều 35")
    assert parsed == LegalReference(article=35, clause=1, point="a")
    assert parse_legal_citation("Khoản một") is None


def test_supported_partial_and_policy_fail_closed() -> None:
    supported = service().verify(
        [
            AtomicClaim(
                claim_id="a", text="người lao động báo trước 45 ngày", cited_context_ids=[CHUNK]
            )
        ],
        [evidence()],
    )
    assert supported.status is VerificationStatus.SUPPORTED
    partial = service().verify(
        [
            AtomicClaim(
                claim_id="b",
                text="người lao động báo trước hợp đồng điều khoản công việc",
                cited_context_ids=[CHUNK],
            )
        ],
        [evidence("người lao động báo trước")],
    )
    assert partial.status is VerificationStatus.PARTIALLY_SUPPORTED
    assert (
        guarded_answer("hallucinated", service().verify([AtomicClaim(claim_id="c", text="x")], []))[
            0
        ]
        != "hallucinated"
    )


@pytest.mark.parametrize(
    ("claim", "contexts", "reason"),
    [
        (AtomicClaim(claim_id="a", text="x"), [], ReasonCode.MISSING_CITATION),
        (
            AtomicClaim(claim_id="a", text="x", cited_context_ids=["unknown"]),
            [],
            ReasonCode.CITATION_NOT_FOUND,
        ),
        (
            AtomicClaim(claim_id="a", text="x", cited_context_ids=[CHUNK]),
            [],
            ReasonCode.CITATION_NOT_IN_RETRIEVED_CONTEXT,
        ),
        (
            AtomicClaim(
                claim_id="a",
                text="người lao động báo trước",
                cited_context_ids=[CHUNK],
                legal_references=[LegalReference(article=35, clause=2)],
            ),
            [evidence("người lao động báo trước")],
            ReasonCode.LEGAL_REFERENCE_MISMATCH,
        ),
        (
            AtomicClaim(
                claim_id="a", text="người lao động báo trước 99 ngày", cited_context_ids=[CHUNK]
            ),
            [evidence()],
            ReasonCode.NUMERIC_CONTRADICTION,
        ),
    ],
)
def test_failure_reason_codes(
    claim: AtomicClaim, contexts: list[EvidenceContext], reason: ReasonCode
) -> None:
    result = service().verify([claim], contexts)
    assert result.status in {
        VerificationStatus.UNSUPPORTED,
        VerificationStatus.INSUFFICIENT_CONTEXT,
    }
    assert reason in result.claims[0].reason_codes


def test_out_of_scope_is_safe_refusal() -> None:
    result = service().verify([], [], out_of_scope_refusal=True)
    assert result.status is VerificationStatus.INSUFFICIENT_CONTEXT
    assert ReasonCode.OUT_OF_SCOPE_REFUSAL.value in result.warnings


def test_clause_chunk_point_labels_preserve_canonical_point_provenance() -> None:
    text = "Điểm a Khoản 1 Điều 35 người lao động báo trước 45 ngày"
    context = EvidenceContext(
        chunk_id=CHUNK,
        content=text,
        article_number=35,
        clause_number=1,
        point_labels=["a", "b", "c", "d"],
    )
    supported = service().verify(
        [AtomicClaim(claim_id="point-a", text=text, cited_context_ids=[CHUNK])], [context]
    )
    assert supported.status is VerificationStatus.SUPPORTED

    mismatch = service().verify(
        [
            AtomicClaim(
                claim_id="point-e",
                text=text,
                cited_context_ids=[CHUNK],
                legal_references=[LegalReference(article=35, clause=1, point="e")],
            )
        ],
        [context],
    )
    assert mismatch.status is VerificationStatus.UNSUPPORTED
    assert mismatch.claims[0].reason_codes == [ReasonCode.LEGAL_REFERENCE_MISMATCH]


def test_agent_claim_can_repeat_a_cited_source_cross_reference() -> None:
    text = "Người sử dụng lao động phải xây dựng phương án sử dụng lao động theo Điều 44."
    context = EvidenceContext(
        chunk_id=CHUNK,
        content=text,
        article_number=43,
        clause_number=1,
    )
    inline = service().verify(
        [AtomicClaim(claim_id="inline", text=text, cited_context_ids=[CHUNK])], [context]
    )
    agent = service().verify(
        [
            AtomicClaim(
                claim_id="agent",
                text=text,
                cited_context_ids=[CHUNK],
                parse_inline_references=False,
            )
        ],
        [context],
    )
    assert inline.claims[0].reason_codes == [ReasonCode.LEGAL_REFERENCE_MISMATCH]
    assert agent.status is VerificationStatus.SUPPORTED


class AmbiguousScorer:
    def score(self, claim: str, evidence: str) -> float:
        del claim, evidence
        return 0.5


class FakeJudge:
    def __init__(self, outcome: VerificationStatus | Exception) -> None:
        self.outcome, self.calls = outcome, 0

    def judge(self, claim: AtomicClaim, evidence: list[EvidenceContext]) -> JudgeDecision:
        del claim, evidence
        self.calls += 1
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return JudgeDecision(status=self.outcome, reason="fixture")


@pytest.mark.parametrize(
    ("outcome", "status", "reason"),
    [
        (VerificationStatus.SUPPORTED, VerificationStatus.SUPPORTED, None),
        (
            VerificationStatus.PARTIALLY_SUPPORTED,
            VerificationStatus.PARTIALLY_SUPPORTED,
            ReasonCode.PARTIAL_EVIDENCE,
        ),
        (
            VerificationStatus.UNSUPPORTED,
            VerificationStatus.UNSUPPORTED,
            ReasonCode.LOW_SEMANTIC_SUPPORT,
        ),
        (
            JudgeUnavailableError("x"),
            VerificationStatus.INSUFFICIENT_CONTEXT,
            ReasonCode.JUDGE_UNAVAILABLE,
        ),
        (
            JudgeInvalidOutputError("x"),
            VerificationStatus.INSUFFICIENT_CONTEXT,
            ReasonCode.JUDGE_INVALID_OUTPUT,
        ),
    ],
)
def test_ambiguous_claim_executes_structured_judge_fail_closed(
    outcome: VerificationStatus | Exception,
    status: VerificationStatus,
    reason: ReasonCode | None,
) -> None:
    judge = FakeJudge(outcome)
    result = CitationGuardrailService(
        CanonicalSourceRegistry(SOURCE), AmbiguousScorer(), judge=judge
    ).verify(
        [AtomicClaim(claim_id="judge", text="người lao động báo trước", cited_context_ids=[CHUNK])],
        [evidence()],
    )
    assert result.status is status and judge.calls == 1
    if reason:
        assert reason in result.claims[0].reason_codes


def test_parser_and_hard_failure_prevent_judge_override() -> None:
    judge = FakeJudge(VerificationStatus.SUPPORTED)
    guardrail = CitationGuardrailService(
        CanonicalSourceRegistry(SOURCE), AmbiguousScorer(), judge=judge
    )
    malformed = guardrail.verify(
        [AtomicClaim(claim_id="bad", text="Khoản một Điều 35", cited_context_ids=[CHUNK])],
        [evidence()],
    )
    missing = guardrail.verify(
        [AtomicClaim(claim_id="missing", text="x", cited_context_ids=["ll_missing"])], []
    )
    assert malformed.claims[0].reason_codes == [ReasonCode.MALFORMED_CITATION]
    assert missing.claims[0].reason_codes == [ReasonCode.CITATION_NOT_FOUND]
    assert judge.calls == 0


def test_partial_policy_reconstructs_claims_without_original_answer() -> None:
    claims = [
        AtomicClaim(claim_id="one", text="supported", cited_context_ids=[CHUNK]),
        AtomicClaim(claim_id="two", text="uncertain", cited_context_ids=[CHUNK]),
    ]
    result = CitationGuardrailService(CanonicalSourceRegistry(SOURCE), AmbiguousScorer()).verify(
        claims, [evidence()]
    )
    answer, _ = guarded_answer("original unsupported wording", result, claims)
    assert "original unsupported wording" not in answer
    assert "Chưa được xác minh đầy đủ" in answer


class Embeddings:
    @property
    def dimension(self) -> int:
        return 2

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        del texts
        return [[1.0, 0.0], [1.0, 0.0]]

    def embed_query(self, text: str) -> list[float]:
        del text
        return [1.0, 0.0]

    def ensure_available(self) -> None:
        return None


def test_bge_semantic_scorer_reuses_embedding_protocol() -> None:
    scorer = BgeM3SemanticScorer(Embeddings())
    scorer.warmup()
    assert scorer.score("claim", "evidence") == 1.0


class CountingEmbeddings:
    def __init__(self) -> None:
        self.ensure_calls = 0
        self.batches: list[list[str]] = []
        self.model_initialization_count = 0

    @property
    def dimension(self) -> int:
        return 2

    def ensure_available(self) -> None:
        self.ensure_calls += 1
        self.model_initialization_count = 1

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        self.batches.append(list(texts))
        return [[1.0, 0.0] for _ in texts]

    def embed_documents_with_batch(
        self, texts: Sequence[str], batch_size: int
    ) -> list[list[float]]:
        assert batch_size >= 1
        return self.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def test_semantic_scorer_warms_once_and_encodes_claims_contexts_by_batch() -> None:
    provider = CountingEmbeddings()
    scorer = BgeM3SemanticScorer(provider, max_claims=2, max_contexts=2, batch_size=2)
    scorer.warmup()
    provider.batches.clear()
    assert scorer.score_matrix(["claim one", "claim two"], ["context one", "context two"]) == [
        [1.0, 1.0],
        [1.0, 1.0],
    ]
    assert provider.ensure_calls == 1
    assert scorer.model_initialization_count == 1
    assert provider.batches == [["claim one", "claim two"], ["context one", "context two"]]


def test_semantic_scorer_enforces_bounds_before_encoding() -> None:
    provider = CountingEmbeddings()
    scorer = BgeM3SemanticScorer(provider, max_claims=1, max_contexts=1, max_text_characters=8)
    scorer.warmup()
    with pytest.raises(ValueError, match="claim bound"):
        scorer.score_matrix(["one", "two"], ["context"])
    with pytest.raises(ValueError, match="text length"):
        scorer.score_matrix(["too long text"], ["context"])
    with pytest.raises(ValueError, match="context bound"):
        scorer.score_matrix(["claim"], ["one", "two"])


def test_semantic_scorer_is_not_usable_before_successful_warmup() -> None:
    class FailingEmbeddings(CountingEmbeddings):
        def ensure_available(self) -> None:
            raise RuntimeError("unavailable")

    scorer = BgeM3SemanticScorer(FailingEmbeddings())
    with pytest.raises(RuntimeError, match="unavailable"):
        scorer.warmup()
    assert scorer.is_ready is False and scorer.last_error_type == "RuntimeError"
    with pytest.raises(RuntimeError, match="not warmed"):
        scorer.score_matrix(["claim"], ["context"])
