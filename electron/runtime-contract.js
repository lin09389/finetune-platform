'use strict';

const PROTOCOL_VERSION = 1;
const SERVICE_STATES = Object.freeze([
  'stopped',
  'starting',
  'ready',
  'degraded',
  'failed',
  'stopping',
]);

const START_ORDER = Object.freeze([
  'control-plane',
  'inference-service',
  'training-worker',
]);

const STOP_ORDER = Object.freeze([
  'training-worker',
  'inference-service',
  'control-plane',
]);

function createServiceDescriptors(paths) {
  const shared = {
    cwd: paths.dataRoot,
    restart: { maxAttempts: 3, windowMs: 60_000, delayMs: 1_000 },
    startupTimeoutMs: 45_000,
    healthIntervalMs: 5_000,
    stopTimeoutMs: 8_000,
  };

  return Object.freeze([
    Object.freeze({
      ...shared,
      id: 'control-plane',
      label: 'Control plane',
      args: ['-m', 'uvicorn', 'server.main:app', '--host', '127.0.0.1', '--port', '8010'],
      host: '127.0.0.1',
      port: 8010,
      healthUrl: 'http://127.0.0.1:8010/health',
      healthValidator: (payload) => payload?.status === 'ok' && payload?.service_status === 'healthy',
    }),
    Object.freeze({
      ...shared,
      id: 'inference-service',
      label: 'Inference service',
      args: ['-m', 'server.inference_server'],
      host: '127.0.0.1',
      port: 8020,
      healthUrl: 'http://127.0.0.1:8020/health',
      healthValidator: (payload) => payload?.status === 'ok' && payload?.service === 'local-inference',
    }),
    Object.freeze({
      ...shared,
      id: 'training-worker',
      label: 'Training worker',
      args: ['-m', 'server.training_worker', '--worker-id', 'desktop-training-worker'],
      healthUrl: null,
      workerId: 'desktop-training-worker',
    }),
  ]);
}

function publicServiceStatus(status) {
  return Object.freeze({
    id: status.id,
    label: status.label,
    state: status.state,
    pid: status.pid || null,
    restarts: status.restarts || 0,
    lastError: status.lastError || null,
    updatedAt: status.updatedAt,
  });
}

module.exports = {
  PROTOCOL_VERSION,
  SERVICE_STATES,
  START_ORDER,
  STOP_ORDER,
  createServiceDescriptors,
  publicServiceStatus,
};
