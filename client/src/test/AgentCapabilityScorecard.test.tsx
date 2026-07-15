import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AgentCapabilityScorecard from '../agent/components/AgentCapabilityScorecard';
import { getAgentEvalOverview } from '../services/agentEvalApi';

vi.mock('../services/agentEvalApi', () => ({
  getAgentEvalOverview: vi.fn(),
}));

const mockedOverview = vi.mocked(getAgentEvalOverview);

describe('AgentCapabilityScorecard', () => {
  beforeEach(() => {
    mockedOverview.mockReset();
  });

  it('renders a privacy-safe local capability summary', async () => {
    mockedOverview.mockResolvedValue({
      schema_version: 1,
      catalog: {
        id: 'phase9-agent-eval',
        checksum: `sha256:${'a'.repeat(64)}`,
        scenario_count: 32,
        by_mode: { coding: 20, training: 6, hybrid: 6 },
      },
      live_model: {
        enabled: false,
        default_dry_run: true,
        requires_explicit_opt_in: true,
      },
      latest_report: {
        report_id: 'eval-1234567890abcdef',
        runner: { kind: 'real_model', model_id: 'local-model' },
        summary: {
          total: 32,
          eligible_total: 30,
          passed: 24,
          partial: 4,
          failed: 2,
          blocked: 2,
          weighted_score: 0.8,
          coverage: 0.9375,
          by_mode: {
            coding: { total: 20, eligible_total: 20, passed: 16, partial: 3, failed: 1, blocked: 0, weighted_score: 0.8, coverage: 1 },
            training: { total: 6, eligible_total: 5, passed: 4, partial: 0, failed: 1, blocked: 1, weighted_score: 0.8, coverage: 0.833333 },
            hybrid: { total: 6, eligible_total: 5, passed: 4, partial: 1, failed: 0, blocked: 1, weighted_score: 0.8, coverage: 0.833333 },
          },
        },
      },
    });

    render(<AgentCapabilityScorecard />);

    expect(await screen.findByText('综合能力分')).toBeInTheDocument();
    expect(screen.getByText('32')).toBeInTheDocument();
    expect(screen.getByText('30 个有效场景 · 94% 覆盖')).toBeInTheDocument();
    expect(screen.getByText('真实模型入口关闭；当前仅展示本地安全基线')).toBeInTheDocument();
  });

  it('shows a contained error without breaking the settings drawer', async () => {
    mockedOverview.mockRejectedValue(new Error('backend unavailable'));
    render(<AgentCapabilityScorecard />);

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('backend unavailable'));
  });
});
