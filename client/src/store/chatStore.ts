import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import axios from 'axios';
import {
  clearChatSessionMessages,
  createChatSession,
  deleteChatSessionMessage,
  deleteChatSession,
  getChatSession,
  getChatSessionMessages,
  listChatSessions,
  replaceChatSessionMessages,
  updateChatSessionMessage,
} from '../services/chatSessionApi';
import type {
  ChatMessage,
  PlaygroundAttachment,
  PlaygroundCandidate,
  PlaygroundPreset,
  PlaygroundSnapshot,
} from '../types';
import {
  addExperimentSnapshotRecord,
  clearActiveExperimentCandidates,
  deleteExperimentPreset,
  initialChatExperimentState,
  saveExperimentPreset,
  setActiveExperimentCandidates,
  updateExperimentSnapshotRecord,
} from './chatExperimentState';

export interface ChatSession {
  id: string;
  title: string;
  modelId: string;
  backend: string;
  createdAt: string;
  updatedAt: string;
  messageCount: number;
  metadata?: Record<string, unknown>;
}

export interface ChatSettings {
  modelId: string;
  backend: 'ollama' | 'huggingface' | 'cloud' | 'llama-cpp';
  useKnowledge: boolean;
  knowledgeCollection?: string;
  useMemory: boolean;
  useProjectContext: boolean;
  projectPath?: string;
  systemPrompt: string;
  temperature: number;
  topP: number;
  maxTokens: number;
  autoRetrieve: boolean;
  responseFormat: 'text' | 'json';
  candidateCount: number;
}

export interface StreamState {
  status: 'idle' | 'connecting' | 'streaming' | 'completed' | 'error' | 'stopped';
  content: string;
  error: string | null;
  chunksReceived: number;
  startTime: number | null;
  bytesReceived: number;
}

interface ChatStore {
  sessions: ChatSession[];
  currentSessionId: string | null;
  messages: ChatMessage[];
  streamingMessageId: string | null;
  streamingContent: string;
  isStreaming: boolean;
  isLoading: boolean;
  error: string | null;
  settings: ChatSettings;
  streamState: StreamState;
  promptDraft: string;
  attachments: PlaygroundAttachment[];
  activeCandidates: PlaygroundCandidate[];
  selectedCandidateId: string | null;
  selectedExperimentId: string | null;
  responseView: 'response' | 'patch' | 'sources' | 'metadata' | 'raw';
  lastRunMetadata: PlaygroundSnapshot | null;
  experimentSnapshots: PlaygroundSnapshot[];
  presets: PlaygroundPreset[];
  selectedPresetId: string | null;

  createSession: (title?: string, modelId?: string) => Promise<ChatSession>;
  loadSession: (sessionId: string) => Promise<void>;
  deleteSession: (sessionId: string) => Promise<void>;
  updateSessionTitle: (sessionId: string, title: string) => void;
  setCurrentSessionId: (sessionId: string | null) => void;
  loadSessions: () => Promise<void>;
  updateSessionMetadata: (sessionId: string, metadata: Record<string, unknown>) => void;

  addMessage: (message: Omit<ChatMessage, 'id' | 'timestamp'>) => string;
  updateMessage: (id: string, updates: Partial<ChatMessage>) => void;
  deleteMessage: (id: string) => Promise<void>;
  editMessage: (id: string, content: string) => Promise<void>;
  clearMessages: () => Promise<void>;
  replaceCurrentSessionMessages: (messages: ChatMessage[]) => Promise<ChatMessage[]>;
  setMessages: (messages: ChatMessage[]) => void;

  startStreaming: (messageId: string) => void;
  updateStreamingContent: (content: string) => void;
  stopStreaming: () => void;
  completeStreaming: () => void;
  setStreamState: (state: Partial<StreamState>) => void;

  updateSettings: (settings: Partial<ChatSettings>) => void;
  setPromptDraft: (promptDraft: string) => void;
  setAttachments: (attachments: PlaygroundAttachment[]) => void;
  addAttachment: (attachment: PlaygroundAttachment) => void;
  removeAttachment: (attachmentId: string) => void;
  clearAttachments: () => void;
  setActiveCandidates: (candidates: PlaygroundCandidate[]) => void;
  updateActiveCandidate: (candidateId: string, updates: Partial<PlaygroundCandidate>) => void;
  clearActiveCandidates: () => void;
  setSelectedCandidateId: (selectedCandidateId: string | null) => void;
  addExperimentSnapshot: (snapshot: PlaygroundSnapshot) => void;
  updateExperimentSnapshot: (snapshotId: string, updates: Partial<PlaygroundSnapshot>) => void;
  setSelectedExperimentId: (experimentId: string | null) => void;
  setResponseView: (view: 'response' | 'patch' | 'sources' | 'metadata' | 'raw') => void;
  setLastRunMetadata: (snapshot: PlaygroundSnapshot | null) => void;
  savePreset: (preset: PlaygroundPreset) => void;
  deletePreset: (presetId: string) => void;
  setSelectedPresetId: (selectedPresetId: string | null) => void;

  cloudConfig: {
    useCloudAI: boolean;
    config: {
      provider: string;
      api_key?: string;
      key_id?: string;
      model?: string;
      group_id?: string;
      base_url?: string;
    } | null;
    providers: Array<{ id: string; provider: string; models?: string[]; default_model?: string }>;
    selectedModel: string;
  };
  setCloudConfig: (config: Partial<ChatStore['cloudConfig']>) => void;

  setError: (error: string | null) => void;
  setIsLoading: (loading: boolean) => void;
}

function messageMetadata(message: ChatMessage): Record<string, unknown> {
  return {
    ...(message.knowledge_sources ? { knowledge_sources: message.knowledge_sources } : {}),
    ...(message.retrieval_info ? { retrieval_info: message.retrieval_info } : {}),
    ...(message.memory_context ? { memory_context: message.memory_context } : {}),
    ...(message.unified_context ? { unified_context: message.unified_context } : {}),
    ...(message.raw_response !== undefined ? { raw_response: message.raw_response } : {}),
    ...(message.attachments ? { attachments: message.attachments } : {}),
    ...(message.experiment_config ? { experiment_config: message.experiment_config } : {}),
    ...(message.run_metrics ? { run_metrics: message.run_metrics } : {}),
    ...(message.agent_metadata ? { agent_metadata: message.agent_metadata } : {}),
    ...(message.isEdited ? { isEdited: message.isEdited } : {}),
  };
}

function mergeLoadedSessionRecord(
  existingSession: ChatSession,
  loadedSession: ChatSession,
): ChatSession {
  return {
    ...existingSession,
    title: loadedSession.title || existingSession.title,
    modelId: loadedSession.modelId || existingSession.modelId,
    backend: loadedSession.backend || existingSession.backend,
    messageCount: loadedSession.messageCount ?? existingSession.messageCount,
    updatedAt: loadedSession.updatedAt || existingSession.updatedAt,
    metadata: loadedSession.metadata || existingSession.metadata || {},
  };
}

function updateSessionSummary(
  sessions: ChatSession[],
  sessionId: string,
  updates: Partial<ChatSession>,
): ChatSession[] {
  return sessions.map((session) =>
    session.id === sessionId
      ? {
          ...session,
          ...updates,
          updatedAt: updates.updatedAt || new Date().toISOString(),
        }
      : session,
  );
}

export const useChatStore = create<ChatStore>()(
  persist(
    (set, get) => ({
      sessions: [],
      currentSessionId: null,
      messages: [],
      streamingMessageId: null,
      streamingContent: '',
      isStreaming: false,
      isLoading: false,
      error: null,
      settings: {
        modelId: '',
        backend: 'ollama',
        useKnowledge: false,
        useMemory: true,
        useProjectContext: false,
        projectPath: '',
        systemPrompt: '',
        temperature: 0.7,
        topP: 0.9,
        maxTokens: 2048,
        autoRetrieve: true,
        responseFormat: 'text',
        candidateCount: 2,
      },
      streamState: {
        status: 'idle',
        content: '',
        error: null,
        chunksReceived: 0,
        startTime: null,
        bytesReceived: 0,
      },
      promptDraft: '',
      attachments: [],
      cloudConfig: {
        useCloudAI: false,
        config: null,
        providers: [],
        selectedModel: '',
      },
      ...initialChatExperimentState,

      createSession: async (title = 'New Chat', modelId) => {
        try {
          const session = await createChatSession(
            title,
            modelId || get().settings.modelId,
            get().settings.backend,
          );

          set((state) => ({
            sessions: [session, ...state.sessions],
            currentSessionId: session.id,
            messages: [],
          }));

          return session;
        } catch (error) {
          console.error('创建会话失败：', error);
          const localSession: ChatSession = {
            id: `local_${Date.now()}`,
            title,
            modelId: modelId || get().settings.modelId,
            backend: get().settings.backend,
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
            messageCount: 0,
          };

          set((state) => ({
            sessions: [localSession, ...state.sessions],
            currentSessionId: localSession.id,
            messages: [],
          }));

          return localSession;
        }
      },

      loadSession: async (sessionId) => {
        try {
          const [sessionData, messagesData] = await Promise.all([
            getChatSession(sessionId, get().settings.backend),
            getChatSessionMessages(sessionId, 500),
          ]);

          set({
            currentSessionId: sessionId,
            messages: messagesData.messages || [],
            sessions: get().sessions.map((session) =>
              session.id === sessionId ? mergeLoadedSessionRecord(session, sessionData) : session,
            ),
          });
        } catch (error) {
          console.error('加载会话失败：', error);
          set({
            error: error instanceof Error ? error.message : '加载会话失败',
          });
          throw error;
        }
      },

      deleteSession: async (sessionId) => {
        // 先乐观更新 UI，提升响应速度
        set((state) => ({
          sessions: state.sessions.filter((s) => s.id !== sessionId),
          currentSessionId: state.currentSessionId === sessionId ? null : state.currentSessionId,
          messages: state.currentSessionId === sessionId ? [] : state.messages,
        }));

        try {
          // 如果是本地临时生成的会话（id 以 local_ 开头），不需要调接口
          if (!sessionId.startsWith('local_')) {
            await deleteChatSession(sessionId);
          }
        } catch (error) {
          console.error('删除会话失败：', error);
          // 可以选择如果失败是否把会话加回来（通常没必要，直接重载一次列表即可）
          get().loadSessions();
        }
      },

      updateSessionTitle: async (sessionId, title) => {
        set((state) => ({
          sessions: state.sessions.map((s) =>
            s.id === sessionId ? { ...s, title, updatedAt: new Date().toISOString() } : s,
          ),
        }));

        if (!sessionId.startsWith('local_')) {
          try {
            const { updateChatSessionTitle } = await import('../services/chatSessionApi');
            await updateChatSessionTitle(sessionId, title);
          } catch (error) {
            console.error('更新会话标题失败：', error);
          }
        }
      },

      setCurrentSessionId: (sessionId) => {
        set({ currentSessionId: sessionId });
      },

      loadSessions: async () => {
        try {
          const sessions = await listChatSessions(get().settings.backend);
          const currentSessionId = get().currentSessionId;
          const hasCurrentSession =
            currentSessionId && sessions.some((session) => session.id === currentSessionId);
          set({
            sessions,
            currentSessionId: hasCurrentSession ? currentSessionId : null,
            messages: hasCurrentSession ? get().messages : [],
          });
        } catch (error) {
          console.error('加载会话列表失败：', error);
        }
      },

      updateSessionMetadata: (sessionId, metadata) => {
        set((state) => ({
          sessions: state.sessions.map((session) =>
            session.id === sessionId
              ? {
                  ...session,
                  metadata: {
                    ...(session.metadata || {}),
                    ...metadata,
                  },
                  updatedAt: new Date().toISOString(),
                }
              : session,
          ),
        }));
      },

      addMessage: (message) => {
        const id = `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        const newMessage: ChatMessage = {
          ...message,
          id,
          timestamp: new Date().toISOString(),
        };

        set((state) => ({
          messages: [...state.messages, newMessage],
        }));

        return id;
      },

      updateMessage: (id, updates) => {
        set((state) => ({
          messages: state.messages.map((m) => (m.id === id ? { ...m, ...updates } : m)),
        }));
      },

      deleteMessage: async (id) => {
        const { currentSessionId, messages } = get();
        const previousMessages = messages;
        set((state) => ({
          messages: state.messages.filter((m) => m.id !== id),
          sessions: state.currentSessionId
            ? updateSessionSummary(state.sessions, state.currentSessionId, {
                messageCount: Math.max(0, state.messages.length - 1),
              })
            : state.sessions,
        }));
        if (!currentSessionId || currentSessionId.startsWith('local_')) {
          return;
        }
        try {
          await deleteChatSessionMessage(currentSessionId, id);
        } catch (error) {
          set({
            messages: previousMessages,
            error: error instanceof Error ? error.message : '删除消息失败',
          });
          throw error;
        }
      },

      editMessage: async (id, content) => {
        const { currentSessionId, messages } = get();
        const previousMessages = messages;
        set((state) => ({
          messages: state.messages.map((m) =>
            m.id === id ? { ...m, content, isEdited: true } : m,
          ),
        }));
        if (!currentSessionId || currentSessionId.startsWith('local_')) {
          return;
        }
        try {
          const current = previousMessages.find((message) => message.id === id);
          await updateChatSessionMessage(currentSessionId, id, {
            role: current?.role,
            content,
            metadata: current ? { ...messageMetadata(current), isEdited: true } : { isEdited: true },
          });
        } catch (error) {
          set({
            messages: previousMessages,
            error: error instanceof Error ? error.message : '编辑消息失败',
          });
          throw error;
        }
      },

      clearMessages: async () => {
        const { currentSessionId, messages } = get();
        if (!currentSessionId || currentSessionId.startsWith('local_')) {
          set({ messages: [] });
          return;
        }
        try {
          await clearChatSessionMessages(currentSessionId);
          set((state) => ({
            messages: [],
            sessions: updateSessionSummary(state.sessions, currentSessionId, { messageCount: 0 }),
          }));
        } catch (error) {
          set({
            messages,
            error: error instanceof Error ? error.message : '清空会话失败',
          });
          throw error;
        }
      },

      replaceCurrentSessionMessages: async (messages) => {
        const { currentSessionId } = get();
        if (!currentSessionId || currentSessionId.startsWith('local_')) {
          set({ messages });
          return messages;
        }
        const payload = messages.map((message) => ({
          id: message.id,
          role: message.role,
          content: message.content,
          created_at: message.timestamp,
          metadata: messageMetadata(message),
        }));
        let targetSessionId = currentSessionId;
        let result;
        try {
          result = await replaceChatSessionMessages(targetSessionId, payload);
        } catch (error) {
          const status = axios.isAxiosError(error) ? error.response?.status : (error as { status?: number })?.status;
          if (status !== 404) {
            throw error;
          }
          const firstUserMessage = messages.find((message) => message.role === 'user');
          const recreated = await createChatSession(
            firstUserMessage?.content?.slice(0, 40) || 'Agent Chat',
            get().settings.modelId,
            get().settings.backend,
          );
          targetSessionId = recreated.id;
          set((state) => ({
            currentSessionId: recreated.id,
            sessions: [recreated, ...state.sessions.filter((session) => session.id !== currentSessionId)],
          }));
          result = await replaceChatSessionMessages(targetSessionId, payload);
        }
        set((state) => ({
          messages: result.messages,
          sessions: updateSessionSummary(state.sessions, targetSessionId, {
            messageCount: result.messages.length,
          }),
        }));
        return result.messages;
      },

      setMessages: (messages) => {
        set({ messages });
      },

      startStreaming: (messageId) => {
        set({
          streamingMessageId: messageId,
          streamingContent: '',
          isStreaming: true,
          streamState: {
            status: 'streaming',
            content: '',
            error: null,
            chunksReceived: 0,
            startTime: Date.now(),
            bytesReceived: 0,
          },
        });
      },

      updateStreamingContent: (content) => {
        set((state) => ({
          streamingContent: content,
          streamState: {
            ...state.streamState,
            content,
            chunksReceived: state.streamState.chunksReceived + 1,
            bytesReceived: state.streamState.bytesReceived + content.length,
          },
        }));

        const { streamingMessageId, messages } = get();
        if (streamingMessageId) {
          const idx = messages.findIndex((m) => m.id === streamingMessageId);
          if (idx !== -1) {
            const next = messages.slice();
            next[idx] = { ...next[idx], content } as ChatMessage;
            set({ messages: next });
          }
        }
      },

      stopStreaming: () => {
        set({
          isStreaming: false,
          streamingMessageId: null,
          streamState: {
            ...get().streamState,
            status: 'stopped',
          },
        });
      },

      completeStreaming: () => {
        const { streamingMessageId } = get();
        if (streamingMessageId) {
          get().updateMessage(streamingMessageId, { isLoading: false });
        }

        set({
          isStreaming: false,
          streamingMessageId: null,
          streamState: {
            ...get().streamState,
            status: 'completed',
          },
        });
      },

      setStreamState: (updates) => {
        set((state) => ({
          streamState: { ...state.streamState, ...updates },
        }));
      },

      updateSettings: (newSettings) => {
        set((state) => ({
          settings: { ...state.settings, ...newSettings },
        }));
      },

      setPromptDraft: (promptDraft) => {
        set({ promptDraft });
      },

      setAttachments: (attachments) => {
        set({ attachments });
      },

      addAttachment: (attachment) => {
        set((state) => ({
          attachments: [...state.attachments, attachment],
        }));
      },

      removeAttachment: (attachmentId) => {
        set((state) => ({
          attachments: state.attachments.filter((attachment) => attachment.id !== attachmentId),
        }));
      },

      clearAttachments: () => {
        set({ attachments: [] });
      },

      setActiveCandidates: (activeCandidates) => {
        set(setActiveExperimentCandidates(activeCandidates));
      },

      updateActiveCandidate: (candidateId, updates) => {
        set((state) => ({
          activeCandidates: state.activeCandidates.map((candidate) =>
            candidate.id === candidateId ? { ...candidate, ...updates } : candidate,
          ),
        }));
      },

      clearActiveCandidates: () => {
        set(clearActiveExperimentCandidates());
      },

      setSelectedCandidateId: (selectedCandidateId) => {
        set({ selectedCandidateId });
      },

      addExperimentSnapshot: (snapshot) => {
        set((state) => addExperimentSnapshotRecord(state.experimentSnapshots, snapshot));
      },

      updateExperimentSnapshot: (snapshotId, updates) => {
        set((state) =>
          updateExperimentSnapshotRecord(
            state.experimentSnapshots,
            snapshotId,
            updates,
            state.lastRunMetadata,
          ),
        );
      },

      setSelectedExperimentId: (selectedExperimentId) => {
        set({ selectedExperimentId });
      },

      setResponseView: (responseView) => {
        set({ responseView });
      },

      setLastRunMetadata: (lastRunMetadata) => {
        set({ lastRunMetadata });
      },

      savePreset: (preset) => {
        set((state) => saveExperimentPreset(state.presets, preset));
      },

      deletePreset: (presetId) => {
        set((state) => deleteExperimentPreset(state.presets, presetId, state.selectedPresetId));
      },

      setSelectedPresetId: (selectedPresetId) => {
        set({ selectedPresetId });
      },

      setError: (error) => {
        set({ error });
      },

      setIsLoading: (loading) => {
        set({ isLoading: loading });
      },

      setCloudConfig: (updates) => {
        set((state) => ({
          cloudConfig: { ...state.cloudConfig, ...updates },
        }));
      },
    }),
    {
      name: 'chat-storage',
      partialize: (state) => ({
        sessions: state.sessions.slice(0, 100),
        currentSessionId: state.currentSessionId,
        messages: state.messages.slice(-500),
        settings: state.settings,
        promptDraft: state.promptDraft,
        attachments: state.attachments,
        activeCandidates: state.activeCandidates,
        selectedCandidateId: state.selectedCandidateId,
        selectedExperimentId: state.selectedExperimentId,
        responseView: state.responseView,
        lastRunMetadata: state.lastRunMetadata,
        experimentSnapshots: state.experimentSnapshots.slice(0, 50),
        presets: state.presets.slice(0, 50),
        selectedPresetId: state.selectedPresetId,
        cloudConfig: state.cloudConfig,
      }),
    },
  ),
);
