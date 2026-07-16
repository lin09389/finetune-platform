'use strict';

const fs = require('node:fs');
const path = require('node:path');

const ACTIVATION_SCHEMA_VERSION = 1;
const COMPLETION_MARKER = '.complete.json';

function storeError(code, message) {
  return Object.assign(new Error(message), { code });
}

function safeSegment(value, label) {
  if (typeof value !== 'string' || !/^[a-zA-Z0-9][a-zA-Z0-9._-]*$/.test(value)) {
    throw storeError('MANAGED_RUNTIME_PATH_UNSAFE', `${label} is not a safe managed-runtime path segment.`);
  }
  return value;
}

function isWithin(parent, candidate) {
  const relation = path.relative(parent, candidate);
  return relation === '' || (!relation.startsWith(`..${path.sep}`) && relation !== '..' && !path.isAbsolute(relation));
}

async function readJson(filePath) {
  try {
    return JSON.parse(await fs.promises.readFile(filePath, 'utf8'));
  } catch (error) {
    if (error.code === 'ENOENT' || error instanceof SyntaxError) return null;
    throw error;
  }
}

class ManagedRuntimeStore {
  constructor({ root }) {
    if (typeof root !== 'string' || !path.isAbsolute(root)) {
      throw storeError('MANAGED_RUNTIME_ROOT_INVALID', 'Managed runtime root must be an absolute path.');
    }
    this.root = path.resolve(root);
    this.stagingRoot = path.join(this.root, 'staging');
    this.versionsRoot = path.join(this.root, 'versions');
    this.quarantineRoot = path.join(this.root, 'quarantine');
    this.activePath = path.join(this.root, 'active.json');
  }

  assertManagedPath(candidate) {
    const resolved = path.resolve(candidate);
    if (!isWithin(this.root, resolved)) {
      throw storeError('MANAGED_RUNTIME_PATH_UNSAFE', 'Managed runtime path escapes the managed runtime root.');
    }
    return resolved;
  }

  versionPath(profile, version) {
    return this.assertManagedPath(path.join(this.versionsRoot, safeSegment(profile, 'profile'), safeSegment(version, 'version')));
  }

  async ensureLayout() {
    await Promise.all([this.stagingRoot, this.versionsRoot, this.quarantineRoot].map((directory) => (
      fs.promises.mkdir(directory, { recursive: true })
    )));
  }

  async createStaging(operationId) {
    await this.ensureLayout();
    const safeOperationId = safeSegment(operationId, 'operation id');
    const stagingPath = this.assertManagedPath(path.join(this.stagingRoot, safeOperationId));
    await fs.promises.mkdir(stagingPath, { recursive: false });
    return stagingPath;
  }

  assertStagingPath(stagingPath) {
    const resolved = this.assertManagedPath(stagingPath);
    if (path.dirname(resolved) !== this.stagingRoot) {
      throw storeError('MANAGED_RUNTIME_PATH_UNSAFE', 'Staging path is not owned by the managed runtime store.');
    }
    safeSegment(path.basename(resolved), 'operation id');
    return resolved;
  }

  completionPath(runtimePath) {
    return path.join(this.assertManagedPath(runtimePath), COMPLETION_MARKER);
  }

  async markStagingComplete(stagingPath, manifest) {
    const ownedStagingPath = this.assertStagingPath(stagingPath);
    const marker = Object.freeze({
      schemaVersion: ACTIVATION_SCHEMA_VERSION,
      profile: safeSegment(manifest.profile, 'profile'),
      version: safeSegment(manifest.version, 'version'),
      unpackedSha256: manifest.unpackedSha256,
      entrypoint: manifest.entrypoint,
      completedAt: new Date().toISOString(),
    });
    const markerPath = this.completionPath(ownedStagingPath);
    await fs.promises.writeFile(markerPath, `${JSON.stringify(marker)}\n`, { encoding: 'utf8', flag: 'wx' });
    return marker;
  }

  async readCompletionMarker(runtimePath) {
    const marker = await readJson(this.completionPath(runtimePath));
    if (!marker || marker.schemaVersion !== ACTIVATION_SCHEMA_VERSION) return null;
    try {
      safeSegment(marker.profile, 'profile');
      safeSegment(marker.version, 'version');
      if (typeof marker.entrypoint !== 'string' || marker.entrypoint.length === 0 || typeof marker.completedAt !== 'string') {
        return null;
      }
      return Object.freeze({ ...marker });
    } catch (_error) {
      return null;
    }
  }

  async commitStaging(stagingPath, manifest) {
    const ownedStagingPath = this.assertStagingPath(stagingPath);
    const marker = await this.readCompletionMarker(ownedStagingPath);
    if (!marker || marker.profile !== manifest.profile || marker.version !== manifest.version
      || marker.unpackedSha256 !== manifest.unpackedSha256 || marker.entrypoint !== manifest.entrypoint) {
      throw storeError('MANAGED_RUNTIME_STAGING_INCOMPLETE', 'Staging runtime does not have a matching completion marker.');
    }
    const destination = this.versionPath(manifest.profile, manifest.version);
    await fs.promises.mkdir(path.dirname(destination), { recursive: true });
    try {
      await fs.promises.rename(ownedStagingPath, destination);
    } catch (error) {
      if (error.code === 'EEXIST' || error.code === 'ENOTEMPTY') {
        throw storeError('MANAGED_RUNTIME_VERSION_EXISTS', 'A runtime with this immutable profile and version already exists.');
      }
      throw error;
    }
    return destination;
  }

  async writeAtomicJson(destination, value) {
    this.assertManagedPath(destination);
    const temporary = this.assertManagedPath(path.join(
      path.dirname(destination),
      `.${path.basename(destination)}.${process.pid}.${Math.random().toString(16).slice(2)}.tmp`,
    ));
    let handle;
    try {
      handle = await fs.promises.open(temporary, 'wx', 0o600);
      await handle.writeFile(`${JSON.stringify(value)}\n`, 'utf8');
      await handle.sync();
      await handle.close();
      handle = null;
      await fs.promises.rename(temporary, destination);
    } finally {
      await handle?.close();
      await fs.promises.rm(temporary, { force: true });
    }
  }

  async activate(manifest, health) {
    const runtimePath = this.versionPath(manifest.profile, manifest.version);
    const marker = await this.readCompletionMarker(runtimePath);
    if (!marker || marker.unpackedSha256 !== manifest.unpackedSha256 || marker.entrypoint !== manifest.entrypoint) {
      throw storeError('MANAGED_RUNTIME_ACTIVATION_INVALID', 'Only completed immutable runtimes may be activated.');
    }
    if (!health || typeof health.pythonVersion !== 'string' || typeof health.checkedAt !== 'string') {
      throw storeError('MANAGED_RUNTIME_HEALTH_INVALID', 'Activation requires a successful health check.');
    }
    const record = Object.freeze({
      schemaVersion: ACTIVATION_SCHEMA_VERSION,
      profile: manifest.profile,
      version: manifest.version,
      entrypoint: manifest.entrypoint,
      health: Object.freeze({ status: 'healthy', pythonVersion: health.pythonVersion, checkedAt: health.checkedAt }),
      activatedAt: new Date().toISOString(),
    });
    await this.writeAtomicJson(this.activePath, record);
    return record;
  }

  async readActive(profile) {
    const record = await readJson(this.activePath);
    if (!record || record.schemaVersion !== ACTIVATION_SCHEMA_VERSION || record.profile !== profile
      || !record.health || record.health.status !== 'healthy') return null;
    try {
      const runtimePath = this.versionPath(record.profile, record.version);
      const marker = await this.readCompletionMarker(runtimePath);
      if (!marker || marker.entrypoint !== record.entrypoint || marker.profile !== record.profile || marker.version !== record.version) {
        return null;
      }
      const executablePath = this.assertManagedPath(path.join(runtimePath, record.entrypoint));
      if (!isWithin(runtimePath, executablePath)) return null;
      await fs.promises.access(executablePath, fs.constants.X_OK);
      return Object.freeze({ ...record, health: Object.freeze({ ...record.health }), runtimePath, executablePath });
    } catch (_error) {
      return null;
    }
  }

  async listStaleStaging({ olderThanMs, now = Date.now() } = {}) {
    const age = Number.isFinite(olderThanMs) && olderThanMs >= 0 ? olderThanMs : 0;
    await this.ensureLayout();
    const entries = await fs.promises.readdir(this.stagingRoot, { withFileTypes: true });
    const stale = [];
    for (const entry of entries) {
      if (!entry.isDirectory()) continue;
      const stagingPath = this.assertStagingPath(path.join(this.stagingRoot, entry.name));
      const stats = await fs.promises.stat(stagingPath);
      if (now - stats.mtimeMs < age || await this.readCompletionMarker(stagingPath)) continue;
      stale.push(Object.freeze({ operationId: entry.name, stagingPath, modifiedAt: new Date(stats.mtimeMs).toISOString() }));
    }
    return Object.freeze(stale);
  }

  async removeStaging(stagingPath) {
    await fs.promises.rm(this.assertStagingPath(stagingPath), { recursive: true, force: true });
  }

  async quarantineStaging(stagingPath, reason) {
    const ownedStagingPath = this.assertStagingPath(stagingPath);
    await this.ensureLayout();
    const operationId = path.basename(ownedStagingPath);
    const metadataPath = this.assertManagedPath(path.join(this.quarantineRoot, `${operationId}.json`));
    await this.writeAtomicJson(metadataPath, {
      schemaVersion: ACTIVATION_SCHEMA_VERSION,
      operationId,
      reason: String(reason || 'unknown'),
      quarantinedAt: new Date().toISOString(),
    });
    await this.removeStaging(ownedStagingPath);
  }
}

module.exports = { ACTIVATION_SCHEMA_VERSION, COMPLETION_MARKER, ManagedRuntimeStore };
