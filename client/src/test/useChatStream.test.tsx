import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mockUseChatStore = vi.hoisted(() => vi.fn())

vi.mock('../store/chatStore', () => ({
  useChatStore: mockUseChatStore,
}))

vi.mock('../services/api', () => ({
  API_BASE_URL: 'http://localhost:8000',
}))

import { useChatStream } from '../hooks/chat/useChatStream'

describe('useChatStream', () => {
  const addMessage = vi.fn()
  const setAgentTaskStatus = vi.fn()
  const appendAgentTimeline = vi.fn()
  const replaceAgentTimeline = vi.fn()
  const clearAgentTimeline = vi.fn()
  const setPendingAgentConfirmation = vi.fn()
  const startStreaming = vi.fn()
  const updateStreamingContent = vi.fn()
  const stopStreaming = vi.fn()
  const completeStreaming = vi.fn()
  const updateMessage = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()

    addMessage
      .mockReturnValueOnce('user-message-id')
      .mockReturnValueOnce('assistant-message-id')

    mockUseChatStore.mockReturnValue({
      addMessage,
      agentWorkspaceRoot: '',
      autoApproveSafeTools: false,
      setAgentTaskStatus,
      appendAgentTimeline,
      replaceAgentTimeline,
      clearAgentTimeline,
      setPendingAgentConfirmation,
      startStreaming,
      updateStreamingContent,
      stopStreaming,
      completeStreaming,
      settings: {
        modelId: 'llama3',
        backend: 'ollama',
        useKnowledge: false,
        knowledgeCollection: undefined,
        useMemory: false,
        systemPrompt: '',
        temperature: 0.7,
        topP: 0.9,
        maxTokens: 2048,
        autoRetrieve: true,
        responseFormat: 'text',
        candidateCount: 2,
      },
      currentSessionId: 'session-1',
      updateMessage,
    })

    global.fetch = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)

      if (url.endsWith('/inference/chat')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            message: { content: 'assistant reply' },
            model: 'llama3',
            backend: 'ollama',
          }),
        } as Response)
      }

      if (url.endsWith('/chat/sessions/session-1/messages')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            ok: true,
            body: init?.body,
          }),
        } as Response)
      }

      return Promise.reject(new Error(`Unexpected fetch: ${url}`))
    }) as typeof fetch
  })

  it('persists completed chat runs through canonical message endpoints', async () => {
    const { result } = renderHook(() => useChatStream())

    let response: Awaited<ReturnType<typeof result.current.sendMessage>>
    await act(async () => {
      response = await result.current.sendMessage({
        prompt: 'hello world',
      })
    })

    expect(response?.content).toBe('assistant reply')

    const fetchCalls = vi.mocked(global.fetch).mock.calls
    expect(fetchCalls).toHaveLength(3)

    expect(String(fetchCalls[1]?.[0])).toBe('http://localhost:8000/chat/sessions/session-1/messages')
    expect(fetchCalls[1]?.[1]?.method).toBe('POST')
    expect(JSON.parse(String(fetchCalls[1]?.[1]?.body))).toEqual({
      role: 'user',
      content: 'hello world',
    })

    expect(String(fetchCalls[2]?.[0])).toBe('http://localhost:8000/chat/sessions/session-1/messages')
    expect(fetchCalls[2]?.[1]?.method).toBe('POST')
    expect(JSON.parse(String(fetchCalls[2]?.[1]?.body))).toEqual({
      role: 'assistant',
      content: 'assistant reply',
    })
  })
})
