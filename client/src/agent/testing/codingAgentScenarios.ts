export type CodingScenarioMode = 'build' | 'hybrid';
export type CodingActivityKind =
  | 'command'
  | 'diff'
  | 'permission'
  | 'failure'
  | 'repair'
  | 'verification'
  | 'summary'
  | 'training';

export interface CodingScenarioActivity {
  id: string;
  kind: CodingActivityKind;
  title: string;
  status: 'completed' | 'failed' | 'pending';
  payload: {
    command?: string;
    changed_files?: string[];
    approval_id?: string;
    training_task_id?: string;
  };
}

export interface CodingAgentScenario {
  id: 'build-golden-path' | 'hybrid-coding-training' | 'refresh-resume';
  mode: CodingScenarioMode;
  sessionId: string;
  changedFiles: string[];
  pendingApprovalId: string | null;
  activities: CodingScenarioActivity[];
}

const codingActivities: CodingScenarioActivity[] = [
  {
    id: 'coding-command-001',
    kind: 'command',
    title: 'Run focused test',
    status: 'completed',
    payload: { command: 'python -m pytest server/tests/test_price.py -q' },
  },
  {
    id: 'coding-diff-001',
    kind: 'diff',
    title: 'Review changed file',
    status: 'completed',
    payload: { changed_files: ['server/app/price.py'] },
  },
  {
    id: 'coding-permission-001',
    kind: 'permission',
    title: 'Approve change',
    status: 'pending',
    payload: { approval_id: 'coding-permission-001' },
  },
  {
    id: 'coding-failure-001',
    kind: 'failure',
    title: 'Verification failed',
    status: 'failed',
    payload: { command: 'python -m pytest server/tests/test_price.py -q' },
  },
  {
    id: 'coding-repair-001',
    kind: 'repair',
    title: 'Reread and repair',
    status: 'completed',
    payload: { changed_files: ['server/app/price.py'] },
  },
  {
    id: 'coding-verification-001',
    kind: 'verification',
    title: 'Verification passed',
    status: 'completed',
    payload: { command: 'python -m pytest server/tests/test_price.py -q' },
  },
  {
    id: 'coding-summary-001',
    kind: 'summary',
    title: 'Coding summary',
    status: 'completed',
    payload: { changed_files: ['server/app/price.py'] },
  },
];

const scenarios: Record<CodingAgentScenario['id'], CodingAgentScenario> = {
  'build-golden-path': {
    id: 'build-golden-path',
    mode: 'build',
    sessionId: 'ags-coding-001',
    changedFiles: ['server/app/price.py'],
    pendingApprovalId: 'coding-permission-001',
    activities: codingActivities,
  },
  'hybrid-coding-training': {
    id: 'hybrid-coding-training',
    mode: 'hybrid',
    sessionId: 'ags-coding-002',
    changedFiles: ['server/app/price.py'],
    pendingApprovalId: 'coding-permission-001',
    activities: [
      ...codingActivities,
      {
        id: 'training-run-001',
        kind: 'training',
        title: 'Training run',
        status: 'completed',
        payload: { training_task_id: 'train-001' },
      },
    ],
  },
  'refresh-resume': {
    id: 'refresh-resume',
    mode: 'build',
    sessionId: 'ags-coding-001',
    changedFiles: ['server/app/price.py'],
    pendingApprovalId: 'coding-permission-001',
    activities: codingActivities,
  },
};

export function codingAgentScenario(id: CodingAgentScenario['id']): CodingAgentScenario {
  const scenario = scenarios[id];
  return {
    ...scenario,
    changedFiles: [...scenario.changedFiles],
    activities: scenario.activities.map((activity) => ({
      ...activity,
      payload: {
        ...activity.payload,
        changed_files: activity.payload.changed_files && [...activity.payload.changed_files],
      },
    })),
  };
}

export function codingActivityTimeline(id: CodingAgentScenario['id']): CodingScenarioActivity[] {
  return codingAgentScenario(id).activities;
}
