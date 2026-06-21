export interface AgentDiagnosticsEvent {
  id: string;
  sessionId: string | null;
  type: 'unknown_event' | 'parse_failure' | 'reconnect' | 'recovery_requested' | 'recovery_succeeded' | 'recovery_failed';
  occurredAt: string;
  detail?: string;
}

export interface AgentDiagnosticsSnapshot {
  version: 1;
  sessionId: string | null;
  protocolVersion: string;
  unknownEvents: number;
  parseFailures: number;
  reconnects: number;
  recoveryRequested: number;
  recoverySucceeded: number;
  recoveryFailed: number;
  attentionByKind: Record<string, number>;
  events: AgentDiagnosticsEvent[];
  updatedAt: string;
}

export const EMPTY_AGENT_DIAGNOSTICS: AgentDiagnosticsSnapshot = {
  version: 1,
  sessionId: null,
  protocolVersion: 'agent.session.v1',
  unknownEvents: 0,
  parseFailures: 0,
  reconnects: 0,
  recoveryRequested: 0,
  recoverySucceeded: 0,
  recoveryFailed: 0,
  attentionByKind: {},
  events: [],
  updatedAt: new Date(0).toISOString(),
};

const STORAGE_KEY = 'finetune.agent-workbench.diagnostics.v1';
const MAX_SESSIONS = 50;
const MAX_EVENTS = 100;

export function recordDiagnostic(
  snapshot: AgentDiagnosticsSnapshot,
  event: Omit<AgentDiagnosticsEvent, 'id' | 'occurredAt'> & { id?: string; occurredAt?: string },
): AgentDiagnosticsSnapshot {
  const occurredAt = event.occurredAt || new Date().toISOString();
  const next = {
    ...snapshot,
    sessionId: event.sessionId,
    updatedAt: occurredAt,
    events: [
      ...snapshot.events,
      {
        ...event,
        id: event.id || `${event.type}:${occurredAt}`,
        occurredAt,
      },
    ].slice(-MAX_EVENTS),
  };
  if (event.type === 'unknown_event') next.unknownEvents += 1;
  if (event.type === 'parse_failure') next.parseFailures += 1;
  if (event.type === 'reconnect') next.reconnects += 1;
  if (event.type === 'recovery_requested') next.recoveryRequested += 1;
  if (event.type === 'recovery_succeeded') next.recoverySucceeded += 1;
  if (event.type === 'recovery_failed') next.recoveryFailed += 1;
  return next;
}

export function readDiagnosticsHistory(
  storage: Pick<Storage, 'getItem'> | null = typeof localStorage === 'undefined' ? null : localStorage,
): AgentDiagnosticsSnapshot[] {
  if (!storage) return [];
  try {
    const value = JSON.parse(storage.getItem(STORAGE_KEY) || '[]');
    return Array.isArray(value) ? value.slice(-MAX_SESSIONS) : [];
  } catch {
    return [];
  }
}

export function persistDiagnosticsSnapshot(
  snapshot: AgentDiagnosticsSnapshot,
  storage: Pick<Storage, 'getItem' | 'setItem'> | null = typeof localStorage === 'undefined' ? null : localStorage,
): void {
  if (!storage || !snapshot.sessionId) return;
  try {
    const history = readDiagnosticsHistory(storage);
    const next = [
      ...history.filter((item) => item.sessionId !== snapshot.sessionId),
      snapshot,
    ].slice(-MAX_SESSIONS);
    storage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    // Diagnostics must never break the workbench.
  }
}
