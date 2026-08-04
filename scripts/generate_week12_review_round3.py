"""Generate the bounded Week 12 round-3 review packet from validated evidence."""

from pathlib import Path

from vietnamese_labor_law_assistant.evaluation.week12_round3_review import build_rows, write_packet


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    rows = build_rows(
        root / "evaluation/review/week12_manual_review_round2_reviewed.csv",
        root / "evaluation/results/week12/round3_remediation_analysis.json",
        root / "evaluation/results/week12/round3_remediation_live.json",
        {
            "W12-R2-006": "W12-R3-006",
            "W12-R2-008": "W12-R3-008",
            "W12-R2-019": "W12-R3-019",
        },
    )
    write_packet(
        rows,
        root / "evaluation/review/week12_manual_review_round3.csv",
        root / "evaluation/review/week12_manual_review_round3.html",
    )


if __name__ == "__main__":
    main()
