import { useCallback, useRef } from 'react';

import { getAgentSessionUiState } from '../../hooks/chat/useAgentSessionViewModel';
import { useChatStore } from '../../store/chatStore';
import type { AgentPart, AgentSession } from '../../services/api';

export function useAgentSessionMessages() {
  const agentSessionStateRef = useRef<Record<string, AgentSession>>({});

  const persistAgentMessages = useCallback(async () => {
    const state = useChatStore.getState();
    if (!state.currentSessionId || state.currentSessionId.startsWith('local_')) return;
    await state.replaceCurrentSessionMessages(state.messages).catch(() => undefined);
  }, []);

  const rememberAgentSession = useCallback((session: AgentSession) => {
    agentSessionStateRef.current[session.id] = session;
    return session;
  }, []);

  const ensureAgentSessionSnapshot = useCallback((
    sessionId: string,
    overrides: Partial<AgentSession> = {},
  ): AgentSession => {
    const cached = agentSessionStateRef.current[sessionId];
    const next: AgentSession = {
      id: sessionId,
      chat_session_id: overrides.chat_session_id ?? cached?.chat_session_id,
      agent_id: overrides.agent_id ?? cached?.agent_id ?? 'build',
      status: overrides.status ?? cached?.status ?? 'running',
      title: overrides.title ?? cached?.title ?? 'Agent Session',
      project_path: overrides.project_path ?? cached?.project_path,
      provider: overrides.provider ?? cached?.provider,
      model: overrides.model ?? cached?.model,
      metadata: overrides.metadata ?? cached?.metadata ?? {},
      parts: overrides.parts ?? cached?.parts ?? [],
      created_at: overrides.created_at ?? cached?.created_at ?? new Date().toISOString(),
      updated_at: overrides.updated_at ?? cached?.updated_at ?? new Date().toISOString(),
    };
    agentSessionStateRef.current[sessionId] = next;
    return next;
  }, []);

  const mergeAgentSessionPart = useCallback((
    sessionId: string,
    part: AgentPart,
    overrides: Partial<AgentSession> = {},
  ): AgentSession => {
    const session = ensureAgentSessionSnapshot(sessionId, overrides);
    const parts = [...(session.parts || [])];
    const index = parts.findIndex((item) => item.id === part.id);
    if (index >= 0) {
      parts[index] = { ...parts[index], ...part };
    } else {
      parts.push(part);
    }
    const next = {
      ...session,
      ...overrides,
      parts,
      updated_at: part.updated_at || overrides.updated_at || session.updated_at,
    };
    agentSessionStateRef.current[sessionId] = next;
    return next;
  }, [ensureAgentSessionSnapshot]);

  const buildAgentPartMetadata = useCallback((session: AgentSession, part: AgentPart) => {
    const uiState = getAgentSessionUiState(session);
    const uiItem = uiState.timeline.find((item) => item.part_id === part.id || item.id === part.id);
    const actionLike = part.type === 'permission' && uiState.pending_permission?.part_id === part.id;
    const summaryPart = part.type === 'summary' ? part : [...(session.parts || [])].reverse().find((item) => item.type === 'summary');
    return {
      agent_run_id: session.id,
      agent_session_id: session.id,
      agent_part_id: part.id,
      kind: 'agent_part' as const,
      status: part.status || session.status,
      action_id: actionLike ? part.id : undefined,
      action_type: part.type,
      can_approve: actionLike && part.status === 'pending',
      can_execute: false,
      ui_state: uiState,
      ui_item: uiItem,
      active_agent_id: session.agent_id,
      task_plan: session.metadata?.task_plan,
      current_stage_id: session.metadata?.current_stage_id,
      current_node_id: session.metadata?.current_node_id,
      agent_part: part,
      agent_parts: session.parts,
      agent_session_state: (session.metadata as any)?.state,
      agent_session_diagnostics: (session.metadata as any)?.diagnostics,
      agent_streaming_diagnostics: (session.metadata as any)?.streaming_diagnostics,
      final_summary: summaryPart?.content,
      recoverable: !['completed', 'failed'].includes(session.status),
      autonomy_mode: (session.metadata as any)?.autonomy_mode,
    };
  }, []);

  const upsertAgentSessionMessage = useCallback(
    async (session: AgentSession, fallbackContent?: string) => {
      rememberAgentSession(session);
      const state = useChatStore.getState();
      const renderableParts = (session.parts || []).filter((part) => !(part.type === 'text' && part.title === '请求'));
      if (!renderableParts.length && fallbackContent) {
        const placeholderId = `${session.id}:pending`;
        const existing = state.messages.find((message) => message.agent_metadata?.agent_part_id === placeholderId);
        const placeholderPart: AgentPart = {
          id: placeholderId,
          session_id: session.id,
          type: 'text',
          status: session.status === 'running' ? 'running' : 'completed',
          title: 'Agent 已启动',
          content: fallbackContent,
          payload: {},
          created_at: session.updated_at,
        };
        const metadata = buildAgentPartMetadata(session, placeholderPart);
        if (existing) {
          state.updateMessage(existing.id, { content: fallbackContent, isLoading: session.status === 'running', agent_metadata: metadata });
        } else {
          state.addMessage({ role: 'assistant', content: fallbackContent, isLoading: session.status === 'running', agent_metadata: metadata });
        }
        await persistAgentMessages();
        return;
      }

      for (const part of renderableParts) {
        const existing = state.messages.find((message) => message.agent_metadata?.agent_part_id === part.id);
        const content = part.content || part.title || session.title;
        const metadata = buildAgentPartMetadata(session, part);
        if (existing) {
          state.queueMessageUpdate(existing.id, {
            content,
            isLoading: part.status === 'running',
            agent_metadata: metadata,
          });
        } else {
          state.addMessage({
            role: 'assistant',
            content,
            isLoading: part.status === 'running',
            agent_metadata: metadata,
          });
        }
      }

      const placeholder = state.messages.find((message) => message.agent_metadata?.agent_part_id === `${session.id}:pending`);
      if (placeholder && renderableParts.length) {
        await state.deleteMessage(placeholder.id).catch(() => undefined);
      }
      state.flushMessageUpdates();
      await persistAgentMessages();
    },
    [buildAgentPartMetadata, persistAgentMessages, rememberAgentSession],
  );

  const upsertAgentSessionPartMessage = useCallback(
    async (
      sessionId: string,
      part: AgentPart,
      overrides: Partial<AgentSession> = {},
      options: { persist?: boolean } = {},
    ) => {
      if (part.type === 'text' && part.title === '请求') return;
      const state = useChatStore.getState();
      const session = mergeAgentSessionPart(sessionId, part, overrides);
      const content = part.content || part.title || session.title;
      const metadata = buildAgentPartMetadata(session, part);
      const existing = state.messages.find((message) => message.agent_metadata?.agent_part_id === part.id);
      if (existing) {
        state.queueMessageUpdate(existing.id, {
          content,
          isLoading: part.status === 'running',
          agent_metadata: metadata,
        });
      } else {
        state.addMessage({
          role: 'assistant',
          content,
          isLoading: part.status === 'running',
          agent_metadata: metadata,
        });
      }
      const placeholder = state.messages.find((message) => message.agent_metadata?.agent_part_id === `${sessionId}:pending`);
      if (placeholder) {
        await state.deleteMessage(placeholder.id).catch(() => undefined);
      }
      state.flushMessageUpdates();
      if (options.persist) {
        await persistAgentMessages();
      }
    },
    [buildAgentPartMetadata, mergeAgentSessionPart, persistAgentMessages],
  );

  const appendAgentSessionError = useCallback(
    async (content: string, session?: Partial<AgentSession> & { id?: string }) => {
      const now = new Date().toISOString();
      const sessionId = session?.id || `agent_error_${Date.now()}`;
      const errorPart: AgentPart = {
        id: `${sessionId}:startup-error`,
        session_id: sessionId,
        type: 'error',
        status: 'failed',
        title: 'Agent 启动失败',
        content,
        payload: {
          guidance: '已停止本次 Agent 执行，没有重复调用工具。可以检查后端日志或稍后重试。',
          fallback: true,
        },
        created_at: now,
        updated_at: now,
      };
      const snapshot = ensureAgentSessionSnapshot(sessionId, {
        ...session,
        id: sessionId,
        status: 'failed',
        title: session?.title || 'Agent Session',
        metadata: {
          ...(session?.metadata || {}),
          diagnostics: {
            stop_reason: content,
            next_action: '检查后端服务状态、模型配置或权限后再重试。',
            refresh_safe: true,
          },
        },
        parts: [errorPart],
        updated_at: now,
      } as Partial<AgentSession>);
      await upsertAgentSessionPartMessage(sessionId, errorPart, snapshot, { persist: true });
    },
    [ensureAgentSessionSnapshot, upsertAgentSessionPartMessage],
  );

  return {
    buildAgentPartMetadata,
    mergeAgentSessionPart,
    ensureAgentSessionSnapshot,
    upsertAgentSessionMessage,
    upsertAgentSessionPartMessage,
    appendAgentSessionError,
  };
}
