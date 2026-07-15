import type {
  DesktopRuntimeDescriptor,
  DesktopServiceState,
  DesktopServiceStatus,
} from '../types';

export interface DesktopRuntimeSnapshot {
  runtime: DesktopRuntimeDescriptor;
  services: DesktopServiceStatus[];
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

  const [runtime, services] = await Promise.all([
    bridge.getRuntime(),
    bridge.getServiceStatuses(),
  ]);
  if (runtime.protocolVersion !== bridge.protocolVersion) {
    throw new Error(
      `Desktop protocol mismatch: renderer=${bridge.protocolVersion}, main=${runtime.protocolVersion}`,
    );
  }

  return {
    runtime,
    services,
    overallState: deriveDesktopOverallState(services),
  };
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
