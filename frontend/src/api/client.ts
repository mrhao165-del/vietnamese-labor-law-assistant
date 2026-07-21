import { ApiClientError } from './errors';
import type { ApiErrorEnvelope, ChatResponse, Conversation, FeedbackValue, Message, Readiness } from './types';

const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');
const timeoutMs = 100_000;

async function request<T>(path: string, init: RequestInit = {}, signal?: AbortSignal): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  const abort = () => controller.abort(); signal?.addEventListener('abort', abort, { once: true });
  try {
    const response = await fetch(`${baseUrl}${path}`, { ...init, signal: controller.signal, headers: { 'Content-Type': 'application/json', ...init.headers } });
    if (!response.ok) {
      const envelope = await response.json().catch(() => undefined) as ApiErrorEnvelope | undefined;
      throw new ApiClientError(response.status === 422 ? 'validation' : response.status >= 500 ? 'unavailable' : 'http', envelope);
    }
    return response.status === 204 ? undefined as T : response.json() as Promise<T>;
  } catch (error) {
    if (error instanceof ApiClientError) throw error;
    if (controller.signal.aborted && !signal?.aborted) throw new ApiClientError('timeout');
    throw new ApiClientError('network');
  } finally { window.clearTimeout(timer); signal?.removeEventListener('abort', abort); }
}

export const api = {
  health: (signal?: AbortSignal) => request<{ status: string }>('/health', {}, signal),
  readiness: (signal?: AbortSignal) => request<Readiness>('/ready', {}, signal),
  conversations: (signal?: AbortSignal) => request<Conversation[]>('/api/v1/conversations', {}, signal),
  createConversation: (title: string) => request<Conversation>('/api/v1/conversations', { method: 'POST', body: JSON.stringify({ title }) }),
  messages: (id: string, signal?: AbortSignal) => request<Message[]>(`/api/v1/conversations/${encodeURIComponent(id)}/messages`, {}, signal),
  deleteConversation: (id: string) => request<void>(`/api/v1/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  chat: (question: string, conversationId?: string, signal?: AbortSignal) => request<ChatResponse>('/api/v1/chat', { method: 'POST', body: JSON.stringify({ question, conversation_id: conversationId }) }, signal),
  feedback: (messageId: string, value: FeedbackValue) => request<void>(`/api/v1/messages/${encodeURIComponent(messageId)}/feedback`, { method: 'PUT', body: JSON.stringify({ value }) }),
};
