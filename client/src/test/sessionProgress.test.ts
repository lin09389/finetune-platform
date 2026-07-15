import { describe, expect, it } from 'vitest';
import { applyEventToSession } from '../agent/protocol/agentProtocol';
import type { AgentSession, AgentSessionEvent } from '../services/api';
import {
  gateGapLabel,
  selectSessionProgress,
  selectToolMetrics,
} from '../agent/selectors/sessionProgress';

describe('sessionProgress selectors', () => {
  it('projects tool_metrics into view model and chips', () => {
    const progress = selectSessionProgress({
      tool_metrics: {
        tools_total: 12,
        tools_failed: 2,
        observe_total: 5,
        verify_attempted: 1,
        verify_ok: 0,
        trajectory_blocks: 1,
        hitl_count: 3,
        budget_soft_warned: true,
        budget_hard_blocked: false,
        last_tool: 'execute',
      },
    });
    expect(progress.hasSignal).toBe(true);
    expect(progress.metrics).toMatchObject({
      toolsTotal: 12,
      toolsFailed: 2,
      verifyAttempted: true,
      verifyOk: false,
      budgetSoftWarned: true,
    });
    expect(progress.chips.some((chip) => chip.key === 'verify' && chip.label === '验证失败')).toBe(true);
    expect(progress.chips.some((chip) => chip.key === 'budget' && chip.tone === 'warn')).toBe(true);
  });

  it('surfaces completion_gate gaps and recovery latch', () => {
    const progress = selectSessionProgress({
      completion_gate: {
        completed_ok: false,
        has_writes: true,
        diff_visible: true,
        verify_attempted: 1,
        verify_ok: 0,
        gaps: ['verification_required'],
        written_paths: ['app.py'],
        summary: '验证未通过',
        status: 'completed',
      },
      recovery_state: {
        require_observation_before_retry: true,
        last_failed_execute: { command: 'python cli.py -1' },
        blind_retry_blocks: 1,
      },
    });
    expect(progress.gate?.completedOk).toBe(false);
    expect(progress.gate?.gaps).toEqual(['verification_required']);
    expect(progress.recovery?.requireObservationBeforeRetry).toBe(true);
    expect(progress.chips.some((chip) => chip.key === 'gate' && chip.label === '完成缺口')).toBe(true);
    expect(progress.chips.some((chip) => chip.key === 'recovery' && chip.label === '先观察')).toBe(true);
    expect(gateGapLabel('verification_required')).toBe('验证未通过');
  });

  it('returns empty signal when metadata has no progress keys', () => {
    expect(selectSessionProgress({}).hasSignal).toBe(false);
    expect(selectToolMetrics({})).toBeNull();
  });

  it('merges session_progress from SSE events into session metadata', () => {
    const session = {
      id: 'ags_1',
      agent_id: 'build',
      status: 'running',
      title: 't',
      project_path: '/tmp/ws',
      provider: 'deepseek',
      model: 'x',
      created_at: '2026-07-15T00:00:00Z',
      updated_at: '2026-07-15T00:00:00Z',
      parts: [],
      preferences: {},
      metadata: { state: { current_phase: 'running' } },
    } as unknown as AgentSession;
    const event = {
      id: 'age_1',
      session_id: 'ags_1',
      event_type: 'tool_call_completed',
      message: 'ok',
      created_at: '2026-07-15T00:00:01Z',
      payload: {
        session_progress: {
          tool_metrics: {
            tools_total: 4,
            tools_failed: 0,
            verify_attempted: 1,
            verify_ok: 1,
          },
          recovery_state: { require_observation_before_retry: false },
        },
      },
    } as unknown as AgentSessionEvent;

    const next = applyEventToSession(session, event);
    expect(next?.metadata?.tool_metrics).toMatchObject({ tools_total: 4, verify_ok: 1 });
    expect(next?.metadata?.recovery_state).toMatchObject({
      require_observation_before_retry: false,
    });
    expect(next?.metadata?.state?.current_phase).toBe('running');
  });
});
