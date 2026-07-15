"""Typed domain errors exposed by the Week 6 retrieval engine."""

from __future__ import annotations


class RetrievalError(RuntimeError):
    """Base error safe to map to a structured API response."""

    code = "RETRIEVAL_ERROR"
    status_code = 503


class EmptyQueryError(RetrievalError):
    code = "EMPTY_QUERY"
    status_code = 422


class InvalidSearchParameterError(RetrievalError):
    code = "INVALID_SEARCH_PARAMETER"
    status_code = 422


class UnsupportedRetrievalModeError(RetrievalError):
    code = "UNSUPPORTED_RETRIEVAL_MODE"
    status_code = 422


class InvalidFilterError(RetrievalError):
    code = "INVALID_FILTER"
    status_code = 422


class ArticleNotFoundError(RetrievalError):
    code = "ARTICLE_NOT_FOUND"
    status_code = 404


class DenseBackendUnavailableError(RetrievalError):
    code = "DENSE_BACKEND_UNAVAILABLE"


class SparseIndexUnavailableError(RetrievalError):
    code = "SPARSE_INDEX_UNAVAILABLE"


class EmbeddingError(RetrievalError):
    code = "EMBEDDING_FAILED"


class QdrantSearchError(RetrievalError):
    code = "QDRANT_SEARCH_FAILED"


class RerankerUnavailableError(RetrievalError):
    code = "RERANKER_UNAVAILABLE"


class RerankerExecutionError(RetrievalError):
    code = "RERANKER_EXECUTION_FAILED"


class CorpusManifestMismatchError(RetrievalError):
    code = "CORPUS_MANIFEST_MISMATCH"


class RetrievalDataError(RetrievalError):
    code = "RETRIEVAL_DATA_ERROR"
