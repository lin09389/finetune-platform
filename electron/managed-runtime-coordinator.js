'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { validateManagedRuntimeManifest } = require('./managed-runtime-manifest');

const MANAGED_RUNTIME_STATUS_VERSION = 1;

function coordinatorError(code, message) {
  return Object.assign(new Error(message), { code });
}

function normalizeError(error) {
  if (error?.code) return error;
  return coordinatorError('MANAGED_RUNTIME_OPERATION_FAILED', error?.message || 'Managed runtime operation failed.');
}

function throwIfAborted(signal) {
  if (signal?.aborted) throw coordinatorError('MANAGED_RUNTIME_CANCELLED', 'Managed runtime operation was cancelled.');
}

async function sha256File(filePath) {
  const hash = crypto.createHash('sha256');
  await new Promise((resolve, reject) => {
    const stream = fs.createReadStream(filePath);
    stream.on('data', (chunk) => hash.update(chunk));
    stream.once('error', reject);
    stream.once('end', resolve);
  });
  return hash.digest('hex');
}

async function digestRuntimeDirectory(root) {
  const hash = crypto.createHash('sha256');
  const files = [];
  async function visit(directory, relative = '') {
    const entries = await fs.promises.readdir(directory, { withFileTypes: true });
    for (const entry of entries.sort((left, right) => Buffer.compare(Buffer.from(left.name), Buffer.from(right.name)))) {
      const entryRelative = relative ? `${relative}/${entry.name}` : entry.name;
      const entryPath = path.join(directory, entry.name);
      if (entry.isSymbolicLink()) {
        throw coordinatorError('MANAGED_RUNTIME_UNPACKED_CONTENT_INVALID', 'Runtime content must not contain symbolic links.');
      }
      if (entry.isDirectory()) {
        await visit(entryPath, entryRelative);
      } else if (entry.isFile()) {
        files.push({ entryRelative, entryPath });
      } else {
        throw coordinatorError('MANAGED_RUNTIME_UNPACKED_CONTENT_INVALID', 'Runtime content must contain only regular files and directories.');
      }
    }
  }
  await visit(root);
  files.sort((left, right) => Buffer.compare(Buffer.from(left.entryRelative), Buffer.from(right.entryRelative)));
  for (const file of files) {
    hash.update(file.entryRelative, 'utf8');
    hash.update('\0');
    hash.update(Buffer.from(await sha256File(file.entryPath), 'hex'));
  }
  return hash.digest('hex');
}

function normalizePythonVersion(result) {
  if (typeof result?.pythonVersion === 'string' && /^3\.11\.\d+$/.test(result.pythonVersion)) return result.pythonVersion;
  if (result?.major === 3 && result?.minor === 11 && Number.isInteger(result.patch) && result.patch >= 0) {
    return `3.11.${result.patch}`;
  }
  throw coordinatorError('MANAGED_RUNTIME_PROBE_INCOMPATIBLE', 'Health probe did not confirm Python 3.11.');
}

function freezeSnapshot(snapshot) {
  return Object.freeze({
    ...snapshot,
    progress: snapshot.progress ? Object.freeze({ ...snapshot.progress }) : null,
  });
}

class ManagedRuntimeCoordinator {
  constructor({ store, target, artifactAdapter, probeAdapter, staleStagingAgeMs = 24 * 60 * 60 * 1_000, clock = () => new Date() }) {
    if (!store || !target || !artifactAdapter || !probeAdapter) {
      throw new TypeError('ManagedRuntimeCoordinator requires store, target, artifactAdapter, and probeAdapter.');
    }
    if (typeof artifactAdapter.acquire !== 'function' || typeof artifactAdapter.extract !== 'function' || typeof probeAdapter.probe !== 'function') {
      throw new TypeError('Managed runtime adapters must implement acquire, extract, and probe.');
    }
    this.store = store;
    this.target = Object.freeze({ ...target });
    this.artifactAdapter = artifactAdapter;
    this.probeAdapter = probeAdapter;
    this.staleStagingAgeMs = staleStagingAgeMs;
    this.clock = clock;
    this.listeners = new Set();
    this.operation = null;
    this.shutdownRequested = false;
    this.abortController = null;
    this.snapshot = this.createSnapshot({ state: 'unavailable', profile: target.profile, recoverable: true });
  }

  createSnapshot({
    state,
    operationId = null,
    profile = this.target.profile,
    runtimeVersion = null,
    pythonVersion = null,
    progress = null,
    recoverable = false,
    lastErrorCode = null,
  }) {
    return freezeSnapshot({
      protocolVersion: MANAGED_RUNTIME_STATUS_VERSION,
      operationId,
      state,
      profile,
      runtimeVersion,
      pythonVersion,
      source: 'managed',
      progress,
      recoverable,
      lastErrorCode,
      updatedAt: this.clock().toISOString(),
    });
  }

  publish(next) {
    this.snapshot = freezeSnapshot(next);
    for (const listener of this.listeners) listener(this.snapshot);
    return this.snapshot;
  }

  getSnapshot() { return this.snapshot; }

  subscribe(listener) {
    if (typeof listener !== 'function') throw new TypeError('Managed runtime listener must be a function.');
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  on(event, listener) {
    if (event !== 'status') throw new TypeError('Managed runtime only emits status events.');
    this.listeners.add(listener);
    return this;
  }

  off(event, listener) {
    if (event === 'status') this.listeners.delete(listener);
    return this;
  }

  async check() {
    this.publish(this.createSnapshot({ state: 'checking', profile: this.target.profile }));
    const active = await this.store.readActive(this.target.profile);
    if (!active) return this.publish(this.createSnapshot({ state: 'unavailable', profile: this.target.profile, recoverable: true }));
    return this.publish(this.createSnapshot({
      state: 'ready',
      profile: active.profile,
      runtimeVersion: active.version,
      pythonVersion: active.health.pythonVersion,
    }));
  }

  prepare(manifestInput) { return this.start('prepare', manifestInput); }

  repair(manifestInput) { return this.start('repair', manifestInput); }

  async loadManifest() {
    if (typeof this.artifactAdapter.getManifest !== 'function') {
      throw coordinatorError('MANAGED_RUNTIME_ARTIFACT_UNAVAILABLE', 'No managed runtime manifest source is configured.');
    }
    return this.artifactAdapter.getManifest({ target: this.target });
  }

  async invokePackagedAction(kind) {
    if (this.shutdownRequested) {
      throw coordinatorError('MANAGED_RUNTIME_CANCELLED', 'Managed runtime is shutting down.');
    }
    try {
      const manifest = await this.loadManifest();
      this.lastAction = kind;
      this.lastManifest = manifest;
      return kind === 'repair' ? this.repair(manifest) : this.prepare(manifest);
    } catch (error) {
      const normalized = normalizeError(error);
      this.publish(this.createSnapshot({
        state: 'repair_required', profile: this.target.profile, recoverable: true, lastErrorCode: normalized.code,
      }));
      throw normalized;
    }
  }

  prepareBaseRuntime() { return this.invokePackagedAction('prepare'); }

  repairBaseRuntime() { return this.invokePackagedAction('repair'); }

  retryRuntimeOperation() { return this.invokePackagedAction(this.lastAction || 'prepare'); }

  start(kind, manifestInput) {
    if (this.operation) return this.operation;
    let manifest;
    try {
      manifest = validateManagedRuntimeManifest(manifestInput, this.target);
    } catch (error) {
      const normalized = normalizeError(error);
      this.publish(this.createSnapshot({
        state: 'repair_required', profile: this.target.profile, recoverable: true, lastErrorCode: normalized.code,
      }));
      return Promise.reject(normalized);
    }
    const operation = this.run(kind, manifest);
    this.operation = operation;
    operation.finally(() => {
      if (this.operation === operation) this.operation = null;
      this.abortController = null;
    }).catch(() => {});
    return operation;
  }

  async cleanupStaleStaging() {
    const stale = await this.store.listStaleStaging({ olderThanMs: this.staleStagingAgeMs });
    await Promise.all(stale.map((entry) => this.store.quarantineStaging(entry.stagingPath, 'stale-interrupted-staging')));
  }

  async run(kind, manifest) {
    const operationId = crypto.randomUUID();
    const controller = new AbortController();
    this.abortController = controller;
    let stagingPath = null;
    let previous = null;
    try {
      throwIfAborted(controller.signal);
      previous = await this.store.readActive(manifest.profile);
      await this.cleanupStaleStaging();
      this.publish(this.createSnapshot({
        state: 'preparing', operationId, profile: manifest.profile,
        runtimeVersion: previous?.version || null, pythonVersion: previous?.health.pythonVersion || null,
        progress: { completed: 1, total: 4 }, recoverable: Boolean(previous),
      }));
      stagingPath = await this.store.createStaging(operationId);
      const artifact = await this.artifactAdapter.acquire({ manifest, stagingPath, signal: controller.signal });
      throwIfAborted(controller.signal);
      if (!artifact || typeof artifact.archivePath !== 'string') {
        throw coordinatorError('MANAGED_RUNTIME_ARTIFACT_INVALID', 'Artifact adapter did not provide an archive path.');
      }
      if (await sha256File(artifact.archivePath) !== manifest.archiveSha256) {
        throw coordinatorError('MANAGED_RUNTIME_ARCHIVE_DIGEST_MISMATCH', 'Runtime archive checksum does not match its manifest.');
      }
      await this.artifactAdapter.extract({ archivePath: artifact.archivePath, destination: stagingPath, manifest, signal: controller.signal });
      throwIfAborted(controller.signal);
      this.publish(this.createSnapshot({
        state: 'verifying', operationId, profile: manifest.profile,
        runtimeVersion: manifest.version,
        progress: { completed: 2, total: 4 }, recoverable: Boolean(previous),
      }));
      if (await digestRuntimeDirectory(stagingPath) !== manifest.unpackedSha256) {
        throw coordinatorError('MANAGED_RUNTIME_UNPACKED_DIGEST_MISMATCH', 'Unpacked runtime content does not match its manifest.');
      }
      const executablePath = this.store.assertManagedPath(path.join(stagingPath, manifest.entrypoint));
      await fs.promises.access(executablePath, fs.constants.X_OK);
      this.publish(this.createSnapshot({
        state: 'verifying', operationId, profile: manifest.profile, runtimeVersion: manifest.version,
        progress: { completed: 3, total: 4 }, recoverable: Boolean(previous),
      }));
      const probeResult = await this.probeAdapter.probe({ executablePath, manifest, signal: controller.signal });
      const pythonVersion = normalizePythonVersion(probeResult);
      throwIfAborted(controller.signal);
      await this.store.markStagingComplete(stagingPath, manifest);
      await this.store.commitStaging(stagingPath, manifest);
      stagingPath = null;
      throwIfAborted(controller.signal);
      await this.store.activate(manifest, { pythonVersion, checkedAt: this.clock().toISOString() });
      return this.publish(this.createSnapshot({
        state: 'ready', profile: manifest.profile, runtimeVersion: manifest.version, pythonVersion,
        progress: { completed: 4, total: 4 },
      }));
    } catch (error) {
      const normalized = controller.signal.aborted ? coordinatorError('MANAGED_RUNTIME_CANCELLED', 'Managed runtime operation was cancelled.') : normalizeError(error);
      if (stagingPath) {
        try { await this.store.quarantineStaging(stagingPath, normalized.code); } catch (_cleanupError) { /* preserve original failure */ }
      }
      this.publish(this.createSnapshot({
        state: previous ? 'failed' : 'repair_required',
        profile: manifest.profile,
        runtimeVersion: previous?.version || null,
        pythonVersion: previous?.health.pythonVersion || null,
        recoverable: true,
        lastErrorCode: normalized.code,
      }));
      throw normalized;
    }
  }

  beginShutdown() {
    this.shutdownRequested = true;
    this.abortController?.abort();
  }
}

module.exports = {
  MANAGED_RUNTIME_STATUS_VERSION,
  ManagedRuntimeCoordinator,
  digestRuntimeDirectory,
  sha256File,
};
