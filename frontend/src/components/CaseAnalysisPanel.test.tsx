import { render, screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';

import type { CaseAnalysis } from '../api/types';
import { CaseAnalysisPanel } from './CaseAnalysisPanel';

const clarificationAnalysis: CaseAnalysis = {
  status: 'CLARIFICATION_REQUIRED',
  error_code: null,
  known_facts: [
    {
      fact_id: 'fact-contract-type',
      fact_key: 'CONTRACT_TYPE',
      raw_value: 'FIXED_TERM',
      normalized_value: 'FIXED_TERM',
      assertion_mode: 'EXPLICIT',
      verification_status: 'UNVERIFIED',
      source_ref: 'user_message:request-1',
      source_span: { start_offset: 0, end_offset: 10, text: 'FIXED_TERM' },
    },
    {
      fact_id: 'fact-contract-end-date',
      fact_key: 'CONTRACT_END_DATE',
      raw_value: '2026-12-31',
      normalized_value: '2026-12-31',
      assertion_mode: 'EXPLICIT',
      verification_status: 'UNVERIFIED',
      source_ref: 'user_message:request-1',
      source_span: { start_offset: 11, end_offset: 21, text: '2026-12-31' },
    },
  ],
  candidate_issues: ['CONTRACT_TERM'],
  missing_fields: [
    {
      fact_key: 'CONTRACT_START_DATE',
      required_by_issues: ['CONTRACT_TERM'],
      critical_for_issues: ['CONTRACT_TERM'],
    },
  ],
  clarification_reason_code: 'CRITICAL_FACTS_MISSING',
  clarification_questions: [
    {
      fact_key: 'CONTRACT_START_DATE',
      question: 'Ngày bắt đầu của khoảng thời gian hợp đồng cần xem xét là ngày nào?',
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

const activeAnalysis: CaseAnalysis = {
  ...clarificationAnalysis,
  status: 'EVIDENCE_REQUEST_READY',
  known_facts: [
    ...clarificationAnalysis.known_facts,
    {
      fact_id: 'fact-contract-start-date',
      fact_key: 'CONTRACT_START_DATE',
      raw_value: '2026-01-01',
      normalized_value: '2026-01-01',
      assertion_mode: 'EXPLICIT',
      verification_status: 'UNVERIFIED',
      source_ref: 'user_message:request-1',
      source_span: { start_offset: 22, end_offset: 32, text: '2026-01-01' },
    },
  ],
  missing_fields: [],
  clarification_reason_code: null,
  clarification_questions: [],
  refined_issues: [
    {
      issue_code: 'CONTRACT_TERM',
      status: 'ACTIVE',
      reason_code: 'REQUIREMENTS_SATISFIED',
      relevant_fact_keys: ['CONTRACT_TYPE', 'CONTRACT_START_DATE', 'CONTRACT_END_DATE'],
      remaining_missing_fields: [],
      critical_missing_fields: [],
    },
  ],
  evidence_requests: [
    {
      document_id: 'labor_law',
      article: 20,
      clause: 1,
      source_chunk_id: 'll_d0c5f537983c0aad635529f412e426f5',
      related_issue_codes: ['CONTRACT_TERM'],
    },
  ],
  calculator_requests: [
    {
      capability: 'CONTRACT_DURATION',
      input_fact_keys: ['CONTRACT_TYPE', 'CONTRACT_START_DATE', 'CONTRACT_END_DATE'],
      related_issue_codes: ['CONTRACT_TERM'],
    },
  ],
  substantive_analysis_blocked: false,
};

const possibleAnalysis: CaseAnalysis = {
  ...activeAnalysis,
  refined_issues: [
    {
      issue_code: 'CONTRACT_TERM',
      status: 'POSSIBLE',
      reason_code: 'CRITICAL_FACTS_MISSING',
      relevant_fact_keys: [],
      remaining_missing_fields: ['CONTRACT_TYPE'],
      critical_missing_fields: ['CONTRACT_TYPE'],
    },
  ],
};

const intakeFailureAnalysis: CaseAnalysis = {
  status: 'CASE_INTAKE_FAILED',
  error_code: 'CASE_INTAKE_PROVIDER_ERROR',
  known_facts: [],
  candidate_issues: [],
  missing_fields: [],
  clarification_reason_code: null,
  clarification_questions: [],
  refined_issues: [],
  evidence_requests: [],
  calculator_requests: [],
  substantive_analysis_blocked: true,
};

describe('CaseAnalysisPanel', () => {
  test('renders a production-valid clarification terminal with its actual missing field', () => {
    render(<CaseAnalysisPanel analysis={clarificationAnalysis} />);

    expect(screen.getByRole('status')).toHaveTextContent('Cần bổ sung thông tin');
    expect(screen.getByRole('heading', { name: 'Thông tin đã biết' })).toBeInTheDocument();
    expect(screen.getByText('FIXED_TERM')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Thông tin còn thiếu' })).toBeInTheDocument();
    expect(screen.getByText('Ngày bắt đầu hợp đồng')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Câu hỏi cần làm rõ' })).toBeInTheDocument();
    expect(
      screen.getByText('Ngày bắt đầu của khoảng thời gian hợp đồng cần xem xét là ngày nào?'),
    ).toBeInTheDocument();
  });

  test('renders an active issue as a neutral continuation state', () => {
    render(<CaseAnalysisPanel analysis={activeAnalysis} />);

    expect(screen.getByRole('heading', { name: 'Trạng thái vấn đề' })).toBeInTheDocument();
    expect(screen.getByText('Đủ dữ kiện để tiếp tục')).toBeInTheDocument();
    expect(screen.queryByText(/thắng|được quyền|vi phạm/i)).not.toBeInTheDocument();
  });

  test('keeps POSSIBLE neutral as isolated forward-compatible presentation coverage', () => {
    render(<CaseAnalysisPanel analysis={possibleAnalysis} />);

    expect(screen.getByText('Đang xem xét — còn thiếu dữ kiện')).toBeInTheDocument();
    expect(screen.queryByText('Đủ dữ kiện để tiếp tục')).not.toBeInTheDocument();
  });

  test('fails closed with fixed copy when case intake failed', () => {
    render(<CaseAnalysisPanel analysis={intakeFailureAnalysis} />);

    expect(screen.getByRole('alert')).toHaveTextContent(
      'Không thể tiếp nhận thông tin vụ việc một cách an toàn.',
    );
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.queryByRole('heading')).not.toBeInTheDocument();
  });

  test('fails closed before ordinary sections for an unknown terminal status', () => {
    render(
      <CaseAnalysisPanel
        analysis={{ ...clarificationAnalysis, status: 'MODEL_GENERATED_STATUS' }}
      />,
    );

    expect(screen.getByRole('alert')).toHaveTextContent(
      'Không thể tiếp tục phân tích vụ việc một cách an toàn.',
    );
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.queryByRole('heading')).not.toBeInTheDocument();
    expect(screen.queryByText('MODEL_GENERATED_STATUS')).not.toBeInTheDocument();
    expect(screen.queryByText('FIXED_TERM')).not.toBeInTheDocument();
  });

  test('fails closed before ordinary sections when a normal terminal carries an error code', () => {
    render(
      <CaseAnalysisPanel
        analysis={{ ...clarificationAnalysis, error_code: 'provider-secret-error' }}
      />,
    );

    expect(screen.getByRole('alert')).toHaveTextContent(
      'Không thể tiếp tục phân tích vụ việc một cách an toàn.',
    );
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.queryByRole('heading')).not.toBeInTheDocument();
    expect(screen.queryByText('provider-secret-error')).not.toBeInTheDocument();
    expect(screen.queryByText('FIXED_TERM')).not.toBeInTheDocument();
  });
});
