import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import AgentInspector from '../components/chat/AgentInspector';
import type { AgentWorkspace } from '../services/api';

vi.mock('../components/chat/AgentChildSessionDrawer', () => ({
  AgentChildSessionDetail: ({ childSessionId }: { childSessionId?: string }) => (
    <div data-testid="child-detail">{childSessionId}</div>
  ),
}));

function workspace(): AgentWorkspace {
  return {
    session: {
      id: 'ags_parent',
      agent_id: 'build',
      status: 'running',
      title: 'Build task',
      metadata: {},
      parts: [
        {
          id: 'part_command',
          session_id: 'ags_parent',
          type: 'command',
          status: 'completed',
          title: '验证命令',
          content: 'ok',
          payload: { command: ['npm', 'run', 'typecheck'], exit_code: 0 },
          created_at: '2026-01-01T00:00:00',
          updated_at: '2026-01-01T00:00:00',
        },
      ],
      created_at: '2026-01-01T00:00:00',
      updated_at: '2026-01-01T00:00:00',
    },
    status_text: { current_phase: 'running', next_action: '等待完成' },
    timeline: [
      {
        id: 'item_1',
        part_id: 'part_command',
        type: 'command',
        status: 'completed',
        title: '验证命令',
        content: 'ok',
        payload: {},
      },
    ],
    pending_permission: {
      part_id: 'part_permission',
      status: 'waiting_permission',
      title: '等待确认',
      content: '需要确认',
      actions: [
        {
          index: 0,
          name: 'command',
          args: { command: 'npm run typecheck' },
          allowed_decisions: ['approve', 'reject'],
        },
      ],
    },
    diagnostics: {},
    async_tasks: {
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
          restart_count: 0,
          created_at: '2026-01-01T00:00:00',
          updated_at: '2026-01-01T00:00:00',
          health_status: 'waiting',
          has_pending_permission: true,
          child_status: 'waiting_permission',
          pending_permission_part_id: 'part_permission',
        },
      ],
      metrics: {
        total: 1,
        by_status: { running: 1 },
        running: 1,
        failed: 0,
        cancelled: 0,
        completed: 0,
        attention: 1,
        recovery_count: 0,
        event_count: 0,
        last_event: null,
      },
    },
    artifacts: [
      {
        id: 'artifact_1',
        artifact_type: 'file_change',
        title: '/workspace/app.py',
        summary: '更新入口',
        payload: { path: '/workspace/app.py' },
        source_part_id: 'part_diff',
      },
      {
        id: 'findings_1',
        artifact_type: 'findings',
        title: '探索发现',
        summary: '发现入口',
        payload: {
          items: [{ title: '入口文件', summary: '入口在 src/app.py', files: ['src/app.py'], confidence: 'medium' }],
          files_examined: ['src/app.py'],
        },
      },
      {
        id: 'risks_1',
        artifact_type: 'risks',
        title: '审查风险',
        summary: '有条件通过',
        payload: {
          verdict: 'conditional',
          items: [{ severity: 'medium', title: '缺少测试', summary: '需要补回归测试', recommendation: '运行 npm test' }],
        },
      },
      {
        id: 'test_1',
        artifact_type: 'test_result',
        title: 'npm run typecheck',
        summary: '验证通过',
        payload: { command: ['npm', 'run', 'typecheck'], exit_code: 0, passed: true, stdout: 'ok', stderr: '' },
      },
      {
        id: 'unknown_1',
        artifact_type: 'custom',
        title: '自定义产物',
        summary: 'fallback',
        payload: { hello: 'world' },
      },
    ],
    changed_files: [
      {
        path: '/workspace/app.py',
        status: 'modified',
        summary: '更新入口',
        source_part_id: 'part_diff',
      },
    ],
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
      {
        id: 'review_risks:risks_1',
        action_type: 'review_risks',
        title: '查看审查风险',
        summary: '有条件通过',
        priority: 'medium',
        source_artifact_id: 'risks_1',
        payload: { artifact_id: 'risks_1' },
      },
      {
        id: 'inspect_file:/workspace/app.py',
        action_type: 'inspect_file',
        title: '查看文件 /workspace/app.py',
        summary: '更新入口',
        priority: 'low',
        payload: { path: '/workspace/app.py' },
      },
      {
        id: 'run_tests:file_changes',
        action_type: 'run_tests',
        title: '补充验证',
        summary: '只展示建议',
        priority: 'medium',
        payload: {},
      },
    ],
    recent_events: [{ id: 'event_1', event_type: 'status', message: 'running' }],
  };
}

describe('AgentInspector', () => {
  it('renders run summary from workspace metrics', () => {
    render(<AgentInspector workspace={workspace()} selection={{ type: 'run', sessionId: 'ags_parent' }} />);

    expect(screen.getByText('Build task')).toBeInTheDocument();
    expect(screen.getByText('子任务')).toBeInTheDocument();
    expect(screen.getByText('待处理')).toBeInTheDocument();
    expect(screen.getByText('建议下一步')).toBeInTheDocument();
    expect(screen.getByText('启动审查子任务')).toBeInTheDocument();
  });

  it('renders loop guard diagnostics for a blocked run', () => {
    const currentWorkspace = workspace();
    currentWorkspace.session.status = 'needs_manual_review';
    currentWorkspace.session.metadata = {
      loop_guard: {
        blocked: true,
        blocked_reason_code: 'repeated_no_progress',
        repeat_count: 4,
        threshold: 4,
        tool: 'read_file',
        input_excerpt: '/workspace/app.py',
        output_excerpt: 'same file contents',
      },
    };

    render(<AgentInspector workspace={currentWorkspace} selection={{ type: 'run', sessionId: 'ags_parent' }} />);

    expect(screen.getByText('循环阻断诊断')).toBeInTheDocument();
    expect(screen.getByText('重复操作但无进展')).toBeInTheDocument();
    expect(screen.getByText('read_file')).toBeInTheDocument();
    expect(screen.getByText('输入：/workspace/app.py')).toBeInTheDocument();
    expect(screen.getByText('重复输出：same file contents')).toBeInTheDocument();
  });

  it('emits next action callbacks from the run inspector', () => {
    const onRunNextAction = vi.fn();
    render(
      <AgentInspector
        workspace={workspace()}
        selection={{ type: 'run', sessionId: 'ags_parent' }}
        onRunNextAction={onRunNextAction}
      />,
    );

    fireEvent.click(screen.getByText('启动审查'));
    fireEvent.click(screen.getByText('查看风险'));
    fireEvent.click(screen.getByText('查看文件'));
    fireEvent.click(screen.getByText('查看建议'));

    expect(onRunNextAction).toHaveBeenCalledTimes(4);
    expect(onRunNextAction.mock.calls.map((call) => call[0].action_type)).toEqual([
      'start_review',
      'review_risks',
      'inspect_file',
      'run_tests',
    ]);
  });

  it('renders async task detail and child session entry', () => {
    render(<AgentInspector workspace={workspace()} selection={{ type: 'async_task', taskId: 'agt_1', childSessionId: 'ags_child', expandDetail: true }} />);

    expect(screen.getByText('explore 子任务')).toBeInTheDocument();
    expect(screen.getByText('inspect code')).toBeInTheDocument();
    expect(screen.getByTestId('child-detail')).toHaveTextContent('ags_child');
  });

  it('renders permission panel and submits decisions', async () => {
    const onSubmitPermission = vi.fn().mockResolvedValue(undefined);
    render(
      <AgentInspector
        workspace={workspace()}
        selection={{ type: 'permission', permissionPartId: 'part_permission' }}
        onSubmitPermission={onSubmitPermission}
      />,
    );

    expect(screen.getByText('确认 1 个 Agent 动作')).toBeInTheDocument();
    fireEvent.click(screen.getByText('提交决策'));

    await waitFor(() => expect(onSubmitPermission).toHaveBeenCalledWith('part_permission', [{ type: 'approve' }]));
  });

  it('does not render a stale permission selection', () => {
    render(<AgentInspector workspace={workspace()} selection={{ type: 'permission', permissionPartId: 'other_permission' }} />);

    expect(screen.getByText('未找到待确认权限')).toBeInTheDocument();
  });

  it('renders artifact and file selections', () => {
    const onOpenFile = vi.fn();
    const currentWorkspace = workspace();
    const { rerender } = render(<AgentInspector workspace={currentWorkspace} selection={{ type: 'artifact', artifactId: 'artifact_1' }} />);

    expect(screen.getByText('/workspace/app.py')).toBeInTheDocument();
    expect(screen.getByText('更新入口')).toBeInTheDocument();

    rerender(<AgentInspector workspace={currentWorkspace} selection={{ type: 'file', path: '/workspace/app.py' }} onOpenFile={onOpenFile} />);
    fireEvent.click(screen.getByText('在工作区打开'));

    expect(onOpenFile).toHaveBeenCalledWith('/workspace/app.py');
  });

  it('renders structured findings, risks, test results, and fallback artifacts', () => {
    const currentWorkspace = workspace();
    const { rerender } = render(<AgentInspector workspace={currentWorkspace} selection={{ type: 'artifact', artifactId: 'findings_1' }} />);

    expect(screen.getByText('入口文件')).toBeInTheDocument();
    expect(screen.getAllByText('src/app.py').length).toBeGreaterThan(0);

    rerender(<AgentInspector workspace={currentWorkspace} selection={{ type: 'artifact', artifactId: 'risks_1' }} />);
    expect(screen.getByText('缺少测试')).toBeInTheDocument();
    expect(screen.getByText('建议：运行 npm test')).toBeInTheDocument();

    rerender(<AgentInspector workspace={currentWorkspace} selection={{ type: 'artifact', artifactId: 'test_1' }} />);
    expect(screen.getAllByText('npm run typecheck').length).toBeGreaterThan(0);
    expect(screen.getByText('stdout')).toBeInTheDocument();

    rerender(<AgentInspector workspace={currentWorkspace} selection={{ type: 'artifact', artifactId: 'unknown_1' }} />);
    expect(screen.getByText(/"hello": "world"/)).toBeInTheDocument();
  });
});
