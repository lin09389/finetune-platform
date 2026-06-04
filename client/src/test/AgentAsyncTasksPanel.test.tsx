import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AgentAsyncTasksPanel from '../components/chat/AgentAsyncTasksPanel';
import type { AgentAsyncTask, AgentAsyncTaskMetrics } from '../services/api';

const apiMocks = vi.hoisted(() => ({
  listAgentAsyncTasks: vi.fn(),
  getAgentAsyncTaskMetrics: vi.fn(),
  listAgentAsyncTaskEvents: vi.fn(),
  getAgentSession: vi.fn(),
  decideAgentPermission: vi.fn(),
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

const tasks: AgentAsyncTask[] = [
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
];

const metrics: AgentAsyncTaskMetrics = {
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
};

function renderPanel(overrides: Partial<React.ComponentProps<typeof AgentAsyncTasksPanel>> = {}) {
  const props = {
    sessionId: 'ags_parent',
    tasks,
    metrics,
    loading: false,
    statusFilter: 'all',
    focusedTaskId: null,
    onStatusFilterChange: vi.fn(),
    onRefresh: vi.fn().mockResolvedValue(undefined),
    onStartTask: vi.fn().mockResolvedValue(undefined),
    onCancelTask: vi.fn().mockResolvedValue(undefined),
    onRestartTask: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
  render(<AgentAsyncTasksPanel {...props} />);
  return props;
}

describe('AgentAsyncTasksPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
    apiMocks.getAgentSession.mockResolvedValue({
      id: 'ags_child',
      chat_session_id: null,
      agent_id: 'explore',
      status: 'waiting_permission',
      title: 'Explore',
      metadata: {
        ui_state: {
          timeline: [],
          pending_permission: {
            part_id: 'part_permission',
            status: 'waiting_permission',
            title: '等待确认',
            content: '需要确认命令',
            actions: [
              {
                index: 0,
                name: 'command',
                args: { command: 'npm run typecheck' },
                allowed_decisions: ['approve', 'reject'],
              },
            ],
          },
        },
      },
      parts: [],
      events: [],
      created_at: '2026-01-01T00:00:00',
      updated_at: '2026-01-01T00:00:00',
    });
    apiMocks.decideAgentPermission.mockResolvedValue({
      session: {
        id: 'ags_child',
        chat_session_id: null,
        agent_id: 'explore',
        status: 'running',
        title: 'Explore',
        metadata: { ui_state: { timeline: [], pending_permission: null } },
        parts: [],
        events: [],
        created_at: '2026-01-01T00:00:00',
        updated_at: '2026-01-01T00:00:00',
      },
    });
  });

  it('renders controlled async task data without loading list or metrics itself', async () => {
    renderPanel();

    expect(await screen.findByText('inspect code')).toBeInTheDocument();
    expect(screen.getByText('review code')).toBeInTheDocument();
    expect(screen.getByText('运行中')).toBeInTheDocument();
    expect(screen.getByText('完成')).toBeInTheDocument();
    expect(screen.getByText('事件 started')).toBeInTheDocument();
    expect(screen.getByText('健康')).toBeInTheDocument();
    expect(apiMocks.listAgentAsyncTasks).not.toHaveBeenCalled();
    expect(apiMocks.getAgentAsyncTaskMetrics).not.toHaveBeenCalled();
  });

  it('delegates refresh, start, cancel, and filter changes to props', async () => {
    const props = renderPanel();

    fireEvent.click(await screen.findByLabelText('刷新异步子任务'));
    expect(props.onRefresh).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByText('新建子任务'));
    fireEvent.change(screen.getByPlaceholderText('输入子任务目标'), { target: { value: 'new task' } });
    fireEvent.click(screen.getByText('创建'));
    await waitFor(() => expect(props.onStartTask).toHaveBeenCalledWith({
      subagent_type: 'explore',
      description: 'new task',
    }));

    fireEvent.click(screen.getByText('取消'));
    await waitFor(() => expect(props.onCancelTask).toHaveBeenCalledWith('agt_1', {
      reason: '用户在任务面板取消。',
    }));
  });

  it('shows child session HITL approval controls and refreshes shared data after decisions', async () => {
    const props = renderPanel();

    await screen.findByText('inspect code');
    const detailButtons = screen.getAllByText('展开详情');
    expect(detailButtons[0]).toBeDefined();
    fireEvent.click(detailButtons[0]!);

    expect(await screen.findByText('确认 1 个 Agent 动作')).toBeInTheDocument();
    fireEvent.click(screen.getByText('提交决策'));

    await waitFor(() => expect(apiMocks.decideAgentPermission).toHaveBeenCalledWith('part_permission', [
      { type: 'approve' },
    ]));
    await waitFor(() => expect(props.onRefresh).toHaveBeenCalled());
  });

  it('highlights a focused async task from the workspace timeline', async () => {
    renderPanel({ focusedTaskId: 'agt_2' });

    const focused = await screen.findByText('review code');

    expect(focused.closest('[data-focused="true"]')).toBeInTheDocument();
    expect(await screen.findByText('子会话 ags_child_2')).toBeInTheDocument();
  });

  it('treats expandedTaskId null as a controlled collapsed state', async () => {
    const onExpandedTaskChange = vi.fn();
    renderPanel({ expandedTaskId: null, onExpandedTaskChange });

    fireEvent.click((await screen.findAllByText('展开详情'))[0]!);

    expect(onExpandedTaskChange).toHaveBeenCalledWith('agt_1');
    expect(screen.queryByText('子会话 ags_child')).not.toBeInTheDocument();
  });
});
