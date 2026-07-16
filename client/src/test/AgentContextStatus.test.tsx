import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import AgentContextStatus from '../agent/components/AgentContextStatus';

describe('AgentContextStatus', () => {
  it('shows empty hint when no context signal', () => {
    render(<AgentContextStatus metadata={{}} />);
    expect(screen.getByText(/任务运行后将显示/)).toBeInTheDocument();
  });

  it('renders offload chip details', () => {
    render(
      <AgentContextStatus
        metadata={{
          deep_context: {
            context_engineering: {
              knowledge_binding: {
                status: 'configured',
                use_knowledge: true,
                source: 'session',
                collection_id: 'kb-abc',
              },
              project_retrieval: { status: 'ok' },
            },
          },
          context_refresh: {
            tool_offload_count: 2,
            recent_offloads: [
              {
                tool: 'execute',
                path: '/large_tool_results/call_1',
                offloaded: true,
                truncated: true,
              },
            ],
          },
        }}
      />,
    );

    expect(screen.getByText(/已用/)).toBeInTheDocument();
    expect(screen.getByText(/外置 2/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '展开详情' }));
    expect(screen.getAllByText(/large_tool_results/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/已外置/)).toBeInTheDocument();
  });
});
