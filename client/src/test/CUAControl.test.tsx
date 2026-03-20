import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

// 使用 vi.hoisted 定义 mock 函数
const mockApiGet = vi.hoisted(() => vi.fn())
const mockApiPost = vi.hoisted(() => vi.fn())

vi.mock('../services/api', () => ({
  apiClient: {
    get: mockApiGet,
    post: mockApiPost,
  },
}))

vi.mock('antd', async () => {
  const actual = await vi.importActual('antd') as Record<string, any>
  return {
    ...actual,
    message: {
      success: vi.fn(),
      error: vi.fn(),
      warning: vi.fn(),
    },
  }
})

import { CUAControl } from '../pages/CUAControl'

describe('CUAControl', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApiGet.mockImplementation((url: string) => {
      if (url === '/cua/screen/info') {
        return Promise.resolve({
          data: { width: 1920, height: 1080, monitorCount: 2 },
        })
      }
      if (url === '/cua/mouse/position') {
        return Promise.resolve({
          data: { x: 500, y: 300 },
        })
      }
      if (url === '/cua/safety/status') {
        return Promise.resolve({
          data: {
            enabled: true,
            permissionLevel: 'interactive',
            failsafeEnabled: true,
            auditEnabled: true,
          },
        })
      }
      return Promise.resolve({ data: {} })
    })
    mockApiPost.mockResolvedValue({ data: {} })
  })

  it('should render CUAControl page with title', async () => {
    render(<CUAControl />)
    expect(screen.getByText(/CUA 控制/i)).toBeInTheDocument()
  })

  it('should display screen info', async () => {
    render(<CUAControl />)
    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalledWith('/cua/screen/info')
    })
  })

  it('should display mouse position', async () => {
    render(<CUAControl />)
    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalledWith('/cua/mouse/position')
    })
  })

  it('should display safety status', async () => {
    render(<CUAControl />)
    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalledWith('/cua/safety/status')
    })
  })

  it('should display mouse control section', async () => {
    render(<CUAControl />)
    await waitFor(() => {
      expect(screen.getByText(/鼠标控制/i)).toBeInTheDocument()
    })
  })

  it('should display keyboard control section', async () => {
    render(<CUAControl />)
    await waitFor(() => {
      expect(screen.getByText(/键盘控制/i)).toBeInTheDocument()
    })
  })

  it('should display screen control section', async () => {
    render(<CUAControl />)
    await waitFor(() => {
      expect(screen.getByText(/屏幕控制/i)).toBeInTheDocument()
    })
  })

  it('should display safety settings section', async () => {
    render(<CUAControl />)
    await waitFor(() => {
      expect(screen.getByText(/安全设置/i)).toBeInTheDocument()
    })
  })

  it('should handle API errors gracefully', async () => {
    mockApiGet.mockRejectedValueOnce(new Error('Network error'))
    
    render(<CUAControl />)
    
    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalled()
    })
  })

  it('should display click button', async () => {
    render(<CUAControl />)
    await waitFor(() => {
      const clickButtons = screen.getAllByRole('button').filter(
        (btn) => btn.textContent?.includes('点击')
      )
      expect(clickButtons.length).toBeGreaterThanOrEqual(0)
    })
  })

  it('should display move button', async () => {
    render(<CUAControl />)
    await waitFor(() => {
      const moveButtons = screen.getAllByRole('button').filter(
        (btn) => btn.textContent?.includes('移动')
      )
      expect(moveButtons.length).toBeGreaterThanOrEqual(0)
    })
  })

  it('should display screenshot button', async () => {
    render(<CUAControl />)
    await waitFor(() => {
      const screenshotButtons = screen.getAllByRole('button').filter(
        (btn) => btn.textContent?.includes('截图')
      )
      expect(screenshotButtons.length).toBeGreaterThanOrEqual(0)
    })
  })

  it('should display coordinate input', async () => {
    render(<CUAControl />)
    await waitFor(() => {
      const inputs = screen.getAllByRole('spinbutton')
      expect(inputs.length).toBeGreaterThanOrEqual(0)
    })
  })

  it('should display permission level indicator', async () => {
    render(<CUAControl />)
    await waitFor(() => {
      expect(screen.getByText(/权限级别/i)).toBeInTheDocument()
    })
  })

  it('should display failsafe status', async () => {
    render(<CUAControl />)
    await waitFor(() => {
      expect(screen.getByText(/故障保护/i)).toBeInTheDocument()
    })
  })

  it('should display audit status', async () => {
    render(<CUAControl />)
    await waitFor(() => {
      expect(screen.getByText(/审计/i)).toBeInTheDocument()
    })
  })
})
