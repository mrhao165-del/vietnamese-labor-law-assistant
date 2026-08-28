export type Route = 'RETRIEVAL_ONLY' | 'CALCULATOR_ONLY' | 'RETRIEVAL_AND_CALCULATOR' | 'CASE_ANALYSIS' | 'OUT_OF_SCOPE';
export type VerificationStatus = 'SUPPORTED' | 'PARTIALLY_SUPPORTED' | 'UNSUPPORTED' | 'INSUFFICIENT_CONTEXT' | 'CLARIFICATION_REQUIRED' | 'ARTICLE_NOT_FOUND' | 'OUT_OF_SCOPE' | 'OUTPUT_INVALID';
export type FeedbackValue = 'up' | 'down';

export interface ApiErrorEnvelope { request_id: string; error_code: string; message: string; retryable: boolean; details?: Record<string, unknown>; timestamp: string; }
export interface Conversation { id: string; title: string; created_at: string; updated_at: string; }
export interface Citation { index: number; chunk_id: string; article_number: number; clause_number: number | null; point_label: string | null; excerpt: string; document_name: string | null; source_file: string | null; }
export interface ToolTrace { sequence: number; tool_name: string; status: string; duration_ms: number; parameters: Record<string, unknown>; result_summary: string | null; error_code: string | null; }
export interface Verification { status: VerificationStatus; warnings: string[]; checks: Array<{ label: string; passed: boolean }>; }
export interface CaseSourceSpan { start_offset: number; end_offset: number; text: string; }
export interface CaseFact { fact_id: string; fact_key: string; raw_value: string; normalized_value: string | number | boolean; assertion_mode: string; verification_status: string; source_ref: string; source_span: CaseSourceSpan; }
export interface CaseMissingField { fact_key: string; required_by_issues: string[]; critical_for_issues: string[]; }
export interface CaseClarificationQuestion { fact_key: string; question: string; critical: boolean; related_issue_codes: string[]; requirement_reasons: string[]; priority: number; }
export interface CaseRefinedIssue { issue_code: string; status: string; reason_code: string; relevant_fact_keys: string[]; remaining_missing_fields: string[]; critical_missing_fields: string[]; }
export interface CaseEvidenceRequest { document_id: string; article: number; clause: number; source_chunk_id: string; related_issue_codes: string[]; }
export interface CaseCalculatorRequest { capability: string; input_fact_keys: string[]; related_issue_codes: string[]; }
export interface CaseAnalysis { status: string; error_code: string | null; known_facts: CaseFact[]; candidate_issues: string[]; missing_fields: CaseMissingField[]; clarification_reason_code: string | null; clarification_questions: CaseClarificationQuestion[]; refined_issues: CaseRefinedIssue[]; evidence_requests: CaseEvidenceRequest[]; calculator_requests: CaseCalculatorRequest[]; substantive_analysis_blocked: boolean; }
export interface Message { id: string; conversation_id: string; role: 'user' | 'assistant'; content: string; created_at: string; metadata: { router_decision?: string | null; planned_tools?: string[]; route?: Route | null; final_status?: string; citations?: Citation[]; tool_trace?: ToolTrace[]; verification?: Verification | null; case_analysis?: CaseAnalysis | null; warnings?: string[]; latency_ms?: number; pipeline_version?: string; }; feedback: FeedbackValue | null; }
export interface ChatResponse { request_id: string; conversation_id: string; user_message_id: string; assistant_message_id: string; answer: string; answer_text: string; verification_code: string | null; user_facing_message: string | null; router_decision: string | null; planned_tools: string[]; route: Route | null; final_status: string; citations: Citation[]; tool_trace: ToolTrace[]; verification: Verification | null; case_analysis: CaseAnalysis | null; warnings: string[]; latency_ms: number; pipeline_version: string; created_at: string; }
export interface Readiness { ready: boolean; checks: Record<string, boolean>; }
