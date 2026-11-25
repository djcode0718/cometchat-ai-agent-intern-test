/**
 * Typed API client for Aster & Row support backend.
 * Provides AbortController signal support, typed models, and structured error reporting.
 */

export interface ChatResponse {
  session_id: string;
  turn_id: number;
  message: string;
  decision_state: string;
  citations: string[];
  handoff_recommended: boolean;
  handoff_reason?: string | null;
  supported_action?: string | null;
  is_fallback: boolean;
  fallback_reason?: string | null;
  safe_order?: Record<string, any> | null;
  proposal?: { id: string; status: string } | null;
}

export interface Proposal {
  id: string;
  order_id: string;
  session_id: string;
  action_type: 'CANCELLATION' | 'ADDRESS_CHANGE';
  status: 'PENDING_APPROVAL' | 'APPROVED' | 'REJECTED' | 'EXPIRED' | 'EXECUTED' | 'FAILED';
  version: number;
  created_at: string;
  expires_at: string;
  decided_by?: string | null;
  decided_at?: string | null;
  decision_reason?: string | null;
  evidence_snapshot: Record<string, any>;
  request_id?: string | null;
}

export interface AuditEvent {
  id: string;
  order_id: string;
  proposal_id?: string | null;
  action: string;
  from_state?: string | null;
  to_state: string;
  decided_by: string;
  reason?: string | null;
  request_id?: string | null;
  timestamp: string;
}

export class ApiError extends Error {
  status: number;
  requestId?: string;
  detail: string;

  constructor(status: number, detail: string, requestId?: string) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.requestId = requestId;
    this.detail = detail;
  }
}

const API_BASE = (import.meta as any).env?.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

async function handleResponse<T>(res: Response): Promise<T> {
  const requestId = res.headers.get('X-Request-ID') || undefined;
  if (!res.ok) {
    let detail = 'Unable to safely process the request.';
    try {
      const err = await res.json();
      if (err?.detail) {
        detail = err.detail;
      }
    } catch {
      // ignore json parse error
    }
    throw new ApiError(res.status, detail, requestId);
  }
  return res.json();
}

export async function sendMessage(
  sessionId: string,
  message: string,
  signal?: AbortSignal
): Promise<ChatResponse> {
  const payload: any = { message: message.trim() };
  if (sessionId) payload.session_id = sessionId;

  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  });
  return handleResponse<ChatResponse>(res);
}

export async function resetSession(sessionId: string, signal?: AbortSignal): Promise<{ status: string }> {
  if (!sessionId) return { status: 'reset' };
  const res = await fetch(`${API_BASE}/sessions/${encodeURIComponent(sessionId)}/reset`, {
    method: 'POST',
    signal,
  });
  return handleResponse<{ status: string }>(res);
}

export async function getSessionProposal(
  sessionId: string,
  signal?: AbortSignal
): Promise<Proposal | null> {
  if (!sessionId) return null;
  try {
    const res = await fetch(`${API_BASE}/sessions/${encodeURIComponent(sessionId)}/proposal`, {
      method: 'GET',
      signal,
    });
    if (res.status === 404) return null;
    return await handleResponse<Proposal>(res);
  } catch (err: any) {
    if (err.status === 404) return null;
    throw err;
  }
}

// ---------------------------------------------------------------------------
// Reviewer Endpoints (Requires X-Reviewer-Key kept in memory)
// ---------------------------------------------------------------------------

export async function listReviewerProposals(
  reviewerKey: string,
  statusFilter?: string,
  signal?: AbortSignal
): Promise<Proposal[]> {
  const url = new URL(`${API_BASE}/reviewer/proposals`);
  if (statusFilter && statusFilter !== 'ALL') {
    url.searchParams.set('status', statusFilter);
  }
  const res = await fetch(url.toString(), {
    method: 'GET',
    headers: {
      'X-Reviewer-Key': reviewerKey,
    },
    signal,
  });
  return handleResponse<Proposal[]>(res);
}

export async function getReviewerProposal(
  proposalId: string,
  reviewerKey: string,
  signal?: AbortSignal
): Promise<Proposal> {
  const res = await fetch(`${API_BASE}/reviewer/proposals/${encodeURIComponent(proposalId)}`, {
    method: 'GET',
    headers: { 'X-Reviewer-Key': reviewerKey },
    signal,
  });
  return handleResponse<Proposal>(res);
}

export async function approveProposal(
  proposalId: string,
  version: number,
  note: string | undefined,
  reviewerKey: string,
  signal?: AbortSignal
): Promise<Proposal> {
  const res = await fetch(`${API_BASE}/reviewer/proposals/${encodeURIComponent(proposalId)}/approve`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Reviewer-Key': reviewerKey,
    },
    body: JSON.stringify({ version, note: note || undefined }),
    signal,
  });
  return handleResponse<Proposal>(res);
}

export async function rejectProposal(
  proposalId: string,
  version: number,
  reason: string,
  reviewerKey: string,
  signal?: AbortSignal
): Promise<Proposal> {
  const res = await fetch(`${API_BASE}/reviewer/proposals/${encodeURIComponent(proposalId)}/reject`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Reviewer-Key': reviewerKey,
    },
    body: JSON.stringify({ version, reason }),
    signal,
  });
  return handleResponse<Proposal>(res);
}

export async function getReviewerAudit(
  reviewerKey: string,
  proposalId?: string,
  signal?: AbortSignal
): Promise<AuditEvent[]> {
  const url = new URL(`${API_BASE}/reviewer/audit`);
  if (proposalId) url.searchParams.set('proposal_id', proposalId);

  const res = await fetch(url.toString(), {
    method: 'GET',
    headers: { 'X-Reviewer-Key': reviewerKey },
    signal,
  });
  return handleResponse<AuditEvent[]>(res);
}
