"""Conservative mapping from completed Agent results to browser-safe data."""

from __future__ import annotations

from typing import Any

from vietnamese_labor_law_assistant.agent.case_graph import CaseAnalysisResult
from vietnamese_labor_law_assistant.agent.models import AgentResult
from vietnamese_labor_law_assistant.guardrails.source_registry import CanonicalSourceRegistry

from .chat_models import (
    CaseAnalysisResponse,
    CaseCalculatorRequestResponse,
    CaseClarificationQuestionResponse,
    CaseEvidenceRequestResponse,
    CaseFactResponse,
    CaseMissingFieldResponse,
    CaseRefinedIssueResponse,
    CaseSourceSpanResponse,
    CitationResponse,
    ToolTraceResponse,
    VerificationResponse,
)

_INTERNAL_INSUFFICIENT_CODE = "INSUFFICIENT_VERIFIED_EVIDENCE"
_INSUFFICIENT_USER_MESSAGE = "Chưa đủ căn cứ pháp lý đã kiểm chứng để trả lời an toàn."
_SAFE_FAILURE_MESSAGES = {
    "CLARIFICATION_REQUIRED": ("Cần thêm thông tin cụ thể trước khi có thể trả lời chính xác."),
    "ARTICLE_NOT_FOUND": "Không tìm thấy điều luật được yêu cầu trong bộ dữ liệu hiện tại.",
    "INSUFFICIENT_CONTEXT": _INSUFFICIENT_USER_MESSAGE,
    "UNSUPPORTED": "Câu trả lời chưa có đủ bằng chứng để xác minh.",
    "OUT_OF_SCOPE": "Yêu cầu nằm ngoài phạm vi Bộ luật Lao động được hệ thống hỗ trợ.",
    "OUTPUT_INVALID": "Không thể hoàn tất yêu cầu một cách an toàn.",
    "EVIDENCE_REQUEST_READY": _INSUFFICIENT_USER_MESSAGE,
    "UNSUPPORTED_SCOPE": "Vụ việc hiện chưa thuộc phạm vi phân tích được hỗ trợ.",
    "CASE_INTAKE_FAILED": "Không thể tiếp nhận thông tin vụ việc một cách an toàn.",
    "CASE_ANALYSIS_FAILED": "Không thể tiếp tục phân tích vụ việc một cách an toàn.",
}


def public_answer(
    answer: str,
    verification: dict[str, Any] | None,
    workflow_status: str | None = None,
) -> str:
    """Never expose an internal fail-closed sentinel as browser answer text."""
    if answer == _INTERNAL_INSUFFICIENT_CODE:
        code = verification_code(verification) or workflow_status or "INSUFFICIENT_CONTEXT"
        return _SAFE_FAILURE_MESSAGES.get(code, _INSUFFICIENT_USER_MESSAGE)
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
            call_id=item.call_id,
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


def case_analysis_for(result: CaseAnalysisResult | None) -> CaseAnalysisResponse | None:
    """Project only allowlisted, typed Case Analysis product state."""

    if result is None:
        return None
    intake = result.intake_result
    missing = result.missing_facts
    clarification = result.clarification
    refined = result.refined_issues
    evidence = result.evidence_request
    return CaseAnalysisResponse(
        status=result.status.value,
        error_code=result.error_code.value if result.error_code else None,
        known_facts=tuple(
            CaseFactResponse(
                fact_id=fact.fact_id,
                fact_key=fact.fact_key,
                raw_value=fact.raw_value,
                normalized_value=fact.normalized_value,
                assertion_mode=fact.assertion_mode.value,
                verification_status=fact.verification_status.value,
                source_ref=fact.source_ref,
                source_span=CaseSourceSpanResponse(
                    start_offset=fact.source_span.start_offset,
                    end_offset=fact.source_span.end_offset,
                    text=fact.source_span.text,
                ),
            )
            for fact in intake.facts
        )
        if intake
        else (),
        candidate_issues=tuple(issue.issue_code.value for issue in intake.candidate_issues)
        if intake
        else (),
        missing_fields=tuple(
            CaseMissingFieldResponse(
                fact_key=field.fact_key.value,
                required_by_issues=tuple(code.value for code in field.required_by_issues),
                critical_for_issues=tuple(code.value for code in field.critical_for_issues),
            )
            for field in missing.fields_needed
        )
        if missing
        else (),
        clarification_reason_code=clarification.reason_code.value if clarification else None,
        clarification_questions=tuple(
            CaseClarificationQuestionResponse(
                fact_key=question.fact_key.value,
                question=question.question,
                critical=question.critical,
                related_issue_codes=tuple(code.value for code in question.related_issue_codes),
                requirement_reasons=tuple(reason.value for reason in question.requirement_reasons),
                priority=question.priority,
            )
            for question in clarification.questions
        )
        if clarification
        else (),
        refined_issues=tuple(
            CaseRefinedIssueResponse(
                issue_code=issue.issue_code.value,
                status=issue.status.value,
                reason_code=issue.reason_code.value,
                relevant_fact_keys=tuple(key.value for key in issue.relevant_fact_keys),
                remaining_missing_fields=tuple(key.value for key in issue.remaining_missing_fields),
                critical_missing_fields=tuple(key.value for key in issue.critical_missing_fields),
            )
            for issue in refined.issues
        )
        if refined
        else (),
        evidence_requests=tuple(
            CaseEvidenceRequestResponse(
                document_id=request.document_id,
                article=request.article,
                clause=request.clause,
                source_chunk_id=request.source_chunk_id,
                related_issue_codes=tuple(trace.issue_code.value for trace in request.issue_traces),
            )
            for request in evidence.evidence_requests
        )
        if evidence
        else (),
        calculator_requests=tuple(
            CaseCalculatorRequestResponse(
                capability=request.capability.value,
                input_fact_keys=tuple(key.value for key in request.input_fact_keys),
                related_issue_codes=tuple(trace.issue_code.value for trace in request.issue_traces),
            )
            for request in evidence.calculator_requests
        )
        if evidence
        else (),
        substantive_analysis_blocked=(
            evidence.substantive_analysis_blocked
            if evidence
            else bool(missing.fields_needed)
            if missing
            else True
        ),
    )


def public_message_content(content: str, metadata: dict[str, Any] | None = None) -> str:
    """Normalize legacy persisted sentinel answers at the HTTP boundary."""
    safe_metadata = metadata or {}
    return public_answer(
        content,
        safe_metadata.get("verification"),
        safe_metadata.get("final_status"),
    )
