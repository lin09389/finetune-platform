import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import DesktopRuntimeSection from '../agent/components/DesktopRuntimeSection';
import type { DesktopServiceStatus, ElectronAPI, ManagedRuntimeStatus } from '../types';

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

const managedRuntime = (overrides: Partial<ManagedRuntimeStatus> = {}): ManagedRuntimeStatus => ({
  protocolVersion: 1,
  state: 'ready',
  operationId: null,
  profile: 'base',
  runtimeVersion: '2026.07.16',
  pythonVersion: '3.11.9',
  source: 'managed',
  progress: null,
  recoverable: true,
  lastErrorCode: null,
  updatedAt: '2026-07-16T00:00:00.000Z',
  ...overrides,
});

const bridge = (runtimeStatus = managedRuntime()): ElectronAPI => ({
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
  getManagedRuntimeStatus: vi.fn().mockResolvedValue(runtimeStatus),
  prepareBaseRuntime: vi.fn().mockResolvedValue(managedRuntime({ state: 'preparing' })),
  repairBaseRuntime: vi.fn().mockResolvedValue(managedRuntime({ state: 'verifying' })),
  retryRuntimeOperation: vi.fn().mockResolvedValue(managedRuntime({ state: 'checking' })),
  revealRuntimeLogs: vi.fn().mockResolvedValue(true),
  onManagedRuntimeStatus: vi.fn(() => () => undefined),
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
    expect(screen.getByText('基础运行时 2026.07.16 · Python 3.11.9')).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '重启推理服务' }));
    });
    expect(api.restartService).toHaveBeenCalledWith('inference');
    await waitFor(() => expect(screen.getAllByText('启动中')).toHaveLength(2));
  });

  it('shows preparation progress and prevents concurrent runtime actions', async () => {
    const api = bridge(managedRuntime({
      state: 'preparing',
      operationId: 'runtime-op-1',
      progress: { completed: 4, total: 10 },
    }));
    window.electronAPI = api;
    render(<DesktopRuntimeSection />);

    expect(await screen.findByText('正在准备基础运行时')).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '40');
    expect(screen.getByRole('button', { name: '正在准备运行时' })).toBeDisabled();
  });

  it('offers scoped repair, retry and log reveal actions for recoverable states', async () => {
    const api = bridge(managedRuntime({
      state: 'repair_required',
      recoverable: true,
      lastErrorCode: 'ARCHIVE_CORRUPT',
    }));
    window.electronAPI = api;
    const { unmount } = render(<DesktopRuntimeSection />);

    await screen.findByText('需要修复');
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: '修复基础运行时' })); });
    expect(api.repairBaseRuntime).toHaveBeenCalledOnce();
    expect(api.revealRuntimeLogs).not.toHaveBeenCalled();

    window.electronAPI = bridge(managedRuntime({
      state: 'failed',
      recoverable: true,
      lastErrorCode: 'DISK_SPACE_LOW',
    }));
    unmount();
    render(<DesktopRuntimeSection />);
    await screen.findByText('准备失败');
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: '重试运行时操作' })); });
    expect(window.electronAPI.retryRuntimeOperation).toHaveBeenCalledOnce();
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: '查看运行时日志' })); });
    expect(window.electronAPI.revealRuntimeLogs).toHaveBeenCalledOnce();
  });
});
