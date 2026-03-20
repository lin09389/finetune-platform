import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

// 在 vi.mock 之前定义 mock 函数
const mockApiGet = vi.hoisted(() => vi.fn())
const mockApiPost = vi.hoisted(() => vi.fn())
const mockApiDelete = vi.hoisted(() => vi.fn())

vi.mock('../services/api', () => ({
  apiClient: {
    get: mockApiGet,
    post: mockApiPost,
    delete: mockApiDelete,
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
    Modal: {
      ...(actual['Modal'] || {}),
      confirm: vi.fn(({ onOk }: { onOk: () => void }) => onOk()),
    },
  }
})

import { ActionRecorder } from '../pages/ActionRecorder'

describe('ActionRecorder', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApiGet.mockImplementation((url: string) => {
      if (url === '/cua/record/actions') {
        return Promise.resolve({
          data: {
            actions: [
              { action_type: 'mouse_click', timestamp: 1234567890, data: { x: 100, y: 200 } },
              { action_type: 'key_press', timestamp: 1234567891, data: { key: 'a' } },
            ],
          },
        })
      }
      if (url === '/cua/record/files') {
        return Promise.resolve({
          data: { files: ['test1.json', 'test2.json'] },
        })
      }
      return Promise.resolve({ data: {} })
    })
    mockApiPost.mockResolvedValue({ data: {} })
    mockApiDelete.mockResolvedValue({ data: {} })
  })

  it('should render ActionRecorder page with title', async () => {
    render(<ActionRecorder />)
    expect(screen.getByText(/操作录制与回放/i)).toBeInTheDocument()
  })

  it('should display recording info alert', async () => {
    render(<ActionRecorder />)
    expect(screen.getByText(/录制说明/i)).toBeInTheDocument()
  })

  it('should fetch actions on mount', async () => {
    render(<ActionRecorder />)
    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalledWith('/cua/record/actions')
    })
  })

  it('should fetch saved files on mount', async () => {
    render(<ActionRecorder />)
    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalledWith('/cua/record/files')
    })
  })

  it('should display start recording button initially', async () => {
    render(<ActionRecorder />)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /开始录制/i })).toBeInTheDocument()
    })
  })

  it('should display playback button', async () => {
    render(<ActionRecorder />)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /回放/i })).toBeInTheDocument()
    })
  })

  it('should display save button', async () => {
    render(<ActionRecorder />)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /保存/i })).toBeInTheDocument()
    })
  })

  it('should display load button', async () => {
    render(<ActionRecorder />)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /加载/i })).toBeInTheDocument()
    })
  })

  it('should display clear button', async () => {
    render(<ActionRecorder />)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /清除/i })).toBeInTheDocument()
    })
  })

  it('should handle start recording', async () => {
    render(<ActionRecorder />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /开始录制/i })).toBeInTheDocument()
    })

    const startBtn = screen.getByRole('button', { name: /开始录制/i })
    fireEvent.click(startBtn)

    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalledWith('/cua/record/action', { action: 'start' })
    })
  })

  it('should display operation count', async () => {
    render(<ActionRecorder />)
    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalledWith('/cua/record/actions')
    })
    await waitFor(() => {
      expect(screen.getByText('操作数量')).toBeInTheDocument()
    })
  })

  it('should display recording status as stopped initially', async () => {
    render(<ActionRecorder />)
    await waitFor(() => {
      expect(screen.getByText('停止')).toBeInTheDocument()
    })
  })

  it('should handle playback with no actions', async () => {
    mockApiGet.mockImplementation((url: string) => {
      if (url === '/cua/record/actions') {
        return Promise.resolve({ data: { actions: [] } })
      }
      return Promise.resolve({ data: {} })
    })

    render(<ActionRecorder />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /回放/i })).toBeInTheDocument()
    })

    const playbackBtn = screen.getByRole('button', { name: /回放/i })
    fireEvent.click(playbackBtn)

    expect(mockApiPost).not.toHaveBeenCalledWith('/cua/record/play', expect.anything())
  })

  it('should handle clear actions', async () => {
    render(<ActionRecorder />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /清除/i })).toBeInTheDocument()
    })

    const clearBtn = screen.getByRole('button', { name: /清除/i })
    fireEvent.click(clearBtn)

    await waitFor(() => {
      expect(mockApiDelete).toHaveBeenCalledWith('/cua/record/actions')
    })
  })

  it('should display action type tags', async () => {
    render(<ActionRecorder />)

    await waitFor(() => {
      expect(screen.getByText('mouse_click')).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(screen.getByText('key_press')).toBeInTheDocument()
    })
  })

  it('should display action table columns', async () => {
    render(<ActionRecorder />)

    await waitFor(() => {
      expect(screen.getByText('类型')).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(screen.getByText('数据')).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(screen.getByText('时间')).toBeInTheDocument()
    })
  })

  it('should handle API errors gracefully', async () => {
    mockApiGet.mockRejectedValueOnce(new Error('Network error'))

    render(<ActionRecorder />)

    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalled()
    })
  })

  it('should display playback speed slider', async () => {
    render(<ActionRecorder />)

    await waitFor(() => {
      expect(screen.getByText('回放速度')).toBeInTheDocument()
    })
  })

  it('should display playback mode select', async () => {
    render(<ActionRecorder />)

    await waitFor(() => {
      expect(screen.getByText('实时模式')).toBeInTheDocument()
    })
  })

  it('should show pause and stop buttons when recording', async () => {
    render(<ActionRecorder />)

    const startBtn = screen.getByRole('button', { name: /开始录制/i })
    fireEvent.click(startBtn)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /暂停/i })).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /停止录制/i })).toBeInTheDocument()
    })
  })

  it('should handle pause recording', async () => {
    render(<ActionRecorder />)

    const startBtn = screen.getByRole('button', { name: /开始录制/i })
    fireEvent.click(startBtn)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /暂停/i })).toBeInTheDocument()
    })

    const pauseBtn = screen.getByRole('button', { name: /暂停/i })
    fireEvent.click(pauseBtn)

    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalledWith('/cua/record/action', { action: 'pause' })
    })
  })

  it('should handle stop recording', async () => {
    render(<ActionRecorder />)

    const startBtn = screen.getByRole('button', { name: /开始录制/i })
    fireEvent.click(startBtn)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /停止录制/i })).toBeInTheDocument()
    })

    const stopBtn = screen.getByRole('button', { name: /停止录制/i })
    fireEvent.click(stopBtn)

    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalledWith('/cua/record/action', { action: 'stop' })
    })
  })

  it('should display selected count', async () => {
    render(<ActionRecorder />)

    await waitFor(() => {
      expect(screen.getByText('已选择')).toBeInTheDocument()
    })
  })
})
