import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it } from 'vitest';
import Sidebar from '../components/Sidebar';
import { useAppStore } from '../store/appStore';

describe('Sidebar capability labels', () => {
  beforeEach(() => {
    useAppStore.setState({
      sidebarCollapsed: false,
      backendStatus: 'connected',
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
  });
});
