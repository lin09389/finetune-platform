'use strict';

const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');

const { ManagedRuntimeStore } = require('../managed-runtime-store');
const { ManagedRuntimeCoordinator, digestRuntimeDirectory } = require('../managed-runtime-coordinator');

function temporary(context) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'finetune-runtime-coordinator-'));
  context.after(() => fs.rmSync(root, { recursive: true, force: true }));
  return root;
}

async function fixture(context, version = '3.11.9-base.1') {
  const root = temporary(context);
  const archivePath = path.join(root, 'runtime.pack');
  const sourcePath = path.join(root, 'source');
  await fs.promises.mkdir(sourcePath);
  await fs.promises.writeFile(path.join(sourcePath, 'python.exe'), 'synthetic-python');
  await fs.promises.writeFile(archivePath, `archive-${version}`);
  return {
    root,
    archivePath,
    sourcePath,
    manifest: {
      schemaVersion: 1,
      profile: 'base',
      version,
      platform: 'win32',
      arch: 'x64',
      python: '>=3.11,<3.12',
      archiveSha256: crypto.createHash('sha256').update(await fs.promises.readFile(archivePath)).digest('hex'),
      unpackedSha256: await digestRuntimeDirectory(sourcePath),
      entrypoint: 'python.exe',
    },
  };
}

function adapters(fixtureData, probe = async () => ({ major: 3, minor: 11, patch: 9 })) {
  return {
    artifact: {
      acquire: async () => ({ archivePath: fixtureData.archivePath }),
      extract: async ({ destination }) => fs.promises.cp(fixtureData.sourcePath, destination, { recursive: true }),
    },
    probe: { probe },
  };
}

function coordinator(store, fixtureData, options = {}) {
  const injected = adapters(fixtureData, options.probe);
  return new ManagedRuntimeCoordinator({
    store,
    target: { platform: 'win32', arch: 'x64', profile: 'base' },
    artifactAdapter: options.artifact || injected.artifact,
    probeAdapter: options.probeAdapter || injected.probe,
    staleStagingAgeMs: 1,
  });
}

test('prepares, verifies, activates and exposes a ready immutable runtime snapshot', async (context) => {
  const data = await fixture(context);
  const store = new ManagedRuntimeStore({ root: path.join(data.root, 'managed') });
  const lifecycle = coordinator(store, data);

  const result = await lifecycle.prepare(data.manifest);
  assert.equal(result.state, 'ready');
  assert.equal(result.runtimeVersion, data.manifest.version);
  assert.equal(result.pythonVersion, '3.11.9');
  assert.equal((await store.readActive('base')).version, data.manifest.version);
});

test('checksum mismatch never activates staging and enters deterministic repair state', async (context) => {
  const data = await fixture(context);
  const store = new ManagedRuntimeStore({ root: path.join(data.root, 'managed') });
  const lifecycle = coordinator(store, data);
  const invalid = { ...data.manifest, archiveSha256: '0'.repeat(64) };

  await assert.rejects(lifecycle.prepare(invalid), { code: 'MANAGED_RUNTIME_ARCHIVE_DIGEST_MISMATCH' });
  assert.equal((await store.readActive('base')), null);
  assert.equal(lifecycle.getSnapshot().state, 'repair_required');
  assert.equal(lifecycle.getSnapshot().lastErrorCode, 'MANAGED_RUNTIME_ARCHIVE_DIGEST_MISMATCH');
});

test('failed health probe preserves the previous healthy activation and reports recoverable failure', async (context) => {
  const first = await fixture(context, '3.11.9-base.1');
  const second = await fixture(context, '3.11.10-base.1');
  const store = new ManagedRuntimeStore({ root: path.join(first.root, 'managed') });
  await coordinator(store, first).prepare(first.manifest);
  const lifecycle = coordinator(store, second, { probe: async () => { throw Object.assign(new Error('probe failed'), { code: 'PROBE_FAILED' }); } });

  await assert.rejects(lifecycle.repair(second.manifest), { code: 'PROBE_FAILED' });
  assert.equal((await store.readActive('base')).version, first.manifest.version);
  assert.equal(lifecycle.getSnapshot().state, 'failed');
  assert.equal(lifecycle.getSnapshot().recoverable, true);
});

test('deduplicates concurrent prepare calls and quarantines interrupted stale staging', async (context) => {
  const data = await fixture(context);
  const store = new ManagedRuntimeStore({ root: path.join(data.root, 'managed') });
  const stale = await store.createStaging('interrupted');
  const old = new Date(Date.now() - 10_000);
  fs.utimesSync(stale, old, old);
  let releaseAcquire;
  let notifyAcquired;
  const acquired = new Promise((resolve) => { notifyAcquired = resolve; });
  const artifact = {
    acquire: async () => new Promise((resolve) => {
      releaseAcquire = () => resolve({ archivePath: data.archivePath });
      notifyAcquired();
    }),
    extract: async ({ destination }) => fs.promises.cp(data.sourcePath, destination, { recursive: true }),
  };
  const lifecycle = coordinator(store, data, { artifact });

  const first = lifecycle.prepare(data.manifest);
  const second = lifecycle.repair(data.manifest);
  assert.strictEqual(first, second);
  await acquired;
  releaseAcquire();
  await first;
  assert.equal(fs.existsSync(stale), false);
  assert.equal(fs.existsSync(path.join(store.quarantineRoot, 'interrupted.json')), true);
});

test('shutdown cancellation prevents a late activation and leaves prior runtime untouched', async (context) => {
  const data = await fixture(context);
  const store = new ManagedRuntimeStore({ root: path.join(data.root, 'managed') });
  const artifact = {
    acquire: async () => ({ archivePath: data.archivePath }),
    extract: async ({ destination }) => {
      await new Promise((resolve) => setTimeout(resolve, 10));
      await fs.promises.cp(data.sourcePath, destination, { recursive: true });
    },
  };
  const lifecycle = coordinator(store, data, { artifact });
  const pending = lifecycle.prepare(data.manifest);
  lifecycle.beginShutdown();
  await assert.rejects(pending, { code: 'MANAGED_RUNTIME_CANCELLED' });
  assert.equal(await store.readActive('base'), null);
});
