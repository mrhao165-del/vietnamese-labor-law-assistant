import type { CaseAnalysis } from '../api/types';

const factLabels: Record<string, string> = {
  CONTRACT_DURATION: 'Thời hạn hợp đồng',
  CONTRACT_EXPIRY_STATEMENT: 'Thông tin về thời điểm hết hạn hợp đồng',
  CONTRACT_SIGNED_DATE: 'Ngày ký hợp đồng',
  CONTRACT_TYPE: 'Loại hợp đồng',
  EVENT_TIME: 'Thời điểm sự việc',
  UNPAID_WAGES_AMOUNT: 'Số tiền lương chưa thanh toán',
  UNPAID_WAGES_DURATION: 'Thời gian chậm trả lương',
  CONTRACT_START_DATE: 'Ngày bắt đầu hợp đồng',
  CONTRACT_END_DATE: 'Ngày kết thúc hợp đồng',
  NOTICE_SPECIAL_CASE: 'Trường hợp báo trước đặc biệt',
  EMPLOYEE_ROLE: 'Vai trò công việc của người lao động',
};

const analysisStatusLabels: Record<string, string> = {
  CLARIFICATION_REQUIRED: 'Cần bổ sung thông tin',
  EVIDENCE_REQUEST_READY: 'Sẵn sàng cho bước cung cấp thông tin tiếp theo',
  UNSUPPORTED_SCOPE: 'Ngoài phạm vi phân tích được hỗ trợ',
};

const issueLabels: Record<string, string> = {
  CONTRACT_TERM: 'Thông tin về thời hạn hợp đồng',
  EMPLOYEE_UNILATERAL_TERMINATION: 'Thông tin về việc người lao động đơn phương chấm dứt hợp đồng',
};

const refinedStatusLabels: Record<string, string> = {
  ACTIVE: 'Đủ dữ kiện để tiếp tục',
  POSSIBLE: 'Đang xem xét — còn thiếu dữ kiện',
  RESOLVED_OUT: 'Không còn được theo dõi trong lần phân tích này',
  UNSUPPORTED_SCOPE: 'Ngoài phạm vi phân tích được hỗ trợ',
};

const refinedReasonLabels: Record<string, string> = {
  REQUIREMENTS_SATISFIED: 'Các thông tin cần thiết đã được cung cấp.',
  REQUIRED_FACTS_MISSING: 'Cần bổ sung thêm thông tin liên quan.',
  CRITICAL_FACTS_MISSING: 'Cần bổ sung thông tin quan trọng trước khi tiếp tục.',
  DETERMINISTIC_EXCLUSION_ESTABLISHED: 'Trạng thái được xác định từ thông tin đã cung cấp.',
  APPLICABILITY_SCOPE_UNSUPPORTED: 'Nội dung này chưa thuộc phạm vi được hỗ trợ.',
};

const failedAnalysisMessages: Record<string, string> = {
  CASE_INTAKE_FAILED: 'Không thể tiếp nhận thông tin vụ việc một cách an toàn.',
  CASE_ANALYSIS_FAILED: 'Không thể tiếp tục phân tích vụ việc một cách an toàn.',
};
const genericFailedAnalysisMessage = 'Không thể tiếp tục phân tích vụ việc một cách an toàn.';

const unknownFactLabel = 'Thông tin đã cung cấp';
const unknownIssueLabel = 'Vấn đề trong yêu cầu';
const unknownRefinedStatusLabel = 'Trạng thái chưa được hỗ trợ';
const unknownReasonLabel = 'Lý do chưa được hỗ trợ';

function factLabel(factKey: string): string {
  return factLabels[factKey] ?? unknownFactLabel;
}

function hasOwnLabel(labels: Record<string, string>, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(labels, key);
}

export function CaseAnalysisPanel({ analysis }: { analysis: CaseAnalysis }) {
  if (hasOwnLabel(failedAnalysisMessages, analysis.status)) {
    return (
      <div role="alert" className="mt-3 rounded-lg bg-error-container p-3 text-sm text-on-error-container">
        {failedAnalysisMessages[analysis.status]}
      </div>
    );
  }

  if (analysis.error_code !== null || !hasOwnLabel(analysisStatusLabels, analysis.status)) {
    return (
      <div role="alert" className="mt-3 rounded-lg bg-error-container p-3 text-sm text-on-error-container">
        {genericFailedAnalysisMessage}
      </div>
    );
  }

  return (
    <section aria-label="Phân tích tình huống" className="mt-3 space-y-3 rounded-lg bg-surface-container-high p-3 text-sm">
      <div role="status" className="font-medium text-on-surface">
        {analysisStatusLabels[analysis.status]}
      </div>

      {analysis.known_facts.length > 0 && (
        <div>
          <h3 className="font-medium text-on-surface">Thông tin đã biết</h3>
          <ul className="mt-1 space-y-2">
            {analysis.known_facts.map((fact) => (
              <li key={fact.fact_id} className="rounded bg-surface-container-lowest p-2">
                <p className="font-medium">{factLabel(fact.fact_key)}</p>
                <p>{fact.raw_value}</p>
                <p className="text-on-surface-variant">
                  Cách xác nhận: {fact.assertion_mode} · Trạng thái xác minh: {fact.verification_status}
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {analysis.missing_fields.length > 0 && (
        <div>
          <h3 className="font-medium text-on-surface">Thông tin còn thiếu</h3>
          <ul className="mt-1 space-y-1">
            {analysis.missing_fields.map((field) => (
              <li key={field.fact_key}>
                {factLabel(field.fact_key)}
                {field.critical_for_issues.length > 0 && (
                  <span className="ml-2 text-error">Thông tin quan trọng</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {analysis.clarification_questions.length > 0 && (
        <div>
          <h3 className="font-medium text-on-surface">Câu hỏi cần làm rõ</h3>
          <ol className="mt-1 list-decimal space-y-1 pl-5">
            {analysis.clarification_questions.map((question, index) => (
              <li key={`${question.fact_key}-${index}`}>
                {question.question}
                {question.critical && <span className="ml-2 text-error">Thông tin quan trọng</span>}
              </li>
            ))}
          </ol>
        </div>
      )}

      {analysis.refined_issues.length > 0 && (
        <div>
          <h3 className="font-medium text-on-surface">Trạng thái vấn đề</h3>
          <ul className="mt-1 space-y-2">
            {analysis.refined_issues.map((issue) => (
              <li key={issue.issue_code} className="rounded bg-surface-container-lowest p-2">
                <p className="font-medium">{issueLabels[issue.issue_code] ?? unknownIssueLabel}</p>
                <p>{refinedStatusLabels[issue.status] ?? unknownRefinedStatusLabel}</p>
                <p className="text-on-surface-variant">
                  {refinedReasonLabels[issue.reason_code] ?? unknownReasonLabel}
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {(analysis.evidence_requests.length > 0 || analysis.calculator_requests.length > 0) && (
        <div>
          <h3 className="font-medium text-on-surface">Nhu cầu thông tin cho bước sau</h3>
          <ul className="mt-1 space-y-1 text-on-surface-variant">
            {analysis.evidence_requests.length > 0 && (
              <li>{analysis.evidence_requests.length} yêu cầu căn cứ cần được cung cấp.</li>
            )}
            {analysis.calculator_requests.length > 0 && (
              <li>{analysis.calculator_requests.length} yêu cầu thông tin tính toán cần được cung cấp.</li>
            )}
          </ul>
        </div>
      )}
    </section>
  );
}
