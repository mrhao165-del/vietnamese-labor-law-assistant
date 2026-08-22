# Case Intake v1.1 development dataset

`case_intake_dev.jsonl` is an unfrozen Week-2 development set. Each JSONL record contains the raw
user-message source, typed expected facts and candidate issues, metric metadata, and human-review
status. Labels are authored development labels only: every record currently has
`human_validated=false` and `review_status=PENDING`.

This folder does not contain model predictions or official benchmark evidence. Week 4 owns freezing
the v1.1 evaluation set and producing any release report.
