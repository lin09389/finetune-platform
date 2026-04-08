import React from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'

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
  default: ({
    open,
    sessions = [],
    onLoadOutcome,
  }: {
    open: boolean
    sessions?: Array<{ id: string; title: string; metadata?: Record<string, unknown> }>
    onLoadOutcome?: (sessionId: string, outcomeId: string) => void
  }) => {
    const [expandedSessionId, setExpandedSessionId] = React.useState<string | null>(null)
    const [selectedOutcomeIndexBySession, setSelectedOutcomeIndexBySession] = React.useState<
      Record<string, number>
    >({})

    if (!open) {
      return null
    }

    return (
      <div data-testid="history-drawer">
        {[...sessions]
          .sort((left, right) => {
            const leftCount = Array.isArray(left.metadata?.task_outcomes)
              ? left.metadata.task_outcomes.length
              : 0
            const rightCount = Array.isArray(right.metadata?.task_outcomes)
              ? right.metadata.task_outcomes.length
              : 0
            return rightCount - leftCount
          })
          .map((session) => {
            const taskOutcomes = Array.isArray(session.metadata?.task_outcomes)
              ? session.metadata.task_outcomes
              : []
            const selectedOutcomeIndex = selectedOutcomeIndexBySession[session.id] || 0
            const latestOutcome =
              taskOutcomes.length ? (taskOutcomes[0] as Record<string, unknown>) : null
            const selectedOutcome =
              taskOutcomes.length && taskOutcomes[selectedOutcomeIndex]
                ? (taskOutcomes[selectedOutcomeIndex] as Record<string, unknown>)
                : latestOutcome
            return (
              <div key={session.id} data-testid={`history-drawer-session-${session.id}`}>
                <span>{session.title}</span>
                {latestOutcome ? (
                  <div>
                    <span data-testid={`history-drawer-outcome-${session.id}`}>
                      {String(latestOutcome.title || latestOutcome.summary || '')}
                    </span>
                    <button
                      type="button"
                      data-testid={`history-drawer-preview-${session.id}`}
                      onClick={() =>
                        setExpandedSessionId((current) => (current === session.id ? null : session.id))
                      }
                    >
                      Preview outcome
                    </button>
                    {expandedSessionId === session.id ? (
                      <div data-testid={`history-drawer-preview-content-${session.id}`}>
                        {taskOutcomes.length > 1
                          ? taskOutcomes.map((outcome, index) => {
                              const typedOutcome = outcome as Record<string, unknown>
                              return (
                                <button
                                  key={`${session.id}-${index}`}
                                  type="button"
                                  data-testid={`history-drawer-outcome-tab-${session.id}-${index}`}
                                  onClick={() =>
                                    setSelectedOutcomeIndexBySession((current) => ({
                                      ...current,
                                      [session.id]: index,
                                    }))
                                  }
                                >
                                  {String(typedOutcome.title || `Outcome ${index + 1}`)}
                                </button>
                              )
                            })
                          : null}
                        <div>{String(selectedOutcome?.summary || selectedOutcome?.title || '')}</div>
                        {selectedOutcome && typeof selectedOutcome.id === 'string' && onLoadOutcome ? (
                          <button
                            type="button"
                            data-testid={`history-drawer-open-outcome-${session.id}`}
                            onClick={() => onLoadOutcome(session.id, selectedOutcome.id as string)}
                          >
                            Open this outcome
                          </button>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            )
          })}
      </div>
    )
  },
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
  const updateSessionMetadata = vi.fn()
  const clearMessages = vi.fn()
  const setAgentMode = vi.fn()
  const setAgentTaskStatus = vi.fn()
  const clearAgentTimeline = vi.fn()
  const setPendingAgentConfirmation = vi.fn()
  const setAgentWorkspaceRoot = vi.fn()
  const setAutoApproveSafeTools = vi.fn()
  const updateSettings = vi.fn()
  const setPromptDraft = vi.fn()
  const setAttachments = vi.fn()
  const removeAttachment = vi.fn()
  const clearAttachments = vi.fn()
  const setActiveCandidates = vi.fn()
  const clearActiveCandidates = vi.fn()
  const addExperimentSnapshot = vi.fn()
  const updateExperimentSnapshot = vi.fn()
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
  const runAgentTask = vi.fn().mockResolvedValue({ status: 'completed' })
  const resumeAgentTask = vi.fn().mockResolvedValue({ status: 'completed' })
  const resumeAgentFromEvent = vi.fn().mockResolvedValue({ status: 'completed' })
  const confirmAgentAction = vi.fn().mockResolvedValue({ status: 'completed' })
  const applyPatchDraft = vi.fn().mockResolvedValue({ status: 'completed' })
  const cancelAgentAction = vi.fn()
  const stop = vi.fn()

  const createStoreState = (overrides: Record<string, unknown> = {}) => ({
    sessions: [],
    currentSessionId: 'session-1',
    messages: [],
    agentMode: false,
    agentTaskStatus: 'idle',
    agentTimeline: [],
    pendingAgentConfirmation: null,
    agentWorkspaceRoot: '',
    autoApproveSafeTools: false,
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
    updateSessionMetadata,
    clearMessages,
    setAgentMode,
    setAgentTaskStatus,
    clearAgentTimeline,
    setPendingAgentConfirmation,
    setAgentWorkspaceRoot,
    setAutoApproveSafeTools,
    updateSettings,
    setPromptDraft,
    setAttachments,
    removeAttachment,
    clearAttachments,
    setActiveCandidates,
    clearActiveCandidates,
    addExperimentSnapshot,
    updateExperimentSnapshot,
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
      runAgentTask,
      resumeAgentTask,
      resumeAgentFromEvent,
      confirmAgentAction,
      applyPatchDraft,
      cancelAgentAction,
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
    expect(screen.getByTestId('agent-panel')).toBeInTheDocument()
  })

  it('passes latest task outcomes into the history drawer sessions', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        sessions: [
          {
            id: 'session-1',
            title: 'Repair session',
            modelId: 'llama3',
            backend: 'ollama',
            createdAt: '2026-04-04T10:00:00.000Z',
            updatedAt: '2026-04-04T10:30:00.000Z',
            messageCount: 12,
            metadata: {
              task_outcomes: [
                {
                  id: 'outcome-1',
                  title: 'Completion summary',
                  summary: 'Patched app.tsx and reran tests successfully.',
                },
              ],
            },
          },
        ],
      })
    )

    render(<Chat />)

    fireEvent.click(await screen.findByText('Sessions'))

    expect(await screen.findByTestId('history-drawer')).toBeInTheDocument()
    expect(screen.getByTestId('history-drawer-session-session-1')).toHaveTextContent('Repair session')
    expect(screen.getByTestId('history-drawer-outcome-session-1')).toHaveTextContent(
      'Completion summary'
    )
    fireEvent.click(screen.getByTestId('history-drawer-preview-session-1'))
    expect(screen.getByTestId('history-drawer-preview-content-session-1')).toHaveTextContent(
      'Patched app.tsx and reran tests successfully.'
    )
  })

  it('prioritizes sessions with task outcomes in the history drawer', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        sessions: [
          {
            id: 'session-plain',
            title: 'Plain session',
            modelId: 'llama3',
            backend: 'ollama',
            createdAt: '2026-04-04T10:00:00.000Z',
            updatedAt: '2026-04-04T10:10:00.000Z',
            messageCount: 3,
            metadata: {},
          },
          {
            id: 'session-outcome',
            title: 'Outcome session',
            modelId: 'llama3',
            backend: 'ollama',
            createdAt: '2026-04-04T09:00:00.000Z',
            updatedAt: '2026-04-04T09:30:00.000Z',
            messageCount: 5,
            metadata: {
              task_outcomes: [
                {
                  id: 'outcome-1',
                  title: 'Completion summary',
                  summary: 'Patched app.tsx and reran tests successfully.',
                },
              ],
            },
          },
        ],
      })
    )

    render(<Chat />)

    fireEvent.click(await screen.findByText('Sessions'))

    const drawer = await screen.findByTestId('history-drawer')
    const sessionNodes = within(drawer).getAllByTestId(/history-drawer-session-/)
    expect(sessionNodes[0]).toHaveAttribute('data-testid', 'history-drawer-session-session-outcome')
    expect(sessionNodes[1]).toHaveAttribute('data-testid', 'history-drawer-session-session-plain')
  })

  it('can switch between multiple outcomes in the history drawer preview', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        sessions: [
          {
            id: 'session-multi',
            title: 'Multi outcome session',
            modelId: 'llama3',
            backend: 'ollama',
            createdAt: '2026-04-04T10:00:00.000Z',
            updatedAt: '2026-04-04T10:30:00.000Z',
            messageCount: 8,
            metadata: {
              task_outcomes: [
                {
                  id: 'outcome-1',
                  title: 'Completion summary',
                  summary: 'First outcome summary.',
                },
                {
                  id: 'outcome-2',
                  title: 'Handoff ready',
                  summary: 'Second outcome summary.',
                },
              ],
            },
          },
        ],
      })
    )

    render(<Chat />)

    fireEvent.click(await screen.findByText('Sessions'))
    fireEvent.click(screen.getByTestId('history-drawer-preview-session-multi'))

    expect(screen.getByTestId('history-drawer-preview-content-session-multi')).toHaveTextContent(
      'First outcome summary.'
    )

    fireEvent.click(screen.getByTestId('history-drawer-outcome-tab-session-multi-1'))
    expect(screen.getByTestId('history-drawer-preview-content-session-multi')).toHaveTextContent(
      'Second outcome summary.'
    )
  })

  it('can load a session from the history drawer and focus a specific outcome', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        sessions: [
          {
            id: 'session-focus',
            title: 'Focused session',
            modelId: 'llama3',
            backend: 'ollama',
            createdAt: '2026-04-04T10:00:00.000Z',
            updatedAt: '2026-04-04T10:30:00.000Z',
            messageCount: 8,
            metadata: {
              task_outcomes: [
                {
                  id: 'outcome-focus',
                  title: 'Completion summary',
                  summary: 'Focus this outcome.',
                },
              ],
            },
          },
        ],
        agentMode: true,
        agentTimeline: [
          {
            id: 'outcome-focus',
            type: 'task_status',
            title: 'Completion summary',
            description: 'Focus this outcome.',
            status: 'completed',
            payload: {
              completion_summary: 'Focus this outcome.',
            },
            createdAt: new Date().toISOString(),
          },
        ],
      })
    )

    render(<Chat />)

    fireEvent.click(await screen.findByText('Sessions'))
    fireEvent.click(screen.getByTestId('history-drawer-preview-session-focus'))
    fireEvent.click(screen.getByTestId('history-drawer-open-outcome-session-focus'))

    await waitFor(() => {
      expect(loadSession).toHaveBeenCalledWith('session-focus')
    })

    expect(screen.getByTestId('agent-outcome-item-outcome-focus')).toHaveTextContent('Focused')
  })

  it('runs an agent task when agent mode is enabled', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        agentMode: true,
        agentTaskStatus: 'idle',
      })
    )

    render(<Chat />)

    fireEvent.click(await screen.findByTestId('run-button'))

    await waitFor(() => {
      expect(runAgentTask).toHaveBeenCalledWith(
        {
          prompt: 'Explain this repo',
          systemPrompt: 'You are helpful.',
          responseFormat: 'text',
          attachments: [],
          agentContext: {
            auto_repair_pipeline: true,
          },
          parameterOverrides: {
            temperature: 0.7,
            topP: 0.9,
            maxTokens: 2048,
            modelId: 'llama3',
            backend: 'ollama',
          },
        },
        undefined
      )
      expect(clearActiveCandidates).toHaveBeenCalled()
      expect(setSelectedExperimentId).toHaveBeenCalledWith(null)
    })
  })

  it('renders automation trace events when present in timeline', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        agentMode: true,
        agentTimeline: [
          {
            id: 'auto-event-1',
            type: 'task_status',
            title: 'Auto-continue attempt 1',
            description: 'Continue with recommended next step.',
            status: 'running',
            payload: {
              automation_type: 'auto_continue',
              automation_attempt: 1,
              automation_reason: 'Continue with recommended next step.',
            },
            createdAt: '2026-04-05T10:00:00.000Z',
          },
        ],
      })
    )

    render(<Chat />)

    expect(await screen.findByTestId('agent-automation-trace-card')).toBeInTheDocument()
    expect(screen.getByTestId('agent-automation-item-auto-event-1')).toHaveTextContent(
      'Auto-continue attempt 1'
    )
    expect(screen.getByText('Auto Continue')).toBeInTheDocument()
  })

  it('filters automation trace and copies failure summary', async () => {
    const writeTextMock = navigator.clipboard.writeText as ReturnType<typeof vi.fn>
    mockUseChatStore.mockReturnValue(
      createStoreState({
        agentMode: true,
        agentTimeline: [
          {
            id: 'auto-continue-1',
            type: 'task_status',
            title: 'Auto-continue attempt 1',
            description: 'Continue after recommendation.',
            status: 'completed',
            payload: {
              automation_type: 'auto_continue',
              automation_attempt: 1,
              automation_reason: 'Continue after recommendation.',
            },
            createdAt: '2026-04-05T10:00:00.000Z',
          },
          {
            id: 'auto-recover-1',
            type: 'task_status',
            title: 'Auto-recover attempt 1',
            description: 'Recover after failed command.',
            status: 'failed',
            payload: {
              automation_type: 'auto_recover',
              automation_attempt: 1,
              automation_reason: 'Recover after failed command.',
            },
            createdAt: '2026-04-05T10:10:00.000Z',
          },
        ],
      })
    )

    render(<Chat />)

    expect(await screen.findByTestId('agent-automation-item-auto-continue-1')).toBeInTheDocument()
    expect(screen.getByTestId('agent-automation-item-auto-recover-1')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Recover'))
    expect(screen.queryByTestId('agent-automation-item-auto-continue-1')).not.toBeInTheDocument()
    expect(screen.getByTestId('agent-automation-item-auto-recover-1')).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('automation-trace-copy-summary'))
    await waitFor(() => {
      expect(writeTextMock).toHaveBeenCalledTimes(1)
      expect(writeTextMock).toHaveBeenCalledWith(expect.stringContaining('Failed events: 1'))
      expect(writeTextMock).toHaveBeenCalledWith(expect.stringContaining('Failure chain:'))
    })
  })

  it('exports automation trace as markdown report', async () => {
    const createObjectUrlMock = global.URL.createObjectURL as ReturnType<typeof vi.fn>
    const revokeObjectUrlMock = global.URL.revokeObjectURL as ReturnType<typeof vi.fn>
    const originalCreateElement = document.createElement.bind(document)
    const anchorClickMock = vi.fn()
    const createElementSpy = vi
      .spyOn(document, 'createElement')
      .mockImplementation(((tagName: string, options?: ElementCreationOptions) => {
        const element = originalCreateElement(tagName, options)
        if (tagName.toLowerCase() === 'a') {
          ;(element as HTMLAnchorElement).click = anchorClickMock as unknown as () => void
        }
        return element
      }) as typeof document.createElement)
    mockUseChatStore.mockReturnValue(
      createStoreState({
        agentMode: true,
        agentTimeline: [
          {
            id: 'auto-recover-export',
            type: 'task_status',
            title: 'Auto-recover attempt 1',
            description: 'Recover after failed command.',
            status: 'failed',
            payload: {
              automation_type: 'auto_recover',
              automation_attempt: 1,
              automation_reason: 'Recover after failed command.',
            },
            createdAt: '2026-04-05T10:10:00.000Z',
          },
        ],
      })
    )

    render(<Chat />)

    fireEvent.click(await screen.findByTestId('automation-trace-export-markdown'))

    await waitFor(() => {
      expect(anchorClickMock).toHaveBeenCalledTimes(1)
      expect(createObjectUrlMock).toHaveBeenCalledTimes(1)
      expect(revokeObjectUrlMock).toHaveBeenCalledTimes(1)
    })

    createElementSpy.mockRestore()
  })

  it('resumes or retries agent tasks from the status card', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        agentMode: true,
        agentTaskStatus: 'waiting_confirmation',
        pendingAgentConfirmation: {
          action: 'command_run',
          description: 'Run tests',
          params: { command: 'pytest' },
          riskLevel: 'high',
        },
        agentTimeline: [
          {
            id: 'evt-1',
            type: 'confirmation_request',
            title: 'Confirmation required',
            createdAt: new Date().toISOString(),
          },
        ],
      })
    )

    render(<Chat />)

    fireEvent.click(await screen.findByTestId('agent-resume-button'))

    await waitFor(() => {
      expect(confirmAgentAction).toHaveBeenCalledTimes(1)
    })

    fireEvent.click(screen.getByTestId('agent-retry-button'))

    await waitFor(() => {
      expect(clearAgentTimeline).toHaveBeenCalled()
      expect(setPendingAgentConfirmation).toHaveBeenCalledWith(null)
    })
  })

  it('shows task history when agent timeline exists', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        agentMode: true,
        agentTaskStatus: 'stopped',
        agentTimeline: [
          {
            id: 'evt-1',
            type: 'tool_result',
            title: 'Read target file',
            tool_name: 'file_read',
            description: 'Loaded app config.',
            payload: { path: 'client/src/app.tsx', summary: 'Loaded app config.' },
            createdAt: new Date().toISOString(),
          },
        ],
      })
    )

    render(<Chat />)

    fireEvent.click(await screen.findByTestId('agent-resume-button'))

    await waitFor(() => {
      expect(screen.getByTestId('agent-history-card')).toBeInTheDocument()
    })
  })

  it('renders loop summary and recommended next step cards from task status events', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        agentMode: true,
        agentTaskStatus: 'completed',
        agentTimeline: [
          {
            id: 'evt-loop-summary',
            type: 'task_status',
            title: 'Loop summary',
            description: 'Completed 2 step(s) successfully.',
            status: 'completed',
            payload: {
              loop_summary: 'Completed 2 step(s) successfully. Last actions: read src/app.tsx, ran command `npm test`.',
            },
            createdAt: new Date().toISOString(),
          },
          {
            id: 'evt-next-step',
            type: 'task_status',
            title: 'Recommended next step',
            description: 'Review the latest result and continue with the next planned task.',
            status: 'completed',
            payload: {
              recommended_next_step: 'Review the latest result and continue with the next planned task.',
            },
            createdAt: new Date().toISOString(),
          },
        ],
      })
    )

    render(<Chat />)

    fireEvent.click(await screen.findByText('Overview'))

    expect(screen.getByTestId('agent-loop-summary-evt-loop-summary')).toHaveTextContent(
      'Completed 2 step(s) successfully.'
    )
    expect(screen.getByTestId('agent-next-step-evt-next-step')).toHaveTextContent(
      'Review the latest result and continue with the next planned task.'
    )
  })

  it('prefers server-provided loop summary and next-step text in task history', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        agentMode: true,
        agentTaskStatus: 'completed',
        agentTimeline: [
          {
            id: 'evt-history-loop',
            type: 'task_status',
            title: 'Loop summary',
            description: 'fallback description',
            status: 'completed',
            payload: {
              loop_summary: 'Completed 1 step(s) successfully. Last actions: command run.',
            },
            createdAt: new Date().toISOString(),
          },
          {
            id: 'evt-history-next',
            type: 'task_status',
            title: 'Recommended next step',
            description: 'fallback next step',
            status: 'completed',
            payload: {
              recommended_next_step: 'Open the changed file and continue with the next task.',
            },
            createdAt: new Date().toISOString(),
          },
        ],
      })
    )

    render(<Chat />)

    fireEvent.click(await screen.findByText('Overview'))

    const historyCard = screen.getByTestId('agent-history-card')
    expect(within(historyCard).getByText('Completed 1 step(s) successfully. Last actions: command run.')).toBeInTheDocument()
    expect(within(historyCard).getByText('Open the changed file and continue with the next task.')).toBeInTheDocument()
  })

  it('shows automatic completion and handoff records in task history', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        agentMode: true,
        agentTaskStatus: 'completed',
        agentTimeline: [
          {
            id: 'evt-auto-complete',
            type: 'task_status',
            title: 'Completion summary',
            description:
              'Patched client/src/app.tsx. Reran `npm test` and got 12 passed / 0 failed. Verification passed, so the task is ready for a completion summary or handoff.',
            status: 'completed',
            payload: {
              completion_summary:
                'Patched client/src/app.tsx. Reran `npm test` and got 12 passed / 0 failed. Verification passed, so the task is ready for a completion summary or handoff.',
            },
            createdAt: new Date().toISOString(),
          },
          {
            id: 'evt-auto-handoff',
            type: 'task_status',
            title: 'Handoff ready',
            description:
              'Updated files: client/src/app.tsx. Verified with `npm test` (12 passed, 0 failed). Next owner step: review the final diff once and merge or continue the broader task.',
            status: 'completed',
            payload: {
              handoff_note:
                'Updated files: client/src/app.tsx. Verified with `npm test` (12 passed, 0 failed). Next owner step: review the final diff once and merge or continue the broader task.',
            },
            createdAt: new Date().toISOString(),
          },
        ],
      })
    )

    render(<Chat />)

    fireEvent.click(await screen.findByText('Overview'))

    const historyCard = screen.getByTestId('agent-history-card')
    expect(within(historyCard).getByText('Completion summary')).toBeInTheDocument()
    expect(
      within(historyCard).getByText(/Patched client\/src\/app\.tsx\. Reran `npm test` and got 12 passed/i)
    ).toBeInTheDocument()
    expect(within(historyCard).getByText('Handoff ready')).toBeInTheDocument()
    expect(
      within(historyCard).getByText(/Updated files: client\/src\/app\.tsx\./i)
    ).toBeInTheDocument()

    const outcomesCard = screen.getByTestId('agent-outcomes-card')
    expect(within(outcomesCard).getByText('Completion summary')).toBeInTheDocument()
    expect(
      within(outcomesCard).getByText(/Patched client\/src\/app\.tsx\. Reran `npm test` and got 12 passed/i)
    ).toBeInTheDocument()
    expect(within(outcomesCard).getByText('Handoff ready')).toBeInTheDocument()
  })

  it('uses the dedicated resume endpoint flow when continuing without pending confirmation', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        agentMode: true,
        agentTaskStatus: 'stopped',
        agentTimeline: [
          {
            id: 'evt-1',
            type: 'tool_result',
            title: 'Read target file',
            tool_name: 'file_read',
            description: 'Loaded app config.',
            payload: { path: 'client/src/app.tsx', summary: 'Loaded app config.' },
            createdAt: new Date().toISOString(),
          },
        ],
      })
    )

    render(<Chat />)

    fireEvent.click(await screen.findByTestId('agent-resume-button'))

    await waitFor(() => {
      expect(resumeAgentTask).toHaveBeenCalledWith(
        expect.objectContaining({
          prompt: 'Explain this repo',
        }),
        undefined
      )
    })
  })

  it('can continue from a specific task history item', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        agentMode: true,
        agentTaskStatus: 'completed',
        agentTimeline: [
          {
            id: 'evt-history-1',
            type: 'tool_result',
            title: 'Read target file',
            tool_name: 'file_read',
            description: 'Loaded app config.',
            payload: { path: 'client/src/app.tsx' },
            status: 'completed',
            createdAt: new Date().toISOString(),
          },
        ],
      })
    )

    render(<Chat />)

    fireEvent.click(await screen.findByTestId('agent-history-resume-evt-history-1'))

    await waitFor(() => {
      expect(resumeAgentFromEvent).toHaveBeenCalledWith(
        'evt-history-1',
        expect.objectContaining({
          prompt: 'Explain this repo',
        }),
        undefined
      )
    })
  })

  it('renders structured test results and file diffs in the agent timeline', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        agentMode: true,
        agentTaskStatus: 'completed',
        agentTimeline: [
          {
            id: 'evt-command-1',
            type: 'command_output',
            title: 'Run tests',
            tool_name: 'tests_run',
            description: 'Executed pytest.',
            payload: {
              command: 'pytest server/tests/test_inference.py -q',
              summary: 'Command exited with code 0: pytest server/tests/test_inference.py -q',
              stdout: '5 passed in 0.42s',
              test_summary: {
                passed: 5,
                failed: 0,
                errors: 0,
                skipped: 0,
                summary_line: '5 passed in 0.42s',
              },
            },
            status: 'completed',
            createdAt: new Date().toISOString(),
          },
          {
            id: 'evt-file-1',
            type: 'file_change',
            title: 'Write config',
            tool_name: 'file_write',
            description: 'Updated config.',
            payload: {
              path: 'client/src/config.ts',
              summary: 'Updated file with +3 / -1 lines',
              diff: '--- config.ts (before)\n+++ config.ts (after)\n@@\n-old\n+new',
            },
            status: 'completed',
            createdAt: new Date().toISOString(),
          },
        ],
      })
    )

    render(<Chat />)

    fireEvent.click(await screen.findByText('Overview'))

    expect(await screen.findByTestId('agent-event-command')).toBeInTheDocument()
    expect(screen.getByText('Passed 5')).toBeInTheDocument()
    expect(screen.getAllByText('5 passed in 0.42s').length).toBeGreaterThan(0)
    expect(screen.getByText(/Verification passed\. Recommended next step/i)).toBeInTheDocument()
    expect(screen.getByTestId('agent-event-file')).toBeInTheDocument()
    expect(screen.getByText('Change summary')).toBeInTheDocument()
  })

  it('renders failed test case details when test summary includes failures', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        agentMode: true,
        agentTaskStatus: 'failed',
        agentTimeline: [
          {
            id: 'evt-command-failed',
            type: 'command_output',
            title: 'Run failing tests',
            tool_name: 'tests_run',
            description: 'Executed pytest with failures.',
            payload: {
              command: 'pytest server/tests/test_chat.py -q',
              summary: 'Command exited with code 1: pytest server/tests/test_chat.py -q',
              stderr: 'FAILED server/tests/test_chat.py::test_resume - AssertionError',
              test_summary: {
                passed: 4,
                failed: 1,
                errors: 0,
                skipped: 0,
                framework: 'pytest',
                exit_reason: 'failed',
                failure_files: ['server/tests/test_chat.py'],
                failure_cases: [
                  {
                    name: 'server/tests/test_chat.py::test_resume',
                    message: 'AssertionError: expected resume flow',
                  },
                ],
              },
            },
            status: 'failed',
            createdAt: new Date().toISOString(),
          },
        ],
      })
    )

    render(<Chat />)

    fireEvent.click(await screen.findByText('Overview'))

    expect(await screen.findByTestId('agent-event-command')).toBeInTheDocument()
    expect(screen.getByText('pytest')).toBeInTheDocument()
    expect(screen.getAllByText('failed').length).toBeGreaterThan(0)
    expect(screen.getByText(/Verification still failing\. Recommended next step/i)).toBeInTheDocument()
    expect(screen.getByText('Failed files')).toBeInTheDocument()
    expect(screen.getByText('server/tests/test_chat.py')).toBeInTheDocument()
    expect(screen.getByText('Failed cases')).toBeInTheDocument()
    expect(screen.getByText('server/tests/test_chat.py::test_resume')).toBeInTheDocument()
  })

  it('can retry a failed test command directly from the agent event card', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        agentMode: true,
        agentTaskStatus: 'failed',
        agentTimeline: [
          {
            id: 'evt-command-retry',
            type: 'command_output',
            title: 'Run failing tests',
            tool_name: 'tests_run',
            description: 'Executed pytest with failures.',
            payload: {
              command: 'pytest server/tests/test_chat.py -q',
              summary: 'Command exited with code 1: pytest server/tests/test_chat.py -q',
              test_summary: {
                failed: 1,
                passed: 4,
              },
            },
            status: 'failed',
            createdAt: new Date().toISOString(),
          },
        ],
      })
    )

    render(<Chat />)

    fireEvent.click(await screen.findByText('Overview'))
    fireEvent.click(await screen.findByTestId('agent-retry-tests-evt-command-retry'))

    await waitFor(() => {
      expect(runAgentTask).toHaveBeenCalledWith(
        expect.objectContaining({
          prompt: 'Retry this test command: pytest server/tests/test_chat.py -q',
          agentContext: {
            detected_intents: [
              expect.objectContaining({
                action: 'tests_run',
                params: { command: 'pytest server/tests/test_chat.py -q' },
              }),
            ],
          },
        }),
        undefined
      )
    })
  })

  it('can open the first failing test file directly from the agent event card', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        agentMode: true,
        agentTaskStatus: 'failed',
        agentTimeline: [
          {
            id: 'evt-command-open-file',
            type: 'command_output',
            title: 'Run failing tests',
            tool_name: 'tests_run',
            description: 'Executed pytest with failures.',
            payload: {
              command: 'pytest server/tests/test_chat.py -q',
              summary: 'Command exited with code 1: pytest server/tests/test_chat.py -q',
              test_summary: {
                failed: 1,
                passed: 4,
                failure_files: ['server/tests/test_chat.py'],
              },
            },
            status: 'failed',
            createdAt: new Date().toISOString(),
          },
        ],
      })
    )

    render(<Chat />)

    fireEvent.click(await screen.findByText('Overview'))
    fireEvent.click(await screen.findByTestId('agent-open-failing-file-evt-command-open-file'))

    await waitFor(() => {
      expect(runAgentTask).toHaveBeenCalledWith(
        expect.objectContaining({
          prompt: 'Open the failing test file: server/tests/test_chat.py',
          agentContext: {
            detected_intents: [
              expect.objectContaining({
                action: 'file_read',
                params: { path: 'server/tests/test_chat.py' },
              }),
            ],
          },
        }),
        undefined
      )
    })
  })

  it('can analyze the first failing test file directly from the agent event card', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        agentMode: true,
        agentTaskStatus: 'failed',
        agentTimeline: [
          {
            id: 'evt-command-analyze-file',
            type: 'command_output',
            title: 'Run failing tests',
            tool_name: 'tests_run',
            description: 'Executed pytest with failures.',
            payload: {
              command: 'pytest server/tests/test_chat.py -q',
              summary: 'Command exited with code 1: pytest server/tests/test_chat.py -q',
              test_summary: {
                failed: 1,
                passed: 4,
                failure_files: ['server/tests/test_chat.py'],
              },
            },
            status: 'failed',
            createdAt: new Date().toISOString(),
          },
        ],
      })
    )

    render(<Chat />)

    fireEvent.click(await screen.findByText('Overview'))
    fireEvent.click(await screen.findByTestId('agent-analyze-failing-file-evt-command-analyze-file'))

    await waitFor(() => {
      expect(runAgentTask).toHaveBeenCalledWith(
        expect.objectContaining({
          prompt: 'Inspect the failing test file and explain the likely failure points: server/tests/test_chat.py',
          agentContext: {
            followup_prompt:
              'Read server/tests/test_chat.py and summarize the likely cause of the failing test. ' +
              'Call out suspicious assertions, fixtures, or setup issues in concise bullets.',
            detected_intents: [
              expect.objectContaining({
                action: 'file_read',
                params: { path: 'server/tests/test_chat.py' },
              }),
            ],
          },
        }),
        undefined
      )
    })
  })

  it('can create a fix plan from the first failing test file directly from the agent event card', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        agentMode: true,
        agentTaskStatus: 'failed',
        agentTimeline: [
          {
            id: 'evt-command-fix-plan',
            type: 'command_output',
            title: 'Run failing tests',
            tool_name: 'tests_run',
            description: 'Executed pytest with failures.',
            payload: {
              command: 'pytest server/tests/test_chat.py -q',
              summary: 'Command exited with code 1: pytest server/tests/test_chat.py -q',
              test_summary: {
                failed: 1,
                passed: 4,
                failure_files: ['server/tests/test_chat.py'],
              },
            },
            status: 'failed',
            createdAt: new Date().toISOString(),
          },
        ],
      })
    )

    render(<Chat />)

    fireEvent.click(await screen.findByText('Overview'))
    fireEvent.click(await screen.findByTestId('agent-create-fix-plan-evt-command-fix-plan'))

    await waitFor(() => {
      expect(runAgentTask).toHaveBeenCalledWith(
        expect.objectContaining({
          prompt: 'Create a fix plan for the failing test file: server/tests/test_chat.py',
          agentContext: {
            followup_prompt:
              'Read server/tests/test_chat.py and write a concise fix plan for the failing test. ' +
              'Return 3-5 actionable steps, calling out what to inspect first and what to change next.',
            detected_intents: [
              expect.objectContaining({
                action: 'file_read',
                params: { path: 'server/tests/test_chat.py' },
              }),
            ],
          },
        }),
        undefined
      )
    })
  })

  it('can start a guided fix from the first failing test file directly from the agent event card', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        agentMode: true,
        agentTaskStatus: 'failed',
        agentTimeline: [
          {
            id: 'evt-command-guided-fix',
            type: 'command_output',
            title: 'Run failing tests',
            tool_name: 'tests_run',
            description: 'Executed pytest with failures.',
            payload: {
              command: 'pytest server/tests/test_chat.py -q',
              summary: 'Command exited with code 1: pytest server/tests/test_chat.py -q',
              test_summary: {
                failed: 1,
                passed: 4,
                failure_files: ['server/tests/test_chat.py'],
              },
            },
            status: 'failed',
            createdAt: new Date().toISOString(),
          },
        ],
      })
    )

    render(<Chat />)

    fireEvent.click(await screen.findByText('Overview'))
    fireEvent.click(await screen.findByTestId('agent-start-guided-fix-evt-command-guided-fix'))

    await waitFor(() => {
      expect(runAgentTask).toHaveBeenCalledWith(
        expect.objectContaining({
          prompt: 'Start a guided fix for the failing test file: server/tests/test_chat.py',
          agentContext: {
            followup_prompt:
              'Read server/tests/test_chat.py and produce a guided fix response for the failing test. ' +
              'Explain the most likely root cause first, then list the first concrete code change to try next.',
            detected_intents: [
              expect.objectContaining({
                action: 'file_read',
                params: { path: 'server/tests/test_chat.py' },
              }),
            ],
          },
        }),
        undefined
      )
    })

  })

  it('can draft a patch proposal from the first failing test file directly from the agent event card', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        agentMode: true,
        agentTaskStatus: 'failed',
        agentTimeline: [
          {
            id: 'evt-command-patch-proposal',
            type: 'command_output',
            title: 'Run failing tests',
            tool_name: 'tests_run',
            description: 'Executed pytest with failures.',
            payload: {
              command: 'pytest server/tests/test_chat.py -q',
              summary: 'Command exited with code 1: pytest server/tests/test_chat.py -q',
              test_summary: {
                failed: 1,
                passed: 4,
                failure_files: ['server/tests/test_chat.py'],
              },
            },
            status: 'failed',
            createdAt: new Date().toISOString(),
          },
        ],
      })
    )

    render(<Chat />)

    fireEvent.click(await screen.findByText('Overview'))
    fireEvent.click(await screen.findByTestId('agent-draft-patch-proposal-evt-command-patch-proposal'))

    await waitFor(() => {
      expect(runAgentTask).toHaveBeenCalledWith(
        expect.objectContaining({
          prompt: 'Draft a patch proposal for the failing test file: server/tests/test_chat.py',
          agentContext: {
            followup_prompt:
              'Read server/tests/test_chat.py and draft a patch proposal for the failing test. ' +
              'Suggest concrete code edits in a diff-like format without applying changes.',
            detected_intents: [
              expect.objectContaining({
                action: 'file_read',
                params: { path: 'server/tests/test_chat.py' },
              }),
            ],
          },
        }),
        undefined
      )
    })

  })

  it('detects and renders a patch draft tab from diff-style candidate output', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        activeCandidates: [
          {
            id: 'candidate-patch',
            index: 0,
            status: 'completed',
            content:
              'Suggested patch:\n```diff\n--- a/server/tests/test_chat.py\n+++ b/server/tests/test_chat.py\n@@ -1,3 +1,3 @@\n-expect(value).toBe(false)\n+expect(value).toBe(true)\n```',
            run_metrics: { model: 'llama3', backend: 'ollama' },
          },
        ],
        selectedCandidateId: 'candidate-patch',
        responseView: 'patch',
      })
    )

    render(<Chat />)

    const patchPanel = await screen.findByTestId('patch-draft-panel')
    expect(patchPanel).toBeInTheDocument()
    expect(within(patchPanel).getByText('server/tests/test_chat.py')).toBeInTheDocument()
    expect(within(patchPanel).getByText(/\+\+\+ b\/server\/tests\/test_chat\.py/)).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('patch-draft-copy'))

    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
        expect.stringContaining('+++ b/server/tests/test_chat.py')
      )
    })
  })

  it('can apply a patch draft from the patch draft tab', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        activeCandidates: [
          {
            id: 'candidate-patch-apply',
            index: 0,
            status: 'completed',
            content:
              'Suggested patch:\n```diff\n--- a/server/tests/test_chat.py\n+++ b/server/tests/test_chat.py\n@@ -1,3 +1,3 @@\n-expect(value).toBe(false)\n+expect(value).toBe(true)\n```',
            run_metrics: { model: 'llama3', backend: 'ollama' },
          },
        ],
        selectedCandidateId: 'candidate-patch-apply',
        responseView: 'patch',
        agentTimeline: [
          {
            id: 'evt-tests-reference',
            type: 'command_output',
            title: 'Run failing tests',
            tool_name: 'tests_run',
            status: 'failed',
            payload: { command: 'pytest server/tests/test_chat.py -q' },
            createdAt: new Date().toISOString(),
          },
        ],
      })
    )

    render(<Chat />)

    fireEvent.click(await screen.findByTestId('patch-draft-apply'))

    await waitFor(() => {
      expect(modalConfirmMock).toHaveBeenCalled()
      expect(applyPatchDraft).toHaveBeenCalledWith(
        expect.stringContaining('+++ b/server/tests/test_chat.py')
      )
    })
  })

  it('can apply a patch draft and rerun the latest failing tests from the patch tab', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        activeCandidates: [
          {
            id: 'candidate-patch-rerun',
            index: 0,
            status: 'completed',
            content:
              'Suggested patch:\n```diff\n--- a/server/tests/test_chat.py\n+++ b/server/tests/test_chat.py\n@@ -1,3 +1,3 @@\n-expect(value).toBe(false)\n+expect(value).toBe(true)\n```',
            run_metrics: { model: 'llama3', backend: 'ollama' },
          },
        ],
        selectedCandidateId: 'candidate-patch-rerun',
        responseView: 'patch',
        agentTimeline: [
          {
            id: 'evt-tests-reference-rerun',
            type: 'command_output',
            title: 'Run failing tests',
            tool_name: 'tests_run',
            status: 'failed',
            payload: { command: 'pytest server/tests/test_chat.py -q' },
            createdAt: new Date().toISOString(),
          },
        ],
      })
    )

    render(<Chat />)

    fireEvent.click(await screen.findByTestId('patch-draft-apply-rerun'))

    await waitFor(() => {
      expect(modalConfirmMock).toHaveBeenCalled()
      expect(applyPatchDraft).toHaveBeenCalledWith(
        expect.stringContaining('+++ b/server/tests/test_chat.py'),
        { rerunCommand: 'pytest server/tests/test_chat.py -q' }
      )
    })
  })

  it('renders a structured verification outcome card after patch validation', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        agentMode: true,
        agentTaskStatus: 'failed',
        agentTimeline: [
          {
            id: 'evt-verification-outcome',
            type: 'task_status',
            title: 'Verification still failing',
            description:
              'Tests are still failing after the patch. Start with server/tests/test_chat.py before redrafting the patch.',
            status: 'failed',
            payload: {
              verification_outcome: 'failed',
              failure_files: ['server/tests/test_chat.py'],
              rerun_command: 'pytest server/tests/test_chat.py -q',
            },
            createdAt: new Date().toISOString(),
          },
        ],
      })
    )

    render(<Chat />)

    fireEvent.click(await screen.findByText('Overview'))

    expect(screen.getByTestId('agent-verification-outcome-evt-verification-outcome')).toHaveTextContent(
      'Patch verification still failing'
    )
    expect(screen.getByTestId('agent-verification-outcome-evt-verification-outcome')).toHaveTextContent(
      'server/tests/test_chat.py'
    )
    fireEvent.click(screen.getByTestId('agent-verification-open-failing-file-evt-verification-outcome'))

    await waitFor(() => {
      expect(runAgentTask).toHaveBeenCalledWith(
        expect.objectContaining({
          prompt: 'Open the failing test file: server/tests/test_chat.py',
        }),
        undefined
      )
    })

    fireEvent.click(screen.getByTestId('agent-verification-start-guided-fix-evt-verification-outcome'))

    await waitFor(() => {
      expect(runAgentTask).toHaveBeenCalledWith(
        expect.objectContaining({
          prompt: 'Start a guided fix for the failing test file: server/tests/test_chat.py',
          agentContext: {
            followup_prompt:
              'Read server/tests/test_chat.py and produce a guided fix response for the failing test. ' +
              'Explain the most likely root cause first, then list the first concrete code change to try next.',
            detected_intents: [
              expect.objectContaining({
                action: 'file_read',
                params: { path: 'server/tests/test_chat.py' },
              }),
            ],
          },
        }),
        undefined
      )
    })

    fireEvent.click(screen.getByTestId('agent-verification-analyze-failing-file-evt-verification-outcome'))

    await waitFor(() => {
      expect(runAgentTask).toHaveBeenCalledWith(
        expect.objectContaining({
          prompt: 'Inspect the failing test file and explain the likely failure points: server/tests/test_chat.py',
          agentContext: {
            followup_prompt:
              'Read server/tests/test_chat.py and summarize the likely cause of the failing test. ' +
              'Call out suspicious assertions, fixtures, or setup issues in concise bullets.',
            detected_intents: [
              expect.objectContaining({
                action: 'file_read',
                params: { path: 'server/tests/test_chat.py' },
              }),
            ],
          },
        }),
        undefined
      )
    })

    fireEvent.click(screen.getByTestId('agent-verification-create-fix-plan-evt-verification-outcome'))

    await waitFor(() => {
      expect(runAgentTask).toHaveBeenCalledWith(
        expect.objectContaining({
          prompt: 'Create a fix plan for the failing test file: server/tests/test_chat.py',
          agentContext: {
            followup_prompt:
              'Read server/tests/test_chat.py and write a concise fix plan for the failing test. ' +
              'Return 3-5 actionable steps, calling out what to inspect first and what to change next.',
            detected_intents: [
              expect.objectContaining({
                action: 'file_read',
                params: { path: 'server/tests/test_chat.py' },
              }),
            ],
          },
        }),
        undefined
      )
    })
  })

  it('can summarize a verified fix directly from a successful verification outcome card', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        agentMode: true,
        agentTaskStatus: 'completed',
        agentTimeline: [
          {
            id: 'evt-verification-success',
            type: 'task_status',
            title: 'Patch verified successfully',
            description:
              'The patched code passed the rerun command. Review the touched file once, then keep moving.',
            status: 'completed',
            payload: {
              verification_outcome: 'passed',
              patched_files: ['server/tests/test_chat.py'],
            },
            createdAt: new Date().toISOString(),
          },
        ],
      })
    )

    render(<Chat />)

    fireEvent.click(await screen.findByText('Overview'))
    expect(screen.getByText('Patched files')).toBeInTheDocument()
    expect(screen.getByText('server/tests/test_chat.py')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('agent-verification-summarize-fix-evt-verification-success'))

    await waitFor(() => {
      expect(runAgentTask).toHaveBeenCalledWith(
        expect.objectContaining({
          prompt: 'Summarize why this verified fix worked: server/tests/test_chat.py',
          agentContext: {
            followup_prompt:
              'Read server/tests/test_chat.py and summarize why the verified patch fixed the failing test. ' +
              'Explain the key code change, why it addressed the failure, and what to watch for next time.',
            detected_intents: [
              expect.objectContaining({
                action: 'file_read',
                params: { path: 'server/tests/test_chat.py' },
              }),
            ],
          },
        }),
        undefined
      )
    })

    fireEvent.click(screen.getByTestId('agent-verification-review-fix-evt-verification-success'))

    await waitFor(() => {
      expect(runAgentTask).toHaveBeenCalledWith(
        expect.objectContaining({
          prompt: 'Review this verified fix for remaining risks: server/tests/test_chat.py',
          agentContext: {
            followup_prompt:
              'Read server/tests/test_chat.py and perform a concise final review of the verified fix. ' +
              'Call out any remaining risks, edge cases, or follow-up tests worth running, and say if the change looks ready.',
            detected_intents: [
              expect.objectContaining({
                action: 'file_read',
                params: { path: 'server/tests/test_chat.py' },
              }),
            ],
          },
        }),
        undefined
      )
    })

    fireEvent.click(screen.getByTestId('agent-verification-completion-summary-evt-verification-success'))

    await waitFor(() => {
      expect(runAgentTask).toHaveBeenCalledWith(
        expect.objectContaining({
          prompt: 'Create a completion summary for this verified fix: server/tests/test_chat.py',
          agentContext: {
            followup_prompt:
              'Read server/tests/test_chat.py and write a concise completion summary for the verified fix. ' +
              'Include what changed, why it fixed the issue, what was verified, and any recommended follow-up in 3-5 bullets.',
            detected_intents: [
              expect.objectContaining({
                action: 'file_read',
                params: { path: 'server/tests/test_chat.py' },
              }),
            ],
          },
        }),
        undefined
      )
    })

    fireEvent.click(screen.getByTestId('agent-verification-handoff-note-evt-verification-success'))

    await waitFor(() => {
      expect(runAgentTask).toHaveBeenCalledWith(
        expect.objectContaining({
          prompt: 'Create a handoff note for this verified fix: server/tests/test_chat.py',
          agentContext: {
            followup_prompt:
              'Read server/tests/test_chat.py and write a short handoff note for the verified fix. ' +
              'Cover what changed, what was verified, remaining watchouts, and the recommended next owner action.',
            detected_intents: [
              expect.objectContaining({
                action: 'file_read',
                params: { path: 'server/tests/test_chat.py' },
              }),
            ],
          },
        }),
        undefined
      )
    })
  })

  it('can rerun failing tests from a successful patch result card', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        agentMode: true,
        agentTaskStatus: 'completed',
        agentTimeline: [
          {
            id: 'evt-file-patch-success',
            type: 'file_change',
            title: 'Patch applied',
            tool_name: 'file_patch',
            description: 'Applied patch to 1 file.',
            payload: {
              path: 'server/tests/test_chat.py',
              summary: 'Applied patch to 1 file',
              diff: '--- a/server/tests/test_chat.py\n+++ b/server/tests/test_chat.py',
              rerun_command: 'pytest server/tests/test_chat.py -q',
            },
            status: 'completed',
            createdAt: new Date().toISOString(),
          },
        ],
      })
    )

    render(<Chat />)

    fireEvent.click(await screen.findByText('Overview'))
    expect(screen.getByTestId('agent-patch-suggestion-evt-file-patch-success')).toHaveTextContent(
      'Recommended next step: rerun the failing tests first'
    )
    fireEvent.click(await screen.findByTestId('agent-rerun-tests-after-patch-evt-file-patch-success'))

    await waitFor(() => {
      expect(runAgentTask).toHaveBeenCalledWith(
        expect.objectContaining({
          prompt: 'Retry this test command: pytest server/tests/test_chat.py -q',
        }),
        undefined
      )
    })
  })

  it('can open the patched file directly from a successful patch result card', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        agentMode: true,
        agentTaskStatus: 'completed',
        agentTimeline: [
          {
            id: 'evt-file-patch-open',
            type: 'file_change',
            title: 'Patch applied',
            tool_name: 'file_patch',
            description: 'Applied patch to 1 file.',
            payload: {
              applied_files: ['server/tests/test_chat.py'],
              summary: 'Applied patch to 1 file',
              diff: '--- a/server/tests/test_chat.py\n+++ b/server/tests/test_chat.py',
            },
            status: 'completed',
            createdAt: new Date().toISOString(),
          },
        ],
      })
    )

    render(<Chat />)

    fireEvent.click(await screen.findByText('Overview'))
    fireEvent.click(await screen.findByTestId('agent-open-patched-file-evt-file-patch-open'))

    await waitFor(() => {
      expect(runAgentTask).toHaveBeenCalledWith(
        expect.objectContaining({
          prompt: 'Open the failing test file: server/tests/test_chat.py',
        }),
        undefined
      )
    })
  })

  it('can recover from a failed patch result card by copying the patch and opening the target file', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        agentMode: true,
        agentTaskStatus: 'failed',
        agentTimeline: [
          {
            id: 'evt-file-patch-failed',
            type: 'file_change',
            title: 'Patch apply failed',
            tool_name: 'file_patch',
            description: 'Patch validation failed.',
            payload: {
              summary: 'Patch validation failed.',
              error: 'patch does not apply',
              patch:
                '--- a/server/tests/test_chat.py\n+++ b/server/tests/test_chat.py\n@@ -1,3 +1,3 @@\n-expect(value).toBe(false)\n+expect(value).toBe(true)\n',
              paths: ['server/tests/test_chat.py'],
            },
            status: 'failed',
            createdAt: new Date().toISOString(),
          },
        ],
      })
    )

    render(<Chat />)

    fireEvent.click(await screen.findByText('Overview'))
    fireEvent.click(await screen.findByTestId('agent-copy-failed-patch-evt-file-patch-failed'))

    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
        expect.stringContaining('+++ b/server/tests/test_chat.py')
      )
    })

    fireEvent.click(screen.getByTestId('agent-open-patch-target-evt-file-patch-failed'))

    await waitFor(() => {
      expect(runAgentTask).toHaveBeenCalledWith(
        expect.objectContaining({
          prompt: 'Open the failing test file: server/tests/test_chat.py',
        }),
        undefined
      )
    })
  })

  it('can analyze patch failure and redraft a patch from a failed patch result card', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        agentMode: true,
        agentTaskStatus: 'failed',
        agentTimeline: [
          {
            id: 'evt-file-patch-failed-actions',
            type: 'file_change',
            title: 'Patch apply failed',
            tool_name: 'file_patch',
            description: 'Patch validation failed.',
            payload: {
              summary: 'Patch validation failed.',
              error: 'patch does not apply',
              patch:
                '--- a/server/tests/test_chat.py\n+++ b/server/tests/test_chat.py\n@@ -1,3 +1,3 @@\n-expect(value).toBe(false)\n+expect(value).toBe(true)\n',
              paths: ['server/tests/test_chat.py'],
            },
            status: 'failed',
            createdAt: new Date().toISOString(),
          },
        ],
      })
    )

    render(<Chat />)

    fireEvent.click(await screen.findByText('Overview'))
    expect(screen.getByTestId('agent-patch-suggestion-evt-file-patch-failed-actions')).toHaveTextContent(
      'Recommended next step: inspect the target file'
    )
    fireEvent.click(await screen.findByTestId('agent-analyze-patch-failure-evt-file-patch-failed-actions'))

    await waitFor(() => {
      expect(runAgentTask).toHaveBeenCalledWith(
        expect.objectContaining({
          prompt: 'Analyze why the patch failed for: server/tests/test_chat.py. Patch error: patch does not apply',
        }),
        undefined
      )
    })

    fireEvent.click(screen.getByTestId('agent-redraft-patch-evt-file-patch-failed-actions'))

    await waitFor(() => {
      expect(runAgentTask).toHaveBeenCalledWith(
        expect.objectContaining({
          prompt: 'Draft a patch proposal for the failing test file: server/tests/test_chat.py',
        }),
        undefined
      )
    })
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

  it('filters experiment history by search, exposes sorting, and supports favorites', async () => {
    mockUseChatStore.mockReturnValue(
      createStoreState({
        experimentSnapshots: [
          {
            id: 'exp-1',
            createdAt: '2026-04-04T10:00:00.000Z',
            lastViewedAt: '2026-04-04T10:10:00.000Z',
            isFavorite: false,
            title: 'Ollama debug run',
            response: 'First ollama result',
            selectedCandidateId: 'exp-1-candidate-1',
            candidates: [
              {
                id: 'exp-1-candidate-1',
                index: 0,
                content: 'First ollama result',
                status: 'completed',
              },
            ],
            experiment_config: {
              prompt: 'Debug ollama prompt',
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
            lastViewedAt: '2026-04-04T10:20:00.000Z',
            isFavorite: true,
            title: 'Cloud json run',
            response: 'Second cloud result',
            selectedCandidateId: 'exp-2-candidate-1',
            candidates: [
              {
                id: 'exp-2-candidate-1',
                index: 0,
                content: 'Second cloud result',
                status: 'completed',
              },
            ],
            experiment_config: {
              prompt: 'Return cloud JSON',
              systemPrompt: 'System',
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
    )

    render(<Chat />)

    expect(await screen.findByText('Ollama debug run')).toBeInTheDocument()
    expect(screen.getByText('Cloud json run')).toBeInTheDocument()
    expect(screen.getByTestId('history-count-tag')).toHaveTextContent('2/2 shown')
    expect(screen.getByTestId('history-sort')).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('history-restore-run-exp-1'))
    await waitFor(() => {
      expect(runExperimentCandidates).toHaveBeenCalledWith(
        expect.objectContaining({
          prompt: 'Debug ollama prompt',
          systemPrompt: 'System',
          responseFormat: 'text',
        }),
        2,
        undefined
      )
      expect(addExperimentSnapshot).toHaveBeenCalledTimes(1)
    })

    fireEvent.change(screen.getByTestId('history-search-input'), {
      target: { value: 'cloud' },
    })
    expect(screen.queryByText('Ollama debug run')).not.toBeInTheDocument()
    expect(screen.getByText('Cloud json run')).toBeInTheDocument()
    expect(screen.getByTestId('history-count-tag')).toHaveTextContent('1/2 shown')

    expect(screen.getByTestId('history-backend-filter')).toBeInTheDocument()
    expect(screen.getByTestId('history-model-filter')).toBeInTheDocument()
    expect(screen.getByTestId('history-favorites-only')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Clear Filters'))
    expect(await screen.findByText('Ollama debug run')).toBeInTheDocument()
    expect(screen.getByText('Cloud json run')).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('history-favorite-exp-1'))
    expect(updateExperimentSnapshot).toHaveBeenCalledWith(
      'exp-1',
      expect.objectContaining({
        isFavorite: true,
      })
    )

    fireEvent.click(screen.getByTestId('history-favorites-only'))
    expect(screen.queryByText('Ollama debug run')).not.toBeInTheDocument()
    expect(screen.getByText('Cloud json run')).toBeInTheDocument()
    expect(screen.getByTestId('history-count-tag')).toHaveTextContent('1/2 shown')
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
