import React from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const mockUseChatStore = vi.hoisted(() => vi.fn())
const mockUseChatStream = vi.hoisted(() => vi.fn())
const modalConfirmMock = vi.hoisted(() => vi.fn())

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
  ;(MockModal as unknown as { confirm: typeof modalConfirmMock }).confirm = modalConfirmMock

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
  const setActiveCandidates = vi.fn()
  const clearActiveCandidates = vi.fn()
  const addExperimentSnapshot = vi.fn()
  const setSelectedCandidateId = vi.fn()
  const setSelectedExperimentId = vi.fn()
  const setResponseView = vi.fn()
  const setLastRunMetadata = vi.fn()
  const savePreset = vi.fn()
  const deletePreset = vi.fn()
  const setSelectedPresetId = vi.fn()
  const runExperimentCandidates = vi.fn().mockResolvedValue([
    {
      id: 'candidate-1',
      index: 0,
      content: 'Local response A',
      status: 'completed',
      run_metrics: { model: 'llama3', backend: 'ollama' },
    },
    {
      id: 'candidate-2',
      index: 1,
      content: 'Local response B',
      status: 'completed',
      run_metrics: { model: 'llama3', backend: 'ollama' },
    },
  ])
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
      candidateCount: 2,
    },
    promptDraft: 'Explain this repo',
    attachments: [],
    activeCandidates: [],
    selectedCandidateId: null,
    selectedExperimentId: null,
    responseView: 'response',
    lastRunMetadata: null,
    experimentSnapshots: [],
    presets: [],
    selectedPresetId: null,
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
    setActiveCandidates,
    clearActiveCandidates,
    addExperimentSnapshot,
    setSelectedCandidateId,
    setSelectedExperimentId,
    setResponseView,
    setLastRunMetadata,
    savePreset,
    deletePreset,
    setSelectedPresetId,
    ...overrides,
  })

  beforeEach(() => {
    vi.clearAllMocks()
    modalConfirmMock.mockImplementation(({ onOk }: { onOk?: () => void }) => onOk?.())

    global.URL.createObjectURL = vi.fn(() => 'blob:mock')
    global.URL.revokeObjectURL = vi.fn()

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
      runExperimentCandidates,
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
    expect(screen.getByTestId('preset-panel')).toBeInTheDocument()
    expect(screen.getByTestId('candidate-grid')).toBeInTheDocument()
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

  it('submits a local experiment with structured multi-candidate payload', async () => {
    render(<Chat />)

    fireEvent.click(await screen.findByTestId('run-button'))

    await waitFor(() => {
      expect(runExperimentCandidates).toHaveBeenCalledWith(
        {
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
        },
        2,
        undefined
      )
      expect(addExperimentSnapshot).toHaveBeenCalledTimes(1)
      expect(setActiveCandidates).toHaveBeenCalledTimes(1)
      expect(setSelectedCandidateId).toHaveBeenCalledWith('candidate-1')
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
          candidateCount: 2,
        },
        promptDraft: 'Return JSON',
      })
    )

    render(<Chat />)

    fireEvent.click(await screen.findByTestId('run-button'))

    await waitFor(() => {
      expect(runExperimentCandidates).toHaveBeenCalledWith(
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
            backend: 'cloud',
          },
        },
        2,
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

  it('saves the current configuration as a preset', async () => {
    render(<Chat />)

    fireEvent.change(await screen.findByTestId('preset-name-input'), {
      target: { value: 'Debug JSON' },
    })
    fireEvent.click(screen.getByTestId('save-preset-button'))

    expect(savePreset).toHaveBeenCalledTimes(1)
    expect(savePreset.mock.calls[0][0]).toMatchObject({
      name: 'Debug JSON',
      config: {
        prompt: 'Explain this repo',
        systemPrompt: 'You are helpful.',
        modelId: 'llama3',
        backend: 'ollama',
        candidateCount: 2,
      },
    })
    expect(setSelectedPresetId).toHaveBeenCalledTimes(1)
  })

  it('shows a compare view after selecting two experiment snapshots', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        experimentSnapshots: [
          {
            id: 'exp-1',
            createdAt: '2026-04-04T10:00:00.000Z',
            title: 'Run one',
            response: 'First result',
            selectedCandidateId: 'exp-1-candidate-1',
            candidates: [
              {
                id: 'exp-1-candidate-1',
                index: 0,
                content: 'First result',
                status: 'completed',
              },
            ],
            experiment_config: {
              prompt: 'First prompt',
              systemPrompt: 'System',
              responseFormat: 'text',
              modelId: 'llama3',
              backend: 'ollama',
              temperature: 0.7,
              topP: 0.9,
              maxTokens: 1024,
              useKnowledge: true,
              knowledgeCollection: 'kb-1',
              useMemory: true,
              autoRetrieve: true,
              candidateCount: 2,
              attachments: [],
            },
          },
          {
            id: 'exp-2',
            createdAt: '2026-04-04T10:05:00.000Z',
            title: 'Run two',
            response: 'Second result',
            selectedCandidateId: 'exp-2-candidate-1',
            candidates: [
              {
                id: 'exp-2-candidate-1',
                index: 0,
                content: 'Second result',
                status: 'completed',
              },
            ],
            experiment_config: {
              prompt: 'Second prompt',
              systemPrompt: 'System',
              responseFormat: 'text',
              modelId: 'qwen',
              backend: 'huggingface',
              temperature: 1,
              topP: 0.8,
              maxTokens: 2048,
              useKnowledge: false,
              knowledgeCollection: 'kb-1',
              useMemory: false,
              autoRetrieve: false,
              candidateCount: 2,
              attachments: [],
            },
          },
        ],
      })
    )

    render(<Chat />)

    const compareButtons = await screen.findAllByText('Compare')
    fireEvent.click(compareButtons[0]!)
    fireEvent.click(compareButtons[1]!)

    expect(await screen.findByTestId('compare-panel')).toBeInTheDocument()
    expect(screen.getAllByText('Run one').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Run two').length).toBeGreaterThan(0)
    expect(screen.getAllByText('First result').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Second result').length).toBeGreaterThan(0)
    expect(screen.getAllByTestId('compare-diff-field').length).toBeGreaterThan(0)
    expect(screen.getAllByTestId('compare-output-diff').length).toBeGreaterThan(0)
  })

  it('can filter compare cards to only show changed fields', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        experimentSnapshots: [
          {
            id: 'exp-1',
            createdAt: '2026-04-04T10:00:00.000Z',
            title: 'Run one',
            response: 'First result',
            selectedCandidateId: 'exp-1-candidate-1',
            candidates: [
              {
                id: 'exp-1-candidate-1',
                index: 0,
                content: 'First result',
                status: 'completed',
              },
            ],
            experiment_config: {
              prompt: 'First prompt',
              systemPrompt: 'System',
              responseFormat: 'text',
              modelId: 'llama3',
              backend: 'ollama',
              temperature: 0.7,
              topP: 0.9,
              maxTokens: 1024,
              useKnowledge: true,
              knowledgeCollection: 'kb-1',
              useMemory: true,
              autoRetrieve: true,
              candidateCount: 2,
              attachments: [],
            },
          },
          {
            id: 'exp-2',
            createdAt: '2026-04-04T10:05:00.000Z',
            title: 'Run two',
            response: 'Second result',
            selectedCandidateId: 'exp-2-candidate-1',
            candidates: [
              {
                id: 'exp-2-candidate-1',
                index: 0,
                content: 'Second result',
                status: 'completed',
              },
            ],
            experiment_config: {
              prompt: 'Second prompt',
              systemPrompt: 'System',
              responseFormat: 'json',
              modelId: 'qwen',
              backend: 'huggingface',
              temperature: 1,
              topP: 0.8,
              maxTokens: 2048,
              useKnowledge: false,
              knowledgeCollection: 'kb-1',
              useMemory: false,
              autoRetrieve: false,
              candidateCount: 2,
              attachments: [],
            },
          },
        ],
      })
    )

    render(<Chat />)

    const compareButtons = await screen.findAllByText('Compare')
    fireEvent.click(compareButtons[0]!)
    fireEvent.click(compareButtons[1]!)

    const diffToggle = await screen.findByTestId('compare-only-diff')
    fireEvent.click(diffToggle)

    expect(screen.getAllByTestId('compare-diff-field').length).toBeGreaterThan(0)
    expect(screen.queryAllByTestId('compare-same-field')).toHaveLength(0)
  })

  it('updates the active preset in place', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        presets: [
          {
            id: 'preset-1',
            name: 'Starter',
            createdAt: '2026-04-04T10:00:00.000Z',
            updatedAt: '2026-04-04T10:00:00.000Z',
            config: {
              prompt: 'Old prompt',
              systemPrompt: 'Old system',
              responseFormat: 'text',
              modelId: 'llama3',
              backend: 'ollama',
              temperature: 0.7,
              topP: 0.9,
              maxTokens: 1024,
              useKnowledge: true,
              knowledgeCollection: 'kb-1',
              useMemory: true,
              autoRetrieve: true,
              candidateCount: 2,
              attachments: [],
            },
          },
        ],
        selectedPresetId: 'preset-1',
      })
    )

    render(<Chat />)

    fireEvent.change(await screen.findByTestId('preset-name-input'), {
      target: { value: 'Starter v2' },
    })
    fireEvent.click(screen.getByTestId('update-preset-button'))

    expect(savePreset).toHaveBeenCalledTimes(1)
    expect(savePreset.mock.calls[0][0]).toMatchObject({
      id: 'preset-1',
      name: 'Starter v2',
      config: {
        prompt: 'Explain this repo',
      },
    })
  })

  it('exports presets as json', async () => {
    const clickSpy = vi.fn()
    const originalCreateElement = document.createElement.bind(document)
    const createElementSpy = vi.spyOn(document, 'createElement').mockImplementation((tagName: string) => {
      if (tagName === 'a') {
        return {
          click: clickSpy,
          set href(_value: string) {},
          set download(_value: string) {},
        } as unknown as HTMLElement
      }
      return originalCreateElement(tagName)
    })

    mockUseChatStore.mockReturnValue(
      createStoreState({
        presets: [
          {
            id: 'preset-1',
            name: 'Starter',
            createdAt: '2026-04-04T10:00:00.000Z',
            updatedAt: '2026-04-04T10:00:00.000Z',
            config: {
              prompt: 'Old prompt',
              systemPrompt: 'Old system',
              responseFormat: 'text',
              modelId: 'llama3',
              backend: 'ollama',
              temperature: 0.7,
              topP: 0.9,
              maxTokens: 1024,
              useKnowledge: true,
              knowledgeCollection: 'kb-1',
              useMemory: true,
              autoRetrieve: true,
              candidateCount: 2,
              attachments: [],
            },
          },
        ],
      })
    )

    render(<Chat />)

    fireEvent.click(await screen.findByTestId('export-presets-button'))

    expect(global.URL.createObjectURL).toHaveBeenCalledTimes(1)
    expect(clickSpy).toHaveBeenCalledTimes(1)

    createElementSpy.mockRestore()
  })

  it('asks before overwriting duplicate presets during import', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        presets: [
          {
            id: 'preset-1',
            name: 'Starter',
            createdAt: '2026-04-04T10:00:00.000Z',
            updatedAt: '2026-04-04T10:00:00.000Z',
            config: {
              prompt: 'Old prompt',
              systemPrompt: 'Old system',
              responseFormat: 'text',
              modelId: 'llama3',
              backend: 'ollama',
              temperature: 0.7,
              topP: 0.9,
              maxTokens: 1024,
              useKnowledge: true,
              knowledgeCollection: 'kb-1',
              useMemory: true,
              autoRetrieve: true,
              candidateCount: 2,
              attachments: [],
            },
          },
        ],
      })
    )

    render(<Chat />)

    const importPayload = JSON.stringify({
      presets: [
        {
          id: 'preset-external',
          name: 'Starter',
          createdAt: '2026-04-05T10:00:00.000Z',
          updatedAt: '2026-04-05T10:00:00.000Z',
          config: {
            prompt: 'Imported prompt',
            systemPrompt: 'Imported system',
            responseFormat: 'json',
            modelId: 'glm-4',
            backend: 'cloud',
            temperature: 1,
            topP: 0.8,
            maxTokens: 2048,
            useKnowledge: false,
            knowledgeCollection: 'kb-1',
            useMemory: false,
            autoRetrieve: false,
            candidateCount: 2,
            attachments: [],
          },
        },
      ],
    })
    const importFile = {
      name: 'presets.json',
      type: 'application/json',
      text: vi.fn().mockResolvedValue(importPayload),
    } as unknown as File

    fireEvent.change(await screen.findByTestId('preset-import-input'), {
      target: { files: [importFile] },
    })

    await waitFor(() => {
      expect(modalConfirmMock).toHaveBeenCalledTimes(1)
      expect(savePreset).toHaveBeenCalledWith(
        expect.objectContaining({
          id: 'preset-1',
          name: 'Starter',
          config: expect.objectContaining({
            prompt: 'Imported prompt',
            backend: 'cloud',
          }),
        })
      )
    })

    expect(
      await screen.findByText('Import summary: 1 imported, 1 overwritten, 0 skipped.')
    ).toBeInTheDocument()
  })

  it('renders candidate cards, shows diff details, and reruns a single candidate', async () => {
    runExperimentCandidates.mockResolvedValueOnce([
      {
        id: 'candidate-rerun',
        index: 0,
        content: 'Updated candidate response',
        status: 'completed',
        run_metrics: {
          model: 'llama3',
          backend: 'ollama',
          duration_ms: 95,
        },
      },
    ])

    mockUseChatStore.mockReturnValue(
      createStoreState({
        activeCandidates: [
          {
            id: 'candidate-1',
            index: 0,
            content: 'First candidate response',
            status: 'completed',
            run_metrics: {
              model: 'llama3',
              backend: 'ollama',
              duration_ms: 110,
            },
          },
          {
            id: 'candidate-2',
            index: 1,
            content: 'Second candidate response with different ending',
            status: 'completed',
            run_metrics: {
              model: 'llama3',
              backend: 'ollama',
            },
          },
        ],
        selectedCandidateId: 'candidate-2',
        selectedExperimentId: 'exp-1',
        lastRunMetadata: {
          id: 'exp-1',
          createdAt: '2026-04-04T10:00:00.000Z',
          title: 'Candidate run',
          response: 'First candidate response',
          selectedCandidateId: 'candidate-1',
          candidates: [
            {
              id: 'candidate-1',
              index: 0,
              content: 'First candidate response',
              status: 'completed',
              run_metrics: {
                model: 'llama3',
                backend: 'ollama',
              },
            },
            {
              id: 'candidate-2',
              index: 1,
              content: 'Second candidate response with different ending',
              status: 'completed',
            },
          ],
          experiment_config: {
            prompt: 'Explain this repo',
            systemPrompt: 'You are helpful.',
            responseFormat: 'text',
            modelId: 'llama3',
            backend: 'ollama',
            temperature: 0.7,
            topP: 0.9,
            maxTokens: 2048,
            useKnowledge: true,
            knowledgeCollection: 'kb-1',
            useMemory: true,
            autoRetrieve: true,
            candidateCount: 2,
            attachments: [],
          },
        },
      })
    )

    render(<Chat />)

    expect(await screen.findByTestId('candidate-card-1')).toBeInTheDocument()
    expect(screen.getByTestId('candidate-card-2')).toBeInTheDocument()
    expect(await screen.findByTestId('candidate-diff-panel')).toBeInTheDocument()
    expect(screen.getAllByTestId('candidate-diff-added').length).toBeGreaterThan(0)

    fireEvent.click(screen.getByTestId('candidate-card-2'))
    expect(setSelectedCandidateId).toHaveBeenCalledWith('candidate-2')

    fireEvent.click(screen.getByTestId('candidate-rerun-2'))
    await waitFor(() => {
      expect(runExperimentCandidates).toHaveBeenCalledWith(
        {
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
        },
        1,
        undefined
      )
    })

    fireEvent.click(screen.getByTestId('candidate-keep-2'))
    expect(setActiveCandidates).toHaveBeenCalledWith([
      expect.objectContaining({
        id: 'candidate-2',
        index: 0,
      }),
    ])

    fireEvent.click(screen.getByTestId('candidate-discard-2'))
    expect(setActiveCandidates).toHaveBeenCalledWith([
      expect.objectContaining({
        id: 'candidate-1',
        index: 0,
      }),
    ])

    fireEvent.click(screen.getByTestId('candidate-primary-2'))
    expect(setSelectedCandidateId).toHaveBeenCalledWith('candidate-2')
  })
})
