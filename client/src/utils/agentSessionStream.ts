import { API_BASE_URL } from '../services/api';

const AGENT_STREAM_RETRY_BASE_MS = 1000;
const AGENT_STREAM_RETRY_MAX_MS = 15000;

export function getAgentStreamRetryDelay(attempt: number): number {
  const normalizedAttempt = Math.max(0, attempt);
  return Math.min(AGENT_STREAM_RETRY_MAX_MS, AGENT_STREAM_RETRY_BASE_MS * (2 ** normalizedAttempt));
}

export function buildAgentSessionStreamUrl(sessionId: string, lastEventId = ''): string {
  const params = new URLSearchParams();
  if (lastEventId) params.set('since_event_id', lastEventId);
  const qs = params.toString();
  return `${API_BASE_URL}/agent-sessions/${encodeURIComponent(sessionId)}/events/stream${qs ? `?${qs}` : ''}`;
}
