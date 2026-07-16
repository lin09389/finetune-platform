'use strict';

const path = require('node:path');

const MANAGED_RUNTIME_MANIFEST_VERSION = 1;
const REQUIRED_PYTHON_RANGE = '>=3.11,<3.12';
const SUPPORTED_PLATFORMS = new Set(['win32']);
const SUPPORTED_ARCHITECTURES = new Set(['x64']);
const FIELDS = new Set([
  'schemaVersion',
  'profile',
  'version',
  'platform',
  'arch',
  'python',
  'archiveSha256',
  'unpackedSha256',
  'entrypoint',
]);

class ManagedRuntimeManifestError extends Error {
  constructor(code, message) {
    super(message);
    this.name = 'ManagedRuntimeManifestError';
    this.code = code;
  }
}

function fail(code, message) {
  throw new ManagedRuntimeManifestError(code, message);
}

function requireString(value, field) {
  if (typeof value !== 'string' || value.length === 0) {
    fail('MANAGED_RUNTIME_MANIFEST_INVALID', `${field} must be a non-empty string.`);
  }
  return value;
}

function validateEntrypoint(entrypoint) {
  requireString(entrypoint, 'entrypoint');
  const normalized = entrypoint.replace(/\\/g, '/');
  if (
    path.posix.isAbsolute(normalized)
    || normalized.split('/').some((segment) => segment === '' || segment === '.' || segment === '..')
  ) {
    fail('MANAGED_RUNTIME_MANIFEST_ENTRYPOINT_UNSAFE', 'entrypoint must be a relative path inside the runtime.');
  }
  return normalized;
}

function validateTarget(target) {
  if (!target || typeof target !== 'object' || Array.isArray(target)) {
    fail('MANAGED_RUNTIME_MANIFEST_TARGET_INVALID', 'target must describe a runtime platform, architecture, and profile.');
  }
  const platform = requireString(target.platform, 'target.platform');
  const arch = requireString(target.arch, 'target.arch');
  const profile = requireString(target.profile, 'target.profile');
  return { platform, arch, profile };
}

function validateManagedRuntimeManifest(input, target) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) {
    fail('MANAGED_RUNTIME_MANIFEST_INVALID', 'manifest must be an object.');
  }
  for (const field of Object.keys(input)) {
    if (!FIELDS.has(field)) fail('MANAGED_RUNTIME_MANIFEST_UNKNOWN_FIELD', `Unknown manifest field: ${field}.`);
  }
  for (const field of FIELDS) {
    if (!Object.hasOwn(input, field)) fail('MANAGED_RUNTIME_MANIFEST_INVALID', `Missing manifest field: ${field}.`);
  }
  if (input.schemaVersion !== MANAGED_RUNTIME_MANIFEST_VERSION) {
    fail('MANAGED_RUNTIME_MANIFEST_SCHEMA_UNSUPPORTED', 'Unsupported managed runtime manifest schema version.');
  }

  const normalizedTarget = validateTarget(target);
  const profile = requireString(input.profile, 'profile');
  const version = requireString(input.version, 'version');
  const platform = requireString(input.platform, 'platform');
  const arch = requireString(input.arch, 'arch');
  const python = requireString(input.python, 'python');
  const archiveSha256 = requireString(input.archiveSha256, 'archiveSha256').toLowerCase();
  const unpackedSha256 = requireString(input.unpackedSha256, 'unpackedSha256').toLowerCase();
  const entrypoint = validateEntrypoint(input.entrypoint);

  if (!/^[a-z][a-z0-9-]*$/.test(profile) || !/^[0-9A-Za-z][0-9A-Za-z._+-]*$/.test(version)) {
    fail('MANAGED_RUNTIME_MANIFEST_INVALID', 'profile or version has an invalid format.');
  }
  if (!SUPPORTED_PLATFORMS.has(platform) || platform !== normalizedTarget.platform) {
    fail('MANAGED_RUNTIME_MANIFEST_PLATFORM_UNSUPPORTED', `Runtime platform is not supported: ${platform}.`);
  }
  if (!SUPPORTED_ARCHITECTURES.has(arch) || arch !== normalizedTarget.arch) {
    fail('MANAGED_RUNTIME_MANIFEST_ARCH_UNSUPPORTED', `Runtime architecture is not supported: ${arch}.`);
  }
  if (profile !== normalizedTarget.profile) {
    fail('MANAGED_RUNTIME_MANIFEST_PROFILE_UNSUPPORTED', `Runtime profile does not match target: ${profile}.`);
  }
  if (python !== REQUIRED_PYTHON_RANGE) {
    fail('MANAGED_RUNTIME_MANIFEST_PYTHON_INCOMPATIBLE', 'Runtime Python must be >=3.11,<3.12.');
  }
  if (!/^[a-f0-9]{64}$/.test(archiveSha256) || !/^[a-f0-9]{64}$/.test(unpackedSha256)) {
    fail('MANAGED_RUNTIME_MANIFEST_DIGEST_INVALID', 'Runtime digests must be lowercase SHA-256 values.');
  }

  return Object.freeze({
    schemaVersion: MANAGED_RUNTIME_MANIFEST_VERSION,
    profile,
    version,
    platform,
    arch,
    python,
    archiveSha256,
    unpackedSha256,
    entrypoint,
  });
}

module.exports = {
  MANAGED_RUNTIME_MANIFEST_VERSION,
  REQUIRED_PYTHON_RANGE,
  ManagedRuntimeManifestError,
  validateManagedRuntimeManifest,
};
