import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockApiGet = vi.hoisted(() => vi.fn());

vi.mock('../services/api', () => ({
  API_BASE_URL: 'http://127.0.0.1:8010',
  apiClient: {
    get: mockApiGet,
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

import Sidebar from '../components/Sidebar';
import { useAppStore } from '../store/appStore';

describe('Sidebar capability labels', () => {
  beforeEach(() => {
    useAppStore.setState({
      sidebarCollapsed: false,
      backendStatus: 'connected',
    });
    mockApiGet.mockResolvedValue({
      data: {
        experimental_enabled: true,
        capability_tiers: {
          ga: ['device'],
          beta: ['memory'],
          experimental: ['gateway', 'heartbeat'],
        },
      },
    });
  });

  it('shows capability labels and descriptions in navigation', async () => {
    render(
      <MemoryRouter
        initialEntries={['/dashboard']}
        future={{
          v7_startTransition: true,
          v7_relativeSplatPath: true,
        }}
      >
        <Sidebar />
      </MemoryRouter>,
    );

    expect(screen.getByText('模型运行')).toBeInTheDocument();
    expect(screen.getByText('接入与 Agent')).toBeInTheDocument();
    expect(screen.getByText('智能记忆')).toBeInTheDocument();
    expect(screen.getByText('三层记忆系统')).toBeInTheDocument();
    expect(screen.getByText('工作空间')).toBeInTheDocument();
    expect(screen.getByText('项目管理')).toBeInTheDocument();
    expect(screen.getByText('项目上下文')).toBeInTheDocument();
    expect(screen.getByText('代码理解')).toBeInTheDocument();
    expect(screen.getByText('Gateway')).toBeInTheDocument();
    expect(screen.getByText('设备配对与路由')).toBeInTheDocument();
    expect(screen.getByText('Heartbeat')).toBeInTheDocument();
    expect(screen.getByText('任务调度验证')).toBeInTheDocument();
    expect(screen.getByText('训练对比')).toBeInTheDocument();
    expect(screen.getByText('指标横评')).toBeInTheDocument();

    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalledWith('/api/info');
    });
    // Beta/Exp badges from tier metadata
    expect(screen.getAllByTestId('tier-badge-beta').length).toBeGreaterThan(0);
    expect(screen.getAllByTestId('tier-badge-experimental').length).toBeGreaterThan(0);
  });

  it('hides experimental group when /api/info disables experimental', async () => {
    mockApiGet.mockResolvedValue({
      data: { experimental_enabled: false, capability_tiers: { experimental: [] } },
    });
    render(
      <MemoryRouter
        initialEntries={['/dashboard']}
        future={{
          v7_startTransition: true,
          v7_relativeSplatPath: true,
        }}
      >
        <Sidebar />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalledWith('/api/info');
    });
    expect(screen.queryByText('Gateway')).not.toBeInTheDocument();
    expect(screen.queryByText('Heartbeat')).not.toBeInTheDocument();
    // GA still visible
    expect(screen.getByText('模型运行')).toBeInTheDocument();
    // Always-on auxiliary cloud-api must remain visible when experimental is off
    expect(screen.getByText('云端 API')).toBeInTheDocument();
  });
});
