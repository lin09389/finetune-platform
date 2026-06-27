import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AgentAttentionRail from '../agent/components/AgentAttentionRail';
import AgentEnvironmentRail from '../agent/components/AgentEnvironmentRail';
import AgentRunTimeline, { CommandCard, DiffCard, TimelineContent } from '../agent/components/AgentRunTimeline';
import AgentSessionRail from '../agent/components/AgentSessionRail';
import AgentTaskComposer from '../agent/components/AgentTaskComposer';
import { initialAgentRuntimeState } from '../agent/runtime/agentRuntime';
import type { RecentAgentSession } from '../agent/runtime/agentRuntime';
import { createFlowScenario } from '../agent/testing/agentFlowScenarios';
import type { AgentSessionUiTimelineItem } from '../services/api';

const recentSessions: RecentAgentSession[] = [
  {
    id: 'ses_done',
    title: 'Completed review',
    displayTitle: 'Completed review',
    status: 'completed' as const,
    agentId: 'review',
    projectPath: 'C:/projects/review',
    updatedAt: '2026-06-20T10:00:00Z',
    preferences: {
      display_title: null,
      pinned: false,
      archived: false,
      updated_at: null,
    },
  },
  {
    id: 'ses_run',
    title: 'Build dashboard',
    displayTitle: 'Build dashboard',
    status: 'running' as const,
    agentId: 'build',
    projectPath: 'C:/projects/dashboard',
    updatedAt: '2026-06-20T11:00:00Z',
    preferences: {
      display_title: null,
      pinned: false,
      archived: false,
      updated_at: null,
    },
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

  it('uses server-owned session preferences when provided', async () => {
    const onUpdatePreferences = vi.fn().mockResolvedValue({});
    render(
      <AgentSessionRail
        sessions={[{
          ...recentSessions[1]!,
          displayTitle: 'Server alias',
          preferences: {
            display_title: 'Server alias',
            pinned: true,
            archived: false,
            updated_at: '2026-06-20T12:00:00Z',
          },
        }]}
        activeSessionId="ses_run"
        onSelect={vi.fn()}
        onNew={vi.fn()}
        onUpdatePreferences={onUpdatePreferences}
      />,
    );

    expect(screen.getByText('Server alias')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '取消置顶 Build dashboard' }));
    expect(onUpdatePreferences).toHaveBeenCalledWith('ses_run', { pinned: false });

    fireEvent.click(screen.getByRole('button', { name: '会话操作 Server alias' }));
    fireEvent.click(await screen.findByRole('menuitem', { name: /归档/ }));
    await waitFor(() => expect(onUpdatePreferences).toHaveBeenCalledWith('ses_run', { archived: true }));
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

  it('shows actionable empty states while a task is submitting or has failed', () => {
    const { rerender } = render(
      <AgentRunTimeline
        timeline={[]}
        pendingLabel="正在提交任务"
        errorMessage={null}
      />,
    );

    expect(screen.getByText('正在提交任务')).toBeInTheDocument();
    expect(screen.getByText(/草稿会自动恢复/)).toBeInTheDocument();

    rerender(
      <AgentRunTimeline
        timeline={[]}
        errorMessage="Network Error"
      />,
    );

    expect(screen.getByText('任务没有成功提交')).toBeInTheDocument();
    expect(screen.getByText(/Network Error/)).toBeInTheDocument();
    expect(screen.getByText(/下方输入框已恢复你的内容/)).toBeInTheDocument();
  });

  it('collapses and expands long timeline output', () => {
    render(<TimelineContent content={Array.from({ length: 20 }, (_, index) => `Line ${index}`).join('\n')} />);
    const expand = screen.getByRole('button', { name: /展开/ });
    expect(expand).toBeInTheDocument();
    fireEvent.click(expand);
    expect(screen.getByRole('button', { name: /收起/ })).toBeInTheDocument();
  });

  it('renders command and diff events as compact expandable execution blocks', () => {
    const timeline: AgentSessionUiTimelineItem[] = [
      {
        id: 'command_1',
        type: 'command',
        status: 'completed',
        payload: {
          command: ['npm', 'run', 'typecheck'],
          stdout: 'TypeScript check passed',
          exit_code: 0,
          duration_ms: 1340,
        },
      },
      {
        id: 'diff_1',
        type: 'diff',
        status: 'completed',
        payload: {
          changed_files: ['src/App.tsx', 'src/App.css'],
          additions: 18,
          deletions: 4,
        },
      },
    ];

    render(
      <>
        <CommandCard item={timeline[0]!} />
        <DiffCard item={timeline[1]!} />
      </>,
    );

    const commandToggle = screen.getByRole('button', { name: '收起 Shell 命令 npm run typecheck' });
    expect(commandToggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('TypeScript check passed')).toBeInTheDocument();
    expect(screen.getByText('进程已退出，代码 0')).toBeInTheDocument();
    expect(screen.getByText('1.3 秒')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '收起 2 个文件变更' })).toBeInTheDocument();
    expect(screen.getByText('+18')).toBeInTheDocument();
    expect(screen.getByText('-4')).toBeInTheDocument();

    fireEvent.click(commandToggle);
    expect(commandToggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('TypeScript check passed')).not.toBeInTheDocument();
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

  it('explains that a failed submission restored the draft', async () => {
    render(
      <AgentTaskComposer
        agents={[]}
        session={null}
        busy={false}
        onSubmit={vi.fn().mockRejectedValue(new Error('offline'))}
        onInterrupt={vi.fn()}
      />,
    );
    const input = screen.getByLabelText('任务目标');
    fireEvent.change(input, { target: { value: 'Please fix the UX' } });
    fireEvent.click(screen.getByRole('button', { name: '提交任务' }));

    await waitFor(() => expect(input).toHaveValue('Please fix the UX'));
    expect(screen.getByText('提交失败，内容已恢复，可再次发送')).toBeInTheDocument();
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

  it('surfaces session diagnostics in the attention center', () => {
    render(
      <AgentAttentionRail
        state={{
          ...initialAgentRuntimeState,
          activeSessionId: 'ses_run',
          diagnostics: {
            ...initialAgentRuntimeState.diagnostics,
            sessionId: 'ses_run',
            unknownEvents: 2,
            parseFailures: 1,
            reconnects: 3,
            recoveryRequested: 2,
            recoverySucceeded: 1,
            recoveryFailed: 1,
            events: [{
              id: 'diag_1',
              sessionId: 'ses_run',
              type: 'parse_failure',
              detail: 'bad payload',
              occurredAt: '2026-06-20T12:00:00Z',
            }],
          },
        }}
        workspace={null}
        onClearError={vi.fn()}
        onRefresh={vi.fn()}
        onDecidePermission={vi.fn()}
        onRecoverNode={vi.fn()}
        onRestartSubagent={vi.fn()}
      />,
    );

    expect(screen.getByLabelText('Agent 运行诊断')).toHaveTextContent('需关注');
    expect(screen.getByText('未知事件')).toBeInTheDocument();
    expect(screen.getByText('解析失败')).toBeInTheDocument();
    expect(screen.getByText('重连')).toBeInTheDocument();
    expect(screen.getByText('50%')).toBeInTheDocument();
    expect(screen.getByText('bad payload')).toBeInTheDocument();
  });

  it('renders the right-side environment rail from the active workspace', () => {
    const { workspace } = createFlowScenario('files_diff_editor');
    render(
      <AgentEnvironmentRail
        state={{
          ...initialAgentRuntimeState,
          activeSessionId: workspace.session.id,
          session: {
            ...workspace.session,
            provider: 'ollama',
            model: 'qwen2.5-coder',
            metadata: { git: { branch: 'feature/agent-ui' } },
          },
          workspace: {
            ...workspace,
            session: {
              ...workspace.session,
              provider: 'ollama',
              model: 'qwen2.5-coder',
              metadata: { git: { branch: 'feature/agent-ui' } },
            },
          },
        }}
        connection="open"
        connectionLabel="实时连接"
        onOpenSettings={vi.fn()}
      />,
    );

    expect(screen.getByRole('complementary', { name: '环境信息' })).toHaveTextContent('feature/agent-ui');
    expect(screen.getByText(/qwen2\.5-coder/)).toBeInTheDocument();
    expect(screen.getByText('project')).toBeInTheDocument();
  });
});
