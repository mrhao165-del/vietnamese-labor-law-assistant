import type { VerificationStatus } from './types';

export const verificationLabel: Record<VerificationStatus, string> = {
  SUPPORTED: 'Được nguồn hỗ trợ',
  PARTIALLY_SUPPORTED: 'Được hỗ trợ một phần',
  UNSUPPORTED: 'Không được nguồn hỗ trợ',
  INSUFFICIENT_CONTEXT: 'Chưa đủ căn cứ',
  OUT_OF_SCOPE: 'Ngoài phạm vi',
};
