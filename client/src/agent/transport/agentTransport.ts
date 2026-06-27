import {
  approveAgentPermission,
  cancelAgentAsyncTask,
  createAgentSession,
  decideAgentPermission,
  getAgentSession,
  listAgentSessions,
  getAgentWorkspace,
  getAgents,
  interruptAgentSession,
  promptAgentSession,
  recoverAgentExecutionPlanNode,
  rejectAgentPermission,
  startAgentAsyncTask,
  updateAgentSessionPreferences,
  type AgentHitlDecision,
  type AgentPromptRequest,
  type AgentSession,
  type AgentSessionCreate,
  type AgentSessionPreferencesUpdate,
  type AgentWorkspace,
  reportAgentDiagnostics,
} from '../../services/api';
import { buildAgentSessionStreamUrl, getAgentStreamRetryDelay } from '../../utils/agentSessionStream';
import { decodeAgentSessionEvent, type AgentConnectionState } from '../protocol/agentProtocol';

export interface AgentStreamHandlers {
  onConnectionChange: (state: AgentConnectionState, attempt: number) => void;
  onEvent: (event: ReturnType<typeof decodeAgentSessionEvent> extends infer T ? Exclude<T, null> : never) => void;
  onDone: (status?: string) => void;
  onMalformedEvent: (raw: string) => void;
}

export interface AgentStreamSubscription {
  close: () => void;
}

export function connectAgentSessionStream(
  sessionId: string,
  lastEventId: string,
  handlers: AgentStreamHandlers,
): AgentStreamSubscription {
  let closed = false;
  let source: EventSource | null = null;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;
  let attempt = 0;
  let cursor = lastEventId;
  let finished = false;

  const open = () => {
    if (closed) return;
    handlers.onConnectionChange(attempt === 0 ? 'connecting' : 'reconnecting', attempt);
    source = new EventSource(buildAgentSessionStreamUrl(sessionId, cursor));

    source.addEventListener('open', () => {
      attempt = 0;
      handlers.onConnectionChange('open', attempt);
    });

    source.addEventListener('agent_session_event', (rawEvent) => {
      try {
        const decoded = decodeAgentSessionEvent(JSON.parse((rawEvent as MessageEvent<string>).data));
        if (!decoded) {
          handlers.onMalformedEvent((rawEvent as MessageEvent<string>).data);
          return;
        }
        cursor = decoded.id || cursor;
        handlers.onEvent(decoded);
      } catch {
        handlers.onMalformedEvent((rawEvent as MessageEvent<string>).data);
      }
    });

    source.addEventListener('agent_session_done', (rawEvent) => {
      let status: string | undefined;
      try {
        status = JSON.parse((rawEvent as MessageEvent<string>).data)?.status;
      } catch {
        status = undefined;
      }
      handlers.onDone(status);
      finished = true;
      source?.close();
      source = null;
      handlers.onConnectionChange('closed', attempt);
    });

    source.onerror = () => {
      source?.close();
      source = null;
      if (closed || finished) return;
      handlers.onConnectionChange('error', attempt);
      const delay = getAgentStreamRetryDelay(attempt);
      attempt += 1;
      retryTimer = setTimeout(open, delay);
    };
  };

  open();
  return {
    close: () => {
      closed = true;
      if (retryTimer) clearTimeout(retryTimer);
      source?.close();
    },
  };
}

export const agentTransport = {
  listAgents: getAgents,
  listSessions: listAgentSessions,
  createSession: (payload: AgentSessionCreate): Promise<AgentSession> => createAgentSession(payload),
  getSession: (sessionId: string): Promise<AgentSession> => getAgentSession(sessionId),
  updateSessionPreferences: (
    sessionId: string,
    payload: AgentSessionPreferencesUpdate,
  ): Promise<AgentSession> => updateAgentSessionPreferences(sessionId, payload),
  getWorkspace: (sessionId: string): Promise<AgentWorkspace> => getAgentWorkspace(sessionId),
  prompt: (sessionId: string, payload: AgentPromptRequest): Promise<AgentSession> => promptAgentSession(sessionId, payload),
  interrupt: (sessionId: string): Promise<AgentSession> => interruptAgentSession(sessionId),
  decidePermission: (partId: string, decisions: AgentHitlDecision[]) => decideAgentPermission(partId, decisions),
  approvePermission: approveAgentPermission,
  rejectPermission: rejectAgentPermission,
  recoverNode: recoverAgentExecutionPlanNode,
  startAsyncTask: startAgentAsyncTask,
  cancelAsyncTask: cancelAgentAsyncTask,
  reportDiagnostics: reportAgentDiagnostics,
  connectStream: connectAgentSessionStream,
};

export type AgentTransport = typeof agentTransport;
