'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');

const { ManagedRuntimeStore } = require('../managed-runtime-store');

function manifest(version = '3.11.9-base.1') {
  return {
    schemaVersion: 1,
    profile: 'base',
    version,
    platform: 'win32',
    arch: 'x64',
    python: '>=3.11,<3.12',
    archiveFile: 'base-runtime.tar.gz',
    archiveSha256: 'a'.repeat(64),
    archiveSize: 1024,
    unpackedSha256: 'b'.repeat(64),
    entrypoint: 'python.exe',
  };
}

function temporaryStore(context) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'finetune-managed-runtime-'));
  context.after(() => fs.rmSync(root, { recursive: true, force: true }));
  return new ManagedRuntimeStore({ root });
}

async function completeAndCommit(store, operationId, runtimeManifest) {
  const stagingPath = await store.createStaging(operationId);
  await fs.promises.writeFile(path.join(stagingPath, runtimeManifest.entrypoint), 'runtime');
  await store.markStagingComplete(stagingPath, runtimeManifest);
  return store.commitStaging(stagingPath, runtimeManifest);
}

test('store creates only managed layout directories and writes an immutable completion marker', async (context) => {
  const store = temporaryStore(context);
  await store.ensureLayout();
  for (const directory of [store.stagingRoot, store.versionsRoot, store.quarantineRoot]) {
    assert.equal(fs.statSync(directory).isDirectory(), true);
  }

  const stagingPath = await store.createStaging('prepare-1');
  await store.markStagingComplete(stagingPath, manifest());
  const marker = await store.readCompletionMarker(stagingPath);
  assert.equal(marker.version, '3.11.9-base.1');
  assert.ok(marker.completedAt);
  await assert.rejects(store.markStagingComplete(stagingPath, manifest()), { code: 'EEXIST' });
});

test('activation records are atomically replaced and preserve the previous healthy version until activation', async (context) => {
  const store = temporaryStore(context);
  const first = manifest('3.11.9-base.1');
  const second = manifest('3.11.10-base.1');
  await completeAndCommit(store, 'prepare-first', first);
  await store.activate(first, { pythonVersion: '3.11.9', checkedAt: '2026-07-16T00:00:00.000Z' });
  const before = await store.readActive('base');

  await completeAndCommit(store, 'prepare-second', second);
  assert.deepEqual(await store.readActive('base'), before);
  await store.activate(second, { pythonVersion: '3.11.10', checkedAt: '2026-07-16T00:01:00.000Z' });
  const active = await store.readActive('base');
  assert.equal(active.version, second.version);
  assert.equal(active.health.status, 'healthy');
  assert.equal(fs.existsSync(`${store.activePath}.tmp`), false);
});

test('store detects incomplete stale staging and refuses paths outside the managed root', async (context) => {
  const store = temporaryStore(context);
  const stalePath = await store.createStaging('interrupted-prepare');
  const staleTime = new Date(Date.now() - 10_000);
  fs.utimesSync(stalePath, staleTime, staleTime);
  const stale = await store.listStaleStaging({ olderThanMs: 1_000 });
  assert.deepEqual(stale.map((entry) => entry.operationId), ['interrupted-prepare']);

  assert.throws(() => store.versionPath('base', '../escape'), { code: 'MANAGED_RUNTIME_PATH_UNSAFE' });
  assert.throws(() => store.assertManagedPath(path.resolve(store.root, '..', 'escape')), { code: 'MANAGED_RUNTIME_PATH_UNSAFE' });
});

test('corrupt activation records never resolve as healthy managed runtimes', async (context) => {
  const store = temporaryStore(context);
  await store.ensureLayout();
  await fs.promises.writeFile(store.activePath, JSON.stringify({
    schemaVersion: 1,
    profile: 'base',
    version: '../escape',
    entrypoint: 'python.exe',
    health: { status: 'healthy' },
  }));
  assert.equal(await store.readActive('base'), null);
});
