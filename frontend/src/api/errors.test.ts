import { describe, expect, test } from 'vitest';

import { ApiClientError, publicApiErrorMessage } from './errors';

describe('publicApiErrorMessage', () => {
  test('redacts a raw unavailable envelope message', () => {
    const error = new ApiClientError('unavailable', {
      request_id: 'request',
      error_code: 'INTERNAL_ERROR',
      message: 'provider-secret',
      retryable: false,
      timestamp: '2026-08-29T00:00:00Z',
    });

    const message = publicApiErrorMessage(error);

    expect(message).toBe('Không thể xử lý yêu cầu. Vui lòng thử lại sau.');
    expect(message).not.toContain('provider-secret');
  });

  test.each([
    ['validation', 'Yêu cầu chưa hợp lệ. Vui lòng kiểm tra lại thông tin.'],
    ['timeout', 'Yêu cầu mất quá nhiều thời gian. Vui lòng thử lại.'],
    ['network', 'Không thể kết nối đến máy chủ. Vui lòng kiểm tra kết nối và thử lại.'],
    ['http', 'Không thể xử lý yêu cầu. Vui lòng thử lại sau.'],
  ] as const)('uses a stable public message for %s errors', (kind, expected) => {
    expect(publicApiErrorMessage(new ApiClientError(kind))).toBe(expected);
  });

  test('uses the generic safe message for unknown errors', () => {
    expect(publicApiErrorMessage(new Error('provider-secret'))).toBe(
      'Không thể xử lý yêu cầu. Vui lòng thử lại sau.',
    );
  });
});
