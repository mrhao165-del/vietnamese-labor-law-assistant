"""Safe, stable error taxonomy for the agent's public workflow result."""


class AgentError(RuntimeError):
    code = "AGENT_ERROR"
    retryable = False


class InvalidAgentInputError(AgentError):
    code = "INVALID_AGENT_INPUT"


class IntentClassificationError(AgentError):
    code = "INTENT_CLASSIFICATION_ERROR"


class InvalidRouterOutputError(IntentClassificationError):
    code = "INVALID_ROUTER_OUTPUT"


class MissingRequiredParameterError(AgentError):
    code = "MISSING_REQUIRED_PARAMETER"


class ToolBudgetExceededError(AgentError):
    code = "TOOL_BUDGET_EXCEEDED"


class ToolTimeoutError(AgentError):
    code = "TOOL_TIMEOUT"
    retryable = True


class ToolProtocolError(AgentError):
    code = "TOOL_PROTOCOL_ERROR"


class ToolResponseValidationError(ToolProtocolError):
    code = "TOOL_RESPONSE_VALIDATION_ERROR"


class RetrievalToolError(AgentError):
    code = "RETRIEVAL_TOOL_ERROR"


class CalculatorToolError(AgentError):
    code = "CALCULATOR_TOOL_ERROR"


class AnswerGenerationError(AgentError):
    code = "ANSWER_GENERATION_ERROR"


class WorkflowVerificationError(AgentError):
    code = "WORKFLOW_VERIFICATION_ERROR"
