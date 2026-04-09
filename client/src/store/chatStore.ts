import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type {
  AgentPendingConfirmation,
  AgentTaskStatus,
  AgentTimelineEvent,
  ChatMessage,
  PlaygroundAttachment,
  PlaygroundCandidate,
  PlaygroundPreset,
  PlaygroundSnapshot,
} from '../types'
import { API_BASE_URL } from '../services/api'
import {
  createChatSession,
  deleteChatSession,
  getChatSession,
  getChatSessionMessages,
  listChatSessions,
} from '../services/chatSessionApi'
import {
  appendAgentTimelineEvent,
  initialChatAgentState,
  replaceAgentTimelineEvents,
  resetAgentRuntimeState,
} from './chatAgentState'
import {
  addExperimentSnapshotRecord,
  clearActiveExperimentCandidates,
  deleteExperimentPreset,
  initialChatExperimentState,
  saveExperimentPreset,
  setActiveExperimentCandidates,
  updateExperimentSnapshotRecord,
} from './chatExperimentState'
import { mergeLoadedSessionRecord, parseAgentSessionState } from './chatSessionState'

export interface ChatSession {
  id: string
  title: string
  modelId: string
  backend: string
  createdAt: string
  updatedAt: string
  messageCount: number
  metadata?: Record<string, unknown>
}

export interface AgentExecution {
  id: string
  status: 'pending' | 'executing' | 'confirming' | 'completed' | 'failed'
  action: string
  description: string
  params?: Record<string, unknown>
  result?: unknown
  error?: string
  timestamp: string
}

export interface ChatSettings {
  modelId: string
  backend: 'ollama' | 'huggingface' | 'cloud'
  useKnowledge: boolean
  knowledgeCollection?: string
  useMemory: boolean
  systemPrompt: string
  temperature: number
  topP: number
  maxTokens: number
  autoRetrieve: boolean
  responseFormat: 'text' | 'json'
  candidateCount: number
}

export interface StreamState {
  status: 'idle' | 'connecting' | 'streaming' | 'completed' | 'error' | 'stopped'
  content: string
  error: string | null
  chunksReceived: number
  startTime: number | null
  bytesReceived: number
}

interface ChatStore {
  sessions: ChatSession[]
  currentSessionId: string | null
  messages: ChatMessage[]
  streamingMessageId: string | null
  streamingContent: string
  agentExecution: AgentExecution | null
  agentMode: boolean
  agentTaskStatus: AgentTaskStatus
  agentTimeline: AgentTimelineEvent[]
  pendingAgentConfirmation: AgentPendingConfirmation | null
  agentWorkspaceRoot: string
  autoApproveSafeTools: boolean
  isStreaming: boolean
  isLoading: boolean
  error: string | null
  settings: ChatSettings
  streamState: StreamState
  promptDraft: string
  attachments: PlaygroundAttachment[]
  activeCandidates: PlaygroundCandidate[]
  selectedCandidateId: string | null
  selectedExperimentId: string | null
  responseView: 'response' | 'patch' | 'sources' | 'metadata' | 'raw'
  lastRunMetadata: PlaygroundSnapshot | null
  experimentSnapshots: PlaygroundSnapshot[]
  presets: PlaygroundPreset[]
  selectedPresetId: string | null

  createSession: (title?: string, modelId?: string) => Promise<ChatSession>
  loadSession: (sessionId: string) => Promise<void>
  deleteSession: (sessionId: string) => Promise<void>
  updateSessionTitle: (sessionId: string, title: string) => void
  setCurrentSessionId: (sessionId: string | null) => void
  loadSessions: () => Promise<void>
  updateSessionMetadata: (sessionId: string, metadata: Record<string, unknown>) => void

  addMessage: (message: Omit<ChatMessage, 'id' | 'timestamp'>) => string
  updateMessage: (id: string, updates: Partial<ChatMessage>) => void
  deleteMessage: (id: string) => void
  editMessage: (id: string, content: string) => void
  clearMessages: () => void
  setMessages: (messages: ChatMessage[]) => void

  startStreaming: (messageId: string) => void
  updateStreamingContent: (content: string) => void
  stopStreaming: () => void
  completeStreaming: () => void
  setStreamState: (state: Partial<StreamState>) => void

  setAgentExecution: (execution: AgentExecution | null) => void
  confirmAgentExecution: () => Promise<void>
  cancelAgentExecution: () => void
  setAgentMode: (enabled: boolean) => void
  setAgentTaskStatus: (status: AgentTaskStatus) => void
  appendAgentTimeline: (event: AgentTimelineEvent) => void
  replaceAgentTimeline: (events: AgentTimelineEvent[]) => void
  clearAgentTimeline: () => void
  setPendingAgentConfirmation: (confirmation: AgentPendingConfirmation | null) => void
  setAgentWorkspaceRoot: (workspaceRoot: string) => void
  setAutoApproveSafeTools: (enabled: boolean) => void

  updateSettings: (settings: Partial<ChatSettings>) => void
  setPromptDraft: (prompt: string) => void
  setAttachments: (attachments: PlaygroundAttachment[]) => void
  addAttachment: (attachment: PlaygroundAttachment) => void
  removeAttachment: (attachmentId: string) => void
  clearAttachments: () => void
  setActiveCandidates: (candidates: PlaygroundCandidate[]) => void
  updateActiveCandidate: (
    candidateId: string,
    updates: Partial<PlaygroundCandidate>
  ) => void
  clearActiveCandidates: () => void
  setSelectedCandidateId: (candidateId: string | null) => void
  addExperimentSnapshot: (snapshot: PlaygroundSnapshot) => void
  updateExperimentSnapshot: (
    snapshotId: string,
    updates: Partial<PlaygroundSnapshot>
  ) => void
  setSelectedExperimentId: (experimentId: string | null) => void
  setResponseView: (view: ChatStore['responseView']) => void
  setLastRunMetadata: (snapshot: PlaygroundSnapshot | null) => void
  savePreset: (preset: PlaygroundPreset) => void
  deletePreset: (presetId: string) => void
  setSelectedPresetId: (presetId: string | null) => void

  setError: (error: string | null) => void
  setIsLoading: (loading: boolean) => void
}

export const useChatStore = create<ChatStore>()(
  persist(
    (set, get) => ({
      sessions: [],
      currentSessionId: null,
      messages: [],
      streamingMessageId: null,
      streamingContent: '',
      agentExecution: null,
      ...initialChatAgentState,
      isStreaming: false,
      isLoading: false,
      error: null,
      settings: {
        modelId: '',
        backend: 'ollama',
        useKnowledge: false,
        useMemory: true,
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
      ...initialChatExperimentState,

      createSession: async (title = '新对话', modelId) => {
        try {
          const session = await createChatSession(
            title,
            modelId || get().settings.modelId,
            get().settings.backend
          )
          
          set((state) => ({
            sessions: [
              session,
              ...state.sessions,
            ],
            currentSessionId: session.id,
            messages: [],
          }))
          
          return session
        } catch (error) {
          console.error('创建会话失败:', error)
          const localSession: ChatSession = {
            id: `local_${Date.now()}`,
            title,
            modelId: modelId || get().settings.modelId,
            backend: get().settings.backend,
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
            messageCount: 0,
          }
          
          set((state) => ({
            sessions: [localSession, ...state.sessions],
            currentSessionId: localSession.id,
            messages: [],
          }))
          
          return localSession
        }
      },

      loadSession: async (sessionId) => {
        try {
          const [sessionData, messagesData] = await Promise.all([
            getChatSession(sessionId, get().settings.backend),
            getChatSessionMessages(sessionId),
          ])
          const agentSessionState = parseAgentSessionState(sessionData.metadata)
          
          set({
            currentSessionId: sessionId,
            messages: messagesData.messages || [],
            promptDraft: agentSessionState.promptDraft ?? get().promptDraft,
            agentMode: agentSessionState.agentMode,
            agentTaskStatus: agentSessionState.agentTaskStatus,
            agentTimeline: agentSessionState.agentTimeline,
            pendingAgentConfirmation: agentSessionState.pendingAgentConfirmation,
            agentWorkspaceRoot: agentSessionState.agentWorkspaceRoot,
            autoApproveSafeTools: agentSessionState.autoApproveSafeTools,
            sessions: get().sessions.map((session) =>
              session.id === sessionId ? mergeLoadedSessionRecord(session, sessionData) : session
            ),
          })
        } catch (error) {
          console.error('加载会话失败:', error)
          set({
            currentSessionId: sessionId,
            messages: [],
            ...resetAgentRuntimeState(),
          })
        }
      },

      deleteSession: async (sessionId) => {
        try {
          await deleteChatSession(sessionId)
        } catch (error) {
          console.error('删除会话失败:', error)
        }
        
        set((state) => ({
          sessions: state.sessions.filter((s) => s.id !== sessionId),
          currentSessionId: state.currentSessionId === sessionId ? null : state.currentSessionId,
          messages: state.currentSessionId === sessionId ? [] : state.messages,
        }))
      },

      updateSessionTitle: (sessionId, title) => {
        set((state) => ({
          sessions: state.sessions.map((s) =>
            s.id === sessionId ? { ...s, title, updatedAt: new Date().toISOString() } : s
          ),
        }))
      },

      setCurrentSessionId: (sessionId) => {
        set({ currentSessionId: sessionId })
      },

      loadSessions: async () => {
        try {
          const sessions = await listChatSessions(get().settings.backend)
          set({
            sessions,
          })
        } catch (error) {
          console.error('加载会话列表失败:', error)
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
              : session
          ),
        }))
      },

      addMessage: (message) => {
        const id = `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
        const newMessage: ChatMessage = {
          ...message,
          id,
          timestamp: new Date().toISOString(),
        }
        
        set((state) => ({
          messages: [...state.messages, newMessage],
        }))
        
        return id
      },

      updateMessage: (id, updates) => {
        set((state) => ({
          messages: state.messages.map((m) =>
            m.id === id ? { ...m, ...updates } : m
          ),
        }))
      },

      deleteMessage: (id) => {
        set((state) => ({
          messages: state.messages.filter((m) => m.id !== id),
        }))
      },

      editMessage: (id, content) => {
        set((state) => ({
          messages: state.messages.map((m) =>
            m.id === id ? { ...m, content, isEdited: true } : m
          ),
        }))
      },

      clearMessages: () => {
        set({ messages: [] })
      },

      setMessages: (messages) => {
        set({ messages })
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
        })
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
        }))
        
        const { streamingMessageId } = get()
        if (streamingMessageId) {
          get().updateMessage(streamingMessageId, { content })
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
        })
      },

      completeStreaming: () => {
        const { streamingMessageId } = get()
        if (streamingMessageId) {
          get().updateMessage(streamingMessageId, { isLoading: false })
        }
        
        set({
          isStreaming: false,
          streamingMessageId: null,
          streamState: {
            ...get().streamState,
            status: 'completed',
          },
        })
      },

      setStreamState: (updates) => {
        set((state) => ({
          streamState: { ...state.streamState, ...updates },
        }))
      },

      setAgentExecution: (execution) => {
        set({ agentExecution: execution })
      },

      confirmAgentExecution: async () => {
        const { agentExecution } = get()
        if (!agentExecution) return

        set({
          agentExecution: { ...agentExecution, status: 'executing' },
        })

        try {
          const response = await fetch(`${API_BASE_URL}/agent/chat-execute`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              message: agentExecution.description,
              auto_confirm: true,
              context: agentExecution.params,
            }),
          })
          
          const result = await response.json()
          
          set({
            agentExecution: {
              ...agentExecution,
              status: 'completed',
              result: result.result,
            },
          })
        } catch (error) {
          set({
            agentExecution: {
              ...agentExecution,
              status: 'failed',
              error: String(error),
            },
          })
        }
      },

      cancelAgentExecution: () => {
        set({ agentExecution: null })
      },

      setAgentMode: (agentMode) => {
        set({ agentMode })
      },

      setAgentTaskStatus: (agentTaskStatus) => {
        set({ agentTaskStatus })
      },

      appendAgentTimeline: (event) => {
        set((state) => ({
          agentTimeline: appendAgentTimelineEvent(state.agentTimeline, event),
        }))
      },

      replaceAgentTimeline: (agentTimeline) => {
        set({ agentTimeline: replaceAgentTimelineEvents(agentTimeline) })
      },

      clearAgentTimeline: () => {
        set({ agentTimeline: resetAgentRuntimeState().agentTimeline })
      },

      setPendingAgentConfirmation: (pendingAgentConfirmation) => {
        set({ pendingAgentConfirmation })
      },

      setAgentWorkspaceRoot: (agentWorkspaceRoot) => {
        set({ agentWorkspaceRoot })
      },

      setAutoApproveSafeTools: (autoApproveSafeTools) => {
        set({ autoApproveSafeTools })
      },

      updateSettings: (newSettings) => {
        set((state) => ({
          settings: { ...state.settings, ...newSettings },
        }))
      },

      setPromptDraft: (promptDraft) => {
        set({ promptDraft })
      },

      setAttachments: (attachments) => {
        set({ attachments })
      },

      addAttachment: (attachment) => {
        set((state) => ({
          attachments: [...state.attachments, attachment],
        }))
      },

      removeAttachment: (attachmentId) => {
        set((state) => ({
          attachments: state.attachments.filter((attachment) => attachment.id !== attachmentId),
        }))
      },

      clearAttachments: () => {
        set({ attachments: [] })
      },

      setActiveCandidates: (activeCandidates) => {
        set(setActiveExperimentCandidates(activeCandidates))
      },

      updateActiveCandidate: (candidateId, updates) => {
        set((state) => ({
          activeCandidates: state.activeCandidates.map((candidate) =>
            candidate.id === candidateId ? { ...candidate, ...updates } : candidate
          ),
        }))
      },

      clearActiveCandidates: () => {
        set(clearActiveExperimentCandidates())
      },

      setSelectedCandidateId: (selectedCandidateId) => {
        set({ selectedCandidateId })
      },

      addExperimentSnapshot: (snapshot) => {
        set((state) => addExperimentSnapshotRecord(state.experimentSnapshots, snapshot))
      },

      updateExperimentSnapshot: (snapshotId, updates) => {
        set((state) =>
          updateExperimentSnapshotRecord(
            state.experimentSnapshots,
            snapshotId,
            updates,
            state.lastRunMetadata
          )
        )
      },

      setSelectedExperimentId: (selectedExperimentId) => {
        set({ selectedExperimentId })
      },

      setResponseView: (responseView) => {
        set({ responseView })
      },

      setLastRunMetadata: (lastRunMetadata) => {
        set({ lastRunMetadata })
      },

      savePreset: (preset) => {
        set((state) => saveExperimentPreset(state.presets, preset))
      },

      deletePreset: (presetId) => {
        set((state) =>
          deleteExperimentPreset(state.presets, presetId, state.selectedPresetId)
        )
      },

      setSelectedPresetId: (selectedPresetId) => {
        set({ selectedPresetId })
      },

      setError: (error) => {
        set({ error })
      },

      setIsLoading: (loading) => {
        set({ isLoading: loading })
      },
    }),
    {
      name: 'chat-storage',
      partialize: (state) => ({
        currentSessionId: state.currentSessionId,
        settings: state.settings,
        sessions: state.sessions.slice(0, 50),
        agentMode: state.agentMode,
        agentWorkspaceRoot: state.agentWorkspaceRoot,
        autoApproveSafeTools: state.autoApproveSafeTools,
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
        pendingAgentConfirmation: state.pendingAgentConfirmation,
      }),
    }
  )
)
