import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';

import type { Message } from '../api/types';
import { MessageBubble } from './MessageBubble';

const directAssistantMessage: Message = {
  id: 'assistant-1',
  conversation_id: 'conversation-1',
  role: 'assistant',
  content: 'Người lao động có quyền được biết điều kiện lao động.',
  created_at: '2026-08-29T00:00:00Z',
  metadata: {
    route: 'RETRIEVAL_ONLY',
    citations: [
      {
        index: 1,
        chunk_id: 'chunk-1',
        article_number: 16,
        clause_number: 1,
        point_label: null,
        excerpt: 'Thông tin về công việc.',
        document_name: 'Bộ luật Lao động',
        source_file: 'labor-code.pdf',
      },
    ],
    verification: {
      status: 'SUPPORTED',
      warnings: [],
      checks: [{ label: 'Nguồn hợp lệ', passed: true }],
    },
  },
  feedback: null,
};

describe('MessageBubble', () => {
  test('preserves direct assistant answer, verification, citation callback, and backend mode', () => {
    const onViewCitation = vi.fn();

    render(
      <MessageBubble
        message={directAssistantMessage}
        onFeedback={vi.fn()}
        onViewCitation={onViewCitation}
      />,
    );

    expect(screen.getByText(directAssistantMessage.content)).toBeInTheDocument();
    expect(screen.getByText('Được nguồn hỗ trợ')).toBeInTheDocument();
    expect(screen.getByText('Tra cứu điều luật')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Xem căn cứ pháp lý' }));

    expect(onViewCitation).toHaveBeenCalledWith(directAssistantMessage);
  });
});
