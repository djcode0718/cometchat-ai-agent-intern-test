import React, { useState, useEffect, useRef } from 'react';
import {
  listReviewerProposals,
  getReviewerProposal,
  approveProposal,
  rejectProposal,
  getReviewerAudit,
  Proposal,
  AuditEvent,
  ApiError,
} from './api';

export function ReviewerConsole() {
  const [reviewerKey, setReviewerKey] = useState('');
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [keyInput, setKeyInput] = useState('');
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Active Proposal Modal State
  const [activeModalProposal, setActiveModalProposal] = useState<Proposal | null>(null);
  const [modalMode, setModalMode] = useState<'approve' | 'reject' | null>(null);
  const [noteOrReason, setNoteOrReason] = useState('');
  const [validationError, setValidationError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Focus trap refs
  const modalRef = useRef<HTMLDivElement>(null);
  const lastActiveElementRef = useRef<HTMLElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Fetch proposals when authenticated or filter changes
  useEffect(() => {
    if (!isAuthenticated || !reviewerKey) return;
    loadProposals();
    loadAudit();
  }, [isAuthenticated, reviewerKey, statusFilter]);

  const loadProposals = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listReviewerProposals(reviewerKey, statusFilter);
      setProposals(data);
    } catch (err: any) {
      handleApiError(err);
    } finally {
      setLoading(false);
    }
  };

  const loadAudit = async () => {
    try {
      const events = await getReviewerAudit(reviewerKey);
      setAuditEvents(events);
    } catch {
      // quiet audit load
    }
  };

  const handleApiError = (err: any) => {
    if (err instanceof ApiError) {
      if (err.status === 401) {
        setIsAuthenticated(false);
        setReviewerKey('');
        setError('Authentication failed: Invalid reviewer key. Please re-enter your key.');
      } else if (err.status === 409) {
        setError(
          `Conflict (409): This proposal was already decided by another reviewer. Ref: ${err.requestId || 'N/A'}`
        );
      } else {
        setError(`${err.detail} (Ref: ${err.requestId || 'N/A'})`);
      }
    } else {
      setError(err.message || 'An unexpected error occurred.');
    }
  };

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    if (!keyInput.trim()) return;
    setReviewerKey(keyInput.trim());
    setIsAuthenticated(true);
    setError(null);
  };

  const openModal = (proposal: Proposal, mode: 'approve' | 'reject') => {
    lastActiveElementRef.current = document.activeElement as HTMLElement;
    setActiveModalProposal(proposal);
    setModalMode(mode);
    setNoteOrReason('');
    setValidationError(null);
  };

  const closeModal = () => {
    setActiveModalProposal(null);
    setModalMode(null);
    setNoteOrReason('');
    setValidationError(null);
    // Restore focus
    setTimeout(() => {
      lastActiveElementRef.current?.focus();
    }, 0);
  };

  // Keyboard trap inside modal
  useEffect(() => {
    if (!activeModalProposal) return;
    inputRef.current?.focus();

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        closeModal();
        return;
      }
      if (e.key === 'Tab' && modalRef.current) {
        const focusables = modalRef.current.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        const first = focusables[0];
        const last = focusables[focusables.length - 1];

        if (e.shiftKey) {
          if (document.activeElement === first) {
            e.preventDefault();
            last.focus();
          }
        } else {
          if (document.activeElement === last) {
            e.preventDefault();
            first.focus();
          }
        }
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [activeModalProposal]);

  const handleModalSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeModalProposal || !modalMode) return;

    const trimmed = noteOrReason.trim();
    if (modalMode === 'reject') {
      if (!trimmed || trimmed.length < 10) {
        setValidationError('Rejection reason must be at least 10 characters.');
        return;
      }
      if (trimmed.length > 500) {
        setValidationError('Rejection reason cannot exceed 500 characters.');
        return;
      }
    }

    setIsSubmitting(true);
    setValidationError(null);

    try {
      if (modalMode === 'approve') {
        await approveProposal(
          activeModalProposal.id,
          activeModalProposal.version,
          noteOrReason.trim() || undefined,
          reviewerKey
        );
      } else {
        await rejectProposal(
          activeModalProposal.id,
          activeModalProposal.version,
          noteOrReason.trim(),
          reviewerKey
        );
      }
      closeModal();
      await loadProposals();
      await loadAudit();
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 409) {
        setValidationError(
          `Conflict (409): Proposal was already decided by another reviewer. Ref: ${err.requestId || 'N/A'}`
        );
      } else {
        setValidationError(err.detail || err.message);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isAuthenticated) {
    return (
      <section aria-labelledby="reviewer-auth-heading" style={{ maxWidth: '480px', margin: '4rem auto', padding: '2rem', background: '#ffffff', border: '1px solid var(--color-border)', borderRadius: '8px' }}>
        <h2 id="reviewer-auth-heading" style={{ fontSize: '1.25rem', marginBottom: '1rem' }}>
          Human Reviewer Sign-In
        </h2>
        <p style={{ color: 'var(--color-text-secondary)', marginBottom: '1.5rem', fontSize: '0.875rem' }}>
          Enter your reviewer authentication key. Keys are held in memory for this session and are never stored in localStorage.
        </p>

        {error && (
          <div role="alert" style={{ padding: '0.75rem', background: 'var(--color-error-bg)', color: 'var(--color-error)', borderRadius: '6px', marginBottom: '1rem', fontSize: '0.875rem' }}>
            {error}
          </div>
        )}

        <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div className="form-group">
            <label htmlFor="reviewer-key-input" className="form-label">
              Reviewer Key
            </label>
            <input
              id="reviewer-key-input"
              type="password"
              className="composer-input"
              value={keyInput}
              onChange={(e) => setKeyInput(e.target.value)}
              placeholder="e.g. secret_admin_key_123"
              required
            />
          </div>
          <button type="submit" className="btn-primary" style={{ width: '100%' }}>
            Access Reviewer Console
          </button>
        </form>
      </section>
    );
  }

  return (
    <section aria-labelledby="reviewer-console-heading" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.5rem', flex: 1 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h2 id="reviewer-console-heading" style={{ fontSize: '1.25rem', fontWeight: 700 }}>
            Reviewer Queue & Approvals
          </h2>
          <p style={{ color: 'var(--color-text-secondary)', fontSize: '0.875rem' }}>
            Inspect customer-safe evidence snapshots and authorize or reject pending actions.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          <label htmlFor="status-filter" style={{ fontWeight: 600, fontSize: '0.875rem' }}>
            Filter Status:
          </label>
          <select
            id="status-filter"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="composer-input"
            style={{ padding: '0.375rem 0.75rem', width: 'auto' }}
          >
            <option value="ALL">All Proposals</option>
            <option value="PENDING_APPROVAL">Pending Approval</option>
            <option value="APPROVED">Approved</option>
            <option value="EXECUTED">Executed</option>
            <option value="REJECTED">Rejected</option>
            <option value="FAILED">Failed</option>
            <option value="EXPIRED">Expired</option>
          </select>
          <button
            className="btn-secondary"
            onClick={() => {
              setIsAuthenticated(false);
              setReviewerKey('');
            }}
          >
            Log Out
          </button>
        </div>
      </div>

      {error && (
        <div role="alert" style={{ padding: '0.75rem 1rem', background: 'var(--color-error-bg)', color: 'var(--color-error)', borderRadius: '6px' }}>
          {error}
        </div>
      )}

      {/* Proposals Table */}
      <div className="table-container">
        <table className="data-table">
          <caption className="sr-only">Customer action proposals awaiting or processed by human review</caption>
          <thead>
            <tr>
              <th scope="col">ID</th>
              <th scope="col">Order ID</th>
              <th scope="col">Action</th>
              <th scope="col">Status</th>
              <th scope="col">Created</th>
              <th scope="col">Expires</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            {proposals.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ textAlign: 'center', padding: '2rem', color: 'var(--color-text-muted)' }}>
                  No proposals found matching the selected filter.
                </td>
              </tr>
            ) : (
              proposals.map((p) => (
                <tr key={p.id}>
                  <td><code>{p.id}</code></td>
                  <td><strong>{p.order_id}</strong></td>
                  <td>{p.action_type}</td>
                  <td>
                    <span className={`decision-badge ${p.status === 'EXECUTED' ? 'ANSWER' : p.status === 'PENDING_APPROVAL' ? 'CONFLICT' : 'ABSTAIN'}`}>
                      {p.status}
                    </span>
                  </td>
                  <td>{new Date(p.created_at).toLocaleTimeString()}</td>
                  <td>{new Date(p.expires_at).toLocaleTimeString()}</td>
                  <td>
                    {p.status === 'PENDING_APPROVAL' ? (
                      <div style={{ display: 'flex', gap: '0.375rem' }}>
                        <button
                          className="btn-primary"
                          style={{ padding: '0.25rem 0.625rem', fontSize: '0.8125rem' }}
                          onClick={() => openModal(p, 'approve')}
                          aria-label={`Approve proposal ${p.id} for order ${p.order_id}`}
                        >
                          Approve
                        </button>
                        <button
                          className="btn-danger"
                          style={{ padding: '0.25rem 0.625rem', fontSize: '0.8125rem' }}
                          onClick={() => openModal(p, 'reject')}
                          aria-label={`Reject proposal ${p.id} for order ${p.order_id}`}
                        >
                          Reject
                        </button>
                      </div>
                    ) : (
                      <span style={{ fontSize: '0.8125rem', color: 'var(--color-text-muted)' }}>
                        Decided by {p.decided_by || 'system'}
                      </span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Audit Timeline */}
      <section aria-labelledby="audit-heading" style={{ background: '#ffffff', padding: '1.25rem', border: '1px solid var(--color-border)', borderRadius: '6px' }}>
        <h3 id="audit-heading" style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.75rem' }}>
          Immutable Audit Timeline (Recent Activity)
        </h3>
        <ol style={{ paddingLeft: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.5rem', fontSize: '0.875rem' }}>
          {auditEvents.slice(0, 10).map((ev) => (
            <li key={ev.id}>
              <strong>{ev.action}</strong> on order <code>{ev.order_id}</code> by <em>{ev.decided_by}</em> &rarr;{' '}
              <span className="decision-badge ANSWER">{ev.to_state}</span> at{' '}
              <time dateTime={ev.timestamp}>{new Date(ev.timestamp).toLocaleString()}</time>
              {ev.reason && <span> &mdash; Note: &ldquo;{ev.reason}&rdquo;</span>}
            </li>
          ))}
        </ol>
      </section>

      {/* Modal Dialog for Approve / Reject */}
      {activeModalProposal && (
        <div className="modal-overlay" role="presentation">
          <div
            ref={modalRef}
            className="modal-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="modal-title"
            aria-describedby="modal-description"
          >
            <div className="modal-header">
              <h3 id="modal-title" style={{ fontSize: '1.125rem', fontWeight: 700 }}>
                {modalMode === 'approve' ? 'Authorize Action' : 'Reject Action'} &mdash;{' '}
                {activeModalProposal.order_id}
              </h3>
              <button
                className="btn-secondary"
                onClick={closeModal}
                aria-label="Close dialog without saving"
                style={{ padding: '0.25rem 0.5rem' }}
              >
                &times;
              </button>
            </div>

            <p id="modal-description" style={{ fontSize: '0.875rem', color: 'var(--color-text-secondary)' }}>
              {modalMode === 'approve'
                ? `You are authorizing the ${activeModalProposal.action_type.toLowerCase()} request. Order eligibility will be atomically verified.`
                : `Please supply a mandatory rejection reason (10 to 500 characters) for auditing and customer notification.`}
            </p>

            {/* Customer-safe evidence snapshot */}
            <div style={{ background: 'var(--color-surface)', padding: '0.75rem', borderRadius: '4px', fontSize: '0.8125rem' }}>
              <strong>Evidence Snapshot:</strong>
              <pre style={{ margin: '0.25rem 0 0', overflowX: 'auto' }}>
                {JSON.stringify(activeModalProposal.evidence_snapshot, null, 2)}
              </pre>
            </div>

            <form onSubmit={handleModalSubmit} noValidate>
              <div className="form-group">
                <label htmlFor="modal-reason-input" className="form-label">
                  {modalMode === 'approve' ? 'Approval Note (Optional)' : 'Rejection Reason (Required)'}
                </label>
                <textarea
                  id="modal-reason-input"
                  ref={inputRef}
                  className="composer-input"
                  rows={3}
                  value={noteOrReason}
                  onChange={(e) => setNoteOrReason(e.target.value)}
                  placeholder={
                    modalMode === 'approve'
                      ? 'e.g. Verified with customer, cancellation within 24h window.'
                      : 'e.g. Order already packaged in warehouse and handed to shipping carrier.'
                  }
                  aria-describedby={validationError ? 'modal-form-error' : undefined}
                  required={modalMode === 'reject'}
                />
                {validationError && (
                  <div id="modal-form-error" className="form-error" role="alert">
                    {validationError}
                  </div>
                )}
              </div>

              <div className="modal-actions">
                <button type="button" className="btn-secondary" onClick={closeModal} disabled={isSubmitting}>
                  Cancel
                </button>
                <button
                  type="submit"
                  className={modalMode === 'approve' ? 'btn-primary' : 'btn-danger'}
                  disabled={isSubmitting}
                >
                  {isSubmitting ? 'Processing...' : modalMode === 'approve' ? 'Confirm Approval' : 'Confirm Rejection'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </section>
  );
}
