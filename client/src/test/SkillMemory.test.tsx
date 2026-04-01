import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import SkillMemory from '../pages/SkillMemory'

const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

vi.mock('../services/api', () => ({
  API_BASE_URL: 'http://localhost:8000',
}))

vi.mock('antd', async () => {
  const actual = await vi.importActual('antd') as Record<string, any>
  const Modal = Object.assign(actual.Modal, {
    confirm: vi.fn(({ onOk }: { onOk?: () => void }) => onOk?.()),
  })
  return {
    ...actual,
    App: {
      useApp: () => ({
        message: {
          success: vi.fn(),
          error: vi.fn(),
          warning: vi.fn(),
        },
      }),
    },
    Modal,
  }
})

describe('SkillMemory', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockFetch.mockImplementation((url: string) => {
      if (url.includes('/skills/memory/configs')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              configs: [
                {
                  skill_name: 'ScreenshotSkill',
                  memory_enabled: true,
                  context_injection: true,
                  result_storage: true,
                  preference_learning: true,
                  max_memories: 50,
                  relevance_threshold: 0.7,
                },
              ],
            }),
        })
      }
      if (url.includes('/skills/memory/preferences')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              preferences: [
                {
                  key: 'preferred_browser',
                  value: 'chrome',
                  learned_at: '2024-01-15T10:30:00Z',
                  confidence: 0.95,
                },
              ],
            }),
        })
      }
      if (url.includes('/skills/memory/history')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              history: [
                {
                  skill_name: 'ScreenshotSkill',
                  timestamp: '2024-01-15T10:30:00Z',
                  success: true,
                  duration: 1.5,
                  params: { monitor: 0 },
                },
              ],
            }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
  })

  it('loads three core APIs on mount', async () => {
    render(<SkillMemory />)
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith('http://localhost:8000/skills/memory/configs')
      expect(mockFetch).toHaveBeenCalledWith('http://localhost:8000/skills/memory/preferences')
      expect(mockFetch).toHaveBeenCalledWith('http://localhost:8000/skills/memory/history')
    })
  })

  it('renders title and skill row', async () => {
    render(<SkillMemory />)
    expect(screen.getByText(/记忆-技能配置/i)).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByText('ScreenshotSkill')).toBeInTheDocument()
    })
  })

  it('shows preference data after switching tab', async () => {
    render(<SkillMemory />)
    fireEvent.click(screen.getByRole('tab', { name: /用户偏好/i }))
    await waitFor(() => {
      expect(screen.getByText('preferred_browser')).toBeInTheDocument()
    })
  })

  it('shows history actions and allows clear', async () => {
    mockFetch.mockImplementation((url: string, options?: RequestInit) => {
      if (url.includes('/skills/memory/history') && options?.method === 'DELETE') {
        return Promise.resolve({ ok: true })
      }
      if (url.includes('/skills/memory/history')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              history: [{ skill_name: 'ScreenshotSkill', timestamp: '2024-01-15T10:30:00Z', success: true, duration: 1.5, params: {} }],
            }),
        })
      }
      if (url.includes('/skills/memory/configs')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ configs: [] }) })
      }
      if (url.includes('/skills/memory/preferences')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ preferences: [] }) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })

    render(<SkillMemory />)
    fireEvent.click(screen.getByRole('tab', { name: /操作历史/i }))
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /清除历史/i })).toBeInTheDocument()
    })
    fireEvent.click(screen.getByRole('button', { name: /清除历史/i }))
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/skills/memory/history',
        expect.objectContaining({ method: 'DELETE' }),
      )
    })
  })

  it('renders empty state for preferences', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url.includes('/skills/memory/preferences')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ preferences: [] }) })
      }
      if (url.includes('/skills/memory/configs')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ configs: [] }) })
      }
      if (url.includes('/skills/memory/history')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ history: [] }) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })

    render(<SkillMemory />)
    fireEvent.click(screen.getByRole('tab', { name: /用户偏好/i }))
    await waitFor(() => {
      expect(screen.getByText('暂无用户偏好')).toBeInTheDocument()
    })
  })
})
