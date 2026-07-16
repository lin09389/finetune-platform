'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');

const inspectorPromise = import(pathToFileURL(path.resolve(__dirname, '../../scripts/desktop/inspect-package.mjs')).href);

function pathToFileURL(filePath) {
  return require('node:url').pathToFileURL(filePath);
}

test('package policy accepts the desktop application code and runtime metadata', async () => {
  const { inspectPackageFiles } = await inspectorPromise;
  const result = inspectPackageFiles([
    'electron/main.js',
    'electron/preload.js',
    'client/dist/index.html',
    'server/main.py',
    'package.json',
  ]);
  assert.deepEqual(result.files, [
    'client/dist/index.html',
    'electron/main.js',
    'electron/preload.js',
    'package.json',
    'server/main.py',
  ]);
});

test('package policy rejects mutable data and developer material', async () => {
  const { inspectPackageFiles } = await inspectorPromise;
  for (const filePath of [
    'server/data/app.db',
    'server/data/.inference-service-key',
    'server/models/model.safetensors',
    'server/assets/downloaded-model.gguf',
    'server/datasets/train.jsonl',
    'server/outputs/result.json',
    'server/workspaces/project/.workspace.json',
    'server/modelscope_cache/index.json',
    'server/logs/runtime.log',
    'electron/test/main.test.js',
    '.venv/Scripts/python.exe',
  ]) {
    assert.throws(
      () => inspectPackageFiles(['electron/main.js', 'electron/preload.js', 'client/dist/index.html', 'server/main.py', 'package.json', filePath]),
      (error) => error.code === 'PACKAGE_POLICY_FORBIDDEN_FILE',
      filePath,
    );
  }
});

test('package policy reports missing application components', async () => {
  const { inspectPackageFiles } = await inspectorPromise;
  assert.throws(
    () => inspectPackageFiles(['electron/main.js', 'package.json']),
    (error) => error.code === 'PACKAGE_POLICY_REQUIRED_FILE_MISSING',
  );
});

test('package inspector can collect a supplied unpacked directory', async (t) => {
  const { collectPackageFiles, inspectPackageFiles } = await inspectorPromise;
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'finetune-package-policy-test-'));
  t.after(async () => fs.rm(root, { recursive: true, force: true }));
  for (const filePath of ['electron/main.js', 'electron/preload.js', 'client/dist/index.html', 'server/main.py', 'package.json']) {
    const absolute = path.join(root, filePath);
    await fs.mkdir(path.dirname(absolute), { recursive: true });
    await fs.writeFile(absolute, 'fixture');
  }
  const result = inspectPackageFiles(await collectPackageFiles(root));
  assert.equal(result.files.length, 5);
});
