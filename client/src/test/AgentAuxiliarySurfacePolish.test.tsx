import { render, screen } from '@testing-library/react';
import { createRef } from 'react';
import { describe, expect, it, vi } from 'vitest';
import AgentRightDock from '../agent/components/AgentRightDock';
import AgentSessionRail from '../agent/components/AgentSessionRail';
import AgentTerminalDock from '../agent/components/AgentTerminalDock';
import AgentWorkspaceView from '../agent/components/AgentWorkspaceView';
import { DEFAULT_AGENT_PANEL_LAYOUT } from '../agent/config/panelLayout';
import type { RecentAgentSession } from '../agent/runtime/agentRuntime';

const session: RecentAgentSession = {
  id: 'session_polish',
  title: 'Polish auxiliary surfaces',
  displayTitle: 'Polish auxiliary surfaces',
  status: 'running',
  agentId: 'build',
  projectPath: 'C:/workspace/finetune-platform',
  updatedAt: '2026-07-12T09:00:00Z',
  preferences: {
    display_title: null,
    pinned: false,
    archived: false,
    updated_at: null,
  },
};

describe('Agent auxiliary surface polish', () => {
  it('keeps the session title and current status ahead of secondary metadata', () => {
    render(
      <AgentSessionRail
        sessions={[session]}
        activeSessionId={session.id}
        onNew={vi.fn()}
        onSelect={vi.fn()}
      />,
    );

    expect(
      screen.getByRole('button', { name: 'Polish auxiliary surfaces 会话状态：运行中' }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText('会话状态：运行中')).toBeInTheDocument();
    expect(screen.getByText('最近运行 · 1')).toHaveAttribute('data-session-secondary', 'true');
  });

  it('uses compact auxiliary empty states without removing workspace or terminal semantics', () => {
    const { rerender } = render(
      <AgentWorkspaceView
        tab="diff"
        workspace={null}
        onRecover={vi.fn()}
        onCancelSubagent={vi.fn()}
        onRunNextAction={vi.fn()}
      />,
    );

    expect(
      screen.getByText('暂无工作区数据').closest('[data-compact-empty-state]'),
    ).toHaveAttribute('data-compact-empty-state', 'true');

    rerender(
      <AgentTerminalDock
        visible
        mounted={false}
        isDesktop={false}
        terminalHeight={220}
        timeline={[]}
        resize={{} as never}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByLabelText('终端尚未运行')).toHaveAttribute(
      'data-compact-empty-state',
      'true',
    );
    expect(screen.getByRole('button', { name: '隐藏终端' })).toBeInTheDocument();
  });

  it('keeps dock tabs, dismissal, and resize controls accessible', () => {
    render(
      <AgentRightDock
        panelLayout={DEFAULT_AGENT_PANEL_LAYOUT}
        rightDockRef={createRef<HTMLElement>()}
        isDesktop
        rightDockVisible
        workspaceTabs={[
          { key: 'files', label: '文件' },
          { key: 'diff', label: 'Diff' },
        ]}
        taskCenterTabs={[{ key: 'plan', label: '计划' }]}
        workspacePanel={<div>文件内容</div>}
        taskCenterPanel={<div>计划内容</div>}
        subagentAttentionCount={0}
        resize={{} as never}
        onOpenWorkspaceTab={vi.fn()}
        onOpenTaskCenterTab={vi.fn()}
        onCollapseWorkspace={vi.fn()}
        onCollapseTaskCenter={vi.fn()}
        onMobileDockClose={vi.fn()}
      />,
    );

    expect(screen.getByRole('tablist', { name: '工作区视图' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '隐藏工作区' })).toHaveAttribute(
      'data-auxiliary-control',
      'true',
    );
    expect(screen.getByRole('button', { name: '隐藏任务中心' })).toHaveAttribute(
      'data-auxiliary-control',
      'true',
    );
    expect(screen.getByRole('separator', { name: '调整工作区宽度' })).toHaveAttribute(
      'aria-valuenow',
      '520',
    );
  });
});
