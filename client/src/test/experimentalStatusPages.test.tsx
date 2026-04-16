import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

const mockApiGet = vi.hoisted(() => vi.fn())

vi.mock('../services/api', () => ({
  API_BASE_URL: 'http://127.0.0.1:8000',
  apiClient: {
    get: mockApiGet,
    post: vi.fn(),
    delete: vi.fn(),
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

import MCPTools from '../pages/MCPTools'
import HeartbeatPage from '../pages/HeartbeatPage'
import GatewayPage from '../pages/GatewayPage'

describe('experimental status visibility', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApiGet.mockImplementation((url: string) => {
      if (url === '/mcp/tools') {
        return Promise.resolve({ data: { tools: [] } })
      }
      if (url === '/mcp/servers') {
        return Promise.resolve({ data: { servers: [] } })
      }
      if (url === '/mcp/status') {
        return Promise.resolve({
          data: {
            tier: 'experimental',
            runtime_status: 'limited',
            dependency_status: 'external_servers_required',
            message: 'MCP 为实验功能；仅当至少一个外部 MCP 服务成功连接后，工具调用能力才可用。',
          },
        })
      }
      if (url === '/heartbeat/status') {
        return Promise.resolve({
          data: {
            tier: 'experimental',
            runtime_status: 'limited',
            dependency_status: 'local_scheduler_required',
            message: 'Heartbeat 为实验功能；页面可用不代表任务已稳定执行，请以调度器状态和执行记录为准。',
            scheduler: { running: false, total_tasks: 0, enabled_tasks: 0 },
            executor: { total_executed: 0, success_count: 0, failure_count: 0 },
          },
        })
      }
      if (url === '/heartbeat/tasks') {
        return Promise.resolve({ data: { tasks: [] } })
      }
      if (url === '/heartbeat/results?limit=20') {
        return Promise.resolve({ data: { results: [] } })
      }
      if (url === '/gateway/status') {
        return Promise.resolve({
          data: {
            tier: 'experimental',
            runtime_status: 'limited',
            dependency_status: 'paired_devices_or_agents_required',
            message: 'Gateway 为实验功能；只有完成设备配对或 Agent 连接后，消息路由与会话能力才具备实际价值。',
            gateway: { active_connections: 0 },
            router: { message_queue_size: 0 },
          },
        })
      }
      if (url === '/gateway/devices') {
        return Promise.resolve({ data: { devices: [] } })
      }
      if (url === '/gateway/bindings') {
        return Promise.resolve({ data: { bindings: [] } })
      }
      return Promise.resolve({ data: {} })
    })
  })

  it('shows MCP runtime limitation notice', async () => {
    render(<MCPTools />)

    await waitFor(() => {
      expect(screen.getByTestId('mcp-runtime-status')).toHaveTextContent('当前能力受限')
      expect(screen.getByTestId('mcp-runtime-status')).toHaveTextContent('external_servers_required')
    })
  })

  it('shows Heartbeat runtime limitation notice', async () => {
    render(<HeartbeatPage />)

    await waitFor(() => {
      expect(screen.getByTestId('heartbeat-runtime-status')).toHaveTextContent('调度能力受限')
      expect(screen.getByTestId('heartbeat-runtime-status')).toHaveTextContent('local_scheduler_required')
    })
  })

  it('shows Gateway runtime limitation notice', async () => {
    render(<GatewayPage />)

    await waitFor(() => {
      expect(screen.getByTestId('gateway-runtime-status')).toHaveTextContent('Gateway 当前能力受限')
      expect(screen.getByTestId('gateway-runtime-status')).toHaveTextContent('paired_devices_or_agents_required')
    })
  })
})
