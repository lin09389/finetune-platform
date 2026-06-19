import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import AgentPartMessage from '../components/chat/AgentPartMessage';
import type { AgentPart } from '../services/api';
import type { ChatAgentMetadata } from '../types';

vi.mock('../components/chat/AgentTerminal', () => ({
  default: ({ terminalId }: { terminalId: string }) => <div data-testid="agent-terminal">{terminalId}</div>,
}));

function metadata(part: AgentPart): ChatAgentMetadata {
  return {
    agent_run_id: 'run_1',
    agent_session_id: part.session_id,
    agent_part_id: part.id,
    kind: 'agent_part',
    status: part.status || '',
    action_id: part.id,
    action_type: part.type,
    agent_part: part,
  };
}

describe('AgentPartMessage terminal rendering', () => {
  it('renders interactive terminal for command parts with terminal_id', () => {
    const part: AgentPart = {
      id: 'agp_terminal',
      session_id: 'ags_1',
      type: 'command',
      status: 'running',
      title: '验证命令',
      content: 'running',
      payload: { command: ['npm', 'run', 'typecheck'], terminal_id: 'agt_123' },
      created_at: '2026-01-01T00:00:00',
    };

    render(<AgentPartMessage content="" metadata={metadata(part)} />);

    expect(screen.getByTestId('agent-terminal')).toHaveTextContent('agt_123');
  });

  it('keeps legacy output panel for command parts without terminal_id', () => {
    const part: AgentPart = {
      id: 'agp_legacy',
      session_id: 'ags_1',
      type: 'command',
      status: 'executed',
      title: '验证命令',
      content: 'done',
      payload: { command: ['npm', 'run', 'typecheck'], stdout: 'ok', exit_code: 0 },
      created_at: '2026-01-01T00:00:00',
    };

    render(<AgentPartMessage content="" metadata={metadata(part)} />);

    expect(screen.queryByTestId('agent-terminal')).not.toBeInTheDocument();
    expect(screen.getByText('查看命令输出')).toBeInTheDocument();
  });

  it('renders async subagent summary metadata and opens the async task panel', () => {
    const onOpenAsyncTask = vi.fn();
    const part: AgentPart = {
      id: 'agp_async',
      session_id: 'ags_1',
      type: 'summary',
      status: 'completed',
      title: '异步子任务完成',
      content: 'Explore finished.',
      payload: {
        agent_role: 'async_subagent',
        agent_name: 'explore',
        async_status: 'completed',
        task_id: 'ast_123',
        child_session_id: 'ags_child',
      },
      created_at: '2026-01-01T00:00:00',
    };

    render(
      <AgentPartMessage
        content=""
        metadata={metadata(part)}
        onOpenAsyncTask={onOpenAsyncTask}
      />,
    );

    expect(screen.getByText('已完成 Explore')).toBeInTheDocument();
    expect(screen.getByText('任务 ast_123')).toBeInTheDocument();
    expect(screen.getByText('子会话 ags_child')).toBeInTheDocument();

    expect(screen.queryByText('查看详情')).not.toBeInTheDocument();
    expect(screen.queryByText('查看子任务')).not.toBeInTheDocument();

    fireEvent.click(screen.getByText('查看任务'));
    expect(onOpenAsyncTask).toHaveBeenCalledWith('ast_123', 'ags_child', { expandDetail: true });
  });

  it('uses a confirmation action for async subagent summaries waiting on child approval', () => {
    const onOpenAsyncTask = vi.fn();
    const part: AgentPart = {
      id: 'agp_async_waiting',
      session_id: 'ags_1',
      type: 'summary',
      status: 'failed',
      title: '异步子任务等待确认',
      content: '子任务状态：waiting_permission',
      payload: {
        agent_role: 'async_subagent',
        agent_name: 'review',
        async_status: 'failed',
        child_status: 'waiting_permission',
        has_pending_permission: true,
        task_id: 'ast_wait',
        child_session_id: 'ags_child_wait',
      },
      created_at: '2026-01-01T00:00:00',
    };

    render(<AgentPartMessage content="" metadata={metadata(part)} onOpenAsyncTask={onOpenAsyncTask} />);

    expect(screen.getByText('已完成 Review')).toBeInTheDocument();
    fireEvent.click(screen.getByText('处理确认'));

    expect(onOpenAsyncTask).toHaveBeenCalledWith('ast_wait', 'ags_child_wait', { expandDetail: true });
  });

  it('marks child manual review as attention and opens the blocked task', () => {
    const onOpenAsyncTask = vi.fn();
    const part: AgentPart = {
      id: 'agp_async_blocked',
      session_id: 'ags_1',
      type: 'summary',
      status: 'failed',
      title: '异步子任务需要人工处理',
      content: '子任务触发循环保护。',
      payload: {
        agent_role: 'async_subagent',
        agent_name: 'review',
        async_status: 'failed',
        child_status: 'needs_manual_review',
        task_id: 'ast_blocked',
        child_session_id: 'ags_child_blocked',
      },
      created_at: '2026-01-01T00:00:00',
    };

    render(<AgentPartMessage content="" metadata={metadata(part)} onOpenAsyncTask={onOpenAsyncTask} />);

    fireEvent.click(screen.getByText('查看阻断'));
    expect(onOpenAsyncTask).toHaveBeenCalledWith('ast_blocked', 'ags_child_blocked', { expandDetail: true });
  });

  it('renders structured loop guard diagnostics', () => {
    const part: AgentPart = {
      id: 'agp_loop_guard',
      session_id: 'ags_1',
      type: 'error',
      status: 'failed',
      title: '连续失败阻断',
      content: '连续 3 次遇到同类工具失败。',
      payload: {
        guard: 'loop_guard',
        reason_code: 'repeated_failure_family',
        repeat_count: 3,
        threshold: 3,
        tool: 'execute',
        input_excerpt: 'python -m pytest',
        error_excerpt: 'Command failed with exit code 1',
      },
      created_at: '2026-01-01T00:00:00',
    };

    render(<AgentPartMessage content="" metadata={metadata(part)} />);

    expect(screen.getByText('阻断类型：重复同类失败')).toBeInTheDocument();
    expect(screen.getByText('触发次数：3 / 阈值 3')).toBeInTheDocument();
    expect(screen.getByText('工具：execute')).toBeInTheDocument();
    expect(screen.getByText('输入：python -m pytest')).toBeInTheDocument();
    expect(screen.getByText('错误：Command failed with exit code 1')).toBeInTheDocument();
  });
});
