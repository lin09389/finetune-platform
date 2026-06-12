import { useCallback, useEffect, useRef, type Dispatch, type SetStateAction } from 'react';

import { useChatStore } from '../../store/chatStore';
import { buildAgentSessionStreamUrl, getAgentStreamRetryDelay } from '../../utils/agentSessionStream';
import { getAgentSession } from '../../services/api';
import type { AgentPart, AgentSession, AgentSessionEvent } from '../../services/api';

export type AgentStreamRetryState = {
  attempt: number;
  timer: ReturnType<typeof setTimeout> | null;
  lastEventId: string;
};

export function useAgentSessionStream(params: {
  enabled: boolean;
  getAgentWorkspaceRefresh: () => (() => Promise<void>) | null;
  setAgentPhase: Dispatch<SetStateAction<{ phase: string; tool?: string; detail?: string; visible: boolean }>>;
  buildAgentPartMetadata: (session: AgentSession, part: AgentPart) => any;
  mergeAgentSessionPart: (sessionId: string, part: AgentPart, overrides?: Partial<AgentSession>) => AgentSession;
  ensureAgentSessionSnapshot: (sessionId: string, overrides?: Partial<AgentSession>) => AgentSession;
  upsertAgentSessionMessage: (session: AgentSession) => Promise<void>;
  upsertAgentSessionPartMessage: (sessionId: string, part: AgentPart, overrides?: Partial<AgentSession>, options?: { persist?: boolean }) => Promise<void>;
  appendAgentSessionError: (content: string, session?: Partial<AgentSession> & { id?: string }) => Promise<void>;
}) {
  const {
    enabled,
    getAgentWorkspaceRefresh,
    setAgentPhase,
    buildAgentPartMetadata,
    mergeAgentSessionPart,
    ensureAgentSessionSnapshot,
    upsertAgentSessionMessage,
    upsertAgentSessionPartMessage,
    appendAgentSessionError,
  } = params;

  const streamsRef = useRef<Record<string, EventSource>>({});
  const retryRef = useRef<Record<string, AgentStreamRetryState>>({});
  const startRef = useRef<((sessionId: string, fromRetry?: boolean) => void) | null>(null);
  const deltaFlushRef = useRef<{ rafId: number | null; pending: Record<string, string> } | null>(null);
  const streamingDeltaRef = useRef<Record<string, { partId: string; content: string }>>({});

  const clearRetry = useCallback((sessionId: string) => {
    const retryState = retryRef.current[sessionId];
    if (retryState?.timer) {
      clearTimeout(retryState.timer);
      retryState.timer = null;
    }
  }, []);

  const closeStream = useCallback((sessionId: string, clearRetryState = true) => {
    streamsRef.current[sessionId]?.close();
    delete streamsRef.current[sessionId];
    if (clearRetryState) {
      clearRetry(sessionId);
      delete retryRef.current[sessionId];
    }
  }, [clearRetry]);

  const startStream = useCallback((sessionId: string, fromRetry = false) => {
    if (!enabled) return;
    closeStream(sessionId, false);
    const retryState = retryRef.current[sessionId] || { attempt: 0, timer: null, lastEventId: '' };
    retryState.timer = null;
    if (!fromRetry) retryState.attempt = 0;
    retryRef.current[sessionId] = retryState;
    const source = new EventSource(buildAgentSessionStreamUrl(sessionId, retryState.lastEventId));
    streamsRef.current[sessionId] = source;

    const flushPending = () => {
      if (!deltaFlushRef.current) return;
      if (deltaFlushRef.current.rafId) cancelAnimationFrame(deltaFlushRef.current.rafId);
      const pending = { ...deltaFlushRef.current.pending };
      deltaFlushRef.current.pending = {};
      deltaFlushRef.current.rafId = null;
      for (const [msgId, pendingDelta] of Object.entries(pending)) {
        useChatStore.getState().appendStreamingDelta(msgId, pendingDelta);
      }
    };

    const handleChunk = async (chunk: AgentSessionEvent) => {
      if (typeof chunk.id === 'string' && chunk.id) retryState.lastEventId = chunk.id;
      retryState.attempt = 0;
      setAgentPhase((prev) => prev.phase === 'connection_lost' ? { phase: '', visible: false } : prev);
      const part = chunk.part || undefined;
      const sessionStatus = chunk.session_status;
      const agentId = chunk.agent_id;

      if (chunk.chunk_type === 'session_snapshot') {
        if (chunk.session_snapshot) {
          await upsertAgentSessionMessage(chunk.session_snapshot as AgentSession);
        }
        flushPending();
        const isTerminal = ['completed', 'failed', 'needs_manual_review', 'interrupted'].includes(sessionStatus || '');
        if (isTerminal) {
          closeStream(sessionId);
          Object.keys(streamingDeltaRef.current).forEach((key) => {
            if (key.startsWith('agp_')) delete streamingDeltaRef.current[key];
          });
          setAgentPhase({ phase: '', visible: false });
        }
        return;
      }

      if (sessionStatus || agentId) {
        ensureAgentSessionSnapshot(sessionId, { status: sessionStatus || undefined, agent_id: agentId || undefined, updated_at: chunk.created_at });
      }
      if (chunk.chunk_type === 'phase') {
        const phaseStr = chunk.phase || (chunk.payload?.phase as string) || '';
        if (phaseStr === 'model_thinking') {
          setAgentPhase({ phase: 'model_thinking', visible: true });
        } else if (phaseStr === 'tool_execution') {
          setAgentPhase({
            phase: 'tool_execution',
            tool: chunk.tool || (chunk.payload?.tool as string | undefined),
            detail: (chunk.payload?.detail as string | undefined),
            visible: true,
          });
        } else if (phaseStr === 'tool_completed') {
          setAgentPhase({
            phase: 'tool_completed',
            tool: chunk.tool || (chunk.payload?.tool as string | undefined),
            detail: (chunk.payload?.detail as string | undefined),
            visible: true,
          });
          setTimeout(() => setAgentPhase((prev) => prev.phase === 'tool_completed' ? { ...prev, visible: false } : prev), 1500);
        } else {
          setAgentPhase({ phase: phaseStr, visible: true });
        }
        return;
      }
      if (['part_complete', 'part_snapshot', 'status', 'summary', 'error', 'async_task', 'done'].includes(String(chunk.chunk_type || ''))) {
        void getAgentWorkspaceRefresh()?.();
      }
      if (chunk.chunk_type === 'part_start') {
        flushPending();
        setAgentPhase({ phase: 'model_streaming', visible: false });
      }
      if (part) {
        if (chunk.chunk_type === 'part_delta' && (chunk.delta !== undefined || chunk.content !== undefined)) {
          streamingDeltaRef.current[part.id] = { partId: part.id, content: (chunk.content || part.content || '') as string };
          const deltaText = (chunk.delta || '') as string;
          const found = useChatStore.getState().messages.find((m) => m.agent_metadata?.agent_part_id === part.id);
          if (found && deltaText) {
            if (!deltaFlushRef.current) deltaFlushRef.current = { rafId: null, pending: {} };
            const flush = deltaFlushRef.current;
            flush.pending[found.id] = (flush.pending[found.id] || '') + deltaText;
            if (!flush.rafId) {
              flush.rafId = requestAnimationFrame(() => {
                const pending = { ...flush.pending };
                flush.pending = {};
                flush.rafId = null;
                for (const [msgId, pendingDelta] of Object.entries(pending)) {
                  useChatStore.getState().appendStreamingDelta(msgId, pendingDelta);
                }
              });
            }
          } else if (found) {
            useChatStore.getState().queueMessageUpdate(found.id, {
              content: (chunk.content || part.content || '') as string,
              isLoading: part.status === 'running',
              agent_metadata: buildAgentPartMetadata(mergeAgentSessionPart(sessionId, part, { status: sessionStatus || undefined, agent_id: agentId || undefined, updated_at: chunk.created_at }), part),
            });
          }
        } else {
          flushPending();
          await upsertAgentSessionPartMessage(sessionId, part, { status: sessionStatus || undefined, agent_id: agentId || undefined, updated_at: chunk.created_at }, { persist: chunk.chunk_type !== 'part_start' });
        }
      }

      if (chunk.chunk_type === 'tool_call') {
        setAgentPhase({ phase: 'tool_execution', tool: chunk.tool || (chunk.payload?.tool as string | undefined), detail: (chunk.payload?.detail as string | undefined), visible: true });
      } else if (chunk.chunk_type === 'tool_result' || chunk.chunk_type === 'summary' || chunk.chunk_type === 'action') {
        setAgentPhase((prev) => ({ ...prev, visible: false }));
      } else if (chunk.chunk_type === 'error') {
        setAgentPhase({ phase: 'model_thinking_fallback', visible: true });
      }

      if (chunk.chunk_type === 'action' || sessionStatus === 'waiting_approval' || sessionStatus === 'waiting_permission') {
        getAgentSession(sessionId).then(upsertAgentSessionMessage).catch(() => undefined);
      }
    };

    source.addEventListener('agent_session_event', (e: MessageEvent) => {
      try { void handleChunk(JSON.parse((e as MessageEvent).data) as AgentSessionEvent); } catch { /* ignore */ }
    });
    source.addEventListener('agent_session_done', () => {
      useChatStore.getState().flushMessageUpdates();
      getAgentSession(sessionId)
        .then((session) => {
          void upsertAgentSessionMessage(session);
          if (!session.parts?.length && ['running', 'verifying', 'repairing'].includes(session.status)) {
            void appendAgentSessionError('Agent 事件流已中断，后端可能仍在运行旧代码或连接被服务端关闭。请重启后端后重试。', session);
          }
          setAgentPhase({ phase: '', visible: false });
        })
        .catch(() => undefined);
      closeStream(sessionId);
    });
    source.onerror = () => {
      flushPending();
      useChatStore.getState().flushMessageUpdates();
      Object.keys(streamingDeltaRef.current).forEach((key) => {
        if (key.startsWith('agp_')) delete streamingDeltaRef.current[key];
      });
      setAgentPhase({ phase: 'connection_lost', visible: true });
      getAgentSession(sessionId)
        .then((session) => {
          void upsertAgentSessionMessage(session);
          if (['completed', 'failed', 'needs_manual_review', 'interrupted'].includes(session.status)) {
            closeStream(sessionId);
            setAgentPhase({ phase: '', visible: false });
          }
        })
        .catch((err) => {
          // session 不存在（404）时直接关闭流，不再重试
          const status = err?.response?.status ?? err?.status;
          if (status === 404) {
            closeStream(sessionId);
            setAgentPhase({ phase: '', visible: false });
            return;
          }
        });
      closeStream(sessionId, false);
      // 只有当 session 确实存在时（非 404）才安排重试
      if (!retryState.timer) {
        const delay = getAgentStreamRetryDelay(retryState.attempt);
        retryState.attempt += 1;
        retryState.timer = setTimeout(() => {
          retryState.timer = null;
          // 重试前再次确认 session 是否存在
          getAgentSession(sessionId)
            .then(() => { startRef.current?.(sessionId, true); })
            .catch((err) => {
              const status = err?.response?.status ?? err?.status;
              if (status === 404) {
                closeStream(sessionId);
                setAgentPhase({ phase: '', visible: false });
              } else {
                startRef.current?.(sessionId, true);
              }
            });
        }, delay);
      }
    };
  }, [appendAgentSessionError, buildAgentPartMetadata, closeStream, enabled, ensureAgentSessionSnapshot, getAgentWorkspaceRefresh, mergeAgentSessionPart, setAgentPhase, upsertAgentSessionMessage, upsertAgentSessionPartMessage]);

  useEffect(() => {
    startRef.current = startStream;
  }, [startStream]);

  useEffect(() => () => {
    Object.values(streamsRef.current).forEach((source) => source.close());
    Object.values(retryRef.current).forEach((retryState) => {
      if (retryState.timer) clearTimeout(retryState.timer);
    });
    streamsRef.current = {};
    retryRef.current = {};
    deltaFlushRef.current = null;
    streamingDeltaRef.current = {};
  }, []);

  return {
    streamsRef,
    retryRef,
    startStream,
    startRef,
    closeStream,
    clearRetry,
    deltaFlushRef,
    streamingDeltaRef,
  };
}
