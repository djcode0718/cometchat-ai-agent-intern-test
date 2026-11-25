import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CustomerView } from '../src/CustomerView';
import { ReviewerConsole } from '../src/ReviewerConsole';
import * as api from '../src/api';
import { vi, describe, it, expect, beforeEach } from 'vitest';

vi.mock('../src/api');

describe('CustomerView Accessibility & Roles', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders chat input with accessible label and transcript role="log"', () => {
    render(<CustomerView />);
    
    // Labelled chat input
    const input = screen.getByLabelText(/type your customer support question/i);
    expect(input).toBeInTheDocument();

    // Transcript landmark role="log"
    const transcript = screen.getByRole('log', { name: /chat messages history/i });
    expect(transcript).toBeInTheDocument();
    expect(transcript).toHaveAttribute('aria-live', 'polite');
  });

  it('announces submitted messages and renders decision badges with text and icon', async () => {
    (api.sendMessage as any).mockResolvedValueOnce({
      session_id: 'sess_1',
      turn_id: 1,
      message: 'Here is our return policy [10-returns.md > Policy].',
      decision_state: 'ANSWER',
      citations: ['10-returns.md > Policy'],
      handoff_recommended: false,
      is_fallback: false,
    });

    render(<CustomerView />);
    const input = screen.getByLabelText(/type your customer support question/i);
    await userEvent.type(input, 'What is returns?{enter}');

    await waitFor(() => {
      expect(screen.getByText(/policy verified/i)).toBeInTheDocument();
    });

    // Check decision badge contains icon and text
    const badge = screen.getByText(/policy verified/i).closest('.decision-badge');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent('✓');
    expect(badge).toHaveTextContent(/policy verified/i);
  });
});

describe('ReviewerConsole Modal & Focus Trap', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('enforces inline rejection reason error with role="alert" and aria-describedby', async () => {
    (api.listReviewerProposals as any).mockResolvedValueOnce([
      {
        id: 'prop_test_1',
        order_id: 'ORD-1001',
        session_id: 'sess_test',
        action_type: 'CANCELLATION',
        status: 'PENDING_APPROVAL',
        version: 1,
        created_at: new Date().toISOString(),
        expires_at: new Date().toISOString(),
        evidence_snapshot: { is_cancellable: true },
      },
    ]);
    (api.getReviewerAudit as any).mockResolvedValueOnce([]);

    render(<ReviewerConsole />);

    // Authenticate
    const keyInput = screen.getByLabelText(/reviewer key/i);
    await userEvent.type(keyInput, 'secret_admin_key_123{enter}');

    // Open reject modal
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /reject proposal prop_test_1/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /reject proposal prop_test_1/i }));

    // Verify modal dialog opened
    const dialog = screen.getByRole('dialog');
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveAttribute('aria-modal', 'true');

    // Attempt submitting without reason
    const submitBtn = screen.getByRole('button', { name: /confirm rejection/i });
    fireEvent.click(submitBtn);

    // Verify inline error tied by aria-describedby and role="alert"
    await waitFor(() => {
      const errorMsg = screen.getByRole('alert');
      expect(errorMsg).toHaveTextContent(/at least 10 characters/i);
      const reasonInput = screen.getByLabelText(/rejection reason/i);
      expect(reasonInput).toHaveAttribute('aria-describedby', errorMsg.id);
    });
  });
});
