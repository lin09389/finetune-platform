import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AgentChildSessionDrawer from '../components/chat/AgentChildSessionDrawer';

const apiMocks = vi.hoisted(() => ({
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

function childSession(pending = true) {
  return {
    id: 'ags_child',
    chat_session_id: null,
    agent_id: 'explore',
    status: pending ? 'waiting_permission' : 'running',
    title: 'Explore',
    metadata: {
      ui_state: {
        timeline: [
          {
            id: 'item_1',
            part_id: 'part_text',
            session_id: 'ags_child',
            type: 'text',
            status: 'completed',
            title: '子任务日志',
            content: 'child timeline content',
            payload: {},
            created_at: '2026-01-01T00:00:00',
          },
        ],
        pending_permission: pending ? {
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
        } : null,
      },
    },
    parts: [
      {
        id: 'part_text',
        session_id: 'ags_child',
        type: 'text',
        status: 'completed',
        title: '子任务日志',
        content: 'child timeline content',
        payload: {},
        created_at: '2026-01-01T00:00:00',
      },
    ],
    events: [],
    created_at: '2026-01-01T00:00:00',
    updated_at: '2026-01-01T00:00:00',
  };
}

describe('AgentChildSessionDrawer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.getAgentSession.mockResolvedValue(childSession(true));
    apiMocks.decideAgentPermission.mockResolvedValue({ session: childSession(false) });
  });

  it('loads and renders child session timeline content', async () => {
    render(<AgentChildSessionDrawer open childSessionId="ags_child" onClose={vi.fn()} />);

    expect(await screen.findByText('Explore')).toBeInTheDocument();
    expect(await screen.findByText('等待确认')).toBeInTheDocument();
    expect(await screen.findByText('child timeline content')).toBeInTheDocument();
    expect(apiMocks.getAgentSession).toHaveBeenCalledWith('ags_child');
  });

  it('submits pending child session HITL decisions and notifies the parent', async () => {
    const onDecisionSubmitted = vi.fn();
    render(
      <AgentChildSessionDrawer
        open
        childSessionId="ags_child"
        onClose={vi.fn()}
        onDecisionSubmitted={onDecisionSubmitted}
      />,
    );

    expect(await screen.findByText('确认 1 个 Agent 动作')).toBeInTheDocument();
    expect(await screen.findByText('command')).toBeInTheDocument();
    expect(await screen.findByText('批准')).toBeInTheDocument();
    fireEvent.click(screen.getByText('提交决策'));

    await waitFor(() => expect(apiMocks.decideAgentPermission).toHaveBeenCalledWith('part_permission', [
      { type: 'approve' },
    ]));
    await waitFor(() => expect(onDecisionSubmitted).toHaveBeenCalledWith(expect.objectContaining({ id: 'ags_child' })));
  });
});
