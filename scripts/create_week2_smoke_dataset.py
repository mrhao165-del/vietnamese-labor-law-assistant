"""Create a non-human-validated smoke set from actual Week 1 article titles."""

from __future__ import annotations

import json
from pathlib import Path

from vietnamese_labor_law_assistant.ingestion.writers import read_articles_jsonl

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    articles = {
        article.article_number: article
        for article in read_articles_jsonl(ROOT / "data/processed/labor_law_articles.jsonl")
    }
    selected = [1, 24, 47, 70, 93, 116, 139, 162, 185, 220]
    rows = []
    for number in selected:
        article = articles[number]
        if not article.article_title:
            raise RuntimeError(f"Article {number} has no title for smoke dataset")
        rows.append(
            {
                "question_id": f"week2-{number:03d}",
                "question": f"Quy định về {article.article_title} là gì?",
                "expected_articles": [number],
                "expected_clauses": [],
                "source_type": "synthetic_from_article_title",
                "human_validated": False,
            }
        )
    output = ROOT / "data/evaluation/week2_dense_smoke.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    print(f"Wrote {len(rows)} synthetic smoke questions to {output.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
