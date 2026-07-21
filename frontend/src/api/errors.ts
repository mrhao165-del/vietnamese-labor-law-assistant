import type { ApiErrorEnvelope } from './types';
export class ApiClientError extends Error { constructor(public readonly kind: 'network' | 'timeout' | 'validation' | 'unavailable' | 'http', public readonly envelope?: ApiErrorEnvelope) { super(envelope?.message ?? kind); } }
