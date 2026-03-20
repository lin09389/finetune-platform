import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import WorkspaceManager from '../pages/WorkspaceManager'

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

describe('WorkspaceManager', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockFetch.mockImplementation((url: string) => {
      if (url.includes('/workspace/workspaces')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve([
              {
                id: 'ws-1',
                name: 'Test Workspace',
                description: 'A test workspace',
                created_at: '2024-01-15T10:00:00Z',
                updated_at: '2024-01-15T11:00:00Z',
                document_count: 5,
                vector_count: 100,
              },
              {
                id: 'ws-2',
                name: 'Another Workspace',
                description: 'Another test',
                created_at: '2024-01-14T10:00:00Z',
                updated_at: '2024-01-14T11:00:00Z',
                document_count: 3,
                vector_count: 50,
              },
            ]),
        })
      }
      return Promise.resolve({ ok: true })
    })
  })

  it('should render WorkspaceManager page', async () => {
    render(<WorkspaceManager />)
    expect(screen.getByText('工作空间管理')).toBeInTheDocument()
  })

  it('should fetch workspaces on mount', async () => {
    render(<WorkspaceManager />)
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/workspace/workspaces'
      )
    })
  })

  it('should display workspace list', async () => {
    render(<WorkspaceManager />)
    await waitFor(() => {
      expect(screen.getByText('Test Workspace')).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(screen.getByText('Another Workspace')).toBeInTheDocument()
    })
  })

  it('should display workspace descriptions', async () => {
    render(<WorkspaceManager />)
    await waitFor(() => {
      expect(screen.getByText('A test workspace')).toBeInTheDocument()
    })
  })

  it('should display document counts', async () => {
    render(<WorkspaceManager />)
    await waitFor(() => {
      expect(screen.getByText('5 文档')).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(screen.getByText('3 文档')).toBeInTheDocument()
    })
  })

  it('should display vector counts', async () => {
    render(<WorkspaceManager />)
    await waitFor(() => {
      expect(screen.getByText('100 向量')).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(screen.getByText('50 向量')).toBeInTheDocument()
    })
  })

  it('should have create workspace button', async () => {
    render(<WorkspaceManager />)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /新建工作空间/i })).toBeInTheDocument()
    })
  })

  it('should have edit buttons for each workspace', async () => {
    render(<WorkspaceManager />)
    await waitFor(() => {
      const editButtons = screen.getAllByRole('button', { name: /编辑/i })
      expect(editButtons.length).toBe(2)
    })
  })

  it('should have delete buttons for each workspace', async () => {
    render(<WorkspaceManager />)
    await waitFor(() => {
      const deleteButtons = screen.getAllByRole('button', { name: /删除/i })
      expect(deleteButtons.length).toBe(2)
    })
  })

  it('should open create modal on button click', async () => {
    render(<WorkspaceManager />)
    
    const createBtn = screen.getByRole('button', { name: /新建工作空间/i })
    fireEvent.click(createBtn)
    
    await waitFor(() => {
      expect(screen.getByText('新建工作空间')).toBeInTheDocument()
    })
  })

  it('should handle create workspace', async () => {
    mockFetch.mockImplementation((url: string, options?: RequestInit) => {
      if (url.includes('/workspace/workspaces') && options?.method === 'POST') {
        return Promise.resolve({ ok: true })
      }
      if (url.includes('/workspace/workspaces') && !options?.method) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([]),
        })
      }
      return Promise.resolve({ ok: true })
    })

    render(<WorkspaceManager />)
    
    const createBtn = screen.getByRole('button', { name: /新建工作空间/i })
    fireEvent.click(createBtn)
    
    await waitFor(() => {
      expect(screen.getByText('新建工作空间')).toBeInTheDocument()
    })
  })

  it('should handle delete workspace', async () => {
    mockFetch.mockImplementation((url: string, options?: RequestInit) => {
      if (url.includes('/workspace/workspaces/') && options?.method === 'DELETE') {
        return Promise.resolve({ ok: true })
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve([
            {
              id: 'ws-1',
              name: 'Test Workspace',
              description: 'Test',
              created_at: '2024-01-15T10:00:00Z',
              updated_at: '2024-01-15T11:00:00Z',
              document_count: 5,
              vector_count: 100,
            },
          ]),
      })
    })

    render(<WorkspaceManager />)
    
    await waitFor(() => {
      expect(screen.getByText('Test Workspace')).toBeInTheDocument()
    })
    
    const deleteBtn = screen.getByRole('button', { name: /删除/i })
    fireEvent.click(deleteBtn)
    
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/workspace/workspaces/'),
        expect.objectContaining({ method: 'DELETE' })
      )
    })
  })

  it('should handle API errors gracefully', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Network error'))

    render(<WorkspaceManager />)

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled()
    })
  })

  it('should display empty state when no workspaces', async () => {
    mockFetch.mockImplementation(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve([]),
      })
    )

    render(<WorkspaceManager />)

    await waitFor(() => {
      expect(screen.getByText('暂无数据')).toBeInTheDocument()
    })
  })

  it('should display creation date', async () => {
    render(<WorkspaceManager />)

    await waitFor(() => {
      expect(screen.getByText(/创建：/)).toBeInTheDocument()
    })
  })

  it('should handle edit workspace', async () => {
    render(<WorkspaceManager />)
    
    await waitFor(() => {
      expect(screen.getByText('Test Workspace')).toBeInTheDocument()
    })
    
    const editButtons = screen.getAllByRole('button').filter((btn) => btn.textContent?.includes('编辑'))
    if (editButtons.length > 0 && editButtons[0]) {
      fireEvent.click(editButtons[0])
    }
    
    await waitFor(() => {
      expect(screen.getByText('编辑工作空间')).toBeInTheDocument()
    })
  })

  it('should handle update workspace', async () => {
    mockFetch.mockImplementation((url: string, options?: RequestInit) => {
      if (url.includes('/workspace/workspaces/') && options?.method === 'PUT') {
        return Promise.resolve({ ok: true })
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve([
            {
              id: 'ws-1',
              name: 'Test Workspace',
              description: 'Test',
              created_at: '2024-01-15T10:00:00Z',
              updated_at: '2024-01-15T11:00:00Z',
              document_count: 5,
              vector_count: 100,
            },
          ]),
      })
    })

    render(<WorkspaceManager />)
    
    await waitFor(() => {
      expect(screen.getByText('Test Workspace')).toBeInTheDocument()
    })
    
    const editButtons = screen.getAllByRole('button').filter((btn) => btn.textContent?.includes('编辑'))
    if (editButtons.length > 0 && editButtons[0]) {
      fireEvent.click(editButtons[0])
    }
    
    await waitFor(() => {
      expect(screen.getByText('编辑工作空间')).toBeInTheDocument()
    })
  })
})
