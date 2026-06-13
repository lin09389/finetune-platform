import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useAgentWorkspace } from '../hooks/chat/useAgentWorkspace';
import { useAgentWorkspaceSelection } from '../hooks/chat/useAgentWorkspaceSelection';
import type { AgentWorkspace } from '../services/api';

const apiMocks = vi.hoisted(() => ({
  getAgentWorkspace: vi.fn(),
  startAgentAsyncTask: vi.fn(),
  cancelAgentAsyncTask: vi.fn(),
  updateAgentAsyncTask: vi.fn(),
}));

vi.mock('../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/api')>();
  return {
    ...actual,
    ...apiMocks,
  };
});

function workspace(): AgentWorkspace {
  return {
    session: {
      id: 'ags_parent',
      agent_id: 'build',
      status: 'running',
      title: 'Build',
      metadata: {},
      parts: [],
      created_at: '2026-01-01T00:00:00',
      updated_at: '2026-01-01T00:00:00',
    },
    status_text: { current_phase: 'running' },
    timeline: [],
    pending_permission: null,
    diagnostics: {},
    async_tasks: {
      tasks: [],
      metrics: {
        total: 0,
        by_status: {},
        running: 0,
        failed: 0,
        cancelled: 0,
        completed: 0,
        attention: 0,
        recovery_count: 0,
        event_count: 0,
        last_event: null,
      },
    },
    artifacts: [],
    changed_files: [],
    next_actions: [
      {
        id: 'start_review:findings_1',
        action_type: 'start_review',
        title: '启动审查子任务',
        summary: '探索结果已经形成',
        priority: 'medium',
        source_artifact_id: 'findings_1',
        payload: { subagent_type: 'review', description: 'review findings' },
      },
    ],
    recent_events: [],
  };
}

describe('useAgentWorkspace', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.getAgentWorkspace.mockResolvedValue(workspace());
    apiMocks.startAgentAsyncTask.mockResolvedValue({});
    apiMocks.cancelAgentAsyncTask.mockResolvedValue({});
    apiMocks.updateAgentAsyncTask.mockResolvedValue({});
  });

  it('loads workspace and refreshes after async task operations', async () => {
    const { result } = renderHook(() => useAgentWorkspace('ags_parent'));

    await waitFor(() => expect(result.current.workspace?.session.id).toBe('ags_parent'));
    expect(apiMocks.getAgentWorkspace).toHaveBeenCalledWith('ags_parent');

    await act(async () => {
      await result.current.startTask({ subagent_type: 'explore', description: 'inspect' });
    });
    expect(apiMocks.startAgentAsyncTask).toHaveBeenCalledWith('ags_parent', {
      subagent_type: 'explore',
      description: 'inspect',
    });

    await act(async () => {
      await result.current.cancelTask('agt_1', { reason: 'stop' });
    });
    expect(apiMocks.cancelAgentAsyncTask).toHaveBeenCalledWith('ags_parent', 'agt_1', { reason: 'stop' });

    await act(async () => {
      await result.current.restartTask('agt_1', { description: 'again' });
    });
    expect(apiMocks.updateAgentAsyncTask).toHaveBeenCalledWith('ags_parent', 'agt_1', { description: 'again' });

    const nextAction = workspace().next_actions[0];
    expect(nextAction).toBeDefined();
    await act(async () => {
      await result.current.runNextAction(nextAction!);
    });
    expect(apiMocks.startAgentAsyncTask).toHaveBeenLastCalledWith('ags_parent', {
      subagent_type: 'review',
      description: 'review findings',
    });
    expect(apiMocks.getAgentWorkspace).toHaveBeenCalledTimes(5);
  });

  it('does not execute display-only next actions', async () => {
    const { result } = renderHook(() => useAgentWorkspace('ags_parent'));

    await waitFor(() => expect(result.current.workspace?.next_actions).toHaveLength(1));
    await act(async () => {
      await result.current.runNextAction({
        id: 'run_tests:file_changes',
        action_type: 'run_tests',
        title: '补充验证',
        summary: '只展示建议',
        priority: 'medium',
        payload: {},
      });
    });

    expect(apiMocks.startAgentAsyncTask).not.toHaveBeenCalled();
  });
});

describe('useAgentWorkspaceSelection', () => {
  it('defaults to the run and supports async task selection', async () => {
    const currentWorkspace = workspace();
    const { result, rerender } = renderHook(
      ({ value }) => useAgentWorkspaceSelection(value),
      { initialProps: { value: currentWorkspace } },
    );

    await waitFor(() => expect(result.current.selection).toEqual({ type: 'run', sessionId: 'ags_parent' }));

    act(() => {
      result.current.selectAsyncTask('agt_1', 'ags_child', { expandDetail: true });
    });
    expect(result.current.selection).toEqual({
      type: 'async_task',
      taskId: 'agt_1',
      childSessionId: 'ags_child',
      expandDetail: true,
    });

    rerender({ value: { ...currentWorkspace, session: { ...currentWorkspace.session, id: 'ags_next' } } });
    await waitFor(() => expect(result.current.selection).toEqual({ type: 'run', sessionId: 'ags_next' }));
  });
});
