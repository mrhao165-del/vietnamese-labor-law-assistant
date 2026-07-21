"""Measure the production BGE-M3 guardrail semantic scorer in one process."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.guardrails.similarity import BgeM3SemanticScorer
from vietnamese_labor_law_assistant.retrieval.embeddings import BgeM3EmbeddingProvider


def _rss_bytes() -> int | None:
    status = Path("/proc/self/status")
    if not status.exists():
        return None
    for line in status.read_text(encoding="utf-8").splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) * 1024
    return None


def _event(name: str, **values: object) -> None:
    """Emit bounded JSON telemetry immediately so a hung phase is attributable."""
    print(json.dumps({"event": name, **values}, ensure_ascii=False), flush=True)


def _measure(
    label: str, scorer: BgeM3SemanticScorer, claims: list[str], contexts: list[str]
) -> dict[str, object]:
    started = time.perf_counter()
    claims_started = time.perf_counter()
    claim_vectors = scorer.provider.embed_documents(claims)
    claims_ms = (time.perf_counter() - claims_started) * 1000
    contexts_started = time.perf_counter()
    context_vectors = scorer.provider.embed_documents(contexts)
    contexts_ms = (time.perf_counter() - contexts_started) * 1000
    similarity_started = time.perf_counter()
    similarities = [
        sum(left * right for left, right in zip(claim, context, strict=True))
        for claim in claim_vectors
        for context in context_vectors
    ]
    similarity_ms = (time.perf_counter() - similarity_started) * 1000
    return {
        "run": label,
        "encode_claims_ms": round(claims_ms, 3),
        "encode_contexts_ms": round(contexts_ms, 3),
        "similarity_ms": round(similarity_ms, 3),
        "total_ms": round((time.perf_counter() - started) * 1000, 3),
        "claim_count": len(claims),
        "unique_context_count": len(set(contexts)),
        "claim_characters": sum(map(len, claims)),
        "context_characters": sum(map(len, contexts)),
        "similarity_count": len(similarities),
        "rss_bytes": _rss_bytes(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--canonical", action="store_true")
    args = parser.parse_args()
    if args.offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
    settings = Settings(embedding_device="cpu", embedding_use_fp16=False)
    provider = BgeM3EmbeddingProvider(settings)
    scorer = BgeM3SemanticScorer(provider)
    _event(
        "constructor_started",
        hf_home=os.getenv("HF_HOME"),
        hf_hub_cache=os.getenv("HF_HUB_CACHE"),
        offline=args.offline,
        device_request=settings.embedding_device,
        use_fp16_request=settings.embedding_use_fp16,
        rss_before_bytes=_rss_bytes(),
    )
    constructor_started = time.perf_counter()
    provider.ensure_available()
    constructor_ms = (time.perf_counter() - constructor_started) * 1000
    _event(
        "constructor_completed",
        model_constructor_ms=round(constructor_ms, 3),
        device=provider.device,
        use_fp16=provider.use_fp16,
        rss_after_constructor_bytes=_rss_bytes(),
    )
    if args.canonical:
        claims = ["Người lao động có quyền đơn phương chấm dứt hợp đồng lao động."]
        contexts = [
            "Người lao động có quyền đơn phương chấm dứt hợp đồng lao động nhưng phải báo trước."
        ]
    else:
        claims, contexts = ["quyền chấm dứt hợp đồng"], ["quyền chấm dứt hợp đồng"]
    _event("cold_run_started", claim_count=len(claims), context_count=len(contexts))
    cold = _measure("COLD_RUN", scorer, claims, contexts)
    _event("cold_run_completed", **cold)
    _event("warm_run_started", claim_count=len(claims), context_count=len(contexts))
    warm = _measure("WARM_RUN", scorer, claims, contexts)
    _event("warm_run_completed", **warm)
    report = {
        "hf_home": os.getenv("HF_HOME"),
        "hf_hub_cache": os.getenv("HF_HUB_CACHE"),
        "offline": args.offline,
        "device": provider.device,
        "use_fp16": provider.use_fp16,
        "torch_num_threads": __import__("torch").get_num_threads(),
        "model_constructor_ms": round(constructor_ms, 3),
        "rss_before_bytes": _rss_bytes(),
        "cold": cold,
        "warm": warm,
        "rss_after_bytes": _rss_bytes(),
    }
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
