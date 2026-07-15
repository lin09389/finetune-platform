import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import DesktopRuntimeSection from '../agent/components/DesktopRuntimeSection';
import type { DesktopServiceStatus, ElectronAPI } from '../types';

const status = (
  id: string,
  label: string,
  state: DesktopServiceStatus['state'],
): DesktopServiceStatus => ({
  id,
  label,
  state,
  pid: state === 'ready' ? 1234 : null,
  restarts: 0,
  lastError: state === 'failed' ? '进程意外退出' : null,
  updatedAt: '2026-07-15T00:00:00.000Z',
});

const bridge = (): ElectronAPI => ({
  protocolVersion: 1,
  getRuntime: vi.fn().mockResolvedValue({
    protocolVersion: 1,
    appVersion: '1.0.0',
    platform: 'win32',
    arch: 'x64',
    packaged: false,
    apiBaseUrl: 'http://127.0.0.1:8010',
  }),
  getServiceStatuses: vi.fn().mockResolvedValue([
    status('api', '控制面', 'ready'),
    status('inference', '推理服务', 'failed'),
  ]),
  onServiceStatus: vi.fn(() => () => undefined),
  restartService: vi.fn().mockResolvedValue([
    status('api', '控制面', 'ready'),
    status('inference', '推理服务', 'starting'),
  ]),
  selectFolder: vi.fn(),
  selectFile: vi.fn(),
  readFile: vi.fn(),
  getBackendUrl: vi.fn(),
  restartBackend: vi.fn(),
  openFolder: vi.fn(),
  getAppPath: vi.fn(),
  onTrainingProgress: vi.fn(),
  onTrainingComplete: vi.fn(),
  onTrainingError: vi.fn(),
  removeTrainingListeners: vi.fn(),
});

afterEach(() => {
  delete window.electronAPI;
});

describe('DesktopRuntimeSection', () => {
  it('stays out of the browser development adapter', () => {
    const { container } = render(<DesktopRuntimeSection />);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows supervised services and can request a scoped restart', async () => {
    const api = bridge();
    window.electronAPI = api;
    render(<DesktopRuntimeSection />);

    expect(await screen.findByText('桌面运行时')).toBeInTheDocument();
    expect(await screen.findByText('控制面')).toBeInTheDocument();
    expect(screen.getByText('推理服务')).toBeInTheDocument();
    expect(screen.getAllByText('异常')).toHaveLength(2);
    expect(screen.getByText('win32 x64 · App 1.0.0')).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '重启推理服务' }));
    });
    expect(api.restartService).toHaveBeenCalledWith('inference');
    await waitFor(() => expect(screen.getAllByText('启动中')).toHaveLength(2));
  });
});
