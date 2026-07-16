import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const REQUIRED_PATHS = Object.freeze([
  'electron/main.js',
  'electron/preload.js',
  'client/dist/index.html',
  'server/main.py',
  'package.json',
]);
const MUTABLE_SEGMENTS = new Set([
  'data', 'models', 'datasets', 'outputs', 'workspaces', 'cache', 'caches', 'logs', 'uploads', 'backups',
  'modelscope_cache', 'chroma', 'chromadb',
]);
const DEVELOPER_SEGMENTS = new Set(['.git', '.venv', 'venv', 'env', '.vscode', '.idea', '.pytest_cache', 'test', 'tests', '__pycache__']);

function policyError(code, message) {
  return Object.assign(new Error(message), { code });
}

function normalizePackagePath(value) {
  if (typeof value !== 'string' || value.length === 0 || value.includes('\0')) {
    throw policyError('PACKAGE_POLICY_INVALID_PATH', 'Package file paths must be non-empty strings.');
  }
  const normalized = value.replaceAll('\\', '/').replace(/^\.\//, '');
  if (path.posix.isAbsolute(normalized) || normalized.split('/').some((part) => part === '' || part === '.' || part === '..')) {
    throw policyError('PACKAGE_POLICY_INVALID_PATH', `Package file path is unsafe: ${value}`);
  }
  return normalized;
}

function isDatasetPackageMarker(filePath) {
  return filePath === 'server/datasets/__init__.py';
}

function isForbidden(filePath) {
  const lower = filePath.toLowerCase();
  const parts = lower.split('/');
  const filename = parts.at(-1);
  return (!isDatasetPackageMarker(filePath) && parts.some((part) => MUTABLE_SEGMENTS.has(part)))
    || parts.some((part) => DEVELOPER_SEGMENTS.has(part))
    || filename === '.env'
    || filename.startsWith('.env.')
    || /\.(db|db-shm|db-wal|sqlite|sqlite3|safetensors|ckpt|h5|bin|pt|pth|gguf|onnx)$/i.test(filename)
    || /(^|[-_.])(secret|credential|private|api[-_.]?key)([-_.]|$)/i.test(filename);
}

function sortPaths(left, right) {
  return Buffer.compare(Buffer.from(left, 'utf8'), Buffer.from(right, 'utf8'));
}

export function inspectPackageFiles(files) {
  if (!Array.isArray(files)) throw policyError('PACKAGE_POLICY_FILE_LIST', 'Package inspection requires a file list.');
  const normalized = [...new Set(files.map(normalizePackagePath))].sort(sortPaths);
  for (const filePath of normalized) {
    if (isForbidden(filePath)) throw policyError('PACKAGE_POLICY_FORBIDDEN_FILE', `Package includes forbidden mutable or development file: ${filePath}`);
  }
  for (const required of REQUIRED_PATHS) {
    if (!normalized.includes(required)) throw policyError('PACKAGE_POLICY_REQUIRED_FILE_MISSING', `Package is missing required application file: ${required}`);
  }
  return Object.freeze({ files: Object.freeze(normalized) });
}

export async function collectPackageFiles(root) {
  const absoluteRoot = path.resolve(root);
  const files = [];
  async function walk(current = '') {
    const entries = await fs.readdir(path.join(absoluteRoot, current), { withFileTypes: true });
    entries.sort((left, right) => sortPaths(left.name, right.name));
    for (const entry of entries) {
      const relative = current ? `${current}/${entry.name}` : entry.name;
      if (entry.isDirectory()) await walk(relative);
      else if (entry.isFile()) files.push(relative);
    }
  }
  await walk();
  return files;
}

function parseArgs(argv) {
  if (argv.length !== 2 || !['--file-list', '--unpacked-dir'].includes(argv[0])) {
    throw new Error('Usage: node scripts/desktop/inspect-package.mjs --file-list <json-file> | --unpacked-dir <directory>');
  }
  return { mode: argv[0], value: argv[1] };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const files = args.mode === '--file-list'
    ? JSON.parse(await fs.readFile(path.resolve(args.value), 'utf8'))
    : await collectPackageFiles(args.value);
  const result = inspectPackageFiles(files);
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url))) {
  main().catch((error) => {
    process.stderr.write(`${error.code ? `${error.code}: ` : ''}${error.message}\n`);
    process.exitCode = 1;
  });
}
