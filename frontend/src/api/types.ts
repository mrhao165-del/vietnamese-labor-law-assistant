export type Route = 'RETRIEVAL_ONLY' | 'CALCULATOR_ONLY' | 'RETRIEVAL_AND_CALCULATOR' | 'OUT_OF_SCOPE';
export type VerificationStatus = 'SUPPORTED' | 'PARTIALLY_SUPPORTED' | 'UNSUPPORTED' | 'INSUFFICIENT_CONTEXT' | 'OUT_OF_SCOPE';
export type FeedbackValue = 'up' | 'down';

export interface ApiErrorEnvelope { request_id: string; error_code: string; message: string; retryable: boolean; details?: Record<string, unknown>; timestamp: string; }
export interface Conversation { id: string; title: string; created_at: string; updated_at: string; }
export interface Citation { index: number; chunk_id: string; article_number: number; clause_number: number | null; point_label: string | null; excerpt: string; document_name: string | null; source_file: string | null; }
export interface ToolTrace { sequence: number; tool_name: string; status: string; duration_ms: number; parameters: Record<string, unknown>; result_summary: string | null; error_code: string | null; }
export interface Verification { status: VerificationStatus; warnings: string[]; checks: Array<{ label: string; passed: boolean }>; }
export interface Message { id: string; conversation_id: string; role: 'user' | 'assistant'; content: string; created_at: string; metadata: { route?: Route; final_status?: string; citations?: Citation[]; tool_trace?: ToolTrace[]; verification?: Verification | null; warnings?: string[]; latency_ms?: number; pipeline_version?: string; }; feedback: FeedbackValue | null; }
export interface ChatResponse { request_id: string; conversation_id: string; user_message_id: string; assistant_message_id: string; answer: string; answer_text: string; verification_code: string | null; user_facing_message: string | null; route: Route | null; final_status: string; citations: Citation[]; tool_trace: ToolTrace[]; verification: Verification | null; warnings: string[]; latency_ms: number; pipeline_version: string; created_at: string; }
export interface Readiness { ready: boolean; checks: Record<string, boolean>; }
