'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const {
  PROTOCOL_VERSION,
  MANAGED_RUNTIME_STATES,
  createServiceDescriptors,
  normalizeManagedRuntimeStatus,
  STOP_ORDER,
} = require('../runtime-contract');
const {
  resolveRuntimePaths,
  ensureRuntimeDirectories,
  getOrCreateRuntimeSecrets,
  buildServiceEnvironment,
} = require('../runtime-paths');

test('desktop protocol and service endpoints are frozen at v1', () => {
  const paths = { projectRoot: 'C:\\app', dataRoot: 'C:\\data' };
  const services = createServiceDescriptors(paths);
  assert.equal(PROTOCOL_VERSION, 1);
  assert.deepEqual(services.map((service) => service.id), [
    'control-plane',
    'inference-service',
    'training-worker',
  ]);
  assert.equal(services[0].healthUrl, 'http://127.0.0.1:8010/health');
  assert.equal(services[1].healthUrl, 'http://127.0.0.1:8020/health');
  assert.equal(services[2].healthUrl, null);
  assert.ok(services.every((service) => service.cwd === paths.dataRoot));
  assert.deepEqual(STOP_ORDER, ['training-worker', 'inference-service', 'control-plane']);
});

test('managed runtime IPC exposes a strict, serializable protocol-v1 status', () => {
  const status = normalizeManagedRuntimeStatus({
    protocolVersion: 1,
    state: 'preparing',
    operationId: 'runtime-op-001',
    profile: 'base',
    runtimeVersion: null,
    pythonVersion: null,
    source: 'managed',
    progress: { completed: 4, total: 10 },
    recoverable: true,
    lastErrorCode: null,
    updatedAt: '2026-07-16T00:00:00.000Z',
  });

  assert.deepEqual(MANAGED_RUNTIME_STATES, [
    'unavailable',
    'checking',
    'preparing',
    'verifying',
    'ready',
    'repair_required',
    'failed',
  ]);
  assert.deepEqual(status.progress, { completed: 4, total: 10 });
  assert.ok(Object.isFrozen(status));
  assert.throws(
    () => normalizeManagedRuntimeStatus({ ...status, state: 'downloading' }),
    (error) => error.code === 'INVALID_MANAGED_RUNTIME_STATUS',
  );
  assert.throws(
    () => normalizeManagedRuntimeStatus({ ...status, internalRuntimePath: 'C:\\secret' }),
    (error) => error.code === 'INVALID_MANAGED_RUNTIME_STATUS',
  );
});

test('runtime data, databases, models and secrets stay under userData', () => {
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'finetune-desktop-'));
  try {
    const paths = resolveRuntimePaths({
      appPath: path.join(temporary, 'app'),
      resourcesPath: path.join(temporary, 'resources'),
      userDataPath: path.join(temporary, 'profile'),
      isPackaged: false,
      env: {},
    });
    ensureRuntimeDirectories(paths);
    assert.equal(paths.managedRuntimeRoot, path.join(temporary, 'profile', 'managed-runtimes'));
    assert.equal(fs.existsSync(paths.managedRuntimeRoot), true);
    const first = getOrCreateRuntimeSecrets(paths);
    const second = getOrCreateRuntimeSecrets(paths);
    assert.deepEqual(first, second);
    assert.notEqual(first.jwt, first.internalService);

    const environment = buildServiceEnvironment(paths, first, { PATH: 'test' });
    for (const key of [
      'BASE_DIR',
      'FINETUNE_PLATFORM_DB_PATH',
      'LANGGRAPH_CHECKPOINT_DB',
      'MODELS_DIR',
      'DATASETS_DIR',
      'OUTPUTS_DIR',
      'MODELSCOPE_CACHE_DIR',
      'FINETUNE_LOG_DIR',
    ]) {
      assert.ok(path.resolve(environment[key]).startsWith(paths.dataRoot));
    }
    assert.equal(environment.INTERNAL_SERVICE_API_KEY, environment.INFERENCE_INTERNAL_API_KEY);
    assert.equal(environment.JWT_SECRET_KEY, first.jwt);
    assert.equal(environment.WORKSPACE_ROOT, paths.workspacesRoot);
  } finally {
    fs.rmSync(temporary, { recursive: true, force: true });
  }
});

test('a packaged app rejects a user-data override inside installation resources', () => {
  const resourcesPath = path.resolve('C:\\Program Files\\Finetune Platform\\resources');
  assert.throws(
    () => resolveRuntimePaths({
      appPath: path.join(resourcesPath, 'app.asar'),
      resourcesPath,
      userDataPath: path.resolve('C:\\Users\\student\\AppData\\Roaming\\Finetune Platform'),
      isPackaged: true,
      env: { FINETUNE_USER_DATA_ROOT: path.join(resourcesPath, 'server', 'data') },
    }),
    (error) => error.code === 'UNSAFE_RUNTIME_DATA_ROOT',
  );
});

test('a packaged app rejects a managed-runtime override inside installation resources', () => {
  const resourcesPath = path.resolve('C:\\Program Files\\Finetune Platform\\resources');
  assert.throws(
    () => resolveRuntimePaths({
      appPath: path.join(resourcesPath, 'app.asar'),
      resourcesPath,
      userDataPath: path.resolve('C:\\Users\\student\\AppData\\Roaming\\Finetune Platform'),
      isPackaged: true,
      env: { FINETUNE_MANAGED_RUNTIME_ROOT: path.join(resourcesPath, 'runtime-packs') },
    }),
    (error) => error.code === 'UNSAFE_MANAGED_RUNTIME_ROOT',
  );
});
