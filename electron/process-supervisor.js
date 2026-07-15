'use strict';

const { EventEmitter } = require('node:events');
const http = require('node:http');
const https = require('node:https');
const net = require('node:net');
const { spawn, execFile } = require('node:child_process');
const { START_ORDER, STOP_ORDER, SERVICE_STATES, publicServiceStatus } = require('./runtime-contract');

const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

function probeHttp(url, timeoutMs = 2_000, validatePayload = null) {
  return new Promise((resolve) => {
    const transport = url.startsWith('https:') ? https : http;
    const request = transport.get(url, { timeout: timeoutMs }, (response) => {
      if (response.statusCode !== 200) {
        response.resume();
        resolve(false);
        return;
      }
      let body = '';
      response.setEncoding('utf8');
      response.on('data', (chunk) => {
        body += chunk;
        if (body.length > 64 * 1024) request.destroy();
      });
      response.on('end', () => {
        if (!validatePayload) {
          resolve(true);
          return;
        }
        try {
          resolve(Boolean(validatePayload(JSON.parse(body))));
        } catch (_error) {
          resolve(false);
        }
      });
    });
    request.on('error', () => resolve(false));
    request.on('timeout', () => {
      request.destroy();
      resolve(false);
    });
  });
}

function isPortAvailable(host, port) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.unref();
    server.once('error', () => resolve(false));
    server.listen({ host, port, exclusive: true }, () => {
      server.close(() => resolve(true));
    });
  });
}

function createTrainingWorkerProbe(python, databasePath) {
  const script = [
    'import sqlite3, sys',
    'db, worker_id, expected_pid = sys.argv[1], sys.argv[2], int(sys.argv[3])',
    'conn = sqlite3.connect(db, timeout=1)',
    'row = conn.execute("SELECT status, pid FROM training_workers WHERE worker_id = ?", (worker_id,)).fetchone()',
    'print("1" if row and row[0] == "online" and int(row[1]) == expected_pid else "0")',
  ].join('; ');
  return (descriptor, child) => new Promise((resolve) => {
    if (descriptor.id !== 'training-worker' || !child?.pid) {
      resolve(Boolean(child && !child.killed && child.exitCode === null));
      return;
    }
    execFile(
      python.command,
      [...python.prefixArgs, '-c', script, databasePath, descriptor.workerId, String(child.pid)],
      { windowsHide: true, timeout: 2_000, encoding: 'utf8' },
      (error, stdout) => resolve(!error && stdout.trim() === '1'),
    );
  });
}

function spawnOwnedProcess(python, descriptor, environment) {
  return spawn(python.command, [...python.prefixArgs, ...descriptor.args], {
    cwd: descriptor.cwd,
    env: environment,
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
    detached: process.platform !== 'win32',
  });
}

async function terminateOwnedProcess(child, { force = false } = {}) {
  if (!child || !child.pid) return;
  if (process.platform === 'win32') {
    await new Promise((resolve) => {
      const args = ['/PID', String(child.pid), '/T'];
      if (force) args.push('/F');
      execFile('taskkill', args, { windowsHide: true }, () => resolve());
    });
    return;
  }
  try {
    process.kill(-child.pid, force ? 'SIGKILL' : 'SIGTERM');
  } catch (error) {
    if (error.code !== 'ESRCH') throw error;
  }
}

class ProcessSupervisor extends EventEmitter {
  constructor({
    descriptors,
    python,
    environment,
    probe = probeHttp,
    probeProcess = async (_descriptor, child) => Boolean(child && !child.killed && child.exitCode === null),
    portAvailable = isPortAvailable,
    spawnProcess = spawnOwnedProcess,
    terminateProcess = terminateOwnedProcess,
    sleep = delay,
    now = Date.now,
    log = console,
  }) {
    super();
    this.descriptors = new Map(descriptors.map((item) => [item.id, item]));
    this.python = python;
    this.environment = environment;
    this.probe = probe;
    this.probeProcess = probeProcess;
    this.portAvailable = portAvailable;
    this.spawnProcess = spawnProcess;
    this.terminateProcess = terminateProcess;
    this.sleep = sleep;
    this.now = now;
    this.log = log;
    this.records = new Map();
    this.shuttingDown = false;

    for (const descriptor of descriptors) {
      this.records.set(descriptor.id, {
        child: null,
        monitor: null,
        restartTimer: null,
        restartHistory: [],
        intentionalStop: false,
        status: {
          id: descriptor.id,
          label: descriptor.label,
          state: 'stopped',
          pid: null,
          restarts: 0,
          lastError: null,
          updatedAt: new Date(this.now()).toISOString(),
        },
      });
    }
  }

  listStatuses() {
    return [...this.records.values()].map((record) => publicServiceStatus(record.status));
  }

  getStatus(id) {
    const record = this.requireRecord(id);
    return publicServiceStatus(record.status);
  }

  setState(id, state, patch = {}) {
    if (!SERVICE_STATES.includes(state)) throw new Error(`Invalid desktop service state: ${state}`);
    const record = this.requireRecord(id);
    record.status = {
      ...record.status,
      ...patch,
      state,
      updatedAt: new Date(this.now()).toISOString(),
    };
    const publicStatus = publicServiceStatus(record.status);
    this.emit('status', publicStatus);
    return publicStatus;
  }

  requireRecord(id) {
    const record = this.records.get(id);
    if (!record) throw Object.assign(new Error(`Unknown desktop service: ${id}`), { code: 'UNKNOWN_SERVICE' });
    return record;
  }

  async startAll() {
    for (const id of START_ORDER) {
      if (this.shuttingDown) break;
      if (!this.descriptors.has(id)) continue;
      try {
        await this.startService(id);
      } catch (error) {
        this.log.error?.(`[desktop:${id}] startup failed`, error);
      }
    }
    return this.listStatuses();
  }

  async startService(id) {
    const descriptor = this.descriptors.get(id);
    const record = this.requireRecord(id);
    if (this.shuttingDown) {
      throw Object.assign(new Error('Desktop runtime is shutting down.'), { code: 'RUNTIME_STOPPING' });
    }
    if (record.child && !record.child.killed) return this.getStatus(id);

    record.intentionalStop = false;
    this.clearRestartTimer(record);
    this.setState(id, 'starting', { pid: null, lastError: null });

    if (descriptor.port && !(await this.portAvailable(descriptor.host, descriptor.port))) {
      const error = new Error(`Port ${descriptor.host}:${descriptor.port} is already in use.`);
      error.code = 'SERVICE_PORT_IN_USE';
      this.setState(id, 'failed', { lastError: error.message });
      throw error;
    }
    if (this.shuttingDown) {
      throw Object.assign(new Error('Desktop runtime is shutting down.'), { code: 'RUNTIME_STOPPING' });
    }

    let child;
    try {
      child = this.spawnProcess(this.python, descriptor, this.environment);
    } catch (error) {
      this.setState(id, 'failed', { lastError: error.message });
      throw error;
    }
    record.child = child;
    this.setState(id, 'starting', { pid: child.pid || null });
    this.pipeOutput(id, child);
    child.once('error', (error) => this.handleChildFailure(id, child, error));
    child.once('exit', (code, signal) => {
      const detail = signal ? `signal ${signal}` : `code ${code}`;
      this.handleChildFailure(id, child, new Error(`Process exited with ${detail}`));
    });

    const ready = await this.waitUntilReady(descriptor, child);
    if (record.child !== child) return this.getStatus(id);
    if (!ready) {
      const error = new Error(`Service did not become ready within ${descriptor.startupTimeoutMs}ms`);
      await this.handleUnhealthy(id, child, error);
      throw error;
    }

    this.setState(id, 'ready', { pid: child.pid || null, lastError: null });
    this.startHealthMonitor(id, child);
    return this.getStatus(id);
  }

  async waitUntilReady(descriptor, child) {
    const startedAt = this.now();
    while (this.now() - startedAt < descriptor.startupTimeoutMs) {
      if (!child || child.killed || child.exitCode !== null) return false;
      if (await this.checkHealth(descriptor, child)) return true;
      await this.sleep(250);
    }
    return false;
  }

  startHealthMonitor(id, child) {
    const descriptor = this.descriptors.get(id);
    const record = this.requireRecord(id);
    this.clearMonitor(record);
    let consecutiveFailures = 0;
    record.monitor = setInterval(async () => {
      if (this.shuttingDown || record.child !== child) return;
      const healthy = await this.checkHealth(descriptor, child);
      if (healthy) {
        consecutiveFailures = 0;
        if (record.status.state === 'degraded') this.setState(id, 'ready', { lastError: null });
        return;
      }
      consecutiveFailures += 1;
      if (consecutiveFailures === 1) {
        this.setState(id, 'degraded', { lastError: 'Health probe failed' });
      } else {
        this.clearMonitor(record);
        await this.handleUnhealthy(id, child, new Error('Health probe failed repeatedly'));
      }
    }, descriptor.healthIntervalMs);
    record.monitor.unref?.();
  }

  async checkHealth(descriptor, child) {
    if (descriptor.healthUrl) {
      return this.probe(descriptor.healthUrl, 2_000, descriptor.healthValidator);
    }
    return this.probeProcess(descriptor, child);
  }

  pipeOutput(id, child) {
    child.stdout?.setEncoding?.('utf8');
    child.stderr?.setEncoding?.('utf8');
    child.stdout?.on?.('data', (chunk) => this.log.info?.(`[desktop:${id}] ${String(chunk).trimEnd()}`));
    child.stderr?.on?.('data', (chunk) => this.log.error?.(`[desktop:${id}] ${String(chunk).trimEnd()}`));
  }

  handleChildFailure(id, child, error) {
    const record = this.requireRecord(id);
    if (record.child !== child) return;
    record.child = null;
    this.clearMonitor(record);
    if (record.intentionalStop || this.shuttingDown) {
      this.setState(id, 'stopped', { pid: null });
      return;
    }
    this.scheduleRestart(id, error);
  }

  async handleUnhealthy(id, child, error) {
    const record = this.requireRecord(id);
    if (record.child !== child) return;
    record.intentionalStop = true;
    await this.stopChild(id, child, this.descriptors.get(id).stopTimeoutMs);
    if (record.child === child) record.child = null;
    record.intentionalStop = false;
    if (!this.shuttingDown) this.scheduleRestart(id, error);
  }

  scheduleRestart(id, error) {
    const descriptor = this.descriptors.get(id);
    const record = this.requireRecord(id);
    if (this.shuttingDown || record.restartTimer) return;
    const cutoff = this.now() - descriptor.restart.windowMs;
    record.restartHistory = record.restartHistory.filter((timestamp) => timestamp >= cutoff);
    if (record.restartHistory.length >= descriptor.restart.maxAttempts) {
      this.setState(id, 'failed', { pid: null, lastError: error.message });
      return;
    }

    record.restartHistory.push(this.now());
    const restarts = record.status.restarts + 1;
    this.setState(id, 'degraded', { pid: null, restarts, lastError: error.message });
    record.restartTimer = setTimeout(async () => {
      record.restartTimer = null;
      try {
        await this.startService(id);
      } catch (restartError) {
        if (!record.restartTimer && !this.shuttingDown && record.status.state !== 'failed') {
          this.scheduleRestart(id, restartError);
        }
      }
    }, descriptor.restart.delayMs);
    record.restartTimer.unref?.();
  }

  async restartService(id) {
    this.requireRecord(id);
    await this.stopService(id);
    return this.startService(id);
  }

  async stopService(id) {
    const descriptor = this.descriptors.get(id);
    const record = this.requireRecord(id);
    this.clearRestartTimer(record);
    this.clearMonitor(record);
    record.intentionalStop = true;
    const child = record.child;
    if (!child) {
      this.setState(id, 'stopped', { pid: null });
      return;
    }

    this.setState(id, 'stopping', { pid: child.pid || null });
    await this.stopChild(id, child, descriptor.stopTimeoutMs);
    if (record.child === child) record.child = null;
    this.setState(id, 'stopped', { pid: null });
  }

  async stopChild(id, child, timeoutMs) {
    if (child.exitCode !== null || child.killed) return;
    let settled = false;
    const exited = new Promise((resolve) => {
      child.once('exit', () => {
        settled = true;
        resolve(true);
      });
    });
    await this.terminateProcess(child, { force: false });
    await Promise.race([exited, this.sleep(timeoutMs)]);
    if (!settled && child.exitCode === null) {
      this.log.warn?.(`[desktop:${id}] forcing owned process tree to stop`);
      await this.terminateProcess(child, { force: true });
      await Promise.race([exited, this.sleep(2_000)]);
    }
  }

  async stopAll() {
    this.shuttingDown = true;
    for (const id of STOP_ORDER) {
      if (this.descriptors.has(id)) await this.stopService(id);
    }
    return this.listStatuses();
  }

  beginShutdown() {
    this.shuttingDown = true;
  }

  clearMonitor(record) {
    if (record.monitor) clearInterval(record.monitor);
    record.monitor = null;
  }

  clearRestartTimer(record) {
    if (record.restartTimer) clearTimeout(record.restartTimer);
    record.restartTimer = null;
  }
}

module.exports = {
  ProcessSupervisor,
  probeHttp,
  isPortAvailable,
  createTrainingWorkerProbe,
  spawnOwnedProcess,
  terminateOwnedProcess,
};
