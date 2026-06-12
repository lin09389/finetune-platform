import { describe, expect, it } from 'vitest';

import { buildAgentSessionStreamUrl, getAgentStreamRetryDelay } from '../utils/agentSessionStream';

describe('agent session stream reconnect helpers', () => {
  it('uses exponential backoff with a cap', () => {
    expect(getAgentStreamRetryDelay(0)).toBe(1000);
    expect(getAgentStreamRetryDelay(1)).toBe(2000);
    expect(getAgentStreamRetryDelay(4)).toBe(15000);
    expect(getAgentStreamRetryDelay(20)).toBe(15000);
  });

  it('builds a resumable SSE URL with the last event id', () => {
    const url = buildAgentSessionStreamUrl('session 1/child', 'evt 1');

    expect(url).toContain('/agent-sessions/session%201%2Fchild/events/stream');
    expect(url).toContain('since_event_id=evt+1');
  });
});
