"""Closed public values for the Week 9 orchestration workflow."""

from enum import StrEnum


class AgentIntent(StrEnum):
    RETRIEVAL_ONLY = "RETRIEVAL_ONLY"
    CALCULATOR_ONLY = "CALCULATOR_ONLY"
    RETRIEVAL_AND_CALCULATOR = "RETRIEVAL_AND_CALCULATOR"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class ToolName(StrEnum):
    SEARCH_LABOR_LAW = "search_labor_law"
    GET_ARTICLE = "get_article"
    GET_CLAUSE = "get_clause"
    GET_DOCUMENT_METADATA = "get_document_metadata"
    CALCULATE_NOTICE_PERIOD = "calculate_notice_period"
    CALCULATE_CONTRACT_DURATION = "calculate_contract_duration"


class WorkflowStatus(StrEnum):
    WORKFLOW_VALID = "WORKFLOW_VALID"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"
    TOOL_ERROR = "TOOL_ERROR"
    ROUTING_ERROR = "ROUTING_ERROR"
    OUTPUT_INVALID = "OUTPUT_INVALID"
