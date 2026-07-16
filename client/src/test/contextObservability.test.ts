import { describe, expect, it } from 'vitest';
import { selectContextObservability } from '../agent/selectors/contextObservability';

describe('selectContextObservability', () => {
  it('returns empty signal without metadata', () => {
    const obs = selectContextObservability(null);
    expect(obs.hasSignal).toBe(false);
    expect(obs.knowledge.label).toContain('未绑定');
  });

  it('maps configured knowledge binding', () => {
    const obs = selectContextObservability({
      deep_context: {
        context_engineering: {
          knowledge_binding: {
            status: 'configured',
            use_knowledge: true,
            source: 'workspace',
            collection_id: 'ws_knowledge_demo',
          },
          project_retrieval: { status: 'ok' },
          virtual_file_count: 4,
        },
      },
    });
    expect(obs.hasSignal).toBe(true);
    expect(obs.knowledge.useKnowledge).toBe(true);
    expect(obs.knowledge.tone).toBe('ok');
    expect(obs.projectRetrievalStatus).toBe('ok');
  });

  it('surfaces tool offload counters for Scheme A', () => {
    const obs = selectContextObservability({
      context_refresh: {
        tool_offload_count: 3,
        tool_truncate_count: 1,
        recent_offloads: [
          { tool: 'execute', path: '/large_tool_results/abc', offloaded: true, truncated: true },
        ],
      },
    });
    expect(obs.refresh.toolOffloadCount).toBe(3);
    expect(obs.refresh.hasSignal).toBe(true);
    expect(obs.refresh.recentOffloads[0]?.path).toContain('large_tool_results');
  });
});
