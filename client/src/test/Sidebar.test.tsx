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

  it('shows beta and experimental tier descriptions in navigation', async () => {
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

    expect(screen.getByText('Beta · 外部模型下载')).toBeInTheDocument();
    expect(screen.getByText('Beta · 三层记忆系统')).toBeInTheDocument();
    expect(screen.getByText('Beta · 项目管理')).toBeInTheDocument();
    expect(screen.getByText('Beta · 代码理解')).toBeInTheDocument();
    expect(screen.getByText('Experimental · 设备配对与路由')).toBeInTheDocument();
    expect(screen.getByText('Experimental · 任务调度验证')).toBeInTheDocument();
    expect(screen.getByText('训练对比')).toBeInTheDocument();
    expect(screen.getByText('指标横评')).toBeInTheDocument();
  });
});
