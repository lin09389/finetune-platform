'use strict';

const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');

const policyPromise = import(pathToFileURL(path.resolve(__dirname, '../../scripts/desktop/runtime-pack-policy.mjs')).href);

function pathToFileURL(filePath) {
  return require('node:url').pathToFileURL(filePath);
}

test('runtime pack policy accepts a deterministic base Python 3.11 layout', async () => {
  const { inspectRuntimeFiles, createRuntimeManifest } = await policyPromise;
  const files = [
    { path: 'Lib/site-packages/fastapi/__init__.py', content: Buffer.from('fastapi') },
    { path: 'Lib/python311.zip', content: Buffer.from('stdlib') },
    { path: 'python.exe', content: Buffer.from('python') },
  ];
  const inspected = inspectRuntimeFiles(files, { profile: 'base', platform: 'win32' });

  assert.deepEqual(inspected.files.map((file) => file.path), [
    'Lib/python311.zip',
    'Lib/site-packages/fastapi/__init__.py',
    'python.exe',
  ]);
  const manifest = createRuntimeManifest({
    profile: 'base',
    version: '2026.07.16',
    platform: 'win32',
    architecture: 'x64',
    pythonVersion: '3.11.9',
    archiveFile: 'base-2026.07.16-win32-x64.tar.gz',
    archiveSha256: crypto.createHash('sha256').update('archive').digest('hex'),
    archiveSize: 7,
    unpackedSha256: inspected.unpackedSha256,
  });

  assert.deepEqual(manifest, {
    schemaVersion: 1,
    profile: 'base',
    version: '2026.07.16',
    platform: 'win32',
    arch: 'x64',
    python: '>=3.11,<3.12',
    archiveFile: 'base-2026.07.16-win32-x64.tar.gz',
    archiveSha256: crypto.createHash('sha256').update('archive').digest('hex'),
    archiveSize: 7,
    unpackedSha256: inspected.unpackedSha256,
    entrypoint: 'python.exe',
  });
});

test('runtime pack policy rejects mutable data, secrets, and CUDA dependencies', async () => {
  const { inspectRuntimeFiles } = await policyPromise;
  for (const filePath of [
    'data/app.db',
    'logs/runtime.log',
    '.env',
    'Lib/site-packages/torch/__init__.py',
  ]) {
    assert.throws(
      () => inspectRuntimeFiles([{ path: 'python.exe', content: Buffer.from('python') }, { path: filePath, content: Buffer.from('x') }], {
        profile: 'base', platform: 'win32',
      }),
      (error) => error.code === 'RUNTIME_PACK_FORBIDDEN_FILE',
      filePath,
    );
  }
});

test('runtime pack policy rejects missing entrypoints and non-3.11 Python versions', async () => {
  const { inspectRuntimeFiles, assertSupportedPythonVersion } = await policyPromise;
  assert.throws(
    () => inspectRuntimeFiles([{ path: 'Lib/python311.zip', content: Buffer.from('stdlib') }], { profile: 'base', platform: 'win32' }),
    (error) => error.code === 'RUNTIME_PACK_ENTRYPOINT_MISSING',
  );
  assert.throws(() => assertSupportedPythonVersion('3.12.0'), (error) => error.code === 'RUNTIME_PACK_PYTHON_VERSION');
  assert.throws(() => assertSupportedPythonVersion('3.10.14'), (error) => error.code === 'RUNTIME_PACK_PYTHON_VERSION');
});

test('runtime pack builder produces byte-identical archives from the same prepared files', async (t) => {
  const { buildRuntimePack } = await import(pathToFileURL(path.resolve(__dirname, '../../scripts/desktop/build-runtime-pack.mjs')).href);
  const temporaryRoot = await fs.mkdtemp(path.join(os.tmpdir(), 'finetune-runtime-pack-test-'));
  t.after(async () => fs.rm(temporaryRoot, { recursive: true, force: true }));
  const runtimeDir = path.join(temporaryRoot, 'runtime');
  await fs.mkdir(path.join(runtimeDir, 'Lib'), { recursive: true });
  await fs.writeFile(path.join(runtimeDir, 'python.exe'), 'python');
  await fs.writeFile(path.join(runtimeDir, 'Lib', 'python311.zip'), 'stdlib');
  const options = {
    runtimeDir,
    profile: 'base',
    version: '2026.07.16',
    platform: 'win32',
    architecture: 'x64',
    pythonVersion: '3.11.9',
  };
  const first = await buildRuntimePack({ ...options, outputDir: path.join(temporaryRoot, 'first') });
  const second = await buildRuntimePack({ ...options, outputDir: path.join(temporaryRoot, 'second') });

  assert.deepEqual(await fs.readFile(first.archivePath), await fs.readFile(second.archivePath));
  assert.equal(first.manifest.archiveSha256, second.manifest.archiveSha256);
  assert.equal(first.manifest.unpackedSha256, second.manifest.unpackedSha256);
});
