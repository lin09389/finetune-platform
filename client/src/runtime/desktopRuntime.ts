import type {
  DesktopRuntimeDescriptor,
  DesktopServiceState,
  DesktopServiceStatus,
  ManagedRuntimeSource,
  ManagedRuntimeState,
  ManagedRuntimeStatus,
} from '../types';

export interface DesktopRuntimeSnapshot {
  runtime: DesktopRuntimeDescriptor;
  services: DesktopServiceStatus[];
  managedRuntime: ManagedRuntimeStatus;
  overallState: DesktopServiceState;
}

const SERVICE_STATE_PRIORITY: Record<DesktopServiceState, number> = {
  failed: 6,
  degraded: 5,
  stopping: 4,
  starting: 3,
  stopped: 2,
  ready: 1,
};

const MANAGED_RUNTIME_STATES = new Set<ManagedRuntimeState>([
  'unavailable',
  'checking',
  'preparing',
  'verifying',
  'ready',
  'repair_required',
  'failed',
]);
const MANAGED_RUNTIME_SOURCES = new Set<ManagedRuntimeSource>([
  'managed',
  'development',
  'system',
  'none',
]);
const MANAGED_RUNTIME_STATUS_KEYS = [
  'protocolVersion',
  'state',
  'operationId',
  'profile',
  'runtimeVersion',
  'pythonVersion',
  'source',
  'progress',
  'recoverable',
  'lastErrorCode',
  'updatedAt',
] as const;

const invalidManagedRuntimeStatus = (): never => {
  throw new Error('Invalid managed runtime status from the desktop bridge.');
};

export const normalizeManagedRuntimeStatus = (input: unknown): ManagedRuntimeStatus => {
  if (!input || typeof input !== 'object' || Array.isArray(input)) invalidManagedRuntimeStatus();
  const value = input as Record<string, unknown>;
  const keys = Object.keys(value);
  if (keys.length !== MANAGED_RUNTIME_STATUS_KEYS.length
    || keys.some((key) => !(MANAGED_RUNTIME_STATUS_KEYS as readonly string[]).includes(key))) {
    invalidManagedRuntimeStatus();
  }
  if (value.protocolVersion !== 1
    || typeof value.state !== 'string'
    || !MANAGED_RUNTIME_STATES.has(value.state as ManagedRuntimeState)
    || value.profile !== 'base'
    || typeof value.source !== 'string'
    || !MANAGED_RUNTIME_SOURCES.has(value.source as ManagedRuntimeSource)
    || typeof value.recoverable !== 'boolean'
    || typeof value.updatedAt !== 'string'
    || Number.isNaN(Date.parse(value.updatedAt))) {
    invalidManagedRuntimeStatus();
  }

  const nullableString = (field: 'operationId' | 'runtimeVersion' | 'pythonVersion' | 'lastErrorCode') => {
    const fieldValue = value[field];
    if (fieldValue === null) return null;
    if (typeof fieldValue !== 'string' || !fieldValue.trim()) invalidManagedRuntimeStatus();
    return fieldValue;
  };
  const operationId = nullableString('operationId');
  const runtimeVersion = nullableString('runtimeVersion');
  const pythonVersion = nullableString('pythonVersion');
  const lastErrorCode = nullableString('lastErrorCode');
  if (lastErrorCode && !/^[A-Z][A-Z0-9_]{2,79}$/.test(lastErrorCode)) invalidManagedRuntimeStatus();

  let progress: ManagedRuntimeStatus['progress'] = null;
  if (value.progress !== null) {
    if (!value.progress || typeof value.progress !== 'object' || Array.isArray(value.progress)) {
      invalidManagedRuntimeStatus();
    }
    const candidate = value.progress as Record<string, unknown>;
    if (Object.keys(candidate).length !== 2
      || !Object.prototype.hasOwnProperty.call(candidate, 'completed')
      || !Object.prototype.hasOwnProperty.call(candidate, 'total')
      || !Number.isInteger(candidate.completed)
      || !Number.isInteger(candidate.total)
      || (candidate.completed as number) < 0
      || (candidate.total as number) <= 0
      || (candidate.completed as number) > (candidate.total as number)) {
      invalidManagedRuntimeStatus();
    }
    progress = { completed: candidate.completed as number, total: candidate.total as number };
  }

  return {
    protocolVersion: 1,
    state: value.state as ManagedRuntimeState,
    operationId,
    profile: 'base',
    runtimeVersion,
    pythonVersion,
    source: value.source as ManagedRuntimeSource,
    progress,
    recoverable: value.recoverable as boolean,
    lastErrorCode,
    updatedAt: value.updatedAt as string,
  };
};

export const isDesktopRuntime = (): boolean => {
  return typeof window !== 'undefined' && window.electronAPI?.protocolVersion === 1;
};

export const deriveDesktopOverallState = (
  services: DesktopServiceStatus[],
): DesktopServiceState => {
  if (services.length === 0) return 'stopped';
  return services.reduce<DesktopServiceState>((worst, service) => (
    SERVICE_STATE_PRIORITY[service.state] > SERVICE_STATE_PRIORITY[worst]
      ? service.state
      : worst
  ), 'ready');
};

export const getDesktopRuntimeSnapshot = async (): Promise<DesktopRuntimeSnapshot | null> => {
  const bridge = typeof window !== 'undefined' ? window.electronAPI : undefined;
  if (!bridge || bridge.protocolVersion !== 1) return null;

  const [runtime, services, managedRuntime] = await Promise.all([
    bridge.getRuntime(),
    bridge.getServiceStatuses(),
    bridge.getManagedRuntimeStatus(),
  ]);
  if (runtime.protocolVersion !== bridge.protocolVersion) {
    throw new Error(
      `Desktop protocol mismatch: renderer=${bridge.protocolVersion}, main=${runtime.protocolVersion}`,
    );
  }

  return {
    runtime,
    services,
    managedRuntime: normalizeManagedRuntimeStatus(managedRuntime),
    overallState: deriveDesktopOverallState(services),
  };
};

export const prepareBaseRuntime = async (): Promise<ManagedRuntimeStatus> => {
  const bridge = typeof window !== 'undefined' ? window.electronAPI : undefined;
  if (!bridge || bridge.protocolVersion !== 1) throw new Error('桌面运行时管理不可用。');
  return normalizeManagedRuntimeStatus(await bridge.prepareBaseRuntime());
};

export const repairBaseRuntime = async (): Promise<ManagedRuntimeStatus> => {
  const bridge = typeof window !== 'undefined' ? window.electronAPI : undefined;
  if (!bridge || bridge.protocolVersion !== 1) throw new Error('桌面运行时管理不可用。');
  return normalizeManagedRuntimeStatus(await bridge.repairBaseRuntime());
};

export const retryRuntimeOperation = async (): Promise<ManagedRuntimeStatus> => {
  const bridge = typeof window !== 'undefined' ? window.electronAPI : undefined;
  if (!bridge || bridge.protocolVersion !== 1) throw new Error('桌面运行时管理不可用。');
  return normalizeManagedRuntimeStatus(await bridge.retryRuntimeOperation());
};

export const revealRuntimeLogs = async (): Promise<boolean> => {
  const bridge = typeof window !== 'undefined' ? window.electronAPI : undefined;
  if (!bridge || bridge.protocolVersion !== 1) throw new Error('桌面运行时管理不可用。');
  return bridge.revealRuntimeLogs();
};

export const subscribeDesktopServiceStatuses = (
  callback: (services: DesktopServiceStatus[], overallState: DesktopServiceState) => void,
): (() => void) => {
  const bridge = typeof window !== 'undefined' ? window.electronAPI : undefined;
  if (!bridge || bridge.protocolVersion !== 1) return () => undefined;
  return bridge.onServiceStatus((services) => {
    callback(services, deriveDesktopOverallState(services));
  });
};

export const subscribeManagedRuntimeStatus = (
  callback: (status: ManagedRuntimeStatus) => void,
): (() => void) => {
  const bridge = typeof window !== 'undefined' ? window.electronAPI : undefined;
  if (!bridge || bridge.protocolVersion !== 1) return () => undefined;
  return bridge.onManagedRuntimeStatus((status) => callback(normalizeManagedRuntimeStatus(status)));
};
