import { describe, expect, it } from 'vitest';
import {
  goldenPathScenario,
  goldenPathTimeline,
  isGenericFallbackScenarioItem,
} from '../agent/testing/agentTrainingScenarios';

describe('Agent training golden-path contract fixtures', () => {
  it('keeps the Train approval timeline ordered and stable after refresh recovery', () => {
    const beforeRefresh = goldenPathTimeline('train-approval');
    const afterRefresh = goldenPathTimeline('refresh-recovery');

    expect(beforeRefresh.map((item) => item.id)).toEqual([
      'activity-proposal-train-001',
      'activity-submission-train-001',
      'activity-run-train-001',
    ]);
    expect(afterRefresh.map((item) => item.id)).toEqual(beforeRefresh.map((item) => item.id));
    expect(
      afterRefresh.map(
        (item) =>
          item.payload.training_activity?.proposal_id ?? item.payload.training_activity?.task_id,
      ),
    ).toEqual(['proposal-train-001', 'proposal-train-001', 'task-train-001']);
  });

  it('preserves ordinary Build activity beside Hybrid training activity', () => {
    const scenario = goldenPathScenario('hybrid-coexistence');

    expect(scenario.mode).toBe('hybrid');
    expect(goldenPathTimeline('hybrid-coexistence').map((item) => item.id)).toEqual([
      'activity-build-command-001',
      'activity-proposal-hybrid-001',
      'activity-submission-hybrid-001',
    ]);
  });

  it('keeps malformed or unknown training projections as generic timeline activity', () => {
    const rejectionTimeline = goldenPathTimeline('train-rejection');
    const fallback = rejectionTimeline[rejectionTimeline.length - 1];

    expect(fallback).toBeDefined();
    expect(isGenericFallbackScenarioItem(fallback!)).toBe(true);
    expect(fallback?.payload.training_activity).toEqual({
      kind: 'unknown',
      source_tool: 'propose_training',
    });
  });

  it('freezes Build exclusion as an empty training projection set', () => {
    const scenario = goldenPathScenario('build-exclusion');

    expect(scenario.mode).toBe('build');
    expect(scenario.trainingTools).toEqual([]);
    expect(goldenPathTimeline('build-exclusion')).toEqual([]);
  });
});
