'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { execFile } = require('node:child_process');
const { promisify } = require('node:util');
const { validateManagedRuntimeManifest } = require('./managed-runtime-manifest');

const execFileAsync = promisify(execFile);

function artifactError(code, message) {
  return Object.assign(new Error(message), { code });
}

function isWithin(parent, candidate) {
  const relation = path.relative(parent, candidate);
  return relation === '' || (!relation.startsWith(`..${path.sep}`) && relation !== '..' && !path.isAbsolute(relation));
}

function normalizeArchiveEntry(value) {
  if (typeof value !== 'string' || !value || value.includes('\0')) {
    throw artifactError('MANAGED_RUNTIME_ARCHIVE_CONTENT_UNSAFE', 'Runtime archive contains an invalid path.');
  }
  const normalized = value.replace(/\\/g, '/').replace(/^\.\//, '');
  if (path.posix.isAbsolute(normalized)
    || normalized.split('/').some((segment) => !segment || segment === '.' || segment === '..')) {
    throw artifactError('MANAGED_RUNTIME_ARCHIVE_CONTENT_UNSAFE', 'Runtime archive path escapes its staging directory.');
  }
  return normalized;
}

class LocalRuntimeArtifactAdapter {
  constructor({ manifestPath = null, manifestDirectory = null, target, runCommand = execFileAsync }) {
    if (!target || typeof target !== 'object') throw new TypeError('A managed runtime target is required.');
    if (!manifestPath && !manifestDirectory) throw new TypeError('A runtime manifest path or directory is required.');
    this.manifestPath = manifestPath ? path.resolve(manifestPath) : null;
    this.manifestDirectory = manifestDirectory ? path.resolve(manifestDirectory) : null;
    this.target = Object.freeze({ ...target });
    this.runCommand = runCommand;
    this.selectedManifestPath = null;
  }

  async readManifest(candidate) {
    let input;
    try {
      input = JSON.parse(await fs.promises.readFile(candidate, 'utf8'));
    } catch (error) {
      if (error.code === 'ENOENT') {
        throw artifactError('MANAGED_RUNTIME_ARTIFACT_UNAVAILABLE', 'No local managed runtime manifest is available.');
      }
      if (error instanceof SyntaxError) {
        throw artifactError('MANAGED_RUNTIME_MANIFEST_INVALID', 'The local managed runtime manifest is invalid JSON.');
      }
      throw error;
    }
    return validateManagedRuntimeManifest(input, this.target);
  }

  async discoverManifest() {
    if (this.manifestPath) return this.manifestPath;
    let entries;
    try {
      entries = await fs.promises.readdir(this.manifestDirectory, { withFileTypes: true });
    } catch (error) {
      if (error.code === 'ENOENT') {
        throw artifactError('MANAGED_RUNTIME_ARTIFACT_UNAVAILABLE', 'No local managed runtime pack directory is available.');
      }
      throw error;
    }
    const candidates = entries
      .filter((entry) => entry.isFile() && entry.name.endsWith('.manifest.json'))
      .map((entry) => path.join(this.manifestDirectory, entry.name))
      .sort((left, right) => Buffer.compare(Buffer.from(left), Buffer.from(right)));
    const compatible = [];
    for (const candidate of candidates) {
      try {
        compatible.push({ path: candidate, manifest: await this.readManifest(candidate) });
      } catch (error) {
        if (!String(error.code || '').includes('UNSUPPORTED') && error.code !== 'MANAGED_RUNTIME_MANIFEST_PROFILE_UNSUPPORTED') {
          throw error;
        }
      }
    }
    if (compatible.length === 0) {
      throw artifactError('MANAGED_RUNTIME_ARTIFACT_UNAVAILABLE', 'No compatible local managed runtime pack is available.');
    }
    if (compatible.length > 1) {
      throw artifactError('MANAGED_RUNTIME_ARTIFACT_AMBIGUOUS', 'Multiple compatible runtime manifests are present; keep exactly one release candidate.');
    }
    this.selectedManifestPath = compatible[0].path;
    return compatible[0].path;
  }

  async getManifest() {
    const candidate = await this.discoverManifest();
    this.selectedManifestPath = candidate;
    return this.readManifest(candidate);
  }

  async acquire({ manifest }) {
    const manifestPath = this.selectedManifestPath || await this.discoverManifest();
    const directory = path.dirname(manifestPath);
    const archivePath = path.resolve(directory, manifest.archiveFile);
    if (!isWithin(directory, archivePath)) {
      throw artifactError('MANAGED_RUNTIME_ARTIFACT_UNSAFE', 'Runtime archive resolves outside its manifest directory.');
    }
    let stats;
    try {
      stats = await fs.promises.stat(archivePath);
    } catch (error) {
      if (error.code === 'ENOENT') {
        throw artifactError('MANAGED_RUNTIME_ARTIFACT_UNAVAILABLE', 'The runtime archive referenced by the manifest is missing.');
      }
      throw error;
    }
    if (!stats.isFile() || stats.size !== manifest.archiveSize) {
      throw artifactError('MANAGED_RUNTIME_ARTIFACT_INVALID', 'Runtime archive size does not match its manifest.');
    }
    return Object.freeze({ archivePath });
  }

  async inspectArchive(archivePath) {
    const options = { windowsHide: true, timeout: 60_000, maxBuffer: 16 * 1024 * 1024, encoding: 'utf8' };
    const [verbose, names] = await Promise.all([
      this.runCommand('tar', ['-tvzf', archivePath], options),
      this.runCommand('tar', ['-tzf', archivePath], options),
    ]);
    const typeLines = String(verbose.stdout || '').split(/\r?\n/).filter(Boolean);
    const entries = String(names.stdout || '').split(/\r?\n/).filter(Boolean).map(normalizeArchiveEntry);
    if (entries.length === 0 || typeLines.length !== entries.length || typeLines.some((line) => line[0] !== '-')) {
      throw artifactError('MANAGED_RUNTIME_ARCHIVE_CONTENT_UNSAFE', 'Runtime archives may contain regular files only.');
    }
    if (new Set(entries).size !== entries.length) {
      throw artifactError('MANAGED_RUNTIME_ARCHIVE_CONTENT_UNSAFE', 'Runtime archive contains duplicate paths.');
    }
    return entries;
  }

  async extract({ archivePath, destination, signal }) {
    await this.inspectArchive(archivePath);
    if (signal?.aborted) throw artifactError('MANAGED_RUNTIME_CANCELLED', 'Managed runtime extraction was cancelled.');
    await this.runCommand('tar', [
      '-xzf', archivePath,
      '-C', destination,
      '--no-same-owner',
      '--no-same-permissions',
    ], { windowsHide: true, timeout: 10 * 60_000, signal });
  }
}

module.exports = { LocalRuntimeArtifactAdapter, normalizeArchiveEntry };
