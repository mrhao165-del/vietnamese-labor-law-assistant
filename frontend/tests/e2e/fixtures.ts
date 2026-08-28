import type { Page } from '@playwright/test';

import type {
  ApiErrorEnvelope,
  CaseAnalysis,
  ChatResponse,
  Citation,
  Conversation,
  Message,
  Verification,
} from '../../src/api/types';

export type Scenario = 'direct' | 'clarification' | 'error';

const createdAt = '2026-08-29T00:00:00Z';
const localViteOrigin = 'http://127.0.0.1:4173';
const googleFontOrigins = new Set([
  'https://fonts.googleapis.com',
  'https://fonts.gstatic.com',
]);

const directCitation: Citation = {
  index: 1,
  chunk_id: 'labor-code-2019-article-35-clause-1',
  article_number: 35,
  clause_number: 1,
  point_label: null,
  excerpt: 'Người lao động phải báo trước khi đơn phương chấm dứt hợp đồng lao động.',
  document_name: 'Bộ luật Lao động 2019',
  source_file: 'labor_law.docx',
};

const directVerification: Verification = {
  status: 'SUPPORTED',
  warnings: [],
  checks: [{ label: 'Căn cứ thuộc nguồn chuẩn', passed: true }],
};

const clarificationVerification: Verification = {
  status: 'CLARIFICATION_REQUIRED',
  warnings: [],
  checks: [{ label: 'Cần bổ sung dữ kiện trước khi tiếp tục', passed: true }],
};

const clarificationAnalysis: CaseAnalysis = {
  status: 'CLARIFICATION_REQUIRED',
  error_code: null,
  known_facts: [
    {
      fact_id: 'fact-contract-start-date',
      fact_key: 'CONTRACT_START_DATE',
      raw_value: '2026-01-01',
      normalized_value: '2026-01-01',
      assertion_mode: 'EXPLICIT',
      verification_status: 'UNVERIFIED',
      source_ref: 'user_message:user-message-clarification',
      source_span: { start_offset: 22, end_offset: 32, text: '2026-01-01' },
    },
    {
      fact_id: 'fact-contract-end-date',
      fact_key: 'CONTRACT_END_DATE',
      raw_value: '2026-12-31',
      normalized_value: '2026-12-31',
      assertion_mode: 'EXPLICIT',
      verification_status: 'UNVERIFIED',
      source_ref: 'user_message:user-message-clarification',
      source_span: { start_offset: 37, end_offset: 47, text: '2026-12-31' },
    },
  ],
  candidate_issues: ['CONTRACT_TERM'],
  missing_fields: [
    {
      fact_key: 'CONTRACT_TYPE',
      required_by_issues: ['CONTRACT_TERM'],
      critical_for_issues: ['CONTRACT_TERM'],
    },
  ],
  clarification_reason_code: 'CRITICAL_FACTS_MISSING',
  clarification_questions: [
    {
      fact_key: 'CONTRACT_TYPE',
      question:
        'Hợp đồng lao động thuộc loại không xác định thời hạn, xác định thời hạn dưới 12 tháng, hay xác định thời hạn từ 12 đến 36 tháng?',
      critical: true,
      related_issue_codes: ['CONTRACT_TERM'],
      requirement_reasons: ['FACT_NOT_PROVIDED'],
      priority: 1,
    },
  ],
  refined_issues: [],
  evidence_requests: [],
  calculator_requests: [],
  substantive_analysis_blocked: true,
};

function assistantMetadata(response: ChatResponse): Message['metadata'] & Record<string, unknown> {
  return {
    router_decision: response.router_decision,
    planned_tools: response.planned_tools,
    route: response.route,
    final_status: response.final_status,
    citations: response.citations,
    tool_trace: response.tool_trace,
    verification: response.verification,
    case_analysis: response.case_analysis,
    warnings: response.warnings,
    answer_text: response.answer_text,
    verification_code: response.verification_code,
    user_facing_message: response.user_facing_message,
    request_id: response.request_id,
    latency_ms: response.latency_ms,
    pipeline_version: response.pipeline_version,
  };
}

function chatResponse(scenario: Exclude<Scenario, 'error'>): ChatResponse {
  const direct = scenario === 'direct';
  const answer = direct
    ? 'Người lao động phải báo trước.'
    : 'Vui lòng bổ sung thông tin để tiếp tục phân tích tình huống.';

  return {
    request_id: `request-${scenario}`,
    conversation_id: `conversation-${scenario}`,
    user_message_id: `user-message-${scenario}`,
    assistant_message_id: `assistant-message-${scenario}`,
    answer,
    answer_text: answer,
    verification_code: direct ? 'SUPPORTED' : 'CLARIFICATION_REQUIRED',
    user_facing_message: null,
    router_decision: direct ? 'RETRIEVAL_ONLY' : 'CASE_ANALYSIS',
    planned_tools: direct ? ['LEGAL_RETRIEVAL'] : [],
    route: direct ? 'RETRIEVAL_ONLY' : 'CASE_ANALYSIS',
    final_status: direct ? 'COMPLETED' : 'CLARIFICATION_REQUIRED',
    citations: direct ? [directCitation] : [],
    tool_trace: [],
    verification: direct ? directVerification : clarificationVerification,
    case_analysis: direct ? null : clarificationAnalysis,
    warnings: [],
    latency_ms: 12,
    pipeline_version: 'week11-agent-guardrail',
    created_at: createdAt,
  };
}

export async function installMockApi(page: Page, scenario: Scenario): Promise<void> {
  const conversations: Conversation[] = [];
  const messages = new Map<string, Message[]>();

  await page.route('**/*', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin !== localViteOrigin) {
      if (googleFontOrigins.has(url.origin)) {
        await route.fulfill({
          status: 204,
          contentType: url.hostname === 'fonts.googleapis.com' ? 'text/css' : 'application/octet-stream',
          body: '',
        });
      } else {
        await route.abort('blockedbyclient');
      }
      return;
    }

    const { pathname } = url;
    const method = request.method();

    if (method === 'GET' && pathname === '/ready') {
      await route.fulfill({
        json: {
          ready: true,
          checks: {
            retrieval: true,
            llm: true,
            semantic_scorer: true,
            runtime_database: true,
          },
        },
      });
      return;
    }

    if (method === 'GET' && pathname === '/api/v1/conversations') {
      await route.fulfill({ json: conversations });
      return;
    }

    const messageListMatch = pathname.match(/^\/api\/v1\/conversations\/([^/]+)\/messages$/);
    if (method === 'GET' && messageListMatch) {
      const conversationId = decodeURIComponent(messageListMatch[1]);
      await route.fulfill({ json: messages.get(conversationId) ?? [] });
      return;
    }

    if (method === 'POST' && pathname === '/api/v1/chat') {
      if (scenario === 'error') {
        const error: ApiErrorEnvelope = {
          request_id: 'request-error',
          error_code: 'AGENT_WORKFLOW_UNAVAILABLE',
          message: 'provider-secret private provider failure',
          retryable: true,
          details: { public_status: 'temporarily_unavailable' },
          timestamp: createdAt,
        };
        await route.fulfill({ status: 503, json: error });
        return;
      }

      const payload = request.postDataJSON() as {
        question: string;
        conversation_id?: string;
      };
      const response = chatResponse(scenario);
      const conversation: Conversation = {
        id: response.conversation_id,
        title: payload.question,
        created_at: createdAt,
        updated_at: createdAt,
      };
      const userMessage: Message = {
        id: response.user_message_id,
        conversation_id: response.conversation_id,
        role: 'user',
        content: payload.question,
        created_at: createdAt,
        metadata: {},
        feedback: null,
      };
      const assistantMessage: Message = {
        id: response.assistant_message_id,
        conversation_id: response.conversation_id,
        role: 'assistant',
        content: response.answer_text,
        created_at: createdAt,
        metadata: assistantMetadata(response),
        feedback: null,
      };

      conversations.splice(0, conversations.length, conversation);
      messages.set(response.conversation_id, [userMessage, assistantMessage]);
      await route.fulfill({ json: response });
      return;
    }

    if (method === 'PUT' && /^\/api\/v1\/messages\/[^/]+\/feedback$/.test(pathname)) {
      await route.fulfill({ status: 204 });
      return;
    }

    if (method === 'DELETE' && /^\/api\/v1\/conversations\/[^/]+$/.test(pathname)) {
      await route.fulfill({ status: 204 });
      return;
    }

    await route.continue();
  });
}
