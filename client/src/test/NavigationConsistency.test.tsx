import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockApiGet = vi.hoisted(() => vi.fn());

vi.mock('../services/api', () => ({
  apiClient: { get: mockApiGet },
  getDeviceInfo: vi.fn().mockResolvedValue({}),
}));

vi.mock('../components/ThemeToggle', () => ({ default: () => <button type="button">主题</button> }));
vi.mock('../components/NotificationPanel', () => ({
  NotificationPanel: () => <button type="button">通知</button>,
  useNotifications: () => ({
    notifications: [],
    addNotification: vi.fn(),
    markAsRead: vi.fn(),
    markAllAsRead: vi.fn(),
    deleteNotification: vi.fn(),
  }),
}));

import HeaderBar from '../components/HeaderBar';
import MobileNav, { MobileBottomNav } from '../components/MobileNav';
import Sidebar from '../components/Sidebar';
import { getRouteLabel, getRouteMetadata, getRouteTitle } from '../navigation/routeMetadata';
import { useAppStore } from '../store/appStore';

const routerFuture = {
  v7_startTransition: true,
  v7_relativeSplatPath: true,
};

function renderAt(pathname: string, content: React.ReactNode) {
  return render(
    <MemoryRouter initialEntries={[pathname]} future={routerFuture}>
      {content}
    </MemoryRouter>,
  );
}

describe('application-shell navigation consistency', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 390 });
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 844 });
    useAppStore.setState({ sidebarCollapsed: false, backendStatus: 'connected' });
    mockApiGet.mockResolvedValue({ data: { experimental_enabled: true } });
  });

  it('uses the shared Agent Workbench title on desktop, header, and compact navigation', async () => {
    const route = getRouteMetadata('/agent');
    const trainingRoute = getRouteMetadata('/training');
    const workspaceRoute = getRouteMetadata('/workspace');
    expect(route).toMatchObject({ label: 'Agent 工作台', mobileLabel: '工作台' });
    expect(getRouteTitle('/agent')).toBe(route?.label);
    expect(getRouteLabel(trainingRoute!, 'bottom')).toBe('模型训练');
    expect(getRouteLabel(workspaceRoute!, 'bottom')).toBe('工作空间');

    const desktop = renderAt('/agent', <Sidebar />);
    expect(screen.getByRole('button', { name: 'Agent 工作台' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    desktop.unmount();

    const header = renderAt('/agent', <HeaderBar />);
    expect(screen.getByRole('heading', { name: route?.label })).toHaveAttribute(
      'data-capability-tier',
      'ga',
    );
    header.unmount();

    renderAt(
      '/agent',
      <>
        <MobileNav />
        <MobileBottomNav />
      </>,
    );
    fireEvent.click(screen.getByRole('button', { name: '打开菜单' }));
    expect(await screen.findByRole('button', { name: route?.label })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(screen.getByRole('button', { name: route?.mobileLabel })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('derives beta tiers and experimental visibility from the runtime capability authority', async () => {
    mockApiGet.mockResolvedValue({ data: { experimental_enabled: false } });

    const desktop = renderAt('/workspace', <Sidebar />);
    expect(screen.getByRole('button', { name: '工作空间' })).toHaveAttribute(
      'data-capability-tier',
      'beta',
    );
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Gateway' })).not.toBeInTheDocument());
    desktop.unmount();

    renderAt('/workspace', <MobileNav />);
    fireEvent.click(screen.getByRole('button', { name: '打开菜单' }));
    expect(await screen.findByRole('button', { name: '工作空间' })).toHaveAttribute(
      'data-capability-tier',
      'beta',
    );
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Gateway' })).not.toBeInTheDocument());
  });
});
