import { describe, expect, it } from 'vitest';
import { codingActivityTimeline, codingAgentScenario } from '../agent/testing/codingAgentScenarios';

describe('Coding Agent golden-path contract fixtures', () => {
  it('keeps normal Build coding activity ordered and visible', () => {
    const scenario = codingAgentScenario('build-golden-path');

    expect(scenario.mode).toBe('build');
    expect(codingActivityTimeline('build-golden-path').map((item) => item.kind)).toEqual([
      'command',
      'diff',
      'permission',
      'failure',
      'repair',
      'verification',
      'summary',
    ]);
  });

  it('keeps Coding activity alongside training activity in Hybrid mode', () => {
    const scenario = codingAgentScenario('hybrid-coding-training');
    const activities = codingActivityTimeline('hybrid-coding-training');

    expect(scenario.mode).toBe('hybrid');
    expect(activities.map((item) => item.id)).toEqual([
      'coding-command-001',
      'coding-diff-001',
      'coding-permission-001',
      'coding-failure-001',
      'coding-repair-001',
      'coding-verification-001',
      'coding-summary-001',
      'training-run-001',
    ]);
    expect(activities.find((item) => item.kind === 'training')?.payload.training_task_id).toBe('train-001');
    expect(activities.find((item) => item.kind === 'diff')?.payload.changed_files).toEqual(['server/app/price.py']);
  });

  it('preserves coding identity, diff/terminal activity, and pending approval after refresh', () => {
    const beforeRefresh = codingAgentScenario('build-golden-path');
    const afterRefresh = codingAgentScenario('refresh-resume');

    expect(afterRefresh.sessionId).toBe(beforeRefresh.sessionId);
    expect(afterRefresh.changedFiles).toEqual(beforeRefresh.changedFiles);
    expect(afterRefresh.pendingApprovalId).toBe(beforeRefresh.pendingApprovalId);
    expect(afterRefresh.activities.map((item) => item.id)).toEqual(beforeRefresh.activities.map((item) => item.id));
    expect(afterRefresh.activities.filter((item) => item.kind === 'command' || item.kind === 'verification')).toHaveLength(2);
    expect(afterRefresh.activities.find((item) => item.kind === 'diff')?.payload.changed_files).toEqual([
      'server/app/price.py',
    ]);
  });
});
