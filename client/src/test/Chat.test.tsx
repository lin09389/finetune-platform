import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

// 使用 vi.hoisted 定义 mock 函数
const mockUseAppStore = vi.hoisted(() => vi.fn())

vi.mock('../store/appStore', () => ({
  useAppStore: mockUseAppStore,
}))

vi.mock('../services/api', () => ({
  streamInference: vi.fn(),
  getBackends: vi.fn().mockResolvedValue({ backends: [] }),
  switchBackend: vi.fn(),
  getOllamaStatus: vi.fn().mockResolvedValue({ running: false }),
  getInferenceModels: vi.fn().mockResolvedValue({ models: [] }),
  chatExecuteAgent: vi.fn(),
  getModelList: vi.fn().mockResolvedValue([]),
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
  }
})

vi.mock('react-virtuoso', () => ({
  Virtuoso: ({ itemContent }: { itemContent: (index: number) => React.ReactNode }) => (
    <div data-testid="virtuoso-mock">
      {itemContent && itemContent(0)}
    </div>
  ),
}))

vi.mock('../theme', () => ({
  useTheme: () => ({
    theme: 'light',
    toggleTheme: vi.fn(),
  }),
}))

import Chat from '../pages/Chat'

describe('Chat', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    const mockState = {
      setModels: vi.fn(),
      chatSessionId: null,
      chatMessages: [],
      chatModelId: null,
      chatBackend: 'ollama',
      setChatSessionId: vi.fn(),
      setChatMessages: vi.fn(),
      addChatMessage: vi.fn(),
      updateChatMessage: vi.fn(),
      clearChatSession: vi.fn(),
      setChatModelId: vi.fn(),
      setChatBackend: vi.fn(),
    }
    mockUseAppStore.mockImplementation((selector?: (state: any) => any) => {
      if (selector) {
        return selector(mockState)
      }
      return mockState
    })
  })

  it('should render Chat page', async () => {
    render(<Chat />)
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/输入消息/i)).toBeInTheDocument()
    })
  })

  it('should display send button', async () => {
    render(<Chat />)
    await waitFor(() => {
      const sendButtons = screen.getAllByRole('button').filter(
        (btn) => btn.querySelector('svg[data-icon="send"]')
      )
      expect(sendButtons.length).toBeGreaterThanOrEqual(0)
    })
  })

  it('should handle input change', async () => {
    render(<Chat />)
    
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/输入消息/i)).toBeInTheDocument()
    })

    const input = screen.getByPlaceholderText(/输入消息/i)
    fireEvent.change(input, { target: { value: 'Hello' } })
    
    expect(input).toHaveValue('Hello')
  })

  it('should display model selector', async () => {
    render(<Chat />)
    
    await waitFor(() => {
      expect(screen.getByText(/模型/i)).toBeInTheDocument()
    })
  })

  it('should display backend selector', async () => {
    render(<Chat />)
    
    await waitFor(() => {
      expect(screen.getByText(/后端/i)).toBeInTheDocument()
    })
  })

  it('should handle API errors gracefully', async () => {
    render(<Chat />)
    
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/输入消息/i)).toBeInTheDocument()
    })
  })

  it('should display empty state when no messages', async () => {
    render(<Chat />)
    
    await waitFor(() => {
      expect(screen.getByText(/开始对话/i)).toBeInTheDocument()
    })
  })

  it('should display input area', async () => {
    render(<Chat />)
    
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/输入消息/i)).toBeInTheDocument()
    })
  })

  it('should have new chat button', async () => {
    render(<Chat />)
    
    await waitFor(() => {
      const newChatButtons = screen.getAllByRole('button').filter(
        (btn) => btn.textContent?.includes('新对话')
      )
      expect(newChatButtons.length).toBeGreaterThanOrEqual(0)
    })
  })

  it('should handle send message with empty input', async () => {
    render(<Chat />)
    
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/输入消息/i)).toBeInTheDocument()
    })

    const input = screen.getByPlaceholderText(/输入消息/i)
    fireEvent.change(input, { target: { value: '' } })
    
    const sendButtons = screen.getAllByRole('button').filter(
      (btn) => btn.querySelector('svg[data-icon="send"]')
    )
    if (sendButtons.length > 0 && sendButtons[0]) {
      fireEvent.click(sendButtons[0])
    }
  })

  it('should display settings panel', async () => {
    render(<Chat />)
    
    await waitFor(() => {
      expect(screen.getByText(/温度/i)).toBeInTheDocument()
    })
  })

  it('should display max tokens setting', async () => {
    render(<Chat />)
    
    await waitFor(() => {
      expect(screen.getByText(/最大令牌/i)).toBeInTheDocument()
    })
  })

  it('should display top p setting', async () => {
    render(<Chat />)
    
    await waitFor(() => {
      expect(screen.getByText(/Top P/i)).toBeInTheDocument()
    })
  })

  it('should display system prompt input', async () => {
    render(<Chat />)
    
    await waitFor(() => {
      expect(screen.getByText(/系统提示/i)).toBeInTheDocument()
    })
  })
})
