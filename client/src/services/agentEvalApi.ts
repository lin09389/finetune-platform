import { apiClient } from './api';

export type AgentEvalMode = 'coding' | 'training' | 'hybrid';
export type AgentEvalOutcome = 'passed' | 'partial' | 'failed' | 'blocked';

export interface AgentEvalOutcomeCounts {
  total: number;
  eligible_total: number;
  passed: number;
  partial: number;
  failed: number;
  blocked: number;
  weighted_score: number;
  coverage: number;
}

export interface AgentEvalReportSummary {
  report_id: string;
  runner: {
    kind: 'deterministic' | 'real_model';
    model_id?: string | null;
  };
  summary: AgentEvalOutcomeCounts & {
    by_mode: Record<AgentEvalMode, AgentEvalOutcomeCounts>;
  };
}

export interface AgentEvalOverview {
  schema_version: 1;
  catalog: {
    id: string;
    checksum: string;
    scenario_count: number;
    by_mode: Record<AgentEvalMode, number>;
  };
  live_model: {
    enabled: boolean;
    default_dry_run: true;
    requires_explicit_opt_in: true;
  };
  latest_report: AgentEvalReportSummary | null;
}

export async function getAgentEvalOverview(): Promise<AgentEvalOverview> {
  const response = await apiClient.get<AgentEvalOverview>('/agent-eval/overview');
  return response.data;
}
