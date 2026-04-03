import React from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const mockUseChatStore = vi.hoisted(() => vi.fn())
const mockUseChatStream = vi.hoisted(() => vi.fn())

const getBackendsMock = vi.hoisted(() => vi.fn())
const getOllamaStatusMock = vi.hoisted(() => vi.fn())
const getInferenceModelsMock = vi.hoisted(() => vi.fn())

vi.mock('../store/chatStore', () => ({
  useChatStore: mockUseChatStore,
}))

vi.mock('../hooks/chat/useChatStream', () => ({
  useChatStream: mockUseChatStream,
}))

vi.mock('../services/api', () => ({
  API_BASE_URL: 'http://localhost:8000',
  getBackends: getBackendsMock,
  getOllamaStatus: getOllamaStatusMock,
  getInferenceModels: getInferenceModelsMock,
}))

vi.mock('../components/shared/AnimatedLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('../components/ChatHistoryDrawer', () => ({
  default: ({ open }: { open: boolean }) => (open ? <div data-testid="history-drawer" /> : null),
}))

vi.mock('../components/MemoryManager', () => ({
  default: ({ open }: { open: boolean }) => (open ? <div data-testid="memory-manager" /> : null),
}))

vi.mock('../pages/APIKeyManager', () => ({
  default: () => <div data-testid="api-key-manager">api-key-manager</div>,
}))

vi.mock('antd', async () => {
  const actual = await vi.importActual('antd')
  const MockModal = ({ children, open }: { children?: React.ReactNode; open?: boolean }) =>
    open ? <div data-testid="mock-modal">{children}</div> : null

  return {
    ...(actual as object),
    Modal: MockModal,
    message: {
      error: vi.fn(),
      success: vi.fn(),
      warning: vi.fn(),
    },
  }
})

import Chat from '../pages/Chat'

describe('Chat Playground', () => {
  const createSession = vi.fn().mockResolvedValue({ id: 'session-1' })
  const loadSession = vi.fn()
  const deleteSession = vi.fn()
  const loadSessions = vi.fn().mockResolvedValue(undefined)
  const clearMessages = vi.fn()
  const updateSettings = vi.fn()
  const setPromptDraft = vi.fn()
  const setAttachments = vi.fn()
  const removeAttachment = vi.fn()
  const clearAttachments = vi.fn()
  const addExperimentSnapshot = vi.fn()
  const setSelectedExperimentId = vi.fn()
  const setResponseView = vi.fn()
  const setLastRunMetadata = vi.fn()
  const sendMessage = vi.fn().mockResolvedValue({
    content: 'Local response',
    metadata: {
      runMetrics: { model: 'llama3', backend: 'ollama' },
    },
  })
  const sendCloudMessage = vi.fn().mockResolvedValue({
    content: 'Cloud response',
    metadata: {
      runMetrics: { model: 'glm-4', backend: 'cloud' },
    },
  })
  const stop = vi.fn()
  const createStoreState = (overrides: Record<string, unknown> = {}) => ({
    sessions: [],
    currentSessionId: 'session-1',
    messages: [],
    settings: {
      modelId: 'llama3',
      backend: 'ollama',
      useKnowledge: true,
      knowledgeCollection: 'kb-1',
      useMemory: true,
      systemPrompt: 'You are helpful.',
      temperature: 0.7,
      topP: 0.9,
      maxTokens: 2048,
      autoRetrieve: true,
      responseFormat: 'text',
    },
    promptDraft: 'Explain this repo',
    attachments: [],
    selectedExperimentId: null,
    responseView: 'response',
    lastRunMetadata: null,
    experimentSnapshots: [],
    createSession,
    loadSession,
    deleteSession,
    loadSessions,
    clearMessages,
    updateSettings,
    setPromptDraft,
    setAttachments,
    removeAttachment,
    clearAttachments,
    addExperimentSnapshot,
    setSelectedExperimentId,
    setResponseView,
    setLastRunMetadata,
    ...overrides,
  })

  beforeEach(() => {
    vi.clearAllMocks()

    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    })

    global.fetch = vi.fn((input: RequestInfo | URL) => {
      const url = String(input)

      if (url.endsWith('/knowledge/collections')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            collections: [
              { name: 'kb-1', count: 3 },
              { name: 'kb-2', count: 1 },
            ],
          }),
        } as Response)
      }

      if (url.endsWith('/cloud/api-keys')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            keys: [{ id: 'key-1', provider: 'glm' }],
          }),
        } as Response)
      }

      if (url.endsWith('/cloud/api-keys/key-1/data')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            group_id: 'group-1',
            base_url: 'https://api.example.com',
          }),
        } as Response)
      }

      return Promise.resolve({
        ok: true,
        json: async () => ({}),
      } as Response)
    }) as typeof fetch

    getBackendsMock.mockResolvedValue({
      backends: [
        { id: 'ollama', name: 'Ollama', available: true },
        { id: 'huggingface', name: 'HuggingFace', available: true },
      ],
    })
    getOllamaStatusMock.mockResolvedValue({ models: [{ name: 'llama3' }] })
    getInferenceModelsMock.mockResolvedValue([{ id: 'qwen', name: 'Qwen' }])

    mockUseChatStore.mockReturnValue(createStoreState())

    mockUseChatStream.mockReturnValue({
      sendMessage,
      sendCloudMessage,
      stop,
      isStreaming: false,
      state: {
        content: '',
      },
    })
  })

  it('renders the playground layout', async () => {
    render(<Chat />)

    expect(await screen.findByTestId('playground-topbar')).toBeInTheDocument()
    expect(screen.getByTestId('playground-left-panel')).toBeInTheDocument()
    expect(screen.getByTestId('playground-right-panel')).toBeInTheDocument()
    expect(screen.getByTestId('parameter-panel')).toBeInTheDocument()
  })

  it('loads backends, sessions, cloud config, and knowledge collections on mount', async () => {
    render(<Chat />)

    await waitFor(() => {
      expect(getBackendsMock).toHaveBeenCalledTimes(1)
      expect(getOllamaStatusMock).toHaveBeenCalledTimes(1)
      expect(getInferenceModelsMock).toHaveBeenCalledTimes(1)
      expect(loadSessions).toHaveBeenCalledTimes(1)
      expect(global.fetch).toHaveBeenCalledWith('http://localhost:8000/cloud/api-keys')
      expect(global.fetch).toHaveBeenCalledWith('http://localhost:8000/knowledge/collections')
    })
  })

  it('submits a local experiment with structured payload', async () => {
    render(<Chat />)

    fireEvent.click(await screen.findByTestId('run-button'))

    await waitFor(() => {
      expect(sendMessage).toHaveBeenCalledWith({
        prompt: 'Explain this repo',
        systemPrompt: 'You are helpful.',
        responseFormat: 'text',
        attachments: [],
        parameterOverrides: {
          temperature: 0.7,
          topP: 0.9,
          maxTokens: 2048,
          modelId: 'llama3',
          backend: 'ollama',
        },
      })
      expect(addExperimentSnapshot).toHaveBeenCalledTimes(1)
      expect(sendCloudMessage).not.toHaveBeenCalled()
    })
  })

  it('submits a cloud experiment when cloud mode is selected', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        settings: {
          modelId: 'glm-4',
          backend: 'cloud',
        useKnowledge: true,
        knowledgeCollection: 'kb-1',
        useMemory: true,
        systemPrompt: 'System prompt',
        temperature: 0.8,
        topP: 0.95,
        maxTokens: 1024,
        autoRetrieve: true,
          responseFormat: 'json',
        },
        promptDraft: 'Return JSON',
      })
    )

    render(<Chat />)

    fireEvent.click(await screen.findByTestId('run-button'))

    await waitFor(() => {
      expect(sendCloudMessage).toHaveBeenCalledWith(
        {
          prompt: 'Return JSON',
          systemPrompt: 'System prompt',
          responseFormat: 'json',
          attachments: [],
          parameterOverrides: {
            temperature: 0.8,
            topP: 0.95,
            maxTokens: 1024,
            modelId: 'glm-4',
          },
        },
        {
          provider: 'glm',
          apiKey: '',
          keyId: 'key-1',
          model: 'glm-4',
          groupId: 'group-1',
          baseUrl: 'https://api.example.com',
        }
      )
    })
  })
})
