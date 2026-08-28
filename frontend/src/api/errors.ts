import type { ApiErrorEnvelope } from './types';
export class ApiClientError extends Error { constructor(public readonly kind: 'network' | 'timeout' | 'validation' | 'unavailable' | 'http', public readonly envelope?: ApiErrorEnvelope) { super(envelope?.message ?? kind); } }

export function publicApiErrorMessage(error: unknown): string {
  if (!(error instanceof ApiClientError)) {
    return 'Không thể xử lý yêu cầu. Vui lòng thử lại sau.';
  }

  switch (error.kind) {
    case 'validation':
      return 'Yêu cầu chưa hợp lệ. Vui lòng kiểm tra lại thông tin.';
    case 'timeout':
      return 'Yêu cầu mất quá nhiều thời gian. Vui lòng thử lại.';
    case 'network':
      return 'Không thể kết nối đến máy chủ. Vui lòng kiểm tra kết nối và thử lại.';
    case 'unavailable':
    case 'http':
      return 'Không thể xử lý yêu cầu. Vui lòng thử lại sau.';
  }
}
