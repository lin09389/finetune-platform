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
  responseView: 'response' | 'sources' | 'metadata' | 'raw'
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
      agentMode: false,
      agentTaskStatus: 'idle',
      agentTimeline: [],
      pendingAgentConfirmation: null,
      agentWorkspaceRoot: '',
      autoApproveSafeTools: false,
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
      activeCandidates: [],
      selectedCandidateId: null,
      selectedExperimentId: null,
      responseView: 'response',
      lastRunMetadata: null,
      experimentSnapshots: [],
      presets: [],
      selectedPresetId: null,

      createSession: async (title = '新对话', modelId) => {
        try {
          const response = await fetch(`${API_BASE_URL}/chat/sessions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
              title, 
              model_id: modelId || get().settings.modelId 
            }),
          })
          
          if (!response.ok) {
            throw new Error('创建会话失败')
          }
          
          const session = await response.json()
          
          set((state) => ({
            sessions: [
              {
                ...session,
                modelId: session.model_id || modelId || get().settings.modelId,
                backend: get().settings.backend,
                createdAt: session.created_at || session.createdAt,
                updatedAt: session.updated_at || session.updatedAt,
                messageCount: session.message_count ?? session.messageCount ?? 0,
                metadata: session.metadata || {},
              },
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
          const [sessionResponse, messagesResponse] = await Promise.all([
            fetch(`${API_BASE_URL}/chat/sessions/${sessionId}`),
            fetch(`${API_BASE_URL}/chat/sessions/${sessionId}/messages`),
          ])
          
          if (!sessionResponse.ok || !messagesResponse.ok) {
            throw new Error('加载会话失败')
          }
          
          const sessionData = await sessionResponse.json()
          const messagesData = await messagesResponse.json()
          
          set({
            currentSessionId: sessionId,
            messages: (messagesData.messages || []).map((message: any) => ({
              ...message,
              timestamp: message.created_at || message.timestamp,
            })),
            promptDraft:
              typeof sessionData.metadata?.last_agent_goal === 'string'
                ? sessionData.metadata.last_agent_goal
                : get().promptDraft,
            agentMode: Boolean(sessionData.metadata?.agent_mode),
            agentTaskStatus: sessionData.metadata?.agent_status || 'idle',
            agentTimeline: Array.isArray(sessionData.metadata?.execution_timeline)
              ? sessionData.metadata.execution_timeline.map((event: any, index: number) => ({
                  id: event.id || `session_event_${index}`,
                  type: event.type || 'task_status',
                  title: event.title || event.stage || 'Session event',
                  description: event.description,
                  status: event.status,
                  tool_name: event.tool_name,
                  payload: event.payload,
                  createdAt: event.createdAt || event.timestamp || new Date().toISOString(),
                }))
              : [],
            pendingAgentConfirmation: sessionData.metadata?.pending_confirmation || null,
            agentWorkspaceRoot: sessionData.metadata?.workspace_root || '',
            autoApproveSafeTools: Boolean(sessionData.metadata?.auto_approve_safe_tools),
            sessions: get().sessions.map((session) =>
              session.id === sessionId
                ? {
                    ...session,
                    title: sessionData.title || session.title,
                    messageCount: sessionData.message_count ?? session.messageCount,
                    updatedAt: sessionData.updated_at || session.updatedAt,
                    metadata: sessionData.metadata || session.metadata || {},
                  }
                : session
            ),
          })
        } catch (error) {
          console.error('加载会话失败:', error)
          set({
            currentSessionId: sessionId,
            messages: [],
            agentTimeline: [],
            pendingAgentConfirmation: null,
          })
        }
      },

      deleteSession: async (sessionId) => {
        try {
          await fetch(`${API_BASE_URL}/chat/sessions/${sessionId}`, { 
            method: 'DELETE' 
          })
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
          const response = await fetch(`${API_BASE_URL}/chat/sessions`)
          
          if (!response.ok) {
            throw new Error('加载会话列表失败')
          }
          
          const data = await response.json()
          set({
            sessions: (data.sessions || []).map((session: any) => ({
              id: session.id,
              title: session.title,
              modelId: session.model_id || '',
              backend: session.backend || 'ollama',
              createdAt: session.created_at || session.createdAt,
              updatedAt: session.updated_at || session.updatedAt,
              messageCount: session.message_count ?? session.messageCount ?? 0,
              metadata: session.metadata || {},
            })),
          })
        } catch (error) {
          console.error('加载会话列表失败:', error)
        }
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
          agentTimeline: [...state.agentTimeline, event].slice(-200),
        }))
      },

      replaceAgentTimeline: (agentTimeline) => {
        set({ agentTimeline: agentTimeline.slice(-200) })
      },

      clearAgentTimeline: () => {
        set({ agentTimeline: [] })
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
        set({
          activeCandidates,
          selectedCandidateId: activeCandidates[0]?.id || null,
        })
      },

      updateActiveCandidate: (candidateId, updates) => {
        set((state) => ({
          activeCandidates: state.activeCandidates.map((candidate) =>
            candidate.id === candidateId ? { ...candidate, ...updates } : candidate
          ),
        }))
      },

      clearActiveCandidates: () => {
        set({
          activeCandidates: [],
          selectedCandidateId: null,
        })
      },

      setSelectedCandidateId: (selectedCandidateId) => {
        set({ selectedCandidateId })
      },

      addExperimentSnapshot: (snapshot) => {
        set((state) => ({
          experimentSnapshots: [snapshot, ...state.experimentSnapshots].slice(0, 100),
          selectedExperimentId: snapshot.id,
          activeCandidates: snapshot.candidates,
          selectedCandidateId: snapshot.selectedCandidateId,
          lastRunMetadata: snapshot,
        }))
      },

      updateExperimentSnapshot: (snapshotId, updates) => {
        set((state) => {
          const experimentSnapshots = state.experimentSnapshots.map((snapshot) =>
            snapshot.id === snapshotId ? { ...snapshot, ...updates } : snapshot
          )
          const lastRunMetadata =
            state.lastRunMetadata?.id === snapshotId
              ? { ...state.lastRunMetadata, ...updates }
              : state.lastRunMetadata

          return {
            experimentSnapshots,
            lastRunMetadata,
          }
        })
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
        set((state) => {
          const existing = state.presets.find((item) => item.id === preset.id)
          if (existing) {
            return {
              presets: state.presets.map((item) => (item.id === preset.id ? preset : item)),
            }
          }

          return {
            presets: [preset, ...state.presets].slice(0, 50),
          }
        })
      },

      deletePreset: (presetId) => {
        set((state) => ({
          presets: state.presets.filter((preset) => preset.id !== presetId),
          selectedPresetId:
            state.selectedPresetId === presetId ? null : state.selectedPresetId,
        }))
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
