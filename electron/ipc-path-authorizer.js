'use strict';

const fs = require('node:fs');
const path = require('node:path');

class IpcPathAuthorizer {
  constructor({ platform = process.platform, realpath = fs.promises.realpath, storePath = null } = {}) {
    this.platform = platform;
    this.realpath = realpath;
    this.storePath = storePath;
    this.files = new Set();
    this.directories = new Map();
  }

  key(value) {
    const normalized = path.normalize(value);
    return this.platform === 'win32' ? normalized.toLowerCase() : normalized;
  }

  async canonical(value) {
    if (typeof value !== 'string' || !path.isAbsolute(value)) {
      throw Object.assign(new Error('An absolute selected path is required.'), { code: 'PATH_NOT_ABSOLUTE' });
    }
    return path.resolve(await this.realpath(value));
  }

  async grantSelectedFile(value) {
    const canonical = await this.canonical(value);
    this.files.add(this.key(canonical));
    return canonical;
  }

  async grantSelectedDirectory(value, { persist = true } = {}) {
    const canonical = await this.canonical(value);
    this.directories.set(this.key(canonical), canonical);
    if (persist) await this.persistDirectories();
    return canonical;
  }

  async registerWorkspace(value) {
    return this.grantSelectedDirectory(value, { persist: false });
  }

  async loadPersistedDirectories() {
    if (!this.storePath) return;
    let values;
    try {
      values = JSON.parse(await fs.promises.readFile(this.storePath, 'utf8'));
    } catch (error) {
      if (error.code === 'ENOENT') return;
      throw error;
    }
    if (!Array.isArray(values)) throw new Error('Desktop path authorization store is invalid.');
    for (const value of values) {
      try {
        const canonical = await this.canonical(value);
        this.directories.set(this.key(canonical), canonical);
      } catch (_error) {
        // Missing directories are dropped when the store is next updated.
      }
    }
  }

  async persistDirectories() {
    if (!this.storePath) return;
    const temporary = `${this.storePath}.${process.pid}.tmp`;
    await fs.promises.mkdir(path.dirname(this.storePath), { recursive: true });
    await fs.promises.writeFile(temporary, JSON.stringify([...this.directories.values()]), {
      encoding: 'utf8',
      mode: 0o600,
    });
    await fs.promises.rename(temporary, this.storePath);
  }

  async assertReadableFile(value) {
    const canonical = await this.canonical(value);
    if (!this.files.has(this.key(canonical))) {
      throw Object.assign(new Error('File access was not granted by the system picker.'), {
        code: 'FILE_ACCESS_DENIED',
      });
    }
    return canonical;
  }

  revokeFile(value) {
    if (typeof value === 'string') this.files.delete(this.key(path.resolve(value)));
  }

  async assertOpenableDirectory(value) {
    const canonical = await this.canonical(value);
    if (!this.directories.has(this.key(canonical))) {
      throw Object.assign(new Error('Directory is not a selected or registered workspace.'), {
        code: 'DIRECTORY_ACCESS_DENIED',
      });
    }
    return canonical;
  }
}

module.exports = { IpcPathAuthorizer };
