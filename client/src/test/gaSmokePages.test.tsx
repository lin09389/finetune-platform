import React from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const mockUseAppStore = vi.hoisted(() => vi.fn())
const mockUseRuntimeContext = vi.hoisted(() => vi.fn())
const mockGetTrainingStatus = vi.hoisted(() => vi.fn())
const mockCheckTrainingResources = vi.hoisted(() => vi.fn())
const mockGetTrainingFailureAnalytics = vi.hoisted(() => vi.fn())
const mockGetTrainingHistory = vi.hoisted(() => vi.fn())
const mockGetTrainingCheckpoints = vi.hoisted(() => vi.fn())
const mockGetTrainingRecoveryOptions = vi.hoisted(() => vi.fn())
const mockResumeTraining = vi.hoisted(() => vi.fn())
const mockSubscribeTrainingProgress = vi.hoisted(() => vi.fn(() => vi.fn()))
const mockGetBackends = vi.hoisted(() => vi.fn())
const mockGetModelList = vi.hoisted(() => vi.fn())
const mockGetOllamaStatus = vi.hoisted(() => vi.fn())
const mockListInferenceEngines = vi.hoisted(() => vi.fn())
const mockGetPerformanceStats = vi.hoisted(() => vi.fn())
const mockGetPerformanceRecommendations = vi.hoisted(() => vi.fn())
const mockFetch = vi.hoisted(() => vi.fn())
const mockLoadSessions = vi.hoisted(() => vi.fn())
const mockCreateSession = vi.hoisted(() => vi.fn())
const mockDeleteSession = vi.hoisted(() => vi.fn())
const mockDeleteMessage = vi.hoisted(() => vi.fn())
const mockClearMessages = vi.hoisted(() => vi.fn())
const mockUpdateSettings = vi.hoisted(() => vi.fn())
const mockSendMessage = vi.hoisted(() => vi.fn())
const mockSendCloudMessage = vi.hoisted(() => vi.fn())
const mockStopStream = vi.hoisted(() => vi.fn())
const mockSyncInferenceSelection = vi.hoisted(() => vi.fn())
const mockSetInferenceSelection = vi.hoisted(() => vi.fn())
const mockSyncKnowledgeCollection = vi.hoisted(() => vi.fn())
const mockRefreshInference = vi.hoisted(() => vi.fn())
const mockRefreshKnowledge = vi.hoisted(() => vi.fn())
const mockRefreshBootstrap = vi.hoisted(() => vi.fn())
const mockNotify = vi.hoisted(() => ({
  success: vi.fn(),
  warning: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
  emit: vi.fn(),
}))

vi.stubGlobal('fetch', mockFetch)

vi.mock('../store/appStore', () => ({
  useAppStore: mockUseAppStore,
}))

vi.mock('../runtime/RuntimeContext', () => ({
  useRuntimeContext: mockUseRuntimeContext,
}))

vi.mock('../utils/notify', () => ({
  notify: mockNotify,
}))

vi.mock('../services/trainingApi', () => ({
  checkTrainingResources: mockCheckTrainingResources,
  getTrainingFailureAnalytics: mockGetTrainingFailureAnalytics,
  getTrainingStatus: mockGetTrainingStatus,
  getTrainingHistory: mockGetTrainingHistory,
  getTrainingCheckpoints: mockGetTrainingCheckpoints,
  getTrainingRecoveryOptions: mockGetTrainingRecoveryOptions,
  resumeTraining: mockResumeTraining,
  startTraining: vi.fn(),
  stopTraining: vi.fn(),
  subscribeTrainingProgress: mockSubscribeTrainingProgress,
  startSwiftTraining: vi.fn(),
}))

vi.mock('../services/api', () => ({
  API_BASE_URL: 'http://localhost:8000',
  getBackends: mockGetBackends,
  getModelList: mockGetModelList,
  getOllamaStatus: mockGetOllamaStatus,
  listInferenceEngines: mockListInferenceEngines,
  getPerformanceStats: mockGetPerformanceStats,
  getPerformanceRecommendations: mockGetPerformanceRecommendations,
  streamInference: vi.fn(),
  streamGenerate: vi.fn(),
  switchBackend: vi.fn(),
  getInferenceModels: vi.fn(() => Promise.resolve([{ id: 'hf-model', name: 'HF Model' }])),
}))

vi.mock('../store/chatStore', () => ({
  useChatStore: () => ({
    sessions: [],
    messages: [],
    settings: {
      backend: 'huggingface',
      modelId: '',
      useKnowledge: false,
      useMemory: false,
    },
    isLoading: false,
    createSession: mockCreateSession,
    loadSession: vi.fn(),
    deleteSession: mockDeleteSession,
    loadSessions: mockLoadSessions,
    deleteMessage: mockDeleteMessage,
    clearMessages: mockClearMessages,
    updateSettings: mockUpdateSettings,
  }),
}))

vi.mock('../hooks/chat/useChatStream', () => ({
  useChatStream: () => ({
    sendMessage: mockSendMessage,
    sendCloudMessage: mockSendCloudMessage,
    stop: mockStopStream,
    isStreaming: false,
  }),
}))

vi.mock('../theme', () => ({
  useTheme: () => ({
    theme: 'light',
    toggleTheme: vi.fn(),
  }),
}))

vi.mock('../hooks/useResponsive', () => ({
  useResponsive: () => ({
    isMobile: false,
  }),
}))

vi.mock('../components/chat/ChatHeader', () => ({
  default: () => <div>Mock Chat Header</div>,
}))

vi.mock('../components/ChatMessage', () => ({
  default: () => <div>Mock Chat Message</div>,
}))

vi.mock('../components/chat/ChatInput', () => ({
  default: () => <div>Mock Chat Input</div>,
}))

vi.mock('../components/ChatHistoryDrawer', () => ({
  default: () => <div>Mock Chat History Drawer</div>,
}))

vi.mock('../components/MemoryManager', () => ({
  default: () => <div>Mock Memory Manager</div>,
}))

vi.mock('../pages/APIKeyManager', () => ({
  default: () => <div>Mock API Key Manager</div>,
}))

vi.mock('../components/shared/GlassCard', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('../components/shared/AnimatedLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('../pages/Training/components/ConfigForm', () => ({
  default: ({ form }: { form: { setFieldsValue: (values: Record<string, unknown>) => void; getFieldValue: (name: string) => unknown } }) => (
    <div>
      <button type="button" onClick={() => form.setFieldsValue({ modelId: 'train-model-1' })}>
        Mock Select Training Model
      </button>
      <div>Mock Config Form</div>
      <div data-testid="mock-training-model">{String(form.getFieldValue('modelId') || '')}</div>
    </div>
  ),
}))

vi.mock('../pages/Training/components/ProgressPanel', () => ({
  default: () => <div>Mock Progress Panel</div>,
}))

vi.mock('../pages/Training/components/LossChart', () => ({
  default: () => <div>Mock Loss Chart</div>,
}))

vi.mock('../components/SwiftChecker', () => ({
  default: ({ onStatusChange }: { onStatusChange: (status: { available: boolean }) => void }) => {
    React.useEffect(() => {
      onStatusChange({ available: false })
    }, [onStatusChange])
    return <div>Mock Swift Checker</div>
  },
}))

vi.mock('../components/TrainingChart', () => ({
  default: () => <div>Mock Training Chart</div>,
}))

vi.mock('react-virtuoso', () => ({
  Virtuoso: ({ itemContent, totalCount }: { itemContent?: (index: number) => React.ReactNode; totalCount?: number }) => (
    <div>{Array.from({ length: totalCount || 0 }, (_, index) => itemContent?.(index))}</div>
  ),
}))

import TrainingPage from '../pages/Training'
import Inference from '../pages/Inference'
import KnowledgeBase from '../pages/KnowledgeBase'
import ChatPage from '../pages/ChatNew'

describe('GA smoke pages', () => {
  beforeEach(() => {
    vi.clearAllMocks()

    mockUseAppStore.mockReturnValue({
      models: [],
      datasets: [],
      backendStatus: 'connected',
      isTraining: false,
      setIsTraining: vi.fn(),
      addTrainingRecord: vi.fn(),
      setModels: vi.fn(),
    })

    mockUseRuntimeContext.mockReturnValue({
      observed: {
        backendStatus: 'connected',
        inference: {
          backends: [
            { id: 'ollama', name: 'Ollama', available: false },
            { id: 'huggingface', name: 'HuggingFace', available: true },
          ],
          currentBackend: 'ollama',
          huggingfaceModels: [],
          ollamaModels: [],
          ollamaAvailable: false,
        },
        knowledge: {
          collections: [],
          embedderStatus: { loaded: false, error: 'unavailable' },
        },
      },
      selected: {
        training: {},
        inference: {
          backend: 'ollama',
          modelId: undefined,
        },
        knowledge: {},
      },
      derived: {
        activeBackend: 'ollama',
        activeModelId: 'runtime-active-model',
        activeKnowledgeCollection: 'default',
        availableModelCount: 0,
        runtimeStatus: 'degraded',
        warnings: [],
      },
      actions: {
        refreshBootstrap: mockRefreshBootstrap,
        refreshInference: mockRefreshInference,
        refreshKnowledge: mockRefreshKnowledge,
        setTrainingSelection: vi.fn(),
        setInferenceSelection: mockSetInferenceSelection,
        setKnowledgeSelection: vi.fn(),
        syncInferenceSelection: mockSyncInferenceSelection,
        syncKnowledgeCollection: mockSyncKnowledgeCollection,
      },
      backendStatus: 'connected',
      inference: {
        backends: [
          { id: 'ollama', name: 'Ollama', available: false },
          { id: 'huggingface', name: 'HuggingFace', available: true },
        ],
        currentBackend: 'ollama',
        selectedBackend: 'ollama',
        selectedModelId: undefined,
        huggingfaceModels: [],
        ollamaModels: [],
        availableModelCount: 0,
        ollamaAvailable: false,
        refresh: vi.fn(),
      },
      knowledge: {
        collections: [],
        selectedCollectionId: 'default',
        embedderStatus: { loaded: false, error: 'unavailable' },
        refresh: vi.fn(),
      },
      chat: {
        backend: 'huggingface',
        modelId: '',
        useKnowledge: false,
        knowledgeCollection: undefined,
        useMemory: false,
        update: vi.fn(),
      },
      training: {},
      summary: {
        activeBackend: 'ollama',
        activeModelId: 'runtime-active-model',
        activeKnowledgeCollection: 'default',
        runtimeStatus: 'degraded',
        warnings: [],
      },
      setTrainingSelection: vi.fn(),
      setInferenceSelection: mockSetInferenceSelection,
      setKnowledgeSelection: vi.fn(),
      syncInferenceSelection: mockSyncInferenceSelection,
      syncKnowledgeCollection: mockSyncKnowledgeCollection,
    })

    mockGetTrainingStatus.mockResolvedValue({
      is_training: false,
      progress: null,
    })
    mockCheckTrainingResources.mockResolvedValue({
      passed: true,
      available_vram: 8,
      required_vram: 4,
      suggestions: [],
      warnings: [],
      recommended_config: {},
      device_name: 'Mock GPU',
    })
    mockGetTrainingFailureAnalytics.mockResolvedValue({
      totalRuns: 0,
      failedRuns: 0,
      stoppedRuns: 0,
      completedRuns: 0,
      failureRate: 0,
      failureRate7d: 0,
      failureRate14d: 0,
      failedRuns7d: 0,
      failedRuns14d: 0,
      totalRuns7d: 0,
      totalRuns14d: 0,
      suspectedVramPressureCount: 0,
      longContextFailureCount: 0,
      unquantizedFailureCount: 0,
      topFailedModels: [],
      topFailedDatasets: [],
      topFailedMethods: [],
      recentFailures: [],
    })
    mockGetTrainingHistory.mockResolvedValue([])
    mockGetTrainingCheckpoints.mockResolvedValue([])
    mockGetTrainingRecoveryOptions.mockResolvedValue({
      generatedAt: new Date().toISOString(),
      options: [],
    })
    mockResumeTraining.mockResolvedValue({
      id: 'resume-task-1',
      modelName: 'mock-model',
      datasetName: 'mock-dataset',
      status: 'running',
      method: 'qlora',
      startTime: new Date().toISOString(),
      outputPath: '/tmp/output',
      config: {},
    })

    mockGetBackends.mockResolvedValue({
      current: 'ollama',
      backends: [
        { id: 'ollama', name: 'Ollama', available: false },
        { id: 'huggingface', name: 'HuggingFace', available: true },
      ],
    })
    mockGetModelList.mockResolvedValue([])
    mockGetOllamaStatus.mockResolvedValue({ models: [] })
    mockListInferenceEngines.mockResolvedValue({ engines: [] })
    mockGetPerformanceStats.mockResolvedValue({
      inference: { total_requests: 0, avg_latency_ms: 0 },
      streaming: { avg_first_token_ms: 0 },
    })
    mockGetPerformanceRecommendations.mockResolvedValue({ recommendations: [] })

    mockFetch.mockImplementation((url: string) => {
      if (url.includes('/knowledge/embedder/status')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ loaded: false, error: 'unavailable' }),
        })
      }
      if (url.includes('/knowledge/collections')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ collections: [] }),
        })
      }
      if (url.includes('/knowledge/collections/default')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ name: 'default', count: 0, documents: [] }),
        })
      }
      if (url.includes('/cloud/api-keys')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ keys: [] }),
        })
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({}),
      })
    })
  })

  it('renders disconnected training empty state', async () => {
    mockUseAppStore.mockReturnValue({
      models: [],
      datasets: [],
      backendStatus: 'disconnected',
      isTraining: false,
      setIsTraining: vi.fn(),
      addTrainingRecord: vi.fn(),
      setModels: vi.fn(),
    })

    render(<TrainingPage />)

    expect(screen.getByText('模型训练')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByText('后端服务未连接，请先启动应用。')).toBeInTheDocument()
    })
  })

  it('bridges training model selection with runtime context', async () => {
    render(<TrainingPage />)

    fireEvent.click(screen.getByRole('button', { name: '使用当前活跃模型' }))
    fireEvent.click(screen.getByRole('button', { name: '设为活跃推理模型' }))
    expect(mockSyncInferenceSelection).toHaveBeenCalledWith({
      backend: 'ollama',
      modelId: 'runtime-active-model',
    })

    fireEvent.click(screen.getByRole('button', { name: 'Mock Select Training Model' }))
    fireEvent.click(screen.getByRole('button', { name: '设为活跃推理模型' }))
    expect(mockSyncInferenceSelection).toHaveBeenCalledWith({
      backend: 'ollama',
      modelId: 'train-model-1',
    })
  })

  it('renders inference backend warning when ollama is unavailable', async () => {
    render(<Inference />)

    expect(screen.getByText('推理测试')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getAllByText('Ollama 未运行').length).toBeGreaterThan(0)
      expect(screen.getByText('请确保 Ollama 已启动，然后刷新页面')).toBeInTheDocument()
    })
  })

  it('renders knowledge embedder warning state', async () => {
    render(<KnowledgeBase />)

    expect(screen.getByText('RAG 知识库')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByText('嵌入模型未加载')).toBeInTheDocument()
      expect(screen.getAllByText('立即加载').length).toBeGreaterThan(0)
    })
  })

  it('renders chat shell and loads primary init resources', async () => {
    render(<ChatPage />)

    expect(screen.getByText('Mock Chat Header')).toBeInTheDocument()
    await waitFor(() => {
      expect(mockLoadSessions).toHaveBeenCalled()
      expect(screen.getByTestId('runtime-context-chat')).toBeInTheDocument()
      expect(mockFetch).toHaveBeenCalledWith('http://localhost:8000/cloud/api-keys')
    })
  })
})
