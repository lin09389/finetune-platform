import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  deriveDesktopOverallState,
  getDesktopRuntimeSnapshot,
  isDesktopRuntime,
  prepareBaseRuntime,
  subscribeManagedRuntimeStatus,
  subscribeDesktopServiceStatuses,
} from '../runtime/desktopRuntime';
import type { DesktopServiceStatus, ElectronAPI, ManagedRuntimeStatus } from '../types';

const service = (
  id: string,
  state: DesktopServiceStatus['state'],
): DesktopServiceStatus => ({
  id,
  label: id,
  state,
  pid: null,
  restarts: 0,
  lastError: null,
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

afterEach(() => {
  delete window.electronAPI;
});

describe('desktopRuntime', () => {
  it('derives the most actionable service state', () => {
    expect(deriveDesktopOverallState([])).toBe('stopped');
    expect(deriveDesktopOverallState([service('api', 'ready')])).toBe('ready');
    expect(deriveDesktopOverallState([
      service('api', 'ready'),
      service('inference', 'degraded'),
      service('training', 'starting'),
    ])).toBe('degraded');
    expect(deriveDesktopOverallState([
      service('api', 'ready'),
      service('training', 'failed'),
    ])).toBe('failed');
  });

  it('returns null in the browser development adapter', async () => {
    expect(isDesktopRuntime()).toBe(false);
    await expect(getDesktopRuntimeSnapshot()).resolves.toBeNull();
  });

  it('loads a versioned desktop snapshot without credentials', async () => {
    window.electronAPI = {
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
        service('api', 'ready'),
        service('inference', 'starting'),
      ]),
      getManagedRuntimeStatus: vi.fn().mockResolvedValue(managedRuntime()),
      prepareBaseRuntime: vi.fn().mockResolvedValue(managedRuntime({ state: 'preparing' })),
      repairBaseRuntime: vi.fn(),
      retryRuntimeOperation: vi.fn(),
      revealRuntimeLogs: vi.fn(),
      onManagedRuntimeStatus: vi.fn(() => () => undefined),
      onServiceStatus: vi.fn(() => () => undefined),
      restartService: vi.fn(),
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
    };

    expect(isDesktopRuntime()).toBe(true);
    await expect(getDesktopRuntimeSnapshot()).resolves.toMatchObject({
      runtime: { protocolVersion: 1, apiBaseUrl: 'http://127.0.0.1:8010' },
      managedRuntime: { state: 'ready', profile: 'base' },
      overallState: 'starting',
    });
  });

  it('rejects malformed runtime statuses and only invokes allowlisted preparation', async () => {
    const api: ElectronAPI = {
      protocolVersion: 1,
      getRuntime: vi.fn().mockResolvedValue({
        protocolVersion: 1,
        appVersion: '1.0.0',
        platform: 'win32',
        arch: 'x64',
        packaged: false,
        apiBaseUrl: 'http://127.0.0.1:8010',
      }),
      getServiceStatuses: vi.fn().mockResolvedValue([]),
      getManagedRuntimeStatus: vi.fn().mockResolvedValue(managedRuntime({ state: 'not-ready' as never })),
      prepareBaseRuntime: vi.fn().mockResolvedValue(managedRuntime({ state: 'preparing' })),
      repairBaseRuntime: vi.fn(),
      retryRuntimeOperation: vi.fn(),
      revealRuntimeLogs: vi.fn(),
      onManagedRuntimeStatus: vi.fn(() => () => undefined),
      onServiceStatus: vi.fn(() => () => undefined),
      restartService: vi.fn(),
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
    };
    window.electronAPI = api;

    await expect(getDesktopRuntimeSnapshot()).rejects.toThrow('Invalid managed runtime status');
    await expect(prepareBaseRuntime()).resolves.toMatchObject({ state: 'preparing' });
    expect(api.prepareBaseRuntime).toHaveBeenCalledOnce();
  });

  it('subscribes through the preload bridge and preserves cleanup', () => {
    const unsubscribe = vi.fn();
    let listener: ((statuses: DesktopServiceStatus[]) => void) | undefined;
    const callback = vi.fn();
    window.electronAPI = {
      protocolVersion: 1,
      getRuntime: vi.fn(),
      getServiceStatuses: vi.fn(),
      getManagedRuntimeStatus: vi.fn(),
      prepareBaseRuntime: vi.fn(),
      repairBaseRuntime: vi.fn(),
      retryRuntimeOperation: vi.fn(),
      revealRuntimeLogs: vi.fn(),
      onManagedRuntimeStatus: vi.fn(() => () => undefined),
      onServiceStatus: vi.fn((next) => {
        listener = next;
        return unsubscribe;
      }),
      restartService: vi.fn(),
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
    };

    const cleanup = subscribeDesktopServiceStatuses(callback);
    listener?.([service('api', 'failed')]);
    expect(callback).toHaveBeenCalledWith(
      [expect.objectContaining({ id: 'api', state: 'failed' })],
      'failed',
    );
    cleanup();
    expect(unsubscribe).toHaveBeenCalledOnce();
  });

  it('subscribes to validated managed runtime updates', () => {
    const unsubscribe = vi.fn();
    let listener: ((status: ManagedRuntimeStatus) => void) | undefined;
    const callback = vi.fn();
    window.electronAPI = {
      protocolVersion: 1,
      getRuntime: vi.fn(),
      getServiceStatuses: vi.fn(),
      getManagedRuntimeStatus: vi.fn(),
      prepareBaseRuntime: vi.fn(),
      repairBaseRuntime: vi.fn(),
      retryRuntimeOperation: vi.fn(),
      revealRuntimeLogs: vi.fn(),
      onManagedRuntimeStatus: vi.fn((next) => {
        listener = next;
        return unsubscribe;
      }),
      onServiceStatus: vi.fn(() => () => undefined),
      restartService: vi.fn(),
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
    };

    const cleanup = subscribeManagedRuntimeStatus(callback);
    listener?.(managedRuntime({ state: 'repair_required', lastErrorCode: 'ARCHIVE_CORRUPT' }));
    expect(callback).toHaveBeenCalledWith(expect.objectContaining({ state: 'repair_required' }));
    cleanup();
    expect(unsubscribe).toHaveBeenCalledOnce();
  });
});
