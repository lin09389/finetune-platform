import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import AgentWorkspaceContainer from '../components/chat/AgentWorkspaceContainer';
import type { UseAgentAsyncTasksResult } from '../hooks/chat/useAgentAsyncTasks';
import type { UseAgentWorkspaceResult } from '../hooks/chat/useAgentWorkspace';
import type { UseAgentWorkspaceSelectionResult } from '../hooks/chat/useAgentWorkspaceSelection';
import type { AgentAsyncTask, AgentAsyncTaskMetrics, AgentWorkspace } from '../services/api';

vi.mock('../components/chat/AgentInspector', () => ({
  default: ({ workspace }: { workspace: AgentWorkspace | null }) => (
    <div data-testid="inspector">{workspace?.session.id}</div>
  ),
}));

vi.mock('../components/chat/AgentAsyncTasksPanel', () => ({
  default: ({ tasks, metrics }: { tasks: AgentAsyncTask[]; metrics: AgentAsyncTaskMetrics | null }) => (
    <div data-testid="async-tasks">{tasks.length}:{metrics?.total ?? 0}</div>
  ),
}));

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
    status_text: {},
    timeline: [],
    pending_permission: null,
    task_plan: null,
    diagnostics: {},
    async_tasks: {
      tasks: [{
        task_id: 'agt_1',
        parent_session_id: 'ags_parent',
        child_session_id: 'ags_child',
        previous_child_session_ids: [],
        agent_name: 'explore',
        status: 'running',
        input: {},
        result: {},
        diagnostics: {},
        duration_ms: null,
        queue_wait_ms: null,
        health_status: 'waiting',
        restart_count: 0,
        created_at: '2026-01-01T00:00:00',
        updated_at: '2026-01-01T00:00:00',
      }],
      metrics: {
        total: 1,
        by_status: { running: 1 },
        running: 1,
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
    next_actions: [],
    recent_events: [],
  };
}

describe('AgentWorkspaceContainer', () => {
  it('passes one workspace-derived data source to inspector and async task panel', () => {
    const currentWorkspace = workspace();
    const agentWorkspace = {
      workspace: currentWorkspace,
      loading: false,
      error: null,
      refresh: vi.fn(),
      startTask: vi.fn(),
      cancelTask: vi.fn(),
      restartTask: vi.fn(),
      runNextAction: vi.fn(),
    } satisfies UseAgentWorkspaceResult;
    const asyncTasks = {
      tasks: currentWorkspace.async_tasks.tasks,
      metrics: currentWorkspace.async_tasks.metrics,
      loading: false,
      statusFilter: 'all',
      focusedTaskId: null,
      expandedTaskId: null,
      setStatusFilter: vi.fn(),
      focusTask: vi.fn(),
      expandTask: vi.fn(),
      refresh: agentWorkspace.refresh,
      startTask: agentWorkspace.startTask,
      cancelTask: agentWorkspace.cancelTask,
      restartTask: agentWorkspace.restartTask,
    } satisfies UseAgentAsyncTasksResult;
    const workspaceSelection = {
      selection: { type: 'run', sessionId: 'ags_parent' },
      selectRun: vi.fn(),
      selectTimelineItem: vi.fn(),
      selectAsyncTask: vi.fn(),
      selectPermission: vi.fn(),
      selectArtifact: vi.fn(),
      selectFile: vi.fn(),
      selectCommand: vi.fn(),
    } satisfies UseAgentWorkspaceSelectionResult;

    const props = {
      onActiveKeyChange: vi.fn(),
      changedFiles: 0,
      runContent: <div>run</div>,
      configContent: <div>config</div>,
      progressContent: <div>progress</div>,
      fileTreeContent: <div>files</div>,
      agentWorkspace,
      asyncTasks,
      workspaceSelection,
      sessionId: 'ags_parent',
      onSubmitPermission: vi.fn(),
      onOpenFile: vi.fn(),
      onRunNextAction: vi.fn(),
    };
    const { rerender } = render(<AgentWorkspaceContainer activeKey="inspector" {...props} />);

    expect(screen.getByTestId('inspector')).toHaveTextContent('ags_parent');
    rerender(<AgentWorkspaceContainer activeKey="async-tasks" {...props} />);
    expect(screen.getByTestId('async-tasks')).toHaveTextContent('1:1');
  });
});
