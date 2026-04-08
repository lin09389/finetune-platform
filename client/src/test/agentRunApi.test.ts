import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../services/api', () => ({
  API_BASE_URL: 'http://localhost:8000',
}))

import {
  executeAgentAction,
  resumeAgentFromTimelineEvent,
  resumeAgentSession,
  runAgentLoop,
} from '../services/agentRunApi'

describe('agentRunApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('targets canonical run and resume endpoints', async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'planning' }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'running' }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'running', event_id: 'evt-1' }),
      } as Response) as typeof fetch

    await runAgentLoop({ message: 'plan' })
    await resumeAgentSession({ session_id: 'session-1' })
    await resumeAgentFromTimelineEvent({ session_id: 'session-1', event_id: 'evt-1' })

    expect(String(vi.mocked(global.fetch).mock.calls[0]?.[0])).toBe(
      'http://localhost:8000/agent/run-loop'
    )
    expect(String(vi.mocked(global.fetch).mock.calls[1]?.[0])).toBe(
      'http://localhost:8000/agent/resume'
    )
    expect(String(vi.mocked(global.fetch).mock.calls[2]?.[0])).toBe(
      'http://localhost:8000/agent/resume-from-event'
    )
  })

  it('sends agent execute payloads through the shared execute endpoint', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true }),
    } as Response) as typeof fetch

    await executeAgentAction({
      action: 'tests_run',
      params: { command: 'pytest' },
      confirm: true,
    })

    expect(String(vi.mocked(global.fetch).mock.calls[0]?.[0])).toBe(
      'http://localhost:8000/agent/execute'
    )
    expect(vi.mocked(global.fetch).mock.calls[0]?.[1]).toMatchObject({
      method: 'POST',
    })
    expect(JSON.parse(String(vi.mocked(global.fetch).mock.calls[0]?.[1]?.body))).toEqual({
      action: 'tests_run',
      params: { command: 'pytest' },
      confirm: true,
    })
  })
})
