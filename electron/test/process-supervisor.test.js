'use strict';

const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const test = require('node:test');
const { ProcessSupervisor } = require('../process-supervisor');

function fakeChild(id, pid) {
  const child = new EventEmitter();
  child.id = id;
  child.pid = pid;
  child.killed = false;
  child.exitCode = null;
  child.stdout = new EventEmitter();
  child.stderr = new EventEmitter();
  return child;
}

function descriptors() {
  const base = {
    cwd: 'C:\\runtime',
    args: [],
    restart: { maxAttempts: 2, windowMs: 60_000, delayMs: 60_000 },
    startupTimeoutMs: 100,
    healthIntervalMs: 60_000,
    stopTimeoutMs: 10,
  };
  return [
    { ...base, id: 'control-plane', label: 'Control', healthUrl: 'http://control/health' },
    { ...base, id: 'inference-service', label: 'Inference', healthUrl: 'http://inference/health' },
    { ...base, id: 'training-worker', label: 'Training', healthUrl: null, processReadyDelayMs: 0 },
  ];
}

test('supervisor starts in dependency order and stops only owned processes in required order', async () => {
  const started = [];
  const stopped = [];
  let pid = 100;
  const supervisor = new ProcessSupervisor({
    descriptors: descriptors(),
    python: { command: 'python', prefixArgs: [] },
    environment: {},
    probe: async () => true,
    sleep: async () => {},
    spawnProcess: (_python, descriptor) => {
      started.push(descriptor.id);
      return fakeChild(descriptor.id, pid += 1);
    },
    terminateProcess: async (child) => {
      stopped.push(child.id);
      child.exitCode = 0;
      child.emit('exit', 0, null);
    },
    log: {},
  });
  await supervisor.startAll();
  assert.deepEqual(started, ['control-plane', 'inference-service', 'training-worker']);
  assert.ok(supervisor.listStatuses().every((status) => status.state === 'ready'));
  await supervisor.stopAll();
  assert.deepEqual(stopped, ['training-worker', 'inference-service', 'control-plane']);
  assert.ok(supervisor.listStatuses().every((status) => status.state === 'stopped'));
});

test('restart budget fails closed after the configured number of crashes', () => {
  const supervisor = new ProcessSupervisor({
    descriptors: descriptors(),
    python: { command: 'python', prefixArgs: [] },
    environment: {},
    spawnProcess: () => fakeChild('unused', 1),
    log: {},
  });
  supervisor.scheduleRestart('control-plane', new Error('first'));
  supervisor.clearRestartTimer(supervisor.requireRecord('control-plane'));
  supervisor.scheduleRestart('control-plane', new Error('second'));
  supervisor.clearRestartTimer(supervisor.requireRecord('control-plane'));
  supervisor.scheduleRestart('control-plane', new Error('third'));
  assert.equal(supervisor.getStatus('control-plane').state, 'failed');
  assert.equal(supervisor.getStatus('control-plane').restarts, 2);
});
