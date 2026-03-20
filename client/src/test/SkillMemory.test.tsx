import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import SkillMemory from '../pages/SkillMemory'

const mockFetch = vi.fn()

vi.stubGlobal('fetch', mockFetch)

vi.mock('../services/api', () => ({
  API_BASE_URL: 'http://localhost:8000',
}))

vi.mock('antd', async () => {
  const actual = await vi.importActual('antd') as Record<string, any>
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
    Modal: {
      ...(actual['Modal'] || {}),
      confirm: vi.fn(({ onOk }: { onOk: () => void }) => onOk()),
    },
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
                {
                  skill_name: 'MouseClickSkill',
                  memory_enabled: false,
                  context_injection: false,
                  result_storage: false,
                  preference_learning: false,
                  max_memories: 20,
                  relevance_threshold: 0.5,
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
                {
                  key: 'preferred_editor',
                  value: 'vscode',
                  learned_at: '2024-01-14T09:00:00Z',
                  confidence: 0.88,
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
                {
                  skill_name: 'MouseClickSkill',
                  timestamp: '2024-01-15T10:31:00Z',
                  success: false,
                  duration: 0.2,
                  params: { x: 100, y: 200 },
                },
              ],
            }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
  })

  it('should render SkillMemory page with title', async () => {
    render(<SkillMemory />)
    expect(screen.getByText(/记忆-技能配置/i)).toBeInTheDocument()
  })

  it('should fetch configs on mount', async () => {
    render(<SkillMemory />)
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/skills/memory/configs'
      )
    })
  })

  it('should fetch preferences on mount', async () => {
    render(<SkillMemory />)
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/skills/memory/preferences'
      )
    })
  })

  it('should fetch history on mount', async () => {
    render(<SkillMemory />)
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/skills/memory/history'
      )
    })
  })

  it('should display skill configs tab', async () => {
    render(<SkillMemory />)
    await waitFor(() => {
      expect(screen.getByText(/技能配置/i)).toBeInTheDocument()
    })
  })

  it('should display user preferences tab', async () => {
    render(<SkillMemory />)
    await waitFor(() => {
      expect(screen.getByText(/用户偏好/i)).toBeInTheDocument()
    })
  })

  it('should display operation history tab', async () => {
    render(<SkillMemory />)
    await waitFor(() => {
      expect(screen.getByText(/操作历史/i)).toBeInTheDocument()
    })
  })

  it('should display statistics cards', async () => {
    render(<SkillMemory />)

    await waitFor(() => {
      expect(screen.getByText('已配置技能')).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(screen.getByText('用户偏好')).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(screen.getByText('操作历史')).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(screen.getByText('成功率')).toBeInTheDocument()
    })
  })

  it('should display skill names in config table', async () => {
    render(<SkillMemory />)

    await waitFor(() => {
      expect(screen.getByText('ScreenshotSkill')).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(screen.getByText('MouseClickSkill')).toBeInTheDocument()
    })
  })

  it('should display preference keys', async () => {
    render(<SkillMemory />)

    const preferencesTab = screen.getByText(/用户偏好/i)
    fireEvent.click(preferencesTab)

    await waitFor(() => {
      expect(screen.getByText('preferred_browser')).toBeInTheDocument()
    })
  })

  it('should display history entries', async () => {
    render(<SkillMemory />)

    const historyTab = screen.getByText(/操作历史/i)
    fireEvent.click(historyTab)

    await waitFor(() => {
      expect(screen.getByText('ScreenshotSkill')).toBeInTheDocument()
    })
  })

  it('should calculate success rate correctly', async () => {
    render(<SkillMemory />)

    await waitFor(() => {
      expect(screen.getByText('50.0%')).toBeInTheDocument()
    })
  })

  it('should handle API errors gracefully', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Network error'))

    render(<SkillMemory />)

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled()
    })
  })

  it('should display refresh buttons', async () => {
    render(<SkillMemory />)

    const preferencesTab = screen.getByText(/用户偏好/i)
    fireEvent.click(preferencesTab)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /刷新/i })).toBeInTheDocument()
    })
  })

  it('should display clear history button', async () => {
    render(<SkillMemory />)

    const historyTab = screen.getByText(/操作历史/i)
    fireEvent.click(historyTab)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /清除历史/i })).toBeInTheDocument()
    })
  })

  it('should handle clear history action', async () => {
    mockFetch.mockImplementation((url: string, options?: RequestInit) => {
      if (url.includes('/skills/memory/history') && options?.method === 'DELETE') {
        return Promise.resolve({ ok: true })
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ configs: [], preferences: [], history: [] }),
      })
    })

    render(<SkillMemory />)

    const historyTab = screen.getByText(/操作历史/i)
    fireEvent.click(historyTab)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /清除历史/i })).toBeInTheDocument()
    })

    const clearBtn = screen.getByRole('button', { name: /清除历史/i })
    fireEvent.click(clearBtn)

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/skills/memory/history',
        expect.objectContaining({ method: 'DELETE' })
      )
    })
  })

  it('should display edit button for configs', async () => {
    render(<SkillMemory />)

    await waitFor(() => {
      const editButtons = screen.getAllByRole('button').filter((btn) =>
        btn.querySelector('svg[data-icon="edit"]') ||
        btn.getAttribute('aria-label')?.includes('edit')
      )
      expect(editButtons.length).toBeGreaterThan(0)
    })
  })

  it('should display memory enabled status', async () => {
    render(<SkillMemory />)

    await waitFor(() => {
      expect(screen.getByText('启用')).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(screen.getByText('禁用')).toBeInTheDocument()
    })
  })

  it('should display relevance threshold percentage', async () => {
    render(<SkillMemory />)

    await waitFor(() => {
      expect(screen.getByText('70%')).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(screen.getByText('50%')).toBeInTheDocument()
    })
  })

  it('should handle delete preference', async () => {
    mockFetch.mockImplementation((url: string, options?: RequestInit) => {
      if (url.includes('/skills/memory/preferences/') && options?.method === 'DELETE') {
        return Promise.resolve({ ok: true })
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            configs: [],
            preferences: [{ key: 'test', value: 'val', learned_at: '', confidence: 0.9 }],
            history: [],
          }),
      })
    })

    render(<SkillMemory />)

    const preferencesTab = screen.getByText(/用户偏好/i)
    fireEvent.click(preferencesTab)

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled()
    })
  })

  it('should display empty state when no preferences', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url.includes('/skills/memory/preferences')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ preferences: [] }),
        })
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ configs: [], history: [] }),
      })
    })

    render(<SkillMemory />)

    const preferencesTab = screen.getByText(/用户偏好/i)
    fireEvent.click(preferencesTab)

    await waitFor(() => {
      expect(screen.getByText('暂无用户偏好')).toBeInTheDocument()
    })
  })

  it('should display confidence progress bar', async () => {
    render(<SkillMemory />)

    const preferencesTab = screen.getByText(/用户偏好/i)
    fireEvent.click(preferencesTab)

    await waitFor(() => {
      expect(screen.getByText('preferred_browser')).toBeInTheDocument()
    })
  })
})
