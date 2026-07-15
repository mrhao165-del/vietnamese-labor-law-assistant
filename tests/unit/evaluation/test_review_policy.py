from vietnamese_labor_law_assistant.evaluation.review_policy import (
    independent_human_review_errors,
    is_independent_human_review,
    is_project_author_source_verification,
    reviewer_is_independent_human,
)


def test_ai_reviewer_cannot_be_counted_as_independent_human() -> None:
    row = {
        "human_decision": "PASS",
        "reviewer_name": "ChatGPT_AI_PRE_REVIEW",
        "reviewer_role": "legal reviewer",
        "reviewed_at": "2026-07-15T10:00:00+07:00",
        "evidence_note": "Compared with source DOCX.",
    }

    assert not reviewer_is_independent_human(row["reviewer_name"])
    assert not is_independent_human_review(row)
    assert (
        "reviewer_name is missing or identifies AI/machine review"
        in independent_human_review_errors(row)
    )


def test_complete_named_human_review_is_accepted() -> None:
    row = {
        "human_decision": "PASS",
        "reviewer_name": "Nguyễn Văn A",
        "reviewer_role": "Legal reviewer",
        "reviewed_at": "2026-07-15T10:00:00+07:00",
        "evidence_note": "Compared against Article 2, Clause 1 in the source DOCX.",
    }

    assert is_independent_human_review(row)


def test_incomplete_human_review_is_not_accepted() -> None:
    assert not is_independent_human_review({"human_decision": "PASS", "reviewer_name": "A"})


def test_project_author_is_source_evidence_but_not_independent_label_review() -> None:
    row = {
        "human_decision": "PASS",
        "reviewer_name": "Gia Hao Dang",
        "reviewer_role": "Project author - manual source verifier",
        "reviewed_at": "2026-07-15T21:25:57+07:00",
        "evidence_note": "Compared against source DOCX blocks.",
    }

    assert is_project_author_source_verification(row)
    assert not is_independent_human_review(row)
