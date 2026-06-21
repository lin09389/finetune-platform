import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AgentAttentionRail from '../agent/components/AgentAttentionRail';
import AgentRunTimeline, { TimelineContent } from '../agent/components/AgentRunTimeline';
import AgentSessionRail from '../agent/components/AgentSessionRail';
import AgentTaskComposer from '../agent/components/AgentTaskComposer';
import { initialAgentRuntimeState } from '../agent/runtime/agentRuntime';
import { createFlowScenario } from '../agent/testing/agentFlowScenarios';
import type { AgentSessionUiTimelineItem } from '../services/api';

const recentSessions = [
  {
    id: 'ses_done',
    title: 'Completed review',
    status: 'completed' as const,
    agentId: 'review',
    projectPath: 'C:/projects/review',
    updatedAt: '2026-06-20T10:00:00Z',
  },
  {
    id: 'ses_run',
    title: 'Build dashboard',
    status: 'running' as const,
    agentId: 'build',
    projectPath: 'C:/projects/dashboard',
    updatedAt: '2026-06-20T11:00:00Z',
  },
];

describe('Agent product polish', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  it('searches, filters, and pins recent sessions', async () => {
    render(
      <AgentSessionRail
        sessions={recentSessions}
        activeSessionId={null}
        onNew={vi.fn()}
        onSelect={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText('搜索 Agent 会话'), { target: { value: 'review' } });
    expect(screen.getByText('Completed review')).toBeInTheDocument();
    expect(screen.queryByText('Build dashboard')).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('搜索 Agent 会话'), { target: { value: '' } });
    fireEvent.click(screen.getByText('进行中'));
    expect(screen.getByText('Build dashboard')).toBeInTheDocument();
    expect(screen.queryByText('Completed review')).not.toBeInTheDocument();

    fireEvent.click(screen.getByText('全部'));
    fireEvent.click(screen.getByRole('button', { name: '置顶 Completed review' }));
    await waitFor(() => expect(
      screen.getByRole('button', { name: '取消置顶 Completed review' }),
    ).toHaveAttribute('aria-pressed', 'true'));

    fireEvent.click(screen.getByRole('button', { name: '会话操作 Completed review' }));
    fireEvent.click(await screen.findByRole('menuitem', { name: /归档/ }));
    await waitFor(() => expect(screen.queryByText('Completed review')).not.toBeInTheDocument());
    fireEvent.click(screen.getByTitle('归档'));
    expect(await screen.findByText('Completed review')).toBeInTheDocument();
  });

  it('renames a session without changing the server-owned session record', async () => {
    render(
      <AgentSessionRail
        sessions={recentSessions}
        activeSessionId="ses_run"
        onSelect={vi.fn()}
        onNew={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: '会话操作 Build dashboard' }));
    fireEvent.click(await screen.findByRole('menuitem', { name: /重命名/ }));
    const input = await screen.findByDisplayValue('Build dashboard');
    fireEvent.change(input, { target: { value: 'Dashboard polish' } });
    fireEvent.click(screen.getByRole('button', { name: /保\s*存/ }));
    expect(await screen.findByText('Dashboard polish')).toBeInTheDocument();
    expect(recentSessions[1]?.title).toBe('Build dashboard');
  });

  it('filters a virtualized timeline without losing the total count', () => {
    const timeline: AgentSessionUiTimelineItem[] = [
      {
        id: 'text_1',
        type: 'text',
        status: 'completed',
        title: 'Agent output',
        content: 'Implementation complete',
        created_at: '2026-06-20T10:00:00Z',
      },
      {
        id: 'tool_1',
        type: 'tool_call',
        status: 'completed',
        title: 'read_file',
        content: 'Read package.json',
        created_at: '2026-06-20T10:00:01Z',
      },
      {
        id: 'error_1',
        type: 'error',
        status: 'failed',
        title: 'Build failed',
        content: 'TypeScript error',
        created_at: '2026-06-20T10:00:02Z',
      },
    ];
    render(<div style={{ height: 600 }}><AgentRunTimeline timeline={timeline} /></div>);

    fireEvent.click(screen.getByText('异常'));
    expect(screen.getByText('1/3')).toBeInTheDocument();

    fireEvent.click(screen.getByText('全部'));
    fireEvent.change(screen.getByLabelText('搜索执行时间线'), { target: { value: 'package' } });
    expect(screen.getByText('1/3')).toBeInTheDocument();
  });

  it('collapses and expands long timeline output', () => {
    render(<TimelineContent content={Array.from({ length: 20 }, (_, index) => `Line ${index}`).join('\n')} />);
    const expand = screen.getByRole('button', { name: /展开/ });
    expect(expand).toBeInTheDocument();
    fireEvent.click(expand);
    expect(screen.getByRole('button', { name: /收起/ })).toBeInTheDocument();
  });

  it('restores a draft per session and focuses the composer with Ctrl+K', () => {
    sessionStorage.setItem('finetune.agent.draft.v1:new', 'Recovered draft');
    render(
      <AgentTaskComposer
        agents={[]}
        session={null}
        busy={false}
        onSubmit={vi.fn()}
        onInterrupt={vi.fn()}
      />,
    );
    const input = screen.getByLabelText('任务目标');
    expect(input).toHaveValue('Recovered draft');
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true });
    expect(input).toHaveFocus();
  });

  it('approves multiple independent attention permissions in one confirmed action', async () => {
    const { workspace } = createFlowScenario('permission');
    const now = new Date().toISOString();
    workspace.session.updated_at = now;
    const childTask = createFlowScenario('subagent').workspace.async_tasks.tasks[0]!;
    workspace.async_tasks.tasks = [{
      ...childTask,
      status: 'running',
      input: { description: 'Review changes' },
      error: undefined,
      health_status: 'waiting',
      has_pending_permission: true,
      pending_permission_part_id: 'part_child',
      updated_at: now,
    }];
    const onDecidePermission = vi.fn().mockResolvedValue(undefined);
    render(
      <AgentAttentionRail
        state={{ ...initialAgentRuntimeState, workspace, session: workspace.session, activeSessionId: workspace.session.id }}
        workspace={workspace}
        onClearError={vi.fn()}
        onRefresh={vi.fn()}
        onDecidePermission={onDecidePermission}
        onRecoverNode={vi.fn()}
        onRestartSubagent={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '全部批准' }));
    fireEvent.click(await screen.findByText('全部批准', { selector: '.ant-popconfirm-buttons button span' }));
    await waitFor(() => expect(onDecidePermission).toHaveBeenCalledTimes(2));
    expect(screen.getByRole('region', { name: '最近处理' })).toBeInTheDocument();
    expect(screen.getAllByText(/批准/).length).toBeGreaterThan(1);
  });
});
