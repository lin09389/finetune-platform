import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useAgentSessionStream } from '../pages/chatNew/useAgentSessionStream';
import type { AgentPart, AgentSessionEvent } from '../services/api';

vi.mock('../services/api', async () => {
  const actual = await vi.importActual<typeof import('../services/api')>('../services/api');
  return {
    ...actual,
    getAgentSession: vi.fn(),
  };
});

class MockEventSource {
  static instances: MockEventSource[] = [];

  listeners = new Map<string, Array<(event: MessageEvent) => void>>();
  onerror: (() => void) | null = null;

  constructor(public url: string) {
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: (event: MessageEvent) => void) {
    const listeners = this.listeners.get(type) || [];
    listeners.push(listener);
    this.listeners.set(type, listeners);
  }

  emit(type: string, data: unknown) {
    for (const listener of this.listeners.get(type) || []) {
      listener({ data: JSON.stringify(data) } as MessageEvent);
    }
  }

  close() {}
}

describe('useAgentSessionStream', () => {
  beforeEach(() => {
    MockEventSource.instances = [];
    vi.stubGlobal('EventSource', MockEventSource as unknown as typeof EventSource);
  });

  it.each(['tool_call_failed', 'loop_guard_triggered'])(
    'clears the active tool phase and refreshes the workspace for %s',
    async (eventType) => {
      const refresh = vi.fn().mockResolvedValue(undefined);
      const setAgentPhase = vi.fn();
      const upsertAgentSessionPartMessage = vi.fn().mockResolvedValue(undefined);
      const part: AgentPart = {
        id: 'agp_error',
        session_id: 'ags_1',
        type: 'error',
        status: 'failed',
        title: '连续失败阻断',
        content: 'stopped',
        payload: { guard: 'loop_guard' },
        created_at: '2026-01-01T00:00:00',
      };
      const { result } = renderHook(() => useAgentSessionStream({
        enabled: true,
        getAgentWorkspaceRefresh: () => refresh,
        setAgentPhase,
        buildAgentPartMetadata: vi.fn(),
        mergeAgentSessionPart: vi.fn(),
        ensureAgentSessionSnapshot: vi.fn(),
        upsertAgentSessionMessage: vi.fn().mockResolvedValue(undefined),
        upsertAgentSessionPartMessage,
        appendAgentSessionError: vi.fn().mockResolvedValue(undefined),
      }));

      act(() => result.current.startStream('ags_1'));
      const source = MockEventSource.instances[0];
      expect(source).toBeDefined();
      const chunk: AgentSessionEvent = {
        id: 'event_1',
        session_id: 'ags_1',
        event_type: eventType,
        chunk_type: 'error',
        message: 'stopped',
        payload: { part },
        created_at: '2026-01-01T00:00:01',
        session_status: 'needs_manual_review',
        part,
      };

      await act(async () => {
        source!.emit('agent_session_event', chunk);
        await Promise.resolve();
      });

      await waitFor(() => {
        expect(setAgentPhase).toHaveBeenCalledWith({ phase: '', visible: false });
        expect(refresh).toHaveBeenCalled();
        expect(upsertAgentSessionPartMessage).toHaveBeenCalled();
      });
    },
  );
});
