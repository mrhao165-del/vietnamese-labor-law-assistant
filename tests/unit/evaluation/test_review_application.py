import json
import shutil
from pathlib import Path

from vietnamese_labor_law_assistant.evaluation.review_application import apply_project_author_review
from vietnamese_labor_law_assistant.ingestion.identifiers import calculate_file_sha256

ROOT = Path(__file__).resolve().parents[3]


def _copy_input(root: Path, relative_path: str) -> None:
    source = ROOT / relative_path
    destination = root / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def test_project_author_application_updates_dataset_and_current_chunk_provenance(
    tmp_path: Path,
) -> None:
    for relative_path in (
        "data/evaluation/labor_law_eval_v1_human_review_packet.csv",
        "data/evaluation/labor_law_eval_v1.jsonl",
        "data/evaluation/labor_law_eval_v1_manifest.json",
        "data/processed/labor_law_clauses.jsonl",
    ):
        _copy_input(tmp_path, relative_path)

    result = apply_project_author_review(
        tmp_path, tmp_path / "data/evaluation/labor_law_eval_v1_human_review_packet.csv"
    )

    manifest_path = tmp_path / "data/evaluation/labor_law_eval_v1_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dataset_path = tmp_path / "data/evaluation/labor_law_eval_v1.jsonl"
    chunks_path = tmp_path / "data/processed/labor_law_clauses.jsonl"
    assert result["applied_question_ids"] == [
        "w3-019",
        "w3-031",
        "w3-032",
        "w3-033",
        "w3-035",
        "w3-036",
        "w3-037",
        "w3-038",
        "w3-041",
        "w3-042",
        "w3-044",
        "w3-045",
        "w3-046",
        "w3-047",
        "w3-048",
        "w3-049",
    ]
    assert manifest["dataset_sha256"] == calculate_file_sha256(dataset_path)
    assert manifest["source_chunks_sha256"] == calculate_file_sha256(chunks_path)
    assert manifest["official_status"] == "PROVISIONAL_PROJECT_AUTHOR_AI_ASSISTED_APPROVAL"
