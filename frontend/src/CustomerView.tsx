import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import { sendMessage, resetSession, getSessionProposal, ChatResponse, Proposal, ApiError } from './api';

export function CustomerView() {
  const [sessionId, setSessionId] = useState('');
  const [messages, setMessages] = useState<any[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeProposal, setActiveProposal] = useState<Proposal | null>(null);
  const [liveAnnouncement, setLiveAnnouncement] = useState('');

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const pollIntervalRef = useRef<any>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  // Poll for proposal status changes if activeProposal is in PENDING_APPROVAL
  useEffect(() => {
    if (!sessionId) return;

    const checkProposal = async () => {
      try {
        const prop = await getSessionProposal(sessionId);
        if (prop) {
          if (activeProposal && activeProposal.status !== prop.status) {
            setLiveAnnouncement(`Proposal update: Request is now ${prop.status.replace('_', ' ')}.`);
          }
          setActiveProposal(prop);
        }
      } catch {
        // quiet poll
      }
    };

    checkProposal();
    pollIntervalRef.current = setInterval(checkProposal, 5000);
    return () => clearInterval(pollIntervalRef.current);
  }, [sessionId, activeProposal?.status]);

  const handleSend = async (queryText?: string) => {
    const query = (queryText || input).trim();
    if (!query || loading) return;

    setError(null);
    const userMsg = { id: `u_${Date.now()}`, role: 'user', text: query };
    setMessages((prev) => [...prev, userMsg]);
    if (!queryText) setInput('');
    setLoading(true);
    setLiveAnnouncement(`Sending message: ${query}`);

    try {
      const data: ChatResponse = await sendMessage(sessionId, query);
      if (data.session_id) setSessionId(data.session_id);

      const assistantMsg = {
        id: `a_${Date.now()}`,
        role: 'assistant',
        text: data.message,
        decision_state: data.decision_state,
        citations: data.citations || [],
        handoff_recommended: data.handoff_recommended,
        handoff_reason: data.handoff_reason,
        supported_action: data.supported_action,
        is_fallback: data.is_fallback,
        safe_order: data.safe_order,
      };

      setMessages((prev) => [...prev, assistantMsg]);
      setLiveAnnouncement(`Response received: ${data.message.slice(0, 100)}...`);

      if (data.proposal) {
        setLiveAnnouncement(
          `Action submitted for human review. Reference ID ${data.proposal.id}.`
        );
        // Immediately fetch the proposal details for the card
        const prop = await getSessionProposal(data.session_id);
        if (prop) setActiveProposal(prop);
      }
    } catch (err: any) {
      const detail = err instanceof ApiError ? `${err.detail} (Ref: ${err.requestId || 'N/A'})` : err.message;
      setError(detail);
      setLiveAnnouncement(`Error: ${detail}`);
    } finally {
      setLoading(false);
    }
  };

  const handleReset = async () => {
    if (loading) return;
    try {
      if (sessionId) await resetSession(sessionId);
    } catch {
      // quiet reset
    }
    setSessionId('');
    setMessages([]);
    setError(null);
    setActiveProposal(null);
    setInput('');
    setLiveAnnouncement('Conversation cleared. Starting new session.');
    textareaRef.current?.focus();
  };

  return (
    <section aria-labelledby="customer-view-heading" style={{ display: 'flex', flexDirection: 'column', flex: 1 }}>
      {/* Polite live region for accessibility announcements */}
      <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">
        {liveAnnouncement}
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.75rem 1.5rem', background: '#ffffff', borderBottom: '1px solid var(--color-border)' }}>
        <h2 id="customer-view-heading" style={{ fontSize: '1.125rem', fontWeight: 600 }}>
          Customer Support Assistant
        </h2>
        <button
          className="btn-secondary"
          onClick={handleReset}
          disabled={loading}
          aria-label="Start a new conversation and reset session"
        >
          Reset Session
        </button>
      </div>

      {/* Main transcript container */}
      <div
        id="main-content"
        className="chat-transcript"
        role="log"
        aria-live="polite"
        aria-label="Chat messages history"
      >
        {messages.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '3rem 1rem' }}>
            <p style={{ fontSize: '1.125rem', fontWeight: 600, color: 'var(--color-text-secondary)' }}>
              How can we assist you with Aster & Row products and orders today?
            </p>
            <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'center', marginTop: '1.25rem', flexWrap: 'wrap' }}>
              {['What is your return policy?', 'Can I cancel order ORD-1001?', 'Where is my order?'].map((q) => (
                <button
                  key={q}
                  className="btn-secondary"
                  onClick={() => handleSend(q)}
                  disabled={loading}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m) => (
            <div key={m.id} className={`message-bubble ${m.role}`}>
              {m.role === 'assistant' && (
                <div>
                  {m.decision_state && (
                    <span className={`decision-badge ${m.decision_state}`} role="status">
                      <span aria-hidden="true">
                        {m.decision_state === 'ANSWER' ? '✓' : m.decision_state === 'CONFLICT' ? '⚠️' : 'ℹ️'}
                      </span>
                      <span>
                        {m.decision_state === 'ANSWER'
                          ? 'Policy Verified'
                          : m.decision_state === 'CONFLICT'
                          ? 'Conflicting Policy Detected'
                          : m.decision_state === 'HANDOFF'
                          ? 'Human Support Recommended'
                          : m.decision_state}
                      </span>
                    </span>
                  )}
                </div>
              )}

              <div style={{ marginTop: '0.25rem' }}>
                <ReactMarkdown
                  components={{
                    a: ({ node, children, ...props }) => (
                      <a {...props} target="_blank" rel="noopener noreferrer">
                        {children || 'External Link'}
                      </a>
                    ),
                  }}
                >
                  {m.text}
                </ReactMarkdown>
              </div>

              {/* Citations as structured list items */}
              {m.citations && m.citations.length > 0 && (
                <div style={{ marginTop: '0.75rem', fontSize: '0.875rem' }}>
                  <p style={{ fontWeight: 600, color: 'var(--color-text-muted)' }}>Sources:</p>
                  <ul style={{ paddingLeft: '1.25rem', margin: '0.25rem 0' }}>
                    {m.citations.map((c: string, idx: number) => (
                      <li key={idx}>
                        <code>{c}</code>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ))
        )}

        {/* Real-time Human Approval Status Card */}
        {activeProposal && (
          <div
            className={`proposal-card ${activeProposal.status}`}
            role="region"
            aria-labelledby="proposal-card-title"
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 id="proposal-card-title" style={{ fontSize: '1rem', fontWeight: 600 }}>
                Human Review Status
              </h3>
              <span
                style={{
                  fontWeight: 700,
                  fontSize: '0.875rem',
                  padding: '0.2rem 0.5rem',
                  borderRadius: '4px',
                  background: '#ffffff',
                }}
              >
                {activeProposal.status.replace('_', ' ')}
              </span>
            </div>
            <p style={{ fontSize: '0.875rem' }}>
              Your {activeProposal.action_type.toLowerCase()} request for order{' '}
              <strong>{activeProposal.order_id}</strong> is under review (Ref: <code>{activeProposal.id}</code>).
            </p>
            {activeProposal.decision_reason && (
              <p style={{ fontSize: '0.8125rem', color: 'var(--color-text-muted)' }}>
                Reason: {activeProposal.decision_reason}
              </p>
            )}
          </div>
        )}

        {/* Loading skeleton */}
        {loading && (
          <div
            className="message-bubble assistant"
            role="status"
            aria-live="polite"
            aria-label="Assistant is analyzing policies and order state"
          >
            <div className="skeleton-box" style={{ width: '60%' }} />
            <div className="skeleton-box" style={{ width: '85%' }} />
            <span className="sr-only">Loading response...</span>
          </div>
        )}

        {error && (
          <div
            role="alert"
            style={{
              padding: '0.75rem 1rem',
              background: 'var(--color-error-bg)',
              color: 'var(--color-error)',
              borderRadius: '6px',
              border: '1px solid var(--color-error)',
            }}
          >
            {error}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Composer footer */}
      <footer className="composer-area">
        <form
          className="composer-form"
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
        >
          <label htmlFor="customer-chat-input" className="sr-only">
            Type your customer support question
          </label>
          <textarea
            id="customer-chat-input"
            ref={textareaRef}
            className="composer-input"
            rows={1}
            placeholder="Ask about orders, returns, warranty, or cancellations..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            disabled={loading}
          />
          <button
            type="submit"
            className="btn-primary"
            disabled={loading || !input.trim()}
            aria-label="Send message"
          >
            Send
          </button>
        </form>
      </footer>
    </section>
  );
}
