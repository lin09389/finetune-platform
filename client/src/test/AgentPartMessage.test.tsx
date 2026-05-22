import { render, screen } from '@testing-library/react';
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
});
