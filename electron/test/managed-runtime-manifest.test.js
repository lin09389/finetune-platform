'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');

const {
  MANAGED_RUNTIME_MANIFEST_VERSION,
  validateManagedRuntimeManifest,
} = require('../managed-runtime-manifest');

const DIGEST = 'a'.repeat(64);
const TARGET = Object.freeze({ platform: 'win32', arch: 'x64', profile: 'base' });

function validManifest(overrides = {}) {
  return {
    schemaVersion: MANAGED_RUNTIME_MANIFEST_VERSION,
    profile: 'base',
    version: '3.11.9-base.1',
    platform: 'win32',
    arch: 'x64',
    python: '>=3.11,<3.12',
    archiveFile: 'base-runtime.tar.gz',
    archiveSha256: DIGEST,
    archiveSize: 1024,
    unpackedSha256: DIGEST,
    entrypoint: 'python.exe',
    ...overrides,
  };
}

test('normalizes and freezes a compatible base runtime manifest', () => {
  const manifest = validateManagedRuntimeManifest(validManifest(), TARGET);
  assert.deepEqual(manifest, validManifest());
  assert.ok(Object.isFrozen(manifest));
  assert.throws(() => { manifest.version = 'changed'; }, TypeError);
});

test('manifest validation rejects unknown schema versions and unknown fields', () => {
  assert.throws(
    () => validateManagedRuntimeManifest(validManifest({ schemaVersion: 2 }), TARGET),
    (error) => error.code === 'MANAGED_RUNTIME_MANIFEST_SCHEMA_UNSUPPORTED',
  );
  assert.throws(
    () => validateManagedRuntimeManifest(validManifest({ unexpected: true }), TARGET),
    (error) => error.code === 'MANAGED_RUNTIME_MANIFEST_UNKNOWN_FIELD',
  );
});

test('manifest validation rejects unsafe entrypoints and incompatible targets', () => {
  assert.throws(
    () => validateManagedRuntimeManifest(validManifest({ entrypoint: '../python.exe' }), TARGET),
    (error) => error.code === 'MANAGED_RUNTIME_MANIFEST_ENTRYPOINT_UNSAFE',
  );
  assert.throws(
    () => validateManagedRuntimeManifest(validManifest({ platform: 'linux' }), TARGET),
    (error) => error.code === 'MANAGED_RUNTIME_MANIFEST_PLATFORM_UNSUPPORTED',
  );
  assert.throws(
    () => validateManagedRuntimeManifest(validManifest({ arch: 'arm64' }), TARGET),
    (error) => error.code === 'MANAGED_RUNTIME_MANIFEST_ARCH_UNSUPPORTED',
  );
});

test('manifest validation rejects incompatible Python constraints and malformed digests', () => {
  assert.throws(
    () => validateManagedRuntimeManifest(validManifest({ python: '>=3.12,<3.13' }), TARGET),
    (error) => error.code === 'MANAGED_RUNTIME_MANIFEST_PYTHON_INCOMPATIBLE',
  );
  assert.throws(
    () => validateManagedRuntimeManifest(validManifest({ archiveSha256: 'not-a-digest' }), TARGET),
    (error) => error.code === 'MANAGED_RUNTIME_MANIFEST_DIGEST_INVALID',
  );
  assert.throws(
    () => validateManagedRuntimeManifest(validManifest({ archiveFile: '../runtime.tar.gz' }), TARGET),
    (error) => error.code === 'MANAGED_RUNTIME_MANIFEST_ENTRYPOINT_UNSAFE',
  );
});
