import type {
  AgentInfo,
  AgentSession,
  AgentSessionCreate,
  AgentSessionEvent,
  AgentSessionPreferences,
  AgentSessionUiTimelineItem,
  AgentWorkspace,
} from '../../services/api';
import {
  applyEventToSession,
  isKnownAgentEvent,
  taskContextFromEvent,
  toUnknownAgentEvent,
  type AgentConnectionState,
  type AgentUnknownEvent,
} from '../protocol/agentProtocol';
import {
  EMPTY_AGENT_DIAGNOSTICS,
  recordDiagnostic,
  type AgentDiagnosticsSnapshot,
} from '../diagnostics/agentDiagnostics';
import { activityFromEvent, type AgentActivity } from '../selectors/currentActivity';

export type TaskMode = NonNullable<AgentSessionCreate['task_mode']>;

export interface SelectedWorkspace {
  id: string;
  label: string;
  projectPath: string;
}

export interface RecentAgentSession {
  id: string;
  title: string;
  displayTitle: string;
  status: AgentSession['status'];
  agentId: string;
  projectPath?: string;
  taskMode?: AgentSession['task_mode'];
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
  taskContextTimeline: AgentSessionUiTimelineItem[];
  selectedWorkspace: SelectedWorkspace | null;
  taskMode: TaskMode;
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
  /** Agent 执行中的即时活动摘要，由 SSE 事件派生 */
  currentActivity: AgentActivity | null;
  /** SSE 重连恢复同步的时间戳，用于短暂提示用户 */
  recoveredAt: number | null;
  /** 最近一次 SSE 事件到达时间戳，用于活跃度/心跳感知 */
  lastEventAt: number | null;
  /** 全局事件流连接状态（多会话感知） */
  globalConnection: AgentConnectionState;
  /** 有未读事件的非活跃会话 ID 集合 */
  unreadSessionIds: string[];
}

export type AgentRuntimeAction =
  | { type: 'hydrate'; sessions: RecentAgentSession[]; activeSessionId: string | null }
  | { type: 'agents_loaded'; agents: AgentInfo[] }
  | { type: 'recent_sessions_loaded'; sessions: AgentSession[] }
  | { type: 'session_selected'; sessionId: string | null }
  | { type: 'workspace_loaded'; workspace: AgentWorkspace }
  | { type: 'task_context_changed'; workspace: SelectedWorkspace | null; taskMode: TaskMode }
  | { type: 'session_loaded'; session: AgentSession }
  | { type: 'session_preferences_updated'; session: AgentSession }
  | { type: 'session_missing'; sessionId: string }
  | { type: 'stream_event'; event: AgentSessionEvent }
  | { type: 'global_stream_event'; event: AgentSessionEvent }
  | { type: 'global_connection_changed'; connection: AgentConnectionState; attempt: number }
  | { type: 'clear_unread'; sessionId: string }
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
  taskContextTimeline: [],
  selectedWorkspace: null,
  taskMode: 'build',
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
  currentActivity: null,
  recoveredAt: null,
  lastEventAt: null,
  globalConnection: 'idle',
  unreadSessionIds: [],
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
    taskMode: session.task_mode,
    updatedAt: session.updated_at,
    preferences,
  };
}

function taskContextTimelineItem(event: AgentSessionEvent): AgentSessionUiTimelineItem | null {
  const context = taskContextFromEvent(event);
  if (!context) return null;
  const modeLabel = context.taskMode
    ? context.taskMode.charAt(0).toUpperCase() + context.taskMode.slice(1)
    : '任务';
  return {
    id: `task-context:${event.id}`,
    session_id: event.session_id,
    type: 'task_context',
    status: 'completed',
    title: '任务上下文',
    content: `工作区：${context.workspaceLabel} · ${modeLabel}`,
    created_at: event.created_at,
    payload: {
      workspace_id: context.workspaceId,
      workspace_label: context.workspaceLabel,
      task_mode: context.taskMode,
    },
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
        taskContextTimeline: [],
        connection: 'idle',
        lastEventId: '',
        lastEventAt: null,
        seenEventIds: [],
        unknownEvents: [],
        malformedEvents: [],
        error: null,
        currentActivity: null,
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
        taskContextTimeline: [],
        lastEventId: '',
        lastEventAt: null,
        seenEventIds: [],
        unknownEvents: [],
        malformedEvents: [],
        error: null,
        currentActivity: null,
        unreadSessionIds: action.sessionId
          ? state.unreadSessionIds.filter((id) => id !== action.sessionId)
          : state.unreadSessionIds,
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
    case 'task_context_changed':
      return {
        ...state,
        selectedWorkspace: action.workspace,
        taskMode: action.taskMode,
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
      const taskContextItem = taskContextTimelineItem(action.event);
      const taskContextTimeline = taskContextItem
        ? [
            ...state.taskContextTimeline.filter((item) => item.id !== taskContextItem.id),
            taskContextItem,
          ]
        : state.taskContextTimeline;
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
      const activityUpdate = activityFromEvent(action.event, Date.now());
      const currentActivity = activityUpdate === null
        ? state.currentActivity
        : activityUpdate ?? null;
      return {
        ...state,
        session,
        workspace: session && state.workspace
          ? { ...state.workspace, session }
          : state.workspace,
        taskContextTimeline,
        recentSessions: session ? mergeRecent(state.recentSessions, session) : state.recentSessions,
        lastEventId: action.event.id || state.lastEventId,
        lastEventAt: Date.now(),
        seenEventIds,
        unknownEvents,
        diagnostics,
        currentActivity,
      };
    }
    case 'connection_changed': {
      const wasReconnecting = state.connection === 'reconnecting' || state.reconnectAttempt > 0;
      const recovered = wasReconnecting && action.connection === 'open';
      return {
        ...state,
        connection: action.connection,
        reconnectAttempt: action.attempt,
        recoveredAt: recovered ? Date.now() : state.recoveredAt,
        diagnostics: action.connection === 'reconnecting'
          ? recordDiagnostic(state.diagnostics, {
              sessionId: state.activeSessionId,
              type: 'reconnect',
              detail: String(action.attempt),
            })
          : state.diagnostics,
      };
    }
    case 'global_connection_changed': {
      return {
        ...state,
        globalConnection: action.connection,
      };
    }
    case 'global_stream_event': {
      const eventSessionId = action.event.session_id;
      // Skip events for the active session (already handled by stream_event).
      if (!eventSessionId || eventSessionId === state.session?.id) return state;

      // Update the recentSessions entry's status/title if present.
      const sessionStatus = action.event.session_status;
      const titlePayload = action.event.payload?.title as string | undefined;
      const eventType = action.event.event_type;
      const recentSessions = state.recentSessions.map((item) => {
        if (item.id !== eventSessionId) return item;
        return {
          ...item,
          status: (sessionStatus || item.status) as typeof item.status,
          title: (eventType === 'session_title_updated' && titlePayload) ? titlePayload : item.title,
          displayTitle: (eventType === 'session_title_updated' && titlePayload)
            ? (item.preferences.display_title || titlePayload)
            : item.displayTitle,
          updatedAt: action.event.created_at || item.updatedAt,
        };
      });

      // Mark as unread if the event is significant (not just part_delta/streaming).
      const significant = !['part_delta', 'model_stream_started', 'model_stream_completed', 'model_stream_failed'].includes(eventType);
      const unreadSessionIds = significant && !state.unreadSessionIds.includes(eventSessionId)
        ? [...state.unreadSessionIds, eventSessionId]
        : state.unreadSessionIds;

      return { ...state, recentSessions, unreadSessionIds };
    }
    case 'clear_unread': {
      return {
        ...state,
        unreadSessionIds: state.unreadSessionIds.filter((id) => id !== action.sessionId),
      };
    }
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
        taskContextTimeline: [],
        connection: 'idle',
        lastEventId: '',
        lastEventAt: null,
        seenEventIds: [],
        unknownEvents: [],
        malformedEvents: [],
        activeOperation: null,
        operations: {},
        error: null,
        currentActivity: null,
        streamRevision: state.streamRevision + 1,
      };
    default:
      return state;
  }
}
