import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import { sendMessage, resetSession } from './api';
import './styles.css';

const EXAMPLE_PROMPTS = [
  'What is your return policy?',
  'Where is order ORD-1007?',
  'Do you ship to Canada?',
  'Can I cancel my order?',
];

export default function App() {
  const [sessionId, setSessionId] = useState('');
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [lastFailedMessage, setLastFailedMessage] = useState(null);

  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);

  // Auto-scroll to newest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const handleSend = async (textToSend) => {
    const query = (textToSend || input).trim();
    if (!query || loading) return;

    setError(null);
    setLastFailedMessage(null);

    const userMessage = {
      id: Date.now(),
      role: 'user',
      text: query,
    };

    setMessages((prev) => [...prev, userMessage]);
    if (!textToSend) setInput('');
    setLoading(true);

    try {
      const data = await sendMessage(sessionId, query);
      
      // Update session ID if newly assigned
      if (data.session_id) {
        setSessionId(data.session_id);
      }

      const assistantMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        text: data.message,
        decision_state: data.decision_state,
        citations: data.citations || [],
        handoff_recommended: data.handoff_recommended,
        handoff_reason: data.handoff_reason,
        supported_action: data.supported_action,
        is_fallback: data.is_fallback,
        fallback_reason: data.fallback_reason,
        safe_order: data.safe_order,
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err) {
      setError(err.message || 'Something went wrong. Please try again.');
      setLastFailedMessage(query);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleReset = async () => {
    if (loading) return;
    try {
      if (sessionId) {
        await resetSession(sessionId);
      }
    } catch {
      // Best effort backend reset
    } finally {
      setSessionId('');
      setMessages([]);
      setError(null);
      setLastFailedMessage(null);
      setInput('');
      if (textareaRef.current) {
        textareaRef.current.focus();
      }
    }
  };

  const handleRetry = () => {
    if (lastFailedMessage) {
      handleSend(lastFailedMessage);
    }
  };

  return (
    <div className="app-container">
      {/* Header */}
      <header className="app-header">
        <div className="brand-section">
          <div className="brand-logo-badge">AR</div>
          <div className="brand-info">
            <h1>
              Aster & Row AI Support
              <span className="status-indicator">
                <span className="status-dot"></span> Online
              </span>
            </h1>
          </div>
        </div>

        <div className="header-actions">
          <button
            className="btn-secondary"
            onClick={handleReset}
            disabled={loading}
            title="Start fresh conversation"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
              <path d="M3 3v5h5" />
            </svg>
            New conversation
          </button>
        </div>
      </header>

      {/* Chat messages viewport */}
      <main className="chat-area">
        {messages.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">🌿</div>
            <h2>How can we help?</h2>
            <p>Ask about orders, delivery timelines, return policies, or product care guidelines.</p>

            <div className="suggestions-grid">
              {EXAMPLE_PROMPTS.map((prompt, idx) => (
                <button
                  key={idx}
                  className="suggestion-card"
                  onClick={() => handleSend(prompt)}
                  disabled={loading}
                >
                  <span>{prompt}</span>
                  <span className="suggestion-arrow">→</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((msg) => (
            <div key={msg.id} className={`message-row ${msg.role}`}>
              <div className="message-bubble">
                {msg.role === 'assistant' && (
                  <div className="message-meta">
                    {msg.decision_state && (
                      <span className={`decision-badge ${msg.decision_state}`}>
                        {msg.decision_state === 'CONFLICT'
                          ? 'Conflicting official info'
                          : msg.decision_state === 'HANDOFF'
                          ? 'Human support recommended'
                          : msg.decision_state === 'ABSTAIN'
                          ? 'Insufficient information'
                          : msg.decision_state === 'CLARIFY'
                          ? 'Clarification needed'
                          : 'Policy verified'}
                      </span>
                    )}
                    {msg.is_fallback && (
                      <span className="fallback-pill">Safe fallback response</span>
                    )}
                  </div>
                )}

                {msg.role === 'assistant' ? (
                  <div className="message-text assistant-markdown">
                    <ReactMarkdown
                      components={{
                        a: ({ node, ...props }) => (
                          <a {...props} target="_blank" rel="noopener noreferrer" />
                        ),
                      }}
                    >
                      {msg.text}
                    </ReactMarkdown>
                  </div>
                ) : (
                  <div className="message-text">{msg.text}</div>
                )}

                {/* Safe Order Details Card */}
                {msg.safe_order && (
                  <div className="order-card">
                    <div className="order-card-header">
                      <span className="order-id-title">Order {msg.safe_order.order_id}</span>
                      <span className={`order-status-badge ${msg.safe_order.status}`}>
                        {msg.safe_order.status}
                      </span>
                    </div>
                    <div className="order-details-grid">
                      {msg.safe_order.carrier && (
                        <div className="order-field">
                          <span className="field-label">Carrier</span>
                          <span className="field-value">{msg.safe_order.carrier}</span>
                        </div>
                      )}
                      {msg.safe_order.tracking_number && (
                        <div className="order-field">
                          <span className="field-label">Tracking Number</span>
                          <span className="field-value">{msg.safe_order.tracking_number}</span>
                        </div>
                      )}
                      <div className="order-field">
                        <span className="field-label">Estimated Delivery</span>
                        <span className="field-value">
                          {msg.safe_order.estimated_delivery || 'Unavailable'}
                        </span>
                      </div>
                      <div className="order-field">
                        <span className="field-label">Cancellation Status</span>
                        <span className="field-value">
                          {msg.safe_order.is_cancellable ? 'Eligible for cancellation' : 'Ineligible for cancellation'}
                        </span>
                      </div>
                    </div>
                  </div>
                )}

                {/* Approved Citations */}
                {msg.citations && msg.citations.length > 0 && (
                  <div className="citations-section">
                    <div className="citations-title">Sources</div>
                    <div className="citations-list">
                      {msg.citations.map((cit, idx) => (
                        <span key={idx} className="citation-chip" title={cit}>
                          {cit}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Handoff Notice Banner */}
                {msg.handoff_recommended && msg.handoff_reason && (
                  <div className="callout-banner handoff">
                    <div className="callout-header">
                      <span>👤</span> Human support recommended
                    </div>
                    <div>{msg.handoff_reason}</div>
                  </div>
                )}

                {/* Conflict Notice Banner */}
                {msg.decision_state === 'CONFLICT' && (
                  <div className="callout-banner conflict">
                    <div className="callout-header">
                      <span>⚠️</span> Conflicting official information
                    </div>
                    <div>
                      The available official documents provide different guidance. Human support may be needed to confirm the correct handling.
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))
        )}

        {/* Loading Indicator */}
        {loading && (
          <div className="message-row assistant">
            <div className="typing-indicator">
              <div className="typing-dot"></div>
              <div className="typing-dot"></div>
              <div className="typing-dot"></div>
            </div>
          </div>
        )}

        {/* Error Notification */}
        {error && (
          <div className="error-banner">
            <span>{error}</span>
            <button className="error-retry-btn" onClick={handleRetry}>
              Retry
            </button>
          </div>
        )}

        <div ref={messagesEndRef} />
      </main>

      {/* Composer Area */}
      <footer className="composer-area">
        <form
          className="composer-form"
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
        >
          <textarea
            ref={textareaRef}
            className="composer-input"
            rows="1"
            placeholder="Type your message here..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading}
          />
          <button
            type="submit"
            className="btn-send"
            disabled={loading || !input.trim()}
          >
            Send
          </button>
        </form>
        <div className="composer-footer">
          Aster & Row AI Assistant · Grounded in official store policies
        </div>
      </footer>
    </div>
  );
}
