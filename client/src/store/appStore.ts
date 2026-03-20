import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { DeviceInfo, ModelInfo, DatasetInfo, TrainingProgress, TrainingRecord, ChatMessage } from '../types'

export type ThemeMode = 'light' | 'dark' | 'system'

export interface ChatSession {
  sessionId: string | null
  messages: ChatMessage[]
  modelId: string | null
  backend: string
}

interface AppState {
  backendUrl: string
  backendStatus: 'connected' | 'disconnected' | 'checking'
  deviceInfo: DeviceInfo | null
  models: ModelInfo[]
  datasets: DatasetInfo[]
  trainingProgress: TrainingProgress | null
  trainingRecords: TrainingRecord[]
  isTraining: boolean
  themeMode: ThemeMode
  actualTheme: 'light' | 'dark'
  sidebarCollapsed: boolean
  chatSessionId: string | null
  chatMessages: ChatMessage[]
  chatModelId: string | null
  chatBackend: string

  setBackendUrl: (url: string) => void
  setBackendStatus: (status: 'connected' | 'disconnected' | 'checking') => void
  setDeviceInfo: (info: DeviceInfo) => void
  setModels: (models: ModelInfo[]) => void
  addModel: (model: ModelInfo) => void
  removeModel: (id: string) => void
  setDatasets: (datasets: DatasetInfo[]) => void
  addDataset: (dataset: DatasetInfo) => void
  removeDataset: (id: string) => void
  setTrainingProgress: (progress: TrainingProgress | null) => void
  setTrainingRecords: (records: TrainingRecord[]) => void
  addTrainingRecord: (record: TrainingRecord) => void
  updateTrainingRecord: (id: string, updates: Partial<TrainingRecord>) => void
  removeTrainingRecord: (id: string) => void
  setIsTraining: (isTraining: boolean) => void
  setThemeMode: (mode: ThemeMode) => void
  setActualTheme: (theme: 'light' | 'dark') => void
  toggleSidebar: () => void
  setChatSession: (session: ChatSession) => void
  setChatSessionId: (sessionId: string | null) => void
  setChatMessages: (messages: ChatMessage[]) => void
  addChatMessage: (message: ChatMessage) => void
  updateChatMessage: (id: string, updates: Partial<ChatMessage>) => void
  clearChatSession: () => void
  setChatModelId: (modelId: string | null) => void
  setChatBackend: (backend: string) => void
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      backendUrl: 'http://127.0.0.1:8000',
      backendStatus: 'checking',
      deviceInfo: null,
      models: [],
      datasets: [],
      trainingProgress: null,
      trainingRecords: [],
      isTraining: false,
      themeMode: 'system',
      actualTheme: 'light',
      sidebarCollapsed: false,
      chatSessionId: null,
      chatMessages: [],
      chatModelId: null,
      chatBackend: 'ollama',

      setBackendUrl: (url) => set({ backendUrl: url }),
      setBackendStatus: (status) => set({ backendStatus: status }),
      setDeviceInfo: (info) => set({ deviceInfo: info }),
      setModels: (models) => set({ models }),
      addModel: (model) => set((state) => ({ models: [...state.models, model] })),
      removeModel: (id) => set((state) => ({ models: state.models.filter(m => m.id !== id) })),
      setDatasets: (datasets) => set({ datasets }),
      addDataset: (dataset) => set((state) => ({ datasets: [...state.datasets, dataset] })),
      removeDataset: (id) => set((state) => ({ datasets: state.datasets.filter(d => d.id !== id) })),
      setTrainingProgress: (progress) => set({ trainingProgress: progress }),
      setTrainingRecords: (records) => set({ trainingRecords: records }),
      addTrainingRecord: (record) => set((state) => ({ trainingRecords: [...state.trainingRecords, record] })),
      updateTrainingRecord: (id, updates) => set((state) => ({
        trainingRecords: state.trainingRecords.map(r => r.id === id ? { ...r, ...updates } : r)
      })),
      removeTrainingRecord: (id) => set((state) => ({
        trainingRecords: state.trainingRecords.filter(r => r.id !== id)
      })),
      setIsTraining: (isTraining) => set({ isTraining }),
      setThemeMode: (mode) => set({ themeMode: mode }),
      setActualTheme: (theme) => set({ actualTheme: theme }),
      toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
      setChatSession: (session) => set({ 
        chatSessionId: session.sessionId,
        chatMessages: session.messages,
        chatModelId: session.modelId,
        chatBackend: session.backend,
      }),
      setChatSessionId: (sessionId) => set({ chatSessionId: sessionId }),
      setChatMessages: (messages) => set({ chatMessages: messages }),
      addChatMessage: (message) => set((state) => ({ 
        chatMessages: [...state.chatMessages, message] 
      })),
      updateChatMessage: (id, updates) => set((state) => ({ 
        chatMessages: state.chatMessages.map(m => m.id === id ? { ...m, ...updates } : m) 
      })),
      clearChatSession: () => set({ 
        chatSessionId: null, 
        chatMessages: [], 
        chatModelId: null, 
        chatBackend: 'ollama' 
      }),
      setChatModelId: (modelId) => set({ chatModelId: modelId }),
      setChatBackend: (backend) => set({ chatBackend: backend }),
    }),
    {
      name: 'finetune-storage',
      partialize: (state) => ({
        backendUrl: state.backendUrl,
        models: state.models,
        datasets: state.datasets,
        trainingRecords: state.trainingRecords,
        themeMode: state.themeMode,
        sidebarCollapsed: state.sidebarCollapsed,
        chatSessionId: state.chatSessionId,
        chatMessages: state.chatMessages,
        chatModelId: state.chatModelId,
        chatBackend: state.chatBackend,
      })
    }
  )
)
