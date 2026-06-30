import { useCallback, useEffect, useMemo, useReducer, useRef } from 'react';
import type {
  AgentExecutionPlanNode,
  AgentHitlDecision,
  AgentSessionPreferencesUpdate,
} from '../../services/api';
import {
  AgentCommandExecutor,
  AgentCommandFailure,
  agentCommandKey,
  commandLabel,
  type AgentCommand,
  type AgentCommandResult,
  type SubmitAgentTaskOptions,
} from '../commands/agentCommands';
import { agentTransport, type AgentTransport } from '../transport/agentTransport';
import { agentRuntimeReducer, initialAgentRuntimeState } from './agentRuntime';
import { persistAgentRuntime, readPersistedAgentRuntime } from './sessionPersistence';
import { persistDiagnosticsSnapshot } from '../diagnostics/agentDiagnostics';
import { selectAttentionItems } from '../attention/selectAttentionItems';

const REFRESH_EVENT_TYPES = new Set([
  'session_snapshot',
  'session_completed',
  'session_failed',
  'session_interrupted',
  'permission_asked',
  'permission_decided',
  'tool_call_completed',
  'tool_call_failed',
  'summary_completed',
  'async_subtask_completed',
  'async_subtask_failed',
  'async_subtask_cancelled',
  'node_recovery_started',
  'node_recovery_completed',
  'node_recovery_failed',
  'loop_guard_triggered',
]);

function errorMessage(error: unknown): string {
  if (error instanceof AgentCommandFailure) {
    const cause = errorMessage(error.originalCause);
    return error.originalCause && cause !== '操作失败'
      ? `${error.message} ${cause}`
      : error.message;
  }
  if (typeof error === 'string') return error;
  if (error && typeof error === 'object') {
    const candidate = error as {
      message?: string;
      response?: { data?: { detail?: string } };
    };
    return candidate.response?.data?.detail || candidate.message || '操作失败';
  }
  return '操作失败';
}

function isMissingSessionError(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false;
  const candidate = error as {
    message?: string;
    response?: { status?: number; data?: { detail?: string } };
  };
  const detail = String(candidate.response?.data?.detail || candidate.message || '').toLowerCase();
  return candidate.response?.status === 404 || detail.includes('session not found');
}

export interface AgentRuntimePersistence {
  read: typeof readPersistedAgentRuntime;
  write: typeof persistAgentRuntime;
}

const browserPersistence: AgentRuntimePersistence = {
  read: readPersistedAgentRuntime,
  write: persistAgentRuntime,
};

export function useAgentWorkbench(
  transport: AgentTransport = agentTransport,
  persistence: AgentRuntimePersistence = browserPersistence,
) {
  const [state, dispatch] = useReducer(agentRuntimeReducer, initialAgentRuntimeState);
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const refreshGenerationRef = useRef(0);
  const navigationGenerationRef = useRef(0);
  const activeSessionIdRef = useRef<string | null>(null);
  const lastEventIdRef = useRef('');
  const executor = useMemo(() => new AgentCommandExecutor(transport), [transport]);
  lastEventIdRef.current = state.lastEventId;
  activeSessionIdRef.current = state.activeSessionId;

  const refreshWorkspace = useCallback(async (sessionId: string) => {
    const generation = ++refreshGenerationRef.current;
    try {
      const workspace = await transport.getWorkspace(sessionId);
      if (
        generation === refreshGenerationRef.current
        && activeSessionIdRef.current === sessionId
      ) {
        dispatch({ type: 'workspace_loaded', workspace });
      }
      return workspace;
    } catch (error) {
      if (isMissingSessionError(error)) {
        if (
          generation === refreshGenerationRef.current
          && activeSessionIdRef.current === sessionId
        ) {
          dispatch({ type: 'session_missing', sessionId });
        }
        return null;
      }
      if (
        generation === refreshGenerationRef.current
        && activeSessionIdRef.current === sessionId
      ) {
        dispatch({ type: 'error', message: errorMessage(error) });
      }
      throw error;
    }
  }, [transport]);

  const scheduleWorkspaceRefresh = useCallback((sessionId: string, delay = 180) => {
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    refreshTimerRef.current = setTimeout(() => {
      void refreshWorkspace(sessionId).catch(() => undefined);
    }, delay);
  }, [refreshWorkspace]);

  useEffect(() => {
    const persisted = persistence.read();
    dispatch({
      type: 'hydrate',
      sessions: persisted.sessions,
      activeSessionId: persisted.activeSessionId,
    });
    void Promise.allSettled([transport.listAgents(), transport.listSessions(100)])
      .then(([agentsResult, sessionsResult]) => {
        dispatch({
          type: 'agents_loaded',
          agents: agentsResult.status === 'fulfilled'
            ? agentsResult.value.filter((agent) => !agent.hidden)
            : [],
        });
        if (sessionsResult.status === 'fulfilled') {
          dispatch({ type: 'recent_sessions_loaded', sessions: sessionsResult.value });
        }
      });
  }, [persistence, transport]);

  useEffect(() => {
    if (!state.hydrated) return;
    persistence.write({
      activeSessionId: state.activeSessionId,
      sessions: state.recentSessions,
    });
  }, [persistence, state.activeSessionId, state.hydrated, state.recentSessions]);

  useEffect(() => {
    if (!state.hydrated || !state.diagnostics.sessionId) return;
    const attentionByKind = selectAttentionItems(state).reduce<Record<string, number>>((counts, item) => {
      counts[item.kind] = (counts[item.kind] || 0) + 1;
      return counts;
    }, {});
    const snapshot = { ...state.diagnostics, attentionByKind };
    persistDiagnosticsSnapshot(snapshot);
    const timer = setTimeout(() => {
      void transport.reportDiagnostics([snapshot]).catch(() => undefined);
    }, 500);
    return () => clearTimeout(timer);
  }, [state, transport]);

  useEffect(() => {
    if (!state.hydrated || !state.activeSessionId) return;
    void refreshWorkspace(state.activeSessionId).catch(() => undefined);
  }, [refreshWorkspace, state.activeSessionId, state.hydrated]);

  useEffect(() => {
    if (!state.activeSessionId) return;
    const sessionId = state.activeSessionId;
    const subscription = transport.connectStream(sessionId, lastEventIdRef.current, {
      onConnectionChange: (connection, attempt) => {
        dispatch({ type: 'connection_changed', connection, attempt });
      },
      onEvent: (event) => {
        dispatch({ type: 'stream_event', event });
        if (REFRESH_EVENT_TYPES.has(event.event_type)) {
          scheduleWorkspaceRefresh(sessionId);
        }
      },
      onDone: () => scheduleWorkspaceRefresh(sessionId, 0),
      onMalformedEvent: (raw) => dispatch({ type: 'malformed_event', raw }),
    });
    return () => subscription.close();
  }, [scheduleWorkspaceRefresh, state.activeSessionId, state.streamRevision, transport]);

  useEffect(() => () => {
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
  }, []);

  const selectSession = useCallback((sessionId: string) => {
    navigationGenerationRef.current += 1;
    refreshGenerationRef.current += 1;
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    dispatch({ type: 'session_selected', sessionId });
  }, []);

  const newSession = useCallback(() => {
    navigationGenerationRef.current += 1;
    refreshGenerationRef.current += 1;
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    dispatch({ type: 'reset_new_session' });
  }, []);

  const applyCommandResult = useCallback(async (result: AgentCommandResult) => {
    if ('session' in result) {
      dispatch({ type: 'session_loaded', session: result.session });
    } else if (result.type === 'decide_permission') {
      dispatch({ type: 'session_loaded', session: result.response.session });
    } else if ('workspace' in result) {
      dispatch({ type: 'workspace_loaded', workspace: result.workspace });
    }

    if (result.restartStream) {
      dispatch({ type: 'stream_restart' });
    }
    if ('refreshSessionId' in result) {
      await refreshWorkspace(result.refreshSessionId);
    }
    return result;
  }, [refreshWorkspace]);

  const executeCommand = useCallback(async (command: AgentCommand) => {
    const key = agentCommandKey(command);
    const navigationGeneration = navigationGenerationRef.current;
    dispatch({
      type: 'operation_started',
      operation: { key, label: commandLabel(command), startedAt: Date.now() },
    });
    try {
      const result = await executor.execute(command);
      if (navigationGeneration !== navigationGenerationRef.current) return result;
      return await applyCommandResult(result);
    } catch (error) {
      if (navigationGeneration !== navigationGenerationRef.current) throw error;
      if (error instanceof AgentCommandFailure && error.partialSession) {
        dispatch({ type: 'session_loaded', session: error.partialSession });
        dispatch({ type: 'stream_restart' });
      }
      dispatch({ type: 'error', message: errorMessage(error) });
      throw error;
    } finally {
      dispatch({ type: 'operation_finished', key });
    }
  }, [applyCommandResult, executor]);

  const submitTask = useCallback(async (options: SubmitAgentTaskOptions) => {
    const content = options.content.trim();
    if (!content) return null;
    return executeCommand({
      type: 'submit',
      currentSession: state.session,
      options: { ...options, content },
    });
  }, [executeCommand, state.session]);

  const interrupt = useCallback(async () => {
    if (!state.activeSessionId) return null;
    return executeCommand({ type: 'interrupt', sessionId: state.activeSessionId });
  }, [executeCommand, state.activeSessionId]);

  const decidePermission = useCallback(async (partId: string, decisions: AgentHitlDecision[]) => {
    return executeCommand({ type: 'decide_permission', partId, decisions });
  }, [executeCommand]);

  const recoverNode = useCallback(async (
    node: AgentExecutionPlanNode,
    instruction?: string,
  ) => {
    if (!state.activeSessionId) return null;
    return executeCommand({
      type: 'recover_node',
      sessionId: state.activeSessionId,
      node,
      instruction,
    });
  }, [executeCommand, state.activeSessionId]);

  const startSubagent = useCallback(async (agentName: string, description: string) => {
    if (!state.activeSessionId) return null;
    return executeCommand({
      type: 'start_subtask',
      sessionId: state.activeSessionId,
      agentName,
      description,
    });
  }, [executeCommand, state.activeSessionId]);

  const cancelSubagent = useCallback(async (taskId: string) => {
    if (!state.activeSessionId) return null;
    return executeCommand({
      type: 'cancel_subtask',
      sessionId: state.activeSessionId,
      taskId,
    });
  }, [executeCommand, state.activeSessionId]);

  const refresh = useCallback(() => {
    if (!state.activeSessionId) return Promise.resolve(null);
    return executeCommand({ type: 'refresh', sessionId: state.activeSessionId });
  }, [executeCommand, state.activeSessionId]);

  const updateSessionPreferences = useCallback(async (
    sessionId: string,
    payload: AgentSessionPreferencesUpdate,
  ) => {
    const session = await transport.updateSessionPreferences(sessionId, payload);
    dispatch({ type: 'session_preferences_updated', session });
    return session;
  }, [transport]);

  return {
    state,
    actions: {
      selectSession,
      newSession,
      refresh,
      submitTask,
      interrupt,
      decidePermission,
      recoverNode,
      startSubagent,
      cancelSubagent,
      updateSessionPreferences,
      clearError: () => dispatch({ type: 'clear_error' }),
    },
  };
}
