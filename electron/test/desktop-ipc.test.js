'use strict';

const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const test = require('node:test');
const { CHANNELS, registerDesktopIpc } = require('../desktop-ipc');

const createStatus = (overrides = {}) => ({
  protocolVersion: 1,
  state: 'unavailable',
  operationId: null,
  profile: 'base',
  runtimeVersion: null,
  pythonVersion: null,
  source: 'none',
  progress: null,
  recoverable: true,
  lastErrorCode: null,
  updatedAt: '2026-07-16T00:00:00.000Z',
  ...overrides,
});

function createIpcMain() {
  const handlers = new Map();
  return {
    handlers,
    handle: (channel, callback) => handlers.set(channel, callback),
    removeHandler: (channel) => handlers.delete(channel),
  };
}

test('runtime management IPC is allowlisted and returns only normalized snapshots', async () => {
  const ipcMain = createIpcMain();
  const coordinator = new EventEmitter();
  coordinator.getSnapshot = () => createStatus();
  coordinator.prepareBaseRuntime = async () => { coordinator.prepared = true; };
  coordinator.repairBaseRuntime = async () => { coordinator.repaired = true; };
  coordinator.retryRuntimeOperation = async () => { coordinator.retried = true; };
  const sent = [];
  const cleanup = registerDesktopIpc({
    ipcMain,
    dialog: {},
    shell: {},
    getWindow: () => ({ isDestroyed: () => false, webContents: { send: (...args) => sent.push(args) } }),
    isTrustedEvent: () => true,
    authorizer: {},
    supervisor: Object.assign(new EventEmitter(), { listStatuses: () => [] }),
    runtimeDescriptor: { appVersion: '1.0.0' },
    managedRuntimeCoordinator: coordinator,
    revealRuntimeLogs: async () => true,
  });

  const invoke = (channel, ...args) => ipcMain.handlers.get(channel)({}, ...args);
  assert.deepEqual(await invoke(CHANNELS.runtimeManagementStatus), createStatus());
  await invoke(CHANNELS.prepareBaseRuntime);
  await invoke(CHANNELS.repairBaseRuntime);
  await invoke(CHANNELS.retryRuntimeOperation);
  assert.equal(await invoke(CHANNELS.revealRuntimeLogs), true);
  assert.equal(coordinator.prepared, true);
  assert.equal(coordinator.repaired, true);
  assert.equal(coordinator.retried, true);
  await assert.rejects(
    invoke(CHANNELS.prepareBaseRuntime, 'C:\\renderer-controlled-path'),
    (error) => error.code === 'INVALID_IPC_ARGUMENTS',
  );

  coordinator.emit('status', createStatus({ state: 'verifying', source: 'managed' }));
  assert.deepEqual(sent.at(-1), [
    CHANNELS.runtimeManagementStatus,
    createStatus({ state: 'verifying', source: 'managed' }),
  ]);
  cleanup();
  assert.equal(ipcMain.handlers.has(CHANNELS.prepareBaseRuntime), false);
});

test('runtime management IPC does not expose actions without a coordinator', async () => {
  const ipcMain = createIpcMain();
  const cleanup = registerDesktopIpc({
    ipcMain,
    dialog: {},
    shell: {},
    getWindow: () => null,
    isTrustedEvent: () => true,
    authorizer: {},
    supervisor: Object.assign(new EventEmitter(), { listStatuses: () => [] }),
    runtimeDescriptor: { appVersion: '1.0.0' },
  });

  await assert.rejects(
    ipcMain.handlers.get(CHANNELS.prepareBaseRuntime)({}),
    (error) => error.code === 'RUNTIME_MANAGEMENT_UNAVAILABLE',
  );
  const snapshot = await ipcMain.handlers.get(CHANNELS.runtimeManagementStatus)({});
  assert.equal(snapshot.state, 'unavailable');
  assert.equal(snapshot.source, 'none');
  cleanup();
});
