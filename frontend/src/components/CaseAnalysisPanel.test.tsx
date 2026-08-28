import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, test } from 'vitest';

import type { CaseAnalysis } from '../api/types';
import { CaseAnalysisPanel } from './CaseAnalysisPanel';

afterEach(cleanup);

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
  ],
  candidate_issues: ['CONTRACT_TERM', 'EMPLOYEE_UNILATERAL_TERMINATION'],
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
      question: 'Hợp đồng bắt đầu từ ngày nào?',
      critical: true,
      related_issue_codes: ['CONTRACT_TERM'],
      requirement_reasons: ['REQUIRED_FACT_MISSING'],
      priority: 1,
    },
    {
      fact_key: 'EMPLOYEE_ROLE',
      question: 'Vai trò công việc của người lao động là gì?',
      critical: false,
      related_issue_codes: ['EMPLOYEE_UNILATERAL_TERMINATION'],
      requirement_reasons: ['REQUIRED_FACT_MISSING'],
      priority: 2,
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
  missing_fields: [],
  clarification_questions: [],
  refined_issues: [
    {
      issue_code: 'CONTRACT_TERM',
      status: 'ACTIVE',
      reason_code: 'REQUIREMENTS_SATISFIED',
      relevant_fact_keys: ['CONTRACT_TYPE'],
      remaining_missing_fields: [],
      critical_missing_fields: [],
    },
  ],
  substantive_analysis_blocked: false,
};

const possibleAnalysis: CaseAnalysis = {
  ...clarificationAnalysis,
  known_facts: [],
  missing_fields: [],
  clarification_questions: [],
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
  test('renders backend clarification state with known, missing, and bounded questions', () => {
    render(<CaseAnalysisPanel analysis={clarificationAnalysis} />);

    expect(screen.getByRole('status')).toHaveTextContent('Cần bổ sung thông tin');
    expect(screen.getByRole('heading', { name: 'Thông tin đã biết' })).toBeInTheDocument();
    expect(screen.getByText('FIXED_TERM')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Thông tin còn thiếu' })).toBeInTheDocument();
    expect(screen.getByText('Loại hợp đồng')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Câu hỏi cần làm rõ' })).toBeInTheDocument();
    expect(screen.getByText('Hợp đồng bắt đầu từ ngày nào?')).toBeInTheDocument();
    expect(screen.getByText('Vai trò công việc của người lao động là gì?')).toBeInTheDocument();
  });

  test('renders an active issue as a neutral continuation state', () => {
    render(<CaseAnalysisPanel analysis={activeAnalysis} />);

    expect(screen.getByRole('heading', { name: 'Trạng thái vấn đề' })).toBeInTheDocument();
    expect(screen.getByText('Đủ dữ kiện để tiếp tục')).toBeInTheDocument();
    expect(screen.queryByText(/thắng|được quyền|vi phạm/i)).not.toBeInTheDocument();
  });

  test('keeps a possible issue in its backend-provided neutral state', () => {
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
});
