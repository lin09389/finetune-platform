import type {
  AgentPart,
  AgentSession,
  AgentSessionEvent,
  AgentSessionUiTimelineItem,
  AgentWorkspace,
} from '../../services/api';

export type AgentConnectionState =
  | 'idle'
  | 'connecting'
  | 'open'
  | 'reconnecting'
  | 'closed'
  | 'error';

/** The persisted Coding Agent review artifact contract. */
export const CODING_DIFF_CONTRACT_VERSION = 'coding_diff.v1' as const;

export type CodingDiffChangeKind = 'added' | 'modified' | 'deleted';

export interface CodingDiffReviewPayload {
  contractVersion: typeof CODING_DIFF_CONTRACT_VERSION;
  path: string;
  changeKind: CodingDiffChangeKind;
  additions: number;
  deletions: number;
  binary: boolean;
  truncated: boolean;
  writeSequence: number;
  reviewStatus: 'ready';
  unifiedDiff?: string;
}

export const TRAINING_TOOL_NAMES = new Set([
  'propose_training',
  'submit_training',
  'get_training_summary',
]);

export function isTrainingToolName(value: unknown): boolean {
  return typeof value === 'string' && TRAINING_TOOL_NAMES.has(value);
}

type TrainingActivityKind = 'proposal' | 'submission' | 'run_summary';
type TrainingActivitySourceTool = 'propose_training' | 'submit_training' | 'get_training_summary';

interface AgentTrainingActivityBase {
  kind: TrainingActivityKind;
  sourceTool: TrainingActivitySourceTool;
  status: string;
  summary: string;
  modelId?: string;
  datasetId?: string;
  method?: string;
}

export interface AgentTrainingProposalActivity extends AgentTrainingActivityBase {
  kind: 'proposal';
  sourceTool: 'propose_training';
  proposalId: string;
  blockers: string[];
  warnings: string[];
}

export interface AgentTrainingSubmissionActivity extends AgentTrainingActivityBase {
  kind: 'submission';
  sourceTool: 'submit_training';
  proposalId: string;
  taskId?: string;
}

export interface AgentTrainingRunSummaryActivity extends AgentTrainingActivityBase {
  kind: 'run_summary';
  sourceTool: 'get_training_summary';
  taskId: string;
  taskGoal?: string;
  finalLoss?: number;
  phase?: string;
  step?: number;
  totalSteps?: number;
  epoch?: number;
  loss?: number;
  elapsedSeconds?: number;
  etaSeconds?: number;
  updatedAt?: string;
  artifactAvailable?: boolean;
}

export type AgentTrainingActivity =
  | AgentTrainingProposalActivity
  | AgentTrainingSubmissionActivity
  | AgentTrainingRunSummaryActivity;

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function nonEmptyString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

function optionalString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined;
}

function stringList(value: unknown): string[] | null {
  if (!Array.isArray(value)) return null;
  const values = value.map((entry) => nonEmptyString(entry));
  return values.every((entry): entry is string => entry !== null) ? values : null;
}

function optionalFiniteNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function optionalNonEmptyStringField(
  record: Record<string, unknown>,
  key: string,
): string | undefined | null {
  if (!(key in record)) return undefined;
  return nonEmptyString(record[key]);
}

function optionalNonNegativeNumberField(
  record: Record<string, unknown>,
  key: string,
): number | undefined | null {
  if (!(key in record)) return undefined;
  const value = optionalFiniteNumber(record[key]);
  return value !== undefined && value >= 0 ? value : null;
}

function optionalBooleanField(
  record: Record<string, unknown>,
  key: string,
): boolean | undefined | null {
  if (!(key in record)) return undefined;
  return typeof record[key] === 'boolean' ? record[key] : null;
}

function isWorkspaceRelativePath(value: string): boolean {
  const normalized = value.replace(/\\/g, '/');
  return (
    Boolean(normalized) &&
    !normalized.startsWith('/') &&
    !/^[a-zA-Z]:\//.test(normalized) &&
    !normalized.split('/').some((segment) => segment === '..')
  );
}

/**
 * Decodes only the immutable, versioned Coding Agent diff review contract.
 * Older diff parts deliberately return null so callers retain the generic
 * artifact fallback instead of guessing at an unversioned payload.
 */
export function selectCodingDiffReviewPayload(
  item: Pick<AgentSessionUiTimelineItem, 'type' | 'payload'>,
): CodingDiffReviewPayload | null {
  if (item.type !== 'diff' || !isRecord(item.payload)) return null;
  const payload = item.payload;
  if (payload.contract_version !== CODING_DIFF_CONTRACT_VERSION) return null;

  const path = nonEmptyString(payload.path);
  const changeKind = payload.change_kind;
  const additions = optionalNonNegativeNumberField(payload, 'additions');
  const deletions = optionalNonNegativeNumberField(payload, 'deletions');
  const binary = optionalBooleanField(payload, 'binary');
  const truncated = optionalBooleanField(payload, 'truncated');
  const writeSequence = optionalNonNegativeNumberField(payload, 'write_sequence');
  const reviewStatus = payload.review_status;
  const unifiedDiff = payload.unified_diff;

  if (
    !path ||
    !isWorkspaceRelativePath(path) ||
    !['added', 'modified', 'deleted'].includes(String(changeKind)) ||
    additions === undefined ||
    additions === null ||
    deletions === undefined ||
    deletions === null ||
    binary === undefined ||
    binary === null ||
    truncated === undefined ||
    truncated === null ||
    writeSequence === undefined ||
    writeSequence === null ||
    reviewStatus !== 'ready' ||
    (unifiedDiff !== undefined && typeof unifiedDiff !== 'string')
  ) {
    return null;
  }

  return {
    contractVersion: CODING_DIFF_CONTRACT_VERSION,
    path,
    changeKind: changeKind as CodingDiffChangeKind,
    additions,
    deletions,
    binary,
    truncated,
    writeSequence,
    reviewStatus: 'ready',
    unifiedDiff,
  };
}

/**
 * Selects the server's persisted training projection without interpreting raw
 * tool output. Unknown or malformed values intentionally return null so the
 * timeline keeps its established generic-tool fallback.
 */
export function selectTrainingActivity(
  item: Pick<AgentSessionUiTimelineItem, 'payload'>,
): AgentTrainingActivity | null {
  const payload = isRecord(item.payload) ? item.payload : null;
  const candidate =
    payload && isRecord(payload.training_activity) ? payload.training_activity : null;
  if (!candidate) return null;

  const kind = candidate.kind;
  const sourceTool = candidate.source_tool;
  const status = nonEmptyString(candidate.status);
  const summary = nonEmptyString(candidate.summary);
  if (!status || !summary) return null;

  const shared = {
    status,
    summary,
    modelId: optionalString(candidate.model_id),
    datasetId: optionalString(candidate.dataset_id),
    method: optionalString(candidate.method),
  };

  if (kind === 'proposal' && sourceTool === 'propose_training') {
    const proposalId = nonEmptyString(candidate.proposal_id);
    const blockers = stringList(candidate.blockers);
    const warnings = stringList(candidate.warnings);
    if (!proposalId || !blockers || !warnings) return null;
    return { kind, sourceTool, proposalId, blockers, warnings, ...shared };
  }

  if (kind === 'submission' && sourceTool === 'submit_training') {
    const proposalId = nonEmptyString(candidate.proposal_id);
    if (!proposalId) return null;
    return {
      kind,
      sourceTool,
      proposalId,
      taskId: optionalString(candidate.task_id),
      ...shared,
    };
  }

  if (kind === 'run_summary' && sourceTool === 'get_training_summary') {
    const taskId = nonEmptyString(candidate.task_id);
    const finalLoss = optionalNonNegativeNumberField(candidate, 'final_loss');
    const phase = optionalNonEmptyStringField(candidate, 'phase');
    const step = optionalNonNegativeNumberField(candidate, 'step');
    const totalSteps = optionalNonNegativeNumberField(candidate, 'total_steps');
    const epoch = optionalNonNegativeNumberField(candidate, 'epoch');
    const loss = optionalNonNegativeNumberField(candidate, 'loss');
    const elapsedSeconds = optionalNonNegativeNumberField(candidate, 'elapsed_time');
    const etaSeconds = optionalNonNegativeNumberField(candidate, 'eta');
    const updatedAt = optionalNonEmptyStringField(candidate, 'updated_at');
    const artifactAvailable = optionalBooleanField(candidate, 'artifact_available');
    if (
      !taskId ||
      finalLoss === null ||
      phase === null ||
      step === null ||
      totalSteps === null ||
      epoch === null ||
      loss === null ||
      elapsedSeconds === null ||
      etaSeconds === null ||
      updatedAt === null ||
      artifactAvailable === null
    )
      return null;
    return {
      kind,
      sourceTool,
      taskId,
      taskGoal: optionalString(candidate.task_goal),
      finalLoss,
      phase,
      step,
      totalSteps,
      epoch,
      loss,
      elapsedSeconds,
      etaSeconds,
      updatedAt,
      artifactAvailable,
      ...shared,
    };
  }

  return null;
}

export interface AgentUnknownEvent {
  id: string;
  eventType: string;
  message: string;
  payload: Record<string, unknown>;
  createdAt: string;
}

export interface AgentTaskContextEvent {
  workspaceId?: string;
  workspaceLabel: string;
  taskMode?: 'build' | 'train' | 'hybrid';
}

const KNOWN_EVENT_TYPES = new Set([
  'session_snapshot',
  'session_started',
  'session_completed',
  'session_failed',
  'session_blocked',
  'session_interrupted',
  'prompt_queued',
  'prompt_already_running',
  'phase_change',
  'model_stream_started',
  'model_stream_completed',
  'model_stream_failed',
  'part_delta',
  'tool_call_started',
  'tool_call_completed',
  'tool_call_failed',
  'permission_asked',
  'permission_decided',
  'summary_completed',
  'chain_completed',
  'command_started',
  'command_output',
  'command_completed',
  'command_failed',
  'action_proposed',
  'action_approved',
  'action_rejected',
  'action_executed',
  'action_failed',
  'async_subtask_started',
  'async_subtask_updated',
  'async_subtask_completed',
  'async_subtask_failed',
  'async_subtask_cancelled',
  'node_recovery_requested',
  'node_recovery_started',
  'node_recovery_completed',
  'node_recovery_failed',
  'node_recovery_rejected',
  'loop_guard_triggered',
  'trajectory_guard_blocked',
  'context_preparing',
  'context_ready',
  'session_title_updated',
  'task_context_initialized',
  // Historical events remain readable after the execution-plan migration.
  'task_plan_created',
  'part_created',
  'agent_chain_failed',
]);

export function isAgentSession(value: unknown): value is AgentSession {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Partial<AgentSession>;
  return (
    typeof candidate.id === 'string' &&
    typeof candidate.agent_id === 'string' &&
    typeof candidate.status === 'string' &&
    Array.isArray(candidate.parts)
  );
}

export function isAgentPart(value: unknown): value is AgentPart {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Partial<AgentPart>;
  return (
    typeof candidate.id === 'string' &&
    typeof candidate.session_id === 'string' &&
    typeof candidate.type === 'string' &&
    typeof candidate.created_at === 'string'
  );
}

export function isAgentWorkspace(value: unknown): value is AgentWorkspace {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Partial<AgentWorkspace>;
  return (
    isAgentSession(candidate.session) &&
    Array.isArray(candidate.timeline) &&
    Array.isArray(candidate.artifacts) &&
    Array.isArray(candidate.changed_files) &&
    Array.isArray(candidate.next_actions)
  );
}

export function decodeAgentSessionEvent(value: unknown): AgentSessionEvent | null {
  if (!value || typeof value !== 'object') return null;
  const candidate = value as Partial<AgentSessionEvent>;
  if (
    typeof candidate.id !== 'string' ||
    typeof candidate.session_id !== 'string' ||
    typeof candidate.event_type !== 'string'
  ) {
    return null;
  }
  return {
    id: candidate.id,
    session_id: candidate.session_id,
    event_type: candidate.event_type,
    chunk_type: candidate.chunk_type,
    message: typeof candidate.message === 'string' ? candidate.message : '',
    payload: candidate.payload && typeof candidate.payload === 'object' ? candidate.payload : {},
    created_at:
      typeof candidate.created_at === 'string' ? candidate.created_at : new Date().toISOString(),
    session_status: candidate.session_status,
    agent_id: candidate.agent_id,
    phase: candidate.phase,
    tool: candidate.tool,
    agent_name: candidate.agent_name,
    agent_role: candidate.agent_role,
    task_id: candidate.task_id,
    child_session_id: candidate.child_session_id,
    async_status: candidate.async_status,
    health_status: candidate.health_status,
    delta: candidate.delta,
    content: candidate.content,
    summary: candidate.summary,
    part: isAgentPart(candidate.part) ? candidate.part : null,
    session_snapshot: candidate.session_snapshot,
  };
}

export function isKnownAgentEvent(eventType: string): boolean {
  return KNOWN_EVENT_TYPES.has(eventType);
}

/** Decode the display-safe context event without falling back to a raw path. */
export function taskContextFromEvent(event: AgentSessionEvent): AgentTaskContextEvent | null {
  if (event.event_type !== 'task_context_initialized') return null;
  const workspaceLabel =
    typeof event.payload?.workspace_label === 'string' ? event.payload.workspace_label.trim() : '';
  if (!workspaceLabel) return null;
  const taskMode = event.payload?.task_mode;
  return {
    workspaceId:
      typeof event.payload?.workspace_id === 'string' ? event.payload.workspace_id : undefined,
    workspaceLabel,
    taskMode:
      taskMode === 'build' || taskMode === 'train' || taskMode === 'hybrid' ? taskMode : undefined,
  };
}

export function toUnknownAgentEvent(event: AgentSessionEvent): AgentUnknownEvent {
  return {
    id: event.id,
    eventType: event.event_type,
    message: event.message,
    payload: event.payload,
    createdAt: event.created_at,
  };
}

export function mergeAgentPart(parts: AgentPart[], incoming: AgentPart): AgentPart[] {
  const index = parts.findIndex((part) => part.id === incoming.id);
  if (index === -1) return [...parts, incoming];
  const next = [...parts];
  next[index] = {
    ...parts[index],
    ...incoming,
    payload: { ...(parts[index]?.payload || {}), ...(incoming.payload || {}) },
  };
  return next;
}

function payloadAgentPart(event: AgentSessionEvent): AgentPart | null {
  const payloadPart = event.payload?.part;
  return isAgentPart(payloadPart) ? payloadPart : null;
}

function mergedDeltaContent(current: string, event: AgentSessionEvent): string {
  const snapshotContent = event.part?.content ?? payloadAgentPart(event)?.content;
  if (typeof snapshotContent === 'string') return snapshotContent;

  if (typeof event.content === 'string') {
    if (event.payload?.streaming === true) return event.content;
    if (!current || event.content.startsWith(current)) return event.content;
    if (event.delta && event.content !== event.delta) return event.content;
  }

  const delta = event.delta ?? event.content ?? '';
  return delta ? `${current}${delta}` : current;
}

function partFromDeltaEvent(event: AgentSessionEvent, partId: string): AgentPart {
  const payloadPart = payloadAgentPart(event);
  const content = mergedDeltaContent('', event);
  return {
    id: partId,
    session_id: event.session_id,
    type: payloadPart?.type || 'text',
    status: payloadPart?.status || 'running',
    title: payloadPart?.title || '生成中',
    content,
    payload: {
      ...(payloadPart?.payload || {}),
      ...(event.payload || {}),
      streaming: true,
    },
    created_at: payloadPart?.created_at || event.created_at,
    updated_at: event.created_at,
  };
}

export function applyEventToSession(
  session: AgentSession | null,
  event: AgentSessionEvent,
): AgentSession | null {
  if (isAgentSession(event.session_snapshot)) return event.session_snapshot;
  if (!session || event.session_id !== session.id) return session;

  let parts = session.parts;
  if (event.part) {
    parts = mergeAgentPart(parts, event.part);
  } else if (
    (event.chunk_type === 'part_delta' || event.event_type === 'part_delta') &&
    event.payload?.part_id
  ) {
    const partId = String(event.payload.part_id);
    let matched = false;
    parts = parts.map((part) => {
      if (part.id !== partId) return part;
      matched = true;
      const payloadPart = payloadAgentPart(event);
      return {
        ...part,
        ...payloadPart,
        content: mergedDeltaContent(part.content || '', event),
        payload: { ...(part.payload || {}), ...(payloadPart?.payload || {}) },
        updated_at: event.created_at,
      };
    });
    if (!matched) parts = mergeAgentPart(parts, partFromDeltaEvent(event, partId));
  }

  return {
    ...session,
    status: event.session_status || session.status,
    parts,
    updated_at: event.created_at || session.updated_at,
    metadata: {
      ...session.metadata,
      state: {
        ...session.metadata?.state,
        current_phase: event.phase || session.metadata?.state?.current_phase,
      },
    },
  };
}
