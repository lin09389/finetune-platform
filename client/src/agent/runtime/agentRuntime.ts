import type {
  AgentInfo,
  AgentSession,
  AgentSessionEvent,
  AgentSessionPreferences,
  AgentWorkspace,
} from '../../services/api';
import {
  applyEventToSession,
  isKnownAgentEvent,
  toUnknownAgentEvent,
  type AgentConnectionState,
  type AgentUnknownEvent,
} from '../protocol/agentProtocol';
import {
  EMPTY_AGENT_DIAGNOSTICS,
  recordDiagnostic,
  type AgentDiagnosticsSnapshot,
} from '../diagnostics/agentDiagnostics';

export interface RecentAgentSession {
  id: string;
  title: string;
  displayTitle: string;
  status: AgentSession['status'];
  agentId: string;
  projectPath?: string;
  updatedAt: string;
  preferences: AgentSessionPreferences;
}

export interface AgentOperation {
  key: string;
  label: string;
  startedAt: number;
}

export interface AgentRuntimeState {
  agents: AgentInfo[];
  recentSessions: RecentAgentSession[];
  activeSessionId: string | null;
  session: AgentSession | null;
  workspace: AgentWorkspace | null;
  connection: AgentConnectionState;
  reconnectAttempt: number;
  lastEventId: string;
  seenEventIds: string[];
  unknownEvents: AgentUnknownEvent[];
  malformedEvents: string[];
  activeOperation: AgentOperation | null;
  operations: Record<string, AgentOperation>;
  error: string | null;
  hydrated: boolean;
  streamRevision: number;
  diagnostics: AgentDiagnosticsSnapshot;
}

export type AgentRuntimeAction =
  | { type: 'hydrate'; sessions: RecentAgentSession[]; activeSessionId: string | null }
  | { type: 'agents_loaded'; agents: AgentInfo[] }
  | { type: 'recent_sessions_loaded'; sessions: AgentSession[] }
  | { type: 'session_selected'; sessionId: string | null }
  | { type: 'workspace_loaded'; workspace: AgentWorkspace }
  | { type: 'session_loaded'; session: AgentSession }
  | { type: 'session_preferences_updated'; session: AgentSession }
  | { type: 'session_missing'; sessionId: string }
  | { type: 'stream_event'; event: AgentSessionEvent }
  | { type: 'connection_changed'; connection: AgentConnectionState; attempt: number }
  | { type: 'malformed_event'; raw: string }
  | { type: 'operation_started'; operation: AgentOperation }
  | { type: 'operation_finished'; key: string }
  | { type: 'stream_restart' }
  | { type: 'error'; message: string }
  | { type: 'clear_error' }
  | { type: 'reset_new_session' };

export const initialAgentRuntimeState: AgentRuntimeState = {
  agents: [],
  recentSessions: [],
  activeSessionId: null,
  session: null,
  workspace: null,
  connection: 'idle',
  reconnectAttempt: 0,
  lastEventId: '',
  seenEventIds: [],
  unknownEvents: [],
  malformedEvents: [],
  activeOperation: null,
  operations: {},
  error: null,
  hydrated: false,
  streamRevision: 0,
  diagnostics: EMPTY_AGENT_DIAGNOSTICS,
};

const MAX_SEEN_EVENTS = 2000;
const MAX_DIAGNOSTIC_EVENTS = 50;

function toRecentSession(session: AgentSession): RecentAgentSession {
  const preferences = session.preferences || {
    display_title: null,
    pinned: false,
    archived: false,
    updated_at: null,
  };
  return {
    id: session.id,
    title: session.title || '未命名任务',
    displayTitle: preferences.display_title || session.title || '未命名任务',
    status: session.status,
    agentId: session.agent_id,
    projectPath: session.project_path,
    updatedAt: session.updated_at,
    preferences,
  };
}

function mergeRecent(sessions: RecentAgentSession[], session: AgentSession): RecentAgentSession[] {
  return [
    toRecentSession(session),
    ...sessions.filter((item) => item.id !== session.id),
  ].slice(0, 20);
}

export function agentRuntimeReducer(
  state: AgentRuntimeState,
  action: AgentRuntimeAction,
): AgentRuntimeState {
  switch (action.type) {
    case 'hydrate':
      return { ...state, recentSessions: action.sessions, activeSessionId: action.activeSessionId, hydrated: true };
    case 'agents_loaded':
      return { ...state, agents: action.agents };
    case 'recent_sessions_loaded': {
      const recentSessions = action.sessions.reduce(
        (current, session) => mergeRecent(current, session),
        state.recentSessions,
      );
      return { ...state, recentSessions };
    }
    case 'session_missing': {
      const recentSessions = state.recentSessions.filter((session) => session.id !== action.sessionId);
      if (state.activeSessionId !== action.sessionId) return { ...state, recentSessions };
      return {
        ...state,
        recentSessions,
        activeSessionId: null,
        session: null,
        workspace: null,
        connection: 'idle',
        lastEventId: '',
        seenEventIds: [],
        unknownEvents: [],
        malformedEvents: [],
        error: null,
        streamRevision: state.streamRevision + 1,
        diagnostics: {
          ...EMPTY_AGENT_DIAGNOSTICS,
          sessionId: null,
          updatedAt: new Date().toISOString(),
        },
      };
    }
    case 'session_selected':
      return {
        ...state,
        activeSessionId: action.sessionId,
        session: action.sessionId === state.session?.id ? state.session : null,
        workspace: action.sessionId === state.workspace?.session.id ? state.workspace : null,
        lastEventId: '',
        seenEventIds: [],
        unknownEvents: [],
        malformedEvents: [],
        error: null,
        streamRevision: state.streamRevision + 1,
        diagnostics: {
          ...EMPTY_AGENT_DIAGNOSTICS,
          sessionId: action.sessionId,
          updatedAt: new Date().toISOString(),
        },
      };
    case 'workspace_loaded':
      return {
        ...state,
        activeSessionId: action.workspace.session.id,
        session: action.workspace.session,
        workspace: action.workspace,
        recentSessions: mergeRecent(state.recentSessions, action.workspace.session),
        diagnostics: {
          ...state.diagnostics,
          sessionId: action.workspace.session.id,
          updatedAt: action.workspace.session.updated_at,
        },
      };
    case 'session_loaded':
      return {
        ...state,
        activeSessionId: action.session.id,
        session: action.session,
        recentSessions: mergeRecent(state.recentSessions, action.session),
        error: null,
        diagnostics: {
          ...state.diagnostics,
          sessionId: action.session.id,
          updatedAt: action.session.updated_at,
        },
      };
    case 'session_preferences_updated':
      return {
        ...state,
        session: state.session?.id === action.session.id ? action.session : state.session,
        workspace: state.workspace?.session.id === action.session.id
          ? { ...state.workspace, session: action.session }
          : state.workspace,
        recentSessions: mergeRecent(state.recentSessions, action.session),
        error: null,
      };
    case 'stream_event': {
      const activeSessionId = state.session?.id || state.activeSessionId;
      if (activeSessionId && action.event.session_id !== activeSessionId) {
        return {
          ...state,
          diagnostics: recordDiagnostic(state.diagnostics, {
            sessionId: activeSessionId,
            type: 'unknown_event',
            detail: `ignored stale event for ${action.event.session_id}`,
            occurredAt: action.event.created_at,
            id: action.event.id,
          }),
        };
      }
      if (state.seenEventIds.includes(action.event.id)) return state;
      const seenEventIds = [...state.seenEventIds, action.event.id].slice(-MAX_SEEN_EVENTS);
      const session = applyEventToSession(state.session, action.event);
      const unknownEvents = isKnownAgentEvent(action.event.event_type)
        ? state.unknownEvents
        : [...state.unknownEvents, toUnknownAgentEvent(action.event)].slice(-MAX_DIAGNOSTIC_EVENTS);
      const diagnostics = !isKnownAgentEvent(action.event.event_type)
        ? recordDiagnostic(state.diagnostics, {
            sessionId: action.event.session_id,
            type: 'unknown_event',
            detail: action.event.event_type,
            occurredAt: action.event.created_at,
            id: action.event.id,
          })
        : action.event.event_type === 'node_recovery_requested'
          ? recordDiagnostic(state.diagnostics, {
              sessionId: action.event.session_id,
              type: 'recovery_requested',
              occurredAt: action.event.created_at,
              id: action.event.id,
            })
          : action.event.event_type === 'node_recovery_completed'
            ? recordDiagnostic(state.diagnostics, {
                sessionId: action.event.session_id,
                type: 'recovery_succeeded',
                occurredAt: action.event.created_at,
                id: action.event.id,
              })
            : action.event.event_type === 'node_recovery_failed'
              ? recordDiagnostic(state.diagnostics, {
                  sessionId: action.event.session_id,
                  type: 'recovery_failed',
                  occurredAt: action.event.created_at,
                  id: action.event.id,
                })
              : state.diagnostics;
      return {
        ...state,
        session,
        workspace: session && state.workspace
          ? { ...state.workspace, session }
          : state.workspace,
        recentSessions: session ? mergeRecent(state.recentSessions, session) : state.recentSessions,
        lastEventId: action.event.id || state.lastEventId,
        seenEventIds,
        unknownEvents,
        diagnostics,
      };
    }
    case 'connection_changed':
      return {
        ...state,
        connection: action.connection,
        reconnectAttempt: action.attempt,
        diagnostics: action.connection === 'reconnecting'
          ? recordDiagnostic(state.diagnostics, {
              sessionId: state.activeSessionId,
              type: 'reconnect',
              detail: String(action.attempt),
            })
          : state.diagnostics,
      };
    case 'malformed_event':
      return {
        ...state,
        malformedEvents: [...state.malformedEvents, action.raw.slice(0, 2000)].slice(-MAX_DIAGNOSTIC_EVENTS),
        diagnostics: recordDiagnostic(state.diagnostics, {
          sessionId: state.activeSessionId,
          type: 'parse_failure',
          detail: action.raw.slice(0, 120),
        }),
      };
    case 'operation_started':
      return {
        ...state,
        activeOperation: action.operation,
        operations: { ...state.operations, [action.operation.key]: action.operation },
        error: null,
      };
    case 'operation_finished': {
      const operations = { ...state.operations };
      delete operations[action.key];
      const remaining = Object.values(operations).sort((left, right) => right.startedAt - left.startedAt);
      return { ...state, operations, activeOperation: remaining[0] || null };
    }
    case 'stream_restart':
      return {
        ...state,
        connection: state.activeSessionId ? 'connecting' : 'idle',
        streamRevision: state.streamRevision + 1,
        diagnostics: {
          ...state.diagnostics,
          sessionId: state.activeSessionId,
          updatedAt: new Date().toISOString(),
        },
      };
    case 'error':
      return { ...state, error: action.message };
    case 'clear_error':
      return { ...state, error: null };
    case 'reset_new_session':
      return {
        ...state,
        activeSessionId: null,
        session: null,
        workspace: null,
        connection: 'idle',
        lastEventId: '',
        seenEventIds: [],
        unknownEvents: [],
        malformedEvents: [],
        activeOperation: null,
        operations: {},
        error: null,
        streamRevision: state.streamRevision + 1,
      };
    default:
      return state;
  }
}
