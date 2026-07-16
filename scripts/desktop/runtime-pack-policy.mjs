import crypto from 'node:crypto';
import path from 'node:path';

export const RUNTIME_PACK_MANIFEST_VERSION = 1;
export const COMPLETED_MARKER = '.finetune-runtime-complete';
export const BASE_RUNTIME_PROFILES = Object.freeze(['base', 'training-gpu']);

const MUTABLE_SEGMENTS = new Set([
  'data', 'models', 'datasets', 'outputs', 'workspaces', 'cache', 'caches', 'logs',
  'uploads', 'backups', 'scratch', 'tmp', 'temp', 'modelscope_cache', 'chroma', 'chromadb',
]);
const DEVELOPER_ROOTS = new Set(['.git', '.venv', 'venv', 'env', '.vscode', '.idea']);
const BASE_HEAVY_SEGMENTS = new Set(['torch', 'torchvision', 'torchaudio', 'cuda', 'nvidia', 'triton', 'deepspeed']);

function policyError(code, message) {
  return Object.assign(new Error(message), { code });
}

function bytewiseSort(left, right) {
  return Buffer.compare(Buffer.from(left, 'utf8'), Buffer.from(right, 'utf8'));
}

export function normalizePackPath(value) {
  if (typeof value !== 'string' || value.length === 0 || value.includes('\0')) {
    throw policyError('RUNTIME_PACK_INVALID_PATH', 'Runtime pack file paths must be non-empty strings.');
  }
  const normalized = value.replaceAll('\\', '/');
  if (path.posix.isAbsolute(normalized) || normalized.split('/').some((part) => part === '' || part === '.' || part === '..')) {
    throw policyError('RUNTIME_PACK_INVALID_PATH', `Runtime pack file path is unsafe: ${value}`);
  }
  return normalized;
}

export function assertSupportedPythonVersion(value) {
  if (typeof value !== 'string' || !/^3\.11\.\d+$/.test(value)) {
    throw policyError('RUNTIME_PACK_PYTHON_VERSION', 'Desktop runtime packs require Python >=3.11,<3.12.');
  }
  return value;
}

function assertProfile(profile) {
  if (!BASE_RUNTIME_PROFILES.includes(profile)) {
    throw policyError('RUNTIME_PACK_PROFILE', `Unsupported runtime pack profile: ${profile}`);
  }
}

function assertSafeRuntimeFile(filePath, profile) {
  const parts = filePath.toLowerCase().split('/');
  const filename = parts.at(-1);
  // A prepared CPython runtime legitimately contains paths such as Lib/venv and
  // package-owned data directories. Only top-level mutable/development roots are
  // product state, rather than Python implementation files.
  if (MUTABLE_SEGMENTS.has(parts[0])
    || DEVELOPER_ROOTS.has(parts[0])
    || filename === '.env'
    || filename.startsWith('.env.')
    || /\.(db|sqlite|sqlite3|safetensors|ckpt|h5|bin|pt|pth|gguf|onnx)$/i.test(filename)
    || /(^|[-_.])(secret|credential|private|api[-_.]?key)([-_.]|$)/i.test(filename)) {
    throw policyError('RUNTIME_PACK_FORBIDDEN_FILE', `Runtime pack includes forbidden mutable or secret file: ${filePath}`);
  }
  if (profile === 'base' && parts.some((part) => BASE_HEAVY_SEGMENTS.has(part))) {
    throw policyError('RUNTIME_PACK_FORBIDDEN_FILE', `Base runtime pack must not include GPU/training dependency: ${filePath}`);
  }
}

function expectedEntrypoint(platform) {
  return platform === 'win32' ? 'python.exe' : 'bin/python3';
}

export function inspectRuntimeFiles(files, { profile, platform }) {
  assertProfile(profile);
  if (!['win32', 'darwin', 'linux'].includes(platform)) {
    throw policyError('RUNTIME_PACK_PLATFORM', `Unsupported runtime pack platform: ${platform}`);
  }
  if (!Array.isArray(files) || files.length === 0) {
    throw policyError('RUNTIME_PACK_EMPTY', 'A runtime pack must contain prepared runtime files.');
  }

  const seen = new Set();
  const normalizedFiles = files.map((file) => {
    const filePath = normalizePackPath(file.path);
    if (seen.has(filePath)) throw policyError('RUNTIME_PACK_DUPLICATE_PATH', `Duplicate runtime pack file: ${filePath}`);
    seen.add(filePath);
    assertSafeRuntimeFile(filePath, profile);
    if (!Buffer.isBuffer(file.content)) {
      throw policyError('RUNTIME_PACK_INVALID_FILE', `Runtime pack file content must be a Buffer: ${filePath}`);
    }
    return Object.freeze({ path: filePath, content: file.content, mode: file.mode ?? 0o644 });
  }).sort((left, right) => bytewiseSort(left.path, right.path));

  const entrypoint = expectedEntrypoint(platform);
  if (!seen.has(entrypoint)) {
    throw policyError('RUNTIME_PACK_ENTRYPOINT_MISSING', `Runtime pack is missing ${entrypoint}.`);
  }

  const digest = crypto.createHash('sha256');
  for (const file of normalizedFiles) {
    digest.update(file.path, 'utf8');
    digest.update('\0');
    digest.update(crypto.createHash('sha256').update(file.content).digest());
  }
  return Object.freeze({
    files: Object.freeze(normalizedFiles),
    entrypoint,
    unpackedSha256: digest.digest('hex'),
  });
}

export function createRuntimeManifest({
  profile, version, platform, architecture, pythonVersion, archiveFile, archiveSha256, archiveSize, unpackedSha256,
}) {
  assertProfile(profile);
  assertSupportedPythonVersion(pythonVersion);
  if (typeof version !== 'string' || !/^[0-9A-Za-z][0-9A-Za-z._-]*$/.test(version)) {
    throw policyError('RUNTIME_PACK_VERSION', 'Runtime pack version must be a safe non-empty identifier.');
  }
  if (!['win32', 'darwin', 'linux'].includes(platform) || !['x64', 'arm64'].includes(architecture)) {
    throw policyError('RUNTIME_PACK_TARGET', 'Runtime pack target is not supported.');
  }
  if (normalizePackPath(archiveFile) !== archiveFile || !archiveFile.endsWith('.tar.gz')) {
    throw policyError('RUNTIME_PACK_ARCHIVE_NAME', 'Runtime pack archive name must be a relative .tar.gz file.');
  }
  if (!/^[a-f0-9]{64}$/.test(archiveSha256) || !/^[a-f0-9]{64}$/.test(unpackedSha256) || !Number.isSafeInteger(archiveSize) || archiveSize < 1) {
    throw policyError('RUNTIME_PACK_DIGEST', 'Runtime pack digests and archive size are invalid.');
  }
  return Object.freeze({
    schemaVersion: RUNTIME_PACK_MANIFEST_VERSION,
    profile,
    version,
    platform,
    architecture,
    python: Object.freeze({ requires: '>=3.11,<3.12', version: pythonVersion }),
    archive: Object.freeze({ file: archiveFile, sha256: archiveSha256, size: archiveSize }),
    unpackedSha256,
    entrypoint: expectedEntrypoint(platform),
    completedMarker: COMPLETED_MARKER,
  });
}
