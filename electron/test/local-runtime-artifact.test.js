'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const { LocalRuntimeArtifactAdapter, normalizeArchiveEntry } = require('../local-runtime-artifact');
const { ManagedRuntimeCoordinator } = require('../managed-runtime-coordinator');
const { ManagedRuntimeStore } = require('../managed-runtime-store');

const DIGEST = 'a'.repeat(64);
const target = { platform: 'win32', arch: 'x64', profile: 'base' };

function manifest(archiveSize) {
  return {
    schemaVersion: 1,
    profile: 'base',
    version: '2026.07.16',
    platform: 'win32',
    arch: 'x64',
    python: '>=3.11,<3.12',
    archiveFile: 'base.tar.gz',
    archiveSha256: DIGEST,
    archiveSize,
    unpackedSha256: DIGEST,
    entrypoint: 'python.exe',
  };
}

test('discovers one compatible manifest and resolves its adjacent archive', async (context) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'finetune-local-pack-'));
  context.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const archive = Buffer.from('runtime');
  fs.writeFileSync(path.join(root, 'base.tar.gz'), archive);
  fs.writeFileSync(path.join(root, 'base.manifest.json'), JSON.stringify(manifest(archive.length)));
  const adapter = new LocalRuntimeArtifactAdapter({ manifestDirectory: root, target });

  const loaded = await adapter.getManifest();
  assert.equal(loaded.arch, 'x64');
  assert.equal((await adapter.acquire({ manifest: loaded })).archivePath, path.join(root, 'base.tar.gz'));
});

test('archive inspection rejects traversal and non-regular entries before extraction', async () => {
  assert.throws(() => normalizeArchiveEntry('../escape'), { code: 'MANAGED_RUNTIME_ARCHIVE_CONTENT_UNSAFE' });
  let calls = 0;
  const runCommand = async (_command, args) => {
    calls += 1;
    if (args[0] === '-tvzf') return { stdout: 'lrwxrwxrwx owner group 0 date link -> ../escape\n' };
    return { stdout: 'link\n' };
  };
  const adapter = new LocalRuntimeArtifactAdapter({ manifestPath: 'C:\\packs\\base.manifest.json', target, runCommand });
  await assert.rejects(adapter.inspectArchive('C:\\packs\\base.tar.gz'), { code: 'MANAGED_RUNTIME_ARCHIVE_CONTENT_UNSAFE' });
  assert.equal(calls, 2);
});

test('extract invokes fixed tar arguments only after safe inspection', async () => {
  const calls = [];
  const runCommand = async (command, args) => {
    calls.push({ command, args });
    if (args[0] === '-tvzf') return { stdout: '-rw-r--r-- owner group 6 date python.exe\n' };
    if (args[0] === '-tzf') return { stdout: 'python.exe\n' };
    return { stdout: '' };
  };
  const adapter = new LocalRuntimeArtifactAdapter({ manifestPath: 'C:\\packs\\base.manifest.json', target, runCommand });
  await adapter.extract({ archivePath: 'C:\\packs\\base.tar.gz', destination: 'C:\\managed\\staging', signal: null });
  assert.deepEqual(calls.at(-1), {
    command: 'tar',
    args: ['-xzf', 'C:\\packs\\base.tar.gz', '-C', 'C:\\managed\\staging', '--no-same-owner', '--no-same-permissions'],
  });
});

test('a runtime pack built by the release script verifies, extracts, and activates', async (context) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'finetune-runtime-pack-integration-'));
  context.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const runtimeDir = path.join(root, 'prepared-runtime');
  await fs.promises.mkdir(path.join(runtimeDir, 'Lib'), { recursive: true });
  await fs.promises.writeFile(path.join(runtimeDir, 'python.exe'), 'synthetic-python');
  await fs.promises.writeFile(path.join(runtimeDir, 'Lib', 'python311.zip'), 'stdlib');
  const { buildRuntimePack } = await import(
    require('node:url').pathToFileURL(path.resolve(__dirname, '../../scripts/desktop/build-runtime-pack.mjs')).href
  );
  const built = await buildRuntimePack({
    runtimeDir,
    outputDir: path.join(root, 'packs'),
    profile: 'base',
    version: '2026.07.16',
    platform: 'win32',
    architecture: 'x64',
    pythonVersion: '3.11.9',
  });
  const adapter = new LocalRuntimeArtifactAdapter({ manifestPath: built.manifestPath, target });
  const store = new ManagedRuntimeStore({ root: path.join(root, 'managed') });
  const coordinator = new ManagedRuntimeCoordinator({
    store,
    target,
    artifactAdapter: adapter,
    probeAdapter: { probe: async () => ({ major: 3, minor: 11, patch: 9 }) },
  });

  const ready = await coordinator.prepareBaseRuntime();
  assert.equal(ready.state, 'ready');
  const active = await store.readActive('base');
  assert.equal(active.version, '2026.07.16');
  assert.equal(fs.existsSync(path.join(active.runtimePath, 'python.exe')), true);
  assert.equal(fs.existsSync(path.join(active.runtimePath, '0000000')), false);
});
