export type AgentTrainingScenarioMode = 'build' | 'train' | 'hybrid';
export type AgentTrainingActivityKind = 'proposal' | 'submission' | 'run_summary' | 'unknown';

export interface AgentTrainingScenarioActivity {
  kind: AgentTrainingActivityKind;
  source_tool: 'propose_training' | 'submit_training' | 'get_training_summary';
  proposal_id?: string;
  task_id?: string;
  status?: string;
  summary?: string;
}

export interface AgentTrainingScenarioTimelineItem {
  sequence: number;
  id: string;
  type: string;
  status: string;
  payload: {
    training_activity?: AgentTrainingScenarioActivity;
    command?: string;
    error?: string;
  };
}

export interface AgentTrainingGoldenPathScenario {
  id: string;
  mode: AgentTrainingScenarioMode;
  trainingTools: readonly string[];
  timeline: readonly AgentTrainingScenarioTimelineItem[];
}

const trainTimeline: readonly AgentTrainingScenarioTimelineItem[] = [
  {
    sequence: 10,
    id: 'activity-proposal-train-001',
    type: 'tool_result',
    status: 'completed',
    payload: {
      training_activity: {
        kind: 'proposal',
        source_tool: 'propose_training',
        proposal_id: 'proposal-train-001',
        status: 'ready',
        summary: 'tiny-model · tiny-dataset · qlora',
      },
    },
  },
  {
    sequence: 20,
    id: 'activity-submission-train-001',
    type: 'tool_result',
    status: 'completed',
    payload: {
      training_activity: {
        kind: 'submission',
        source_tool: 'submit_training',
        proposal_id: 'proposal-train-001',
        task_id: 'task-train-001',
        status: 'queued',
        summary: 'Training task queued after approval',
      },
    },
  },
  {
    sequence: 30,
    id: 'activity-run-train-001',
    type: 'tool_result',
    status: 'completed',
    payload: {
      training_activity: {
        kind: 'run_summary',
        source_tool: 'get_training_summary',
        task_id: 'task-train-001',
        status: 'completed',
        summary: 'Training completed in 2m',
      },
    },
  },
];

const scenarios: readonly AgentTrainingGoldenPathScenario[] = [
  {
    id: 'train-approval',
    mode: 'train',
    trainingTools: ['propose_training', 'submit_training', 'get_training_summary'],
    timeline: trainTimeline,
  },
  {
    id: 'train-rejection',
    mode: 'train',
    trainingTools: ['propose_training', 'submit_training', 'get_training_summary'],
    timeline: [
      {
        sequence: 10,
        id: 'activity-proposal-rejected-001',
        type: 'tool_result',
        status: 'completed',
        payload: {
          training_activity: {
            kind: 'proposal',
            source_tool: 'propose_training',
            proposal_id: 'proposal-rejected-001',
            status: 'ready',
            summary: 'Ready for explicit approval',
          },
        },
      },
      {
        sequence: 20,
        id: 'activity-rejection-fallback-001',
        type: 'tool_result',
        status: 'failed',
        payload: {
          training_activity: { kind: 'unknown', source_tool: 'propose_training' },
          error: 'Approval rejected; no training task was created.',
        },
      },
    ],
  },
  {
    id: 'duplicate-retry',
    mode: 'train',
    trainingTools: ['propose_training', 'submit_training', 'get_training_summary'],
    timeline: [
      {
        sequence: 10,
        id: 'activity-submission-duplicate-001',
        type: 'tool_result',
        status: 'completed',
        payload: {
          training_activity: {
            kind: 'submission',
            source_tool: 'submit_training',
            proposal_id: 'proposal-train-001',
            task_id: 'task-train-001',
            status: 'queued',
            summary: 'Training task queued after approval',
          },
        },
      },
      {
        sequence: 20,
        id: 'activity-duplicate-fallback-001',
        type: 'tool_result',
        status: 'failed',
        payload: {
          error: 'This proposal was already submitted; the existing task remains task-train-001.',
        },
      },
    ],
  },
  {
    id: 'refresh-recovery',
    mode: 'train',
    trainingTools: ['propose_training', 'submit_training', 'get_training_summary'],
    timeline: trainTimeline,
  },
  {
    id: 'hybrid-coexistence',
    mode: 'hybrid',
    trainingTools: ['propose_training', 'submit_training', 'get_training_summary'],
    timeline: [
      {
        sequence: 10,
        id: 'activity-build-command-001',
        type: 'command',
        status: 'completed',
        payload: { command: 'rg --files' },
      },
      {
        sequence: 20,
        id: 'activity-proposal-hybrid-001',
        type: 'tool_result',
        status: 'completed',
        payload: {
          training_activity: {
            kind: 'proposal',
            source_tool: 'propose_training',
            proposal_id: 'proposal-hybrid-001',
            status: 'warning',
            summary: 'Training can proceed with a VRAM warning',
          },
        },
      },
      {
        sequence: 30,
        id: 'activity-submission-hybrid-001',
        type: 'tool_result',
        status: 'completed',
        payload: {
          training_activity: {
            kind: 'submission',
            source_tool: 'submit_training',
            proposal_id: 'proposal-hybrid-001',
            task_id: 'task-hybrid-001',
            status: 'queued',
            summary: 'Training task queued after approval',
          },
        },
      },
    ],
  },
  { id: 'build-exclusion', mode: 'build', trainingTools: [], timeline: [] },
];

export function goldenPathScenario(id: string): AgentTrainingGoldenPathScenario {
  const scenario = scenarios.find((candidate) => candidate.id === id);
  if (!scenario) throw new Error(`Unknown Agent training golden-path scenario: ${id}`);
  return scenario;
}

/** Return a fresh, deterministically ordered projection just as a refresh would. */
export function goldenPathTimeline(id: string): AgentTrainingScenarioTimelineItem[] {
  return goldenPathScenario(id)
    .timeline.map((item) => ({
      ...item,
      payload: {
        ...item.payload,
        training_activity: item.payload.training_activity && { ...item.payload.training_activity },
      },
    }))
    .sort((left, right) => left.sequence - right.sequence);
}

/** Unknown activity deliberately stays on the generic timeline renderer. */
export function isGenericFallbackScenarioItem(item: AgentTrainingScenarioTimelineItem): boolean {
  const activity = item.payload.training_activity;
  return !activity || activity.kind === 'unknown';
}
