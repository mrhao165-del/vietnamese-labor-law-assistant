"""Call the running FastAPI RAG service without embedding API credentials in code."""

from __future__ import annotations

import argparse

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    response = httpx.post(
        f"{args.url}/api/v1/query", json={"question": args.question, "top_k": 5}, timeout=90
    )
    response.raise_for_status()
    result = response.json()
    print(result["answer"])
    for citation in result["citations"]:
        print(f"- {citation['display_label']}: {citation['source_endpoint']}")
    print(f"Latency: {result['total_latency_ms']:.1f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
