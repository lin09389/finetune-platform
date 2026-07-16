'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');
const { VERSION_SCRIPT, pythonCandidates, resolvePython } = require('../python-resolver');

const OPTIONS = {
  explicitPython: 'C:\\configured\\python.exe',
  projectRoot: 'C:\\project',
  managedRuntime: {
    profile: 'base',
    version: '3.11.9-base.1',
    executablePath: 'C:\\managed\\versions\\base\\3.11.9-base.1\\python.exe',
    health: { status: 'healthy', pythonVersion: '3.11.9' },
  },
  platform: 'win32',
};

test('Python candidates preserve explicit, venv, managed, system order', () => {
  assert.doesNotMatch(VERSION_SCRIPT, /[,{}]\s*;/);
  assert.deepEqual(pythonCandidates(OPTIONS).map((candidate) => candidate.source), [
    'explicit',
    'project-venv',
    'managed-runtime',
    'system',
    'system',
  ]);
});

test('resolver only receives a managed candidate from a healthy activation record', () => {
  const unhealthy = {
    ...OPTIONS,
    managedRuntime: { ...OPTIONS.managedRuntime, health: { status: 'failed' } },
  };
  assert.equal(pythonCandidates(unhealthy).some((candidate) => candidate.source === 'managed-runtime'), false);
  assert.equal(pythonCandidates({ ...OPTIONS, managedRuntime: null }).some((candidate) => candidate.source === 'managed-runtime'), false);
});

test('resolver rejects incompatible Python and reports selected 3.11 runtime', async () => {
  const seen = [];
  const selected = await resolvePython(OPTIONS, async (candidate) => {
    seen.push(candidate.source);
    if (candidate.source === 'explicit') return { major: 3, minor: 12, patch: 1 };
    if (candidate.source === 'project-venv') throw Object.assign(new Error('missing'), { code: 'ENOENT' });
    return { major: 3, minor: 11, patch: 9, executable: 'C:\\managed\\python.exe' };
  });
  assert.deepEqual(seen, ['explicit', 'project-venv', 'managed-runtime']);
  assert.equal(selected.source, 'managed-runtime');
  assert.equal(selected.version, '3.11.9');
  assert.equal(selected.diagnostics[0].status, 'incompatible');
});

test('resolver fails closed when no candidate is exactly Python 3.11', async () => {
  await assert.rejects(
    resolvePython(OPTIONS, async () => ({ major: 3, minor: 10, patch: 14 })),
    (error) => error.code === 'PYTHON_311_NOT_FOUND' && error.diagnostics.length === 5,
  );
});
