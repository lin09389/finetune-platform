import type { AgentPart, AgentSession, AgentSessionEvent, AgentWorkspace } from '../../services/api';

export interface CodingDiffReviewScenario {
  id: 'live-to-refresh' | 'chronological-history' | 'unknown-contract';
  session: AgentSession;
  workspace: AgentWorkspace;
  events: AgentSessionEvent[];
}

const sessionId = 'ags-coding-diff-review-001';
const timestamp = '2026-07-11T10:00:00Z';

function part(
  id: string,
  payload: Record<string, unknown>,
  createdAt: string,
): AgentPart {
  return {
    id,
    session_id: sessionId,
    type: 'diff',
    status: 'completed',
    title: String(payload.path || 'Diff review'),
    content: String(payload.unified_diff || ''),
    payload,
    created_at: createdAt,
  };
}

const firstDiff = part('diff-001', {
  contract_version: 1,
  path: 'server/app.py',
  status: 'modified',
  additions: 1,
  deletions: 1,
  binary: false,
  truncated: false,
  write_sequence: 2,
  review_status: 'ready',
  unified_diff: '@@ -1 +1 @@\n-VALUE = "before"\n+VALUE = "after"\n',
}, '2026-07-11T10:00:02Z');

const secondDiff = part('diff-002', {
  contract_version: 1,
  path: 'server/app.py',
  status: 'modified',
  additions: 1,
  deletions: 1,
  binary: false,
  truncated: false,
  write_sequence: 5,
  review_status: 'ready',
  unified_diff: '@@ -1 +1 @@\n-VALUE = "after"\n+VALUE = "ready"\n',
}, '2026-07-11T10:00:05Z');

const verification: AgentPart = {
  id: 'command-001',
  session_id: sessionId,
  type: 'command',
  status: 'completed',
  title: 'python -m py_compile server/app.py',
  content: 'Verification passed',
  payload: { command: 'python -m py_compile server/app.py', exit_code: 0, verification_for_write_sequence: 5 },
  created_at: '2026-07-11T10:00:06Z',
};

function baseSession(parts: AgentPart[]): AgentSession {
  return {
    id: sessionId,
    agent_id: 'build',
    status: 'completed',
    title: 'Review persisted diffs',
    project_path: 'C:/workspace/review-project',
    metadata: { state: { changed_files: ['server/app.py'], current_phase: 'completed' } },
    parts,
    preferences: { display_title: null, pinned: false, archived: false, updated_at: null },
    created_at: timestamp,
    updated_at: '2026-07-11T10:00:07Z',
  };
}

function workspaceFor(session: AgentSession): AgentWorkspace {
  return {
    session,
    status_text: { current_phase: 'completed' },
    timeline: [],
    pending_permission: null,
    diagnostics: {},
    async_tasks: { tasks: [], metrics: { total: 0, by_status: {}, running: 0, failed: 0, cancelled: 0, completed: 0, attention: 0, recovery_count: 0, event_count: 0 } },
    artifacts: [],
    changed_files: [{ path: 'server/app.py', status: 'modified', summary: 'Ready for review', source_part_id: 'diff-002' }],
    next_actions: [],
    recent_events: [],
  };
}

function event(id: string, sequencePart: AgentPart): AgentSessionEvent {
  return {
    id,
    session_id: sessionId,
    event_type: 'part_created',
    chunk_type: 'part_delta',
    message: 'Persisted Coding diff is ready for review',
    payload: { part_id: sequencePart.id, part_type: 'diff', part: sequencePart },
    part: sequencePart,
    created_at: sequencePart.created_at,
    session_status: 'running',
  };
}

const scenarios: Record<CodingDiffReviewScenario['id'], CodingDiffReviewScenario> = {
  'live-to-refresh': (() => {
    const persisted = baseSession([firstDiff, secondDiff, verification]);
    return { id: 'live-to-refresh', session: persisted, workspace: workspaceFor(persisted), events: [event('event-diff-001', firstDiff), event('event-diff-002', secondDiff)] };
  })(),
  'chronological-history': (() => {
    const persisted = baseSession([firstDiff, secondDiff, verification]);
    return { id: 'chronological-history', session: persisted, workspace: workspaceFor(persisted), events: [] };
  })(),
  'unknown-contract': (() => {
    const unknown = part('diff-unknown', { ...firstDiff.payload, contract_version: 2 }, '2026-07-11T10:00:08Z');
    const persisted = baseSession([unknown]);
    return { id: 'unknown-contract', session: persisted, workspace: workspaceFor(persisted), events: [] };
  })(),
};

export function codingDiffReviewScenario(id: CodingDiffReviewScenario['id']): CodingDiffReviewScenario {
  const scenario = scenarios[id];
  return {
    ...scenario,
    session: { ...scenario.session, metadata: { ...scenario.session.metadata }, parts: scenario.session.parts.map((item) => ({ ...item, payload: { ...item.payload } })) },
    workspace: { ...scenario.workspace, session: { ...scenario.workspace.session, parts: scenario.workspace.session.parts.map((item) => ({ ...item, payload: { ...item.payload } })) } },
    events: scenario.events.map((item) => ({ ...item, payload: { ...item.payload }, part: item.part && { ...item.part, payload: { ...item.part.payload } } })),
  };
}
