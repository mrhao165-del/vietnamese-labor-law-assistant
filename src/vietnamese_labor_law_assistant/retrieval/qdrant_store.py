"""Qdrant named-dense-vector storage and source-payload access."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any, cast

from qdrant_client import QdrantClient, models

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.ingestion.models import LegalChunk

from .models import LegalSearchFilters

VECTOR_NAME = "dense"
POINT_NAMESPACE = uuid.UUID("9b8a970c-1e2f-5230-a7de-4057e980d023")


class QdrantStoreError(RuntimeError):
    """A descriptive Qdrant availability or collection-contract error."""


def build_qdrant_point_id(chunk_id: str) -> str:
    """Return a Qdrant-compatible deterministic UUIDv5 for an immutable chunk ID."""
    return str(uuid.uuid5(POINT_NAMESPACE, chunk_id))


class QdrantStore:
    """Thin adapter around Qdrant, with no in-memory default for production."""

    def __init__(self, settings: Settings, client: QdrantClient | Any | None = None) -> None:
        self.settings = settings
        self.collection_name = settings.qdrant_collection
        if client is not None:
            self.client = client
        elif settings.qdrant_mode == "local":
            self.client = QdrantClient(path=str(settings.qdrant_local_path.resolve()))
        else:
            self.client = QdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key.get_secret_value()
                if settings.qdrant_api_key
                else None,
                timeout=15,
            )

    def collection_exists(self) -> bool:
        return bool(self.client.collection_exists(self.collection_name))

    def ensure_collection(self, dimension: int, recreate: bool = False) -> None:
        """Create a compatible named-vector collection; delete only on explicit request."""
        if self.collection_exists():
            if recreate:
                self.client.delete_collection(self.collection_name)
            else:
                self.validate_collection_config(dimension)
                return
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config={
                VECTOR_NAME: models.VectorParams(size=dimension, distance=models.Distance.COSINE)
            },
        )

    def validate_collection_config(self, dimension: int) -> None:
        """Reject existing collections that are incompatible with current BGE output."""
        info = self.client.get_collection(self.collection_name)
        config = info.config.params.vectors
        if not isinstance(config, dict) or VECTOR_NAME not in config:
            raise QdrantStoreError("Collection does not expose the required named vector 'dense'")
        vector = config[VECTOR_NAME]
        if vector.size != dimension or vector.distance != models.Distance.COSINE:
            raise QdrantStoreError("Collection dense vector dimension or distance is incompatible")

    def create_payload_indexes(self) -> None:
        """Create useful filter indexes; Qdrant safely treats duplicate creation as idempotent."""
        fields = {
            "chunk_id": models.PayloadSchemaType.KEYWORD,
            "document_id": models.PayloadSchemaType.KEYWORD,
            "article_number": models.PayloadSchemaType.INTEGER,
            "clause_number": models.PayloadSchemaType.INTEGER,
            "chapter_number": models.PayloadSchemaType.KEYWORD,
        }
        for field_name, field_schema in fields.items():
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name=field_name,
                field_schema=field_schema,
                wait=True,
            )

    def _payload(self, chunk: LegalChunk, input_sha256: str) -> dict[str, Any]:
        payload = chunk.model_dump(mode="json")
        payload.update({"embedding_text_version": "v1", "input_jsonl_sha256": input_sha256})
        return payload

    def upsert_points(
        self, chunks: Sequence[LegalChunk], vectors: Sequence[Sequence[float]], input_sha256: str
    ) -> None:
        """Idempotently upsert one named dense vector per legal chunk."""
        if len(chunks) != len(vectors):
            raise ValueError("chunk and vector counts must match")
        points = [
            models.PointStruct(
                id=build_qdrant_point_id(chunk.chunk_id),
                vector={VECTOR_NAME: list(vector)},
                payload=self._payload(chunk, input_sha256),
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        self.client.upsert(collection_name=self.collection_name, points=points, wait=True)

    def _filter(self, filters: LegalSearchFilters | None):
        conditions = []
        for key, value in filters.as_dict().items() if filters is not None else []:
            if value is not None:
                conditions.append(
                    models.FieldCondition(key=key, match=models.MatchValue(value=value))
                )
        return models.Filter(must=conditions) if conditions else None

    def query_dense(
        self,
        vector: Sequence[float],
        limit: int,
        article_number: int | None = None,
        clause_number: int | None = None,
        document_id: str | None = None,
        filters: LegalSearchFilters | None = None,
    ) -> list[Any]:
        """Search named dense vectors and return scored Qdrant point objects."""
        try:
            response = self.client.query_points(
                collection_name=self.collection_name,
                query=list(vector),
                using=VECTOR_NAME,
                query_filter=self._filter(
                    filters
                    or LegalSearchFilters(
                        article_number=article_number,
                        clause_number=clause_number,
                        document_id=document_id,
                    )
                ),
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
            return list(response.points)
        except Exception as exc:
            raise QdrantStoreError(f"Dense Qdrant query failed: {exc}") from exc

    def get_by_chunk_id(self, chunk_id: str) -> dict[str, Any] | None:
        """Return verified source payload by its public chunk ID."""
        records, _ = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(key="chunk_id", match=models.MatchValue(value=chunk_id))
                ]
            ),
            limit=1,
            with_payload=True,
            with_vectors=False,
        )
        if not records:
            return None
        payload = cast(Mapping[str, Any], records[0].payload or {})
        return dict(payload)

    def get_point_id_by_chunk_id(self, chunk_id: str) -> str | None:
        """Return the persisted point UUID for an explicit idempotence check."""
        records, _ = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(key="chunk_id", match=models.MatchValue(value=chunk_id))
                ]
            ),
            limit=1,
            with_payload=False,
            with_vectors=False,
        )
        return str(records[0].id) if records else None

    def count_points(self) -> int:
        return int(self.client.count(collection_name=self.collection_name, exact=True).count)

    def collection_ready(self) -> bool:
        try:
            return self.collection_exists() and self.count_points() > 0
        except Exception:
            return False
