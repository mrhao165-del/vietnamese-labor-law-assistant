from vietnamese_labor_law_assistant.evaluation.review_packets import build_evaluation_packet_rows


def test_packet_preserves_machine_evidence_and_leaves_human_fields_blank() -> None:
    rows = build_evaluation_packet_rows(
        [
            {
                "question_id": "w3-001",
                "question": "Question",
                "category": "direct",
                "review_status": "PASS",
                "reviewer": "ChatGPT_AI_PRE_REVIEW",
                "machine_article_clause_check": "MACHINE_PASS",
            }
        ],
        {},
    )

    assert rows[0]["current_machine_ai_review_evidence"].startswith("legacy_review_status=PASS")
    assert rows[0]["human_decision"] == ""
    assert rows[0]["reviewer_name"] == ""
