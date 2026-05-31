import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AgentAsyncTasksPanel from '../components/chat/AgentAsyncTasksPanel';

const apiMocks = vi.hoisted(() => ({
  listAgentAsyncTasks: vi.fn(),
  getAgentAsyncTaskMetrics: vi.fn(),
  listAgentAsyncTaskEvents: vi.fn(),
  startAgentAsyncTask: vi.fn(),
  cancelAgentAsyncTask: vi.fn(),
  updateAgentAsyncTask: vi.fn(),
  getAgentSession: vi.fn(),
}));

vi.mock('../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/api')>();
  return {
    ...actual,
    ...apiMocks,
  };
});

vi.mock('../utils/notify', () => ({
  notify: {
    error: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
}));

describe('AgentAsyncTasksPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.listAgentAsyncTasks.mockResolvedValue({
      status_filter: 'all',
      tasks: [
        {
          task_id: 'agt_1',
          parent_session_id: 'ags_parent',
          child_session_id: 'ags_child',
          previous_child_session_ids: [],
          agent_name: 'explore',
          status: 'running',
          input: { description: 'inspect code' },
          result: {},
          diagnostics: { last_event_type: 'started', warnings: [] },
          duration_ms: 1200,
          queue_wait_ms: 100,
          health_status: 'waiting',
          restart_count: 0,
          created_at: '2026-01-01T00:00:00',
          updated_at: '2026-01-01T00:00:00',
        },
        {
          task_id: 'agt_2',
          parent_session_id: 'ags_parent',
          child_session_id: 'ags_child_2',
          previous_child_session_ids: [],
          agent_name: 'review',
          status: 'completed',
          input: { description: 'review code' },
          result: { summary: 'done' },
          diagnostics: { last_event_type: 'completed', warnings: [] },
          duration_ms: 2400,
          queue_wait_ms: 50,
          health_status: 'ok',
          restart_count: 0,
          created_at: '2026-01-01T00:00:00',
          updated_at: '2026-01-01T00:00:00',
        },
      ],
    });
    apiMocks.getAgentAsyncTaskMetrics.mockResolvedValue({
      total: 2,
      by_status: { running: 1, completed: 1 },
      running: 1,
      failed: 0,
      cancelled: 0,
      completed: 1,
      attention: 0,
      recovery_count: 0,
      event_count: 2,
      last_event: null,
    });
    apiMocks.listAgentAsyncTaskEvents.mockResolvedValue([
      {
        id: 'aste_1',
        task_id: 'agt_1',
        parent_session_id: 'ags_parent',
        child_session_id: 'ags_child',
        event_type: 'started',
        status: 'running',
        message: 'started',
        payload: {},
        created_at: '2026-01-01T00:00:00',
      },
    ]);
  });

  it('renders async task statuses and available actions', async () => {
    render(<AgentAsyncTasksPanel sessionId="ags_parent" />);

    expect(await screen.findByText('inspect code')).toBeInTheDocument();
    expect(screen.getByText('review code')).toBeInTheDocument();
    expect(screen.getByText('运行中')).toBeInTheDocument();
    expect(screen.getByText('完成')).toBeInTheDocument();
    expect(screen.getByText('事件 started')).toBeInTheDocument();
    expect(screen.getByText('健康')).toBeInTheDocument();
    expect(screen.getByText('取消')).toBeInTheDocument();
    expect(screen.getAllByText('重启').length).toBeGreaterThan(0);
  });

  it('starts and cancels tasks through the API client', async () => {
    apiMocks.startAgentAsyncTask.mockResolvedValue({});
    apiMocks.cancelAgentAsyncTask.mockResolvedValue({});
    render(<AgentAsyncTasksPanel sessionId="ags_parent" />);

    const input = await screen.findByPlaceholderText('输入子任务目标');
    fireEvent.change(input, { target: { value: 'new task' } });
    fireEvent.click(screen.getByText('创建'));

    await waitFor(() => expect(apiMocks.startAgentAsyncTask).toHaveBeenCalledWith('ags_parent', {
      subagent_type: 'explore',
      description: 'new task',
    }));

    fireEvent.click(screen.getByText('取消'));
    await waitFor(() => expect(apiMocks.cancelAgentAsyncTask).toHaveBeenCalledWith('ags_parent', 'agt_1', {
      reason: '用户在任务面板取消。',
    }));
  });
});
