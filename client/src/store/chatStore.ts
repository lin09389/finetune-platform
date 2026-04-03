import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type {
  ChatMessage,
  PlaygroundAttachment,
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
  isStreaming: boolean
  isLoading: boolean
  error: string | null
  settings: ChatSettings
  streamState: StreamState
  promptDraft: string
  attachments: PlaygroundAttachment[]
  selectedExperimentId: string | null
  responseView: 'response' | 'sources' | 'metadata' | 'raw'
  lastRunMetadata: PlaygroundSnapshot | null
  experimentSnapshots: PlaygroundSnapshot[]

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

  updateSettings: (settings: Partial<ChatSettings>) => void
  setPromptDraft: (prompt: string) => void
  setAttachments: (attachments: PlaygroundAttachment[]) => void
  addAttachment: (attachment: PlaygroundAttachment) => void
  removeAttachment: (attachmentId: string) => void
  clearAttachments: () => void
  addExperimentSnapshot: (snapshot: PlaygroundSnapshot) => void
  setSelectedExperimentId: (experimentId: string | null) => void
  setResponseView: (view: ChatStore['responseView']) => void
  setLastRunMetadata: (snapshot: PlaygroundSnapshot | null) => void

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
      selectedExperimentId: null,
      responseView: 'response',
      lastRunMetadata: null,
      experimentSnapshots: [],

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
            sessions: [session, ...state.sessions],
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
            sessions: get().sessions.map((session) =>
              session.id === sessionId
                ? {
                    ...session,
                    title: sessionData.title || session.title,
                    messageCount: sessionData.message_count ?? session.messageCount,
                    updatedAt: sessionData.updated_at || session.updatedAt,
                  }
                : session
            ),
          })
        } catch (error) {
          console.error('加载会话失败:', error)
          set({
            currentSessionId: sessionId,
            messages: [],
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
          set({ sessions: data.sessions || [] })
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

      addExperimentSnapshot: (snapshot) => {
        set((state) => ({
          experimentSnapshots: [snapshot, ...state.experimentSnapshots].slice(0, 100),
          selectedExperimentId: snapshot.id,
          lastRunMetadata: snapshot,
        }))
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
        promptDraft: state.promptDraft,
        attachments: state.attachments,
        selectedExperimentId: state.selectedExperimentId,
        responseView: state.responseView,
        lastRunMetadata: state.lastRunMetadata,
        experimentSnapshots: state.experimentSnapshots.slice(0, 50),
      }),
    }
  )
)
