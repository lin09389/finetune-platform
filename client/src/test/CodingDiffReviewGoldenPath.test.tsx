import { describe, expect, it } from 'vitest';
import { agentRuntimeReducer, initialAgentRuntimeState } from '../agent/runtime/agentRuntime';
import { selectTimeline } from '../agent/selectors/workbenchSelectors';
import { codingDiffReviewScenario } from '../agent/testing/codingDiffReviewScenarios';

describe('Coding Diff Review persisted golden path', () => {
  it('converges live part events and the refreshed persisted session onto the same review projection', () => {
    const scenario = codingDiffReviewScenario('live-to-refresh');
    let live = agentRuntimeReducer(initialAgentRuntimeState, {
      type: 'session_loaded',
      session: { ...scenario.session, status: 'running', parts: [] },
    });
    for (const event of scenario.events) {
      live = agentRuntimeReducer(live, { type: 'stream_event', event });
    }
    const refreshed = agentRuntimeReducer(initialAgentRuntimeState, { type: 'workspace_loaded', workspace: scenario.workspace });

    const projection = (state: typeof live) => selectTimeline(state)
      .filter((item) => item.type === 'diff')
      .map((item) => ({ id: item.id, status: item.status, payload: item.payload, content: item.content }));

    expect(projection(live)).toEqual(projection(refreshed));
    expect(projection(refreshed)).toEqual([
      expect.objectContaining({ id: 'diff-001', payload: expect.objectContaining({ path: 'server/app.py', write_sequence: 2, review_status: 'ready' }) }),
      expect.objectContaining({ id: 'diff-002', payload: expect.objectContaining({ path: 'server/app.py', write_sequence: 5, review_status: 'ready' }) }),
    ]);
  });

  it('keeps repeated writes chronologically reviewable and verification newer than the last diff', () => {
    const scenario = codingDiffReviewScenario('chronological-history');
    const state = agentRuntimeReducer(initialAgentRuntimeState, { type: 'workspace_loaded', workspace: scenario.workspace });
    const timeline = selectTimeline(state);
    const diffs = timeline.filter((item) => item.type === 'diff');
    const verification = timeline.find((item) => item.id === 'command-001');

    expect(diffs.map((item) => item.payload?.write_sequence)).toEqual([2, 5]);
    expect(diffs.map((item) => item.payload?.path)).toEqual(['server/app.py', 'server/app.py']);
    expect(verification?.payload?.verification_for_write_sequence).toBe(5);
    expect(verification?.created_at).toBeTruthy();
    expect(diffs[1]?.created_at).toBeTruthy();
    expect(String(verification?.created_at) > String(diffs[1]?.created_at)).toBe(true);
  });

  it('retains a future diff payload as generic persisted timeline data rather than mutating it client-side', () => {
    const scenario = codingDiffReviewScenario('unknown-contract');
    const state = agentRuntimeReducer(initialAgentRuntimeState, { type: 'workspace_loaded', workspace: scenario.workspace });
    const diff = selectTimeline(state).find((item) => item.id === 'diff-unknown');

    expect(diff?.type).toBe('diff');
    expect(diff?.payload?.contract_version).toBe(2);
    expect(diff?.payload?.path).toBe('server/app.py');
  });
});
