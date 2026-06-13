import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useAgentAsyncTasks } from '../hooks/chat/useAgentAsyncTasks';
import type { UseAgentWorkspaceResult } from '../hooks/chat/useAgentWorkspace';
import type { AgentAsyncTask, AgentAsyncTaskMetrics, AgentWorkspace } from '../services/api';

function task(id: string, status: AgentAsyncTask['status']): AgentAsyncTask {
  return {
    task_id: id,
    parent_session_id: 'ags_parent',
    child_session_id: `ags_child_${id}`,
    previous_child_session_ids: [],
    agent_name: 'explore',
    status,
    input: { description: id },
    result: {},
    diagnostics: {},
    duration_ms: null,
    queue_wait_ms: null,
    health_status: status === 'failed' ? 'failed' : 'waiting',
    restart_count: 0,
    created_at: '2026-01-01T00:00:00',
    updated_at: '2026-01-01T00:00:00',
  };
}

function metrics(overrides: Partial<AgentAsyncTaskMetrics> = {}): AgentAsyncTaskMetrics {
  return {
    total: 2,
    by_status: { running: 1, completed: 1 },
    running: 1,
    failed: 0,
    cancelled: 0,
    completed: 1,
    attention: 0,
    recovery_count: 0,
    event_count: 0,
    last_event: null,
    ...overrides,
  };
}

function workspace(tasks: AgentAsyncTask[] = [task('agt_1', 'running'), task('agt_2', 'completed')]): AgentWorkspace {
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
      tasks,
      metrics: metrics({
        total: tasks.length,
        running: tasks.filter((item) => item.status === 'running').length,
        completed: tasks.filter((item) => item.status === 'completed').length,
        by_status: tasks.reduce<Record<string, number>>((acc, item) => {
          acc[item.status] = (acc[item.status] || 0) + 1;
          return acc;
        }, {}),
      }),
    },
    artifacts: [],
    changed_files: [],
    next_actions: [],
    recent_events: [],
  };
}

function workspaceResult(currentWorkspace: AgentWorkspace | null, overrides: Partial<UseAgentWorkspaceResult> = {}): UseAgentWorkspaceResult {
  return {
    workspace: currentWorkspace,
    loading: false,
    error: null,
    refresh: vi.fn(),
    startTask: vi.fn(),
    cancelTask: vi.fn(),
    restartTask: vi.fn(),
    runNextAction: vi.fn(),
    ...overrides,
  };
}

describe('useAgentAsyncTasks', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('derives task list and metrics from the workspace response', () => {
    const source = workspace();
    const { result } = renderHook(() => useAgentAsyncTasks(workspaceResult(source)));

    expect(result.current.tasks.map((item) => item.task_id)).toEqual(['agt_1', 'agt_2']);
    expect(result.current.metrics?.total).toBe(2);

    act(() => result.current.setStatusFilter('completed'));

    expect(result.current.tasks.map((item) => item.task_id)).toEqual(['agt_2']);
  });

  it('delegates start, cancel, restart, and refresh to the workspace controller', async () => {
    const refresh = vi.fn();
    const startTask = vi.fn();
    const cancelTask = vi.fn();
    const restartTask = vi.fn();
    const { result } = renderHook(() => useAgentAsyncTasks(workspaceResult(workspace(), {
      refresh,
      startTask,
      cancelTask,
      restartTask,
    })));

    await act(async () => {
      await result.current.startTask({ subagent_type: 'explore', description: 'inspect' });
      await result.current.cancelTask('agt_1', { reason: 'stop' });
      await result.current.restartTask('agt_1', { description: 'again' });
      await result.current.refresh();
    });

    expect(startTask).toHaveBeenCalledWith({ subagent_type: 'explore', description: 'inspect' });
    expect(cancelTask).toHaveBeenCalledWith('agt_1', { reason: 'stop' });
    expect(restartTask).toHaveBeenCalledWith('agt_1', { description: 'again' });
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it('polls the workspace while tasks are active and stops after terminal status', async () => {
    vi.useFakeTimers();
    const refresh = vi.fn();
    let current = workspace([task('agt_1', 'running')]);
    const { rerender } = renderHook(() => useAgentAsyncTasks(workspaceResult(current, { refresh }), { pollIntervalMs: 1000 }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(refresh).toHaveBeenCalledTimes(1);

    current = workspace([task('agt_1', 'completed')]);
    rerender();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it('keeps focus and expansion as local UI state', () => {
    const { result } = renderHook(() => useAgentAsyncTasks(workspaceResult(workspace())));

    act(() => result.current.focusTask('agt_1'));
    expect(result.current.focusedTaskId).toBe('agt_1');

    act(() => result.current.expandTask('agt_1'));
    expect(result.current.expandedTaskId).toBe('agt_1');
  });
});
