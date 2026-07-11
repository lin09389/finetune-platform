export type TrainingLiveStatus = 'queued' | 'loading' | 'running' | 'completed' | 'failed' | 'missing' | 'degraded';

export interface AgentTrainingLiveSnapshot {
  cardId: string;
  status: TrainingLiveStatus;
  step?: number;
  totalSteps?: number;
  artifactAvailable?: boolean;
}

export interface AgentTrainingLiveScenario {
  id: string;
  taskId: string;
  snapshots: AgentTrainingLiveSnapshot[];
}

export const agentTrainingLiveScenarios: readonly AgentTrainingLiveScenario[] = [
  { id: 'ordered-progress', taskId: 'task-live-001', snapshots: [
    { cardId: 'part-training-task-live-001', status: 'queued', step: 0, totalSteps: 100 },
    { cardId: 'part-training-task-live-001', status: 'loading', step: 0, totalSteps: 100 },
    { cardId: 'part-training-task-live-001', status: 'running', step: 40, totalSteps: 100 },
  ] },
  { id: 'duplicate-replay', taskId: 'task-live-001', snapshots: [
    { cardId: 'part-training-task-live-001', status: 'running', step: 40, totalSteps: 100 },
    { cardId: 'part-training-task-live-001', status: 'running', step: 40, totalSteps: 100 },
  ] },
  { id: 'api-restart-cursor-recovery', taskId: 'task-live-002', snapshots: [
    { cardId: 'part-training-task-live-002', status: 'running', step: 25, totalSteps: 100 },
    { cardId: 'part-training-task-live-002', status: 'running', step: 50, totalSteps: 100 },
  ] },
  { id: 'refresh-recovery', taskId: 'task-live-003', snapshots: [
    { cardId: 'part-training-task-live-003', status: 'running', step: 75, totalSteps: 100 },
    { cardId: 'part-training-task-live-003', status: 'running', step: 75, totalSteps: 100 },
  ] },
  { id: 'worker-outage-recovery', taskId: 'task-live-004', snapshots: [
    { cardId: 'part-training-task-live-004', status: 'running', step: 30, totalSteps: 100 },
    { cardId: 'part-training-task-live-004', status: 'degraded', step: 30, totalSteps: 100 },
    { cardId: 'part-training-task-live-004', status: 'running', step: 45, totalSteps: 100 },
  ] },
  { id: 'missing-job-grace', taskId: 'task-live-005', snapshots: [
    { cardId: 'part-training-task-live-005', status: 'missing' },
  ] },
  { id: 'cross-user-rejection', taskId: 'task-live-006', snapshots: [] },
  { id: 'terminal-completion', taskId: 'task-live-007', snapshots: [
    { cardId: 'part-training-task-live-007', status: 'running', step: 100, totalSteps: 100 },
    { cardId: 'part-training-task-live-007', status: 'completed', step: 100, totalSteps: 100, artifactAvailable: true },
  ] },
  { id: 'safe-artifact-handoff', taskId: 'task-live-008', snapshots: [
    { cardId: 'part-training-task-live-008', status: 'completed', step: 100, totalSteps: 100, artifactAvailable: true },
  ] },
  { id: 'unknown-event-cursor-advance', taskId: 'task-live-009', snapshots: [
    { cardId: 'part-training-task-live-009', status: 'running', step: 20, totalSteps: 100 },
    { cardId: 'part-training-task-live-009', status: 'running', step: 20, totalSteps: 100 },
  ] },
  { id: 'terminal-old-event-cannot-regress', taskId: 'task-live-010', snapshots: [
    { cardId: 'part-training-task-live-010', status: 'completed', step: 100, totalSteps: 100 },
    { cardId: 'part-training-task-live-010', status: 'completed', step: 100, totalSteps: 100 },
  ] },
  { id: 'build-session-exclusion', taskId: 'task-live-012', snapshots: [] },
  { id: 'hybrid-coding-coexistence', taskId: 'task-live-013', snapshots: [
    { cardId: 'part-training-task-live-013', status: 'running', step: 50, totalSteps: 100 },
  ] },
  { id: 'terminal-isolation-and-refresh', taskId: 'task-live-014', snapshots: [
    { cardId: 'part-training-task-live-014', status: 'completed', step: 100, totalSteps: 100, artifactAvailable: true },
    { cardId: 'part-training-task-live-014', status: 'completed', step: 100, totalSteps: 100, artifactAvailable: true },
  ] },
];

export function hasStableCardIdentity(scenario: AgentTrainingLiveScenario): boolean {
  return scenario.snapshots.length < 2 || scenario.snapshots.every((snapshot) => snapshot.cardId === scenario.snapshots[0]?.cardId);
}

export function hasMonotonicDisplayedProgress(scenario: AgentTrainingLiveScenario): boolean {
  let previous = -1;
  for (const snapshot of scenario.snapshots) {
    if (snapshot.step === undefined || snapshot.totalSteps === undefined || snapshot.totalSteps <= 0) continue;
    const percentage = Math.max(0, Math.min(100, (snapshot.step / snapshot.totalSteps) * 100));
    if (percentage < previous) return false;
    previous = percentage;
  }
  return true;
}
