"""Read-only, lazy canonical snapshot registry owned by server configuration."""

from __future__ import annotations

import json
from pathlib import Path

from vietnamese_labor_law_assistant.ingestion.models import LegalChunk


class SourceRegistryError(ValueError):
    pass


class CanonicalSourceRegistry:
    def __init__(self, source_path: Path) -> None:
        self._source_path = source_path
        self._records: dict[str, LegalChunk] | None = None

    def records(self) -> dict[str, LegalChunk]:
        if self._records is None:
            if not self._source_path.is_file():
                raise SourceRegistryError("canonical source is unavailable")
            loaded: dict[str, LegalChunk] = {}
            for line_number, line in enumerate(
                self._source_path.read_text(encoding="utf-8").splitlines(), 1
            ):
                if not line.strip():
                    continue
                try:
                    record = LegalChunk.model_validate(json.loads(line))
                except Exception as exc:
                    raise SourceRegistryError(
                        f"malformed canonical record at line {line_number}"
                    ) from exc
                if record.chunk_id in loaded:
                    raise SourceRegistryError(f"duplicate canonical chunk_id: {record.chunk_id}")
                loaded[record.chunk_id] = record
            self._records = loaded
        return self._records

    def get(self, chunk_id: str) -> LegalChunk | None:
        return self.records().get(chunk_id)
