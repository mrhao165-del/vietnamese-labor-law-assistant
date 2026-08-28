import { render, screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';

import { ModeBadge } from './ModeBadge';

describe('ModeBadge', () => {
  test('labels backend direct QA routes as statutory lookup', () => {
    render(<ModeBadge route="RETRIEVAL_ONLY" />);

    expect(screen.getByText('Tra cứu điều luật')).toBeInTheDocument();
  });

  test('labels only the backend Case Analysis route as situation analysis', () => {
    render(<ModeBadge route="CASE_ANALYSIS" />);

    expect(screen.getByText('Phân tích tình huống')).toBeInTheDocument();
  });

  test('does not guess a mode when route is absent', () => {
    const { container } = render(<ModeBadge />);

    expect(container).toBeEmptyDOMElement();
  });
});
