"""Conservative mapping from completed Agent results to browser-safe data."""

from __future__ import annotations

from typing import Any

from vietnamese_labor_law_assistant.agent.models import AgentResult
from vietnamese_labor_law_assistant.guardrails.source_registry import CanonicalSourceRegistry

from .chat_models import CitationResponse, ToolTraceResponse, VerificationResponse

_INTERNAL_INSUFFICIENT_CODE = "INSUFFICIENT_VERIFIED_EVIDENCE"
_INSUFFICIENT_USER_MESSAGE = "Chưa đủ căn cứ pháp lý đã kiểm chứng để trả lời an toàn."


def public_answer(answer: str, verification: dict[str, Any] | None) -> str:
    """Never expose an internal fail-closed sentinel as browser answer text."""
    if answer == _INTERNAL_INSUFFICIENT_CODE:
        return _INSUFFICIENT_USER_MESSAGE
    return answer


def verification_code(verification: dict[str, Any] | None) -> str | None:
    if not isinstance(verification, dict):
        return None
    reason = verification.get("reason")
    if isinstance(reason, str) and reason:
        return reason
    for claim in verification.get("claims", []):
        if isinstance(claim, dict):
            reasons = claim.get("reason_codes", [])
            if isinstance(reasons, list) and reasons and isinstance(reasons[0], str):
                return reasons[0]
    status = verification.get("status")
    return str(status) if status else None


_SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "token",
    "prompt",
    "system_prompt",
    "question",
    "environment",
    "exception",
    "content",
}


def _safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _safe_value(item)
            for key, item in value.items()
            if str(key).lower() not in _SENSITIVE_KEYS
        }
    if isinstance(value, list):
        return [_safe_value(item) for item in value[:10]]
    if isinstance(value, str):
        return value[:300]
    return value if value is None or isinstance(value, (bool, int, float)) else str(value)[:300]


def citations_for(result: AgentResult, registry: CanonicalSourceRegistry) -> list[CitationResponse]:
    mapped: list[CitationResponse] = []
    seen_chunk_ids: set[str] = set()
    for index, citation in enumerate(result.citations, 1):
        chunk_id = citation.get("chunk_id") if isinstance(citation, dict) else None
        if not isinstance(chunk_id, str) or chunk_id in seen_chunk_ids:
            continue
        seen_chunk_ids.add(chunk_id)
        chunk = registry.get(chunk_id)
        if chunk is None:
            continue
        mapped.append(
            CitationResponse(
                index=index,
                chunk_id=chunk.chunk_id,
                article_number=chunk.article_number,
                clause_number=chunk.clause_number,
                point_label=chunk.point_label,
                excerpt=chunk.content[:1500],
                document_name=chunk.document_name,
                source_file=chunk.source_file,
            )
        )
    return mapped


def tool_trace_for(result: AgentResult) -> list[ToolTraceResponse]:
    return [
        ToolTraceResponse(
            sequence=item.sequence,
            tool_name=item.tool_name.value,
            status=item.status,
            duration_ms=item.latency_ms,
            parameters=_safe_value(item.sanitized_arguments),
            result_summary="Completed" if item.status == "ok" else None,
            error_code=item.error_code,
        )
        for item in result.tool_trace
    ]


def verification_for(result: AgentResult) -> VerificationResponse | None:
    raw = result.verification
    if not isinstance(raw, dict):
        return None
    claims = raw.get("claims", [])
    checks = [
        {
            "label": str(item.get("claim_id", "claim")),
            "passed": item.get("status") in {"SUPPORTED", "PARTIALLY_SUPPORTED"},
        }
        for item in claims
        if isinstance(item, dict)
    ]
    return VerificationResponse(
        status=str(raw.get("status", "INSUFFICIENT_CONTEXT")),
        warnings=[str(item)[:300] for item in raw.get("warnings", []) if isinstance(item, str)],
        checks=checks,
    )


def public_message_content(content: str, metadata: dict[str, Any] | None = None) -> str:
    """Normalize legacy persisted sentinel answers at the HTTP boundary."""
    return public_answer(content, (metadata or {}).get("verification"))
