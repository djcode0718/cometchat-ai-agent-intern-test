/**
 * API client for Aster & Row AI Support backend.
 * Provides HTTP communication without embedding business logic.
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export async function sendMessage(sessionId, message) {
  const payload = {
    message: message.trim(),
  };
  if (sessionId) {
    payload.session_id = sessionId;
  }

  const response = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    let errorDetail = 'Unable to safely process the request.';
    try {
      const errData = await response.json();
      if (errData && errData.detail) {
        errorDetail = errData.detail;
      }
    } catch {
      // Use generic error string
    }
    throw new Error(errorDetail);
  }

  return response.json();
}

export async function resetSession(sessionId) {
  if (!sessionId) return { status: 'reset' };

  const response = await fetch(`${API_BASE}/sessions/${encodeURIComponent(sessionId)}/reset`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error('Failed to reset session.');
  }

  return response.json();
}

export async function getTrace(sessionId) {
  if (!sessionId) return null;

  const response = await fetch(`${API_BASE}/sessions/${encodeURIComponent(sessionId)}/trace`, {
    method: 'GET',
  });

  if (!response.ok) {
    throw new Error('Failed to fetch trace.');
  }

  return response.json();
}
