"""Safe, fixed-location provenance metadata for the legal source corpus."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from vietnamese_labor_law_assistant.ingestion.models import SourceMetadata, ValidationReport


class DocumentMetadata(BaseModel):
    """Public legal provenance only; intentionally excludes local filesystem paths."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    document_name: str
    document_number: str | None = None
    source_url: str | None = None
    effective_date: str | None = None
    data_snapshot_date: str
    sha256: str | None = None
    article_count: int
    clause_count: int
    chunk_count: int


class LegalDocumentMetadataProvider:
    """Read the repository's fixed, allowlisted provenance artefacts."""

    def __init__(
        self,
        source_metadata_path: Path = Path("data/raw/source_metadata.json"),
        validation_report_path: Path = Path("data/processed/validation_report.json"),
    ) -> None:
        self._source_metadata_path = source_metadata_path
        self._validation_report_path = validation_report_path

    def get(self) -> DocumentMetadata:
        """Return source metadata without accepting any caller-controlled path."""
        source = SourceMetadata.model_validate(
            json.loads(self._source_metadata_path.read_text(encoding="utf-8"))
        )
        validation = ValidationReport.model_validate(
            json.loads(self._validation_report_path.read_text(encoding="utf-8"))
        )
        return DocumentMetadata(
            document_id=source.document_id,
            document_name=source.document_name,
            document_number=source.document_number,
            source_url=source.source_url,
            effective_date=source.effective_date.isoformat() if source.effective_date else None,
            data_snapshot_date=source.data_snapshot_date.isoformat(),
            sha256=source.sha256,
            article_count=validation.article_count,
            clause_count=validation.clause_count,
            chunk_count=validation.chunk_count,
        )
