import { describe, expect, it } from 'vitest';
import {
  agentTrainingLiveScenarios,
  hasMonotonicDisplayedProgress,
  hasStableCardIdentity,
} from '../agent/testing/agentTrainingLiveScenarios';

describe('Agent training live-sync acceptance scenarios', () => {
  it('freezes every recovery and handoff scenario', () => {
    expect(agentTrainingLiveScenarios.map((scenario) => scenario.id)).toEqual([
      'ordered-progress',
      'duplicate-replay',
      'api-restart-cursor-recovery',
      'refresh-recovery',
      'worker-outage-recovery',
      'missing-job-grace',
      'cross-user-rejection',
      'terminal-completion',
      'safe-artifact-handoff',
      'unknown-event-cursor-advance',
      'terminal-old-event-cannot-regress',
      'build-session-exclusion',
      'hybrid-coding-coexistence',
      'terminal-isolation-and-refresh',
    ]);
  });

  it('keeps one card identity across replay, restart, refresh, and outage recovery', () => {
    for (const scenario of agentTrainingLiveScenarios) {
      expect(hasStableCardIdentity(scenario), scenario.id).toBe(true);
    }
  });

  it('never lets displayed progress move backward', () => {
    for (const scenario of agentTrainingLiveScenarios) {
      expect(hasMonotonicDisplayedProgress(scenario), scenario.id).toBe(true);
    }
  });

  it('does not project a card for cross-user rejection and gates artifact handoff on completion', () => {
    const rejected = agentTrainingLiveScenarios.find((scenario) => scenario.id === 'cross-user-rejection');
    const handoff = agentTrainingLiveScenarios.find((scenario) => scenario.id === 'safe-artifact-handoff');
    expect(rejected?.snapshots).toEqual([]);
    expect(handoff?.snapshots).toEqual([
      { cardId: 'part-training-task-live-008', status: 'completed', step: 100, totalSteps: 100, artifactAvailable: true },
    ]);
  });
});
