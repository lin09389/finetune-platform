import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import AgentWorkspaceStatusBar from '../components/chat/AgentWorkspaceStatusBar';

describe('AgentWorkspaceStatusBar', () => {
  it('shows agent and async task status and opens task panel', () => {
    const onOpenAsyncTasks = vi.fn();

    render(
      <AgentWorkspaceStatusBar
        agentName="Build Agent"
        sessionStatus="running"
        asyncMetrics={{
          total: 3,
          by_status: { running: 1, failed: 1, completed: 1 },
          running: 1,
          failed: 1,
          cancelled: 0,
          completed: 1,
          attention: 1,
          recovery_count: 0,
          event_count: 3,
          last_event: null,
        }}
        onOpenAsyncTasks={onOpenAsyncTasks}
      />,
    );

    expect(screen.getByText('Build Agent')).toBeInTheDocument();
    expect(screen.getByText('运行中')).toBeInTheDocument();
    expect(screen.getByText('需要处理')).toBeInTheDocument();
    expect(screen.getByText('子任务')).toBeInTheDocument();
    expect(screen.getByText('活跃')).toBeInTheDocument();
    expect(screen.getByText('待处理')).toBeInTheDocument();

    fireEvent.click(screen.getByText('打开子任务'));

    expect(onOpenAsyncTasks).toHaveBeenCalledTimes(1);
  });
});
