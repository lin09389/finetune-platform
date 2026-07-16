'use strict';

const PROTOCOL_VERSION = 1;
const MANAGED_RUNTIME_STATES = Object.freeze([
  'unavailable',
  'checking',
  'preparing',
  'verifying',
  'ready',
  'repair_required',
  'failed',
]);
const MANAGED_RUNTIME_SOURCES = Object.freeze(['managed', 'development', 'system', 'none']);
const MANAGED_RUNTIME_STATUS_KEYS = Object.freeze([
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
]);
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

function invalidManagedRuntimeStatus(message) {
  return Object.assign(new Error(`Invalid managed runtime status: ${message}`), {
    code: 'INVALID_MANAGED_RUNTIME_STATUS',
  });
}

function nullableString(value, field) {
  if (value === null) return null;
  if (typeof value !== 'string' || !value.trim()) {
    throw invalidManagedRuntimeStatus(`${field} must be a non-empty string or null.`);
  }
  return value;
}

function normalizeManagedRuntimeStatus(input) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) {
    throw invalidManagedRuntimeStatus('status must be an object.');
  }
  const keys = Object.keys(input);
  if (keys.length !== MANAGED_RUNTIME_STATUS_KEYS.length
    || keys.some((key) => !MANAGED_RUNTIME_STATUS_KEYS.includes(key))) {
    throw invalidManagedRuntimeStatus('status contains unknown or missing fields.');
  }
  if (input.protocolVersion !== PROTOCOL_VERSION) {
    throw invalidManagedRuntimeStatus('unsupported protocol version.');
  }
  if (!MANAGED_RUNTIME_STATES.includes(input.state)) {
    throw invalidManagedRuntimeStatus('unknown state.');
  }
  if (input.profile !== 'base') {
    throw invalidManagedRuntimeStatus('only the base profile is renderer-visible.');
  }
  if (!MANAGED_RUNTIME_SOURCES.includes(input.source)) {
    throw invalidManagedRuntimeStatus('unknown source.');
  }
  if (typeof input.recoverable !== 'boolean') {
    throw invalidManagedRuntimeStatus('recoverable must be a boolean.');
  }
  const operationId = nullableString(input.operationId, 'operationId');
  const runtimeVersion = nullableString(input.runtimeVersion, 'runtimeVersion');
  const pythonVersion = nullableString(input.pythonVersion, 'pythonVersion');
  const lastErrorCode = nullableString(input.lastErrorCode, 'lastErrorCode');
  if (lastErrorCode && !/^[A-Z][A-Z0-9_]{2,79}$/.test(lastErrorCode)) {
    throw invalidManagedRuntimeStatus('lastErrorCode must be a stable error code.');
  }
  if (typeof input.updatedAt !== 'string' || Number.isNaN(Date.parse(input.updatedAt))) {
    throw invalidManagedRuntimeStatus('updatedAt must be an ISO timestamp.');
  }

  let progress = null;
  if (input.progress !== null) {
    if (!input.progress || typeof input.progress !== 'object' || Array.isArray(input.progress)
      || Object.keys(input.progress).length !== 2
      || !Object.hasOwn(input.progress, 'completed')
      || !Object.hasOwn(input.progress, 'total')
      || !Number.isInteger(input.progress.completed)
      || !Number.isInteger(input.progress.total)
      || input.progress.completed < 0
      || input.progress.total <= 0
      || input.progress.completed > input.progress.total) {
      throw invalidManagedRuntimeStatus('progress must be bounded completed/total integers.');
    }
    progress = Object.freeze({ completed: input.progress.completed, total: input.progress.total });
  }

  return Object.freeze({
    protocolVersion: PROTOCOL_VERSION,
    state: input.state,
    operationId,
    profile: 'base',
    runtimeVersion,
    pythonVersion,
    source: input.source,
    progress,
    recoverable: input.recoverable,
    lastErrorCode,
    updatedAt: input.updatedAt,
  });
}

function createUnavailableManagedRuntimeStatus(updatedAt = new Date().toISOString()) {
  return normalizeManagedRuntimeStatus({
    protocolVersion: PROTOCOL_VERSION,
    state: 'unavailable',
    operationId: null,
    profile: 'base',
    runtimeVersion: null,
    pythonVersion: null,
    source: 'none',
    progress: null,
    recoverable: true,
    lastErrorCode: null,
    updatedAt,
  });
}

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
  MANAGED_RUNTIME_STATES,
  MANAGED_RUNTIME_SOURCES,
  SERVICE_STATES,
  START_ORDER,
  STOP_ORDER,
  createServiceDescriptors,
  normalizeManagedRuntimeStatus,
  createUnavailableManagedRuntimeStatus,
  publicServiceStatus,
};
