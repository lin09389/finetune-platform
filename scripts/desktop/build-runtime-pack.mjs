import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { gzipSync } from 'node:zlib';
import { createRuntimeManifest, inspectRuntimeFiles } from './runtime-pack-policy.mjs';

function usage() {
  return 'Usage: node scripts/desktop/build-runtime-pack.mjs --runtime-dir <prepared-python-dir> --output-dir <artifact-dir> --profile <base|training-gpu> --version <version> --platform <win32|darwin|linux> --architecture <x64|arm64> --python-version <3.11.x>';
}

function parseArgs(argv) {
  const values = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith('--') || value === undefined || values[key] !== undefined) throw new Error(usage());
    values[key] = value;
  }
  for (const key of ['--runtime-dir', '--output-dir', '--profile', '--version', '--platform', '--architecture', '--python-version']) {
    if (!values[key]) throw new Error(usage());
  }
  return values;
}

function sortPaths(left, right) {
  return Buffer.compare(Buffer.from(left, 'utf8'), Buffer.from(right, 'utf8'));
}

async function collectPreparedRuntime(root, current = '') {
  const directory = path.join(root, current);
  const entries = await fs.readdir(directory, { withFileTypes: true });
  entries.sort((left, right) => sortPaths(left.name, right.name));
  const files = [];
  for (const entry of entries) {
    const relative = current ? `${current}/${entry.name}` : entry.name;
    if (entry.isSymbolicLink()) throw Object.assign(new Error(`Runtime directory must not contain symbolic links: ${relative}`), { code: 'RUNTIME_PACK_SYMLINK' });
    if (entry.isDirectory()) files.push(...await collectPreparedRuntime(root, relative));
    else if (entry.isFile()) {
      const absolute = path.join(root, relative);
      const stat = await fs.stat(absolute);
      files.push({ path: relative, content: await fs.readFile(absolute), mode: stat.mode & 0o777 });
    } else throw Object.assign(new Error(`Runtime directory contains unsupported entry: ${relative}`), { code: 'RUNTIME_PACK_FILE_TYPE' });
  }
  return files;
}

function writeString(buffer, offset, length, value) {
  Buffer.from(value, 'utf8').copy(buffer, offset, 0, Math.min(length, Buffer.byteLength(value)));
}

function writeOctal(buffer, offset, length, value) {
  const text = value.toString(8).padStart(length - 1, '0');
  writeString(buffer, offset, length - 1, text);
  buffer[offset + length - 1] = 0;
}

function splitTarPath(filePath) {
  if (Buffer.byteLength(filePath) <= 100) return { name: filePath, prefix: '' };
  const separator = filePath.lastIndexOf('/', 155);
  if (separator > 0 && Buffer.byteLength(filePath.slice(0, separator)) <= 155 && Buffer.byteLength(filePath.slice(separator + 1)) <= 100) {
    return { prefix: filePath.slice(0, separator), name: filePath.slice(separator + 1) };
  }
  throw Object.assign(new Error(`Runtime pack path is too long for portable tar: ${filePath}`), { code: 'RUNTIME_PACK_TAR_PATH' });
}

function tarHeader(file) {
  const header = Buffer.alloc(512, 0);
  const { name, prefix } = splitTarPath(file.path);
  writeString(header, 0, 100, name);
  writeOctal(header, 100, 8, file.mode & 0o777);
  writeOctal(header, 108, 8, 0);
  writeOctal(header, 116, 8, 0);
  writeOctal(header, 124, 12, file.content.length);
  writeOctal(header, 136, 12, 0);
  header.fill(0x20, 148, 156);
  header[156] = '0'.charCodeAt(0);
  writeString(header, 257, 6, 'ustar');
  writeString(header, 263, 2, '00');
  writeString(header, 265, 32, 'root');
  writeString(header, 297, 32, 'root');
  writeString(header, 329, 8, '0000000');
  writeString(header, 337, 8, '0000000');
  writeString(header, 345, 155, prefix);
  let checksum = 0;
  for (const byte of header) checksum += byte;
  writeOctal(header, 148, 8, checksum);
  return header;
}

function buildDeterministicArchive(files) {
  const chunks = [];
  for (const file of files) {
    chunks.push(tarHeader(file), file.content);
    const remainder = file.content.length % 512;
    if (remainder) chunks.push(Buffer.alloc(512 - remainder, 0));
  }
  chunks.push(Buffer.alloc(1024, 0));
  return gzipSync(Buffer.concat(chunks), { mtime: 0 });
}

export async function buildRuntimePack(options) {
  const runtimeDir = path.resolve(options.runtimeDir);
  const outputDir = path.resolve(options.outputDir);
  const relation = path.relative(runtimeDir, outputDir);
  if (relation === '' || (!relation.startsWith(`..${path.sep}`) && relation !== '..' && !path.isAbsolute(relation))) {
    throw Object.assign(new Error('Artifact output directory must not be inside the prepared runtime directory.'), { code: 'RUNTIME_PACK_OUTPUT_INSIDE_RUNTIME' });
  }
  const stat = await fs.stat(runtimeDir);
  if (!stat.isDirectory()) throw Object.assign(new Error(`Prepared runtime directory does not exist: ${runtimeDir}`), { code: 'RUNTIME_PACK_RUNTIME_DIR' });
  const inspected = inspectRuntimeFiles(await collectPreparedRuntime(runtimeDir), options);
  const archiveName = `${options.profile}-${options.version}-${options.platform}-${options.architecture}.tar.gz`;
  const archive = buildDeterministicArchive(inspected.files);
  const archiveSha256 = crypto.createHash('sha256').update(archive).digest('hex');
  const manifest = createRuntimeManifest({
    ...options,
    archiveFile: archiveName,
    archiveSha256,
    archiveSize: archive.length,
    unpackedSha256: inspected.unpackedSha256,
  });
  await fs.mkdir(outputDir, { recursive: true });
  await fs.writeFile(path.join(outputDir, archiveName), archive, { flag: 'w' });
  const manifestName = `${archiveName}.manifest.json`;
  await fs.writeFile(path.join(outputDir, manifestName), `${JSON.stringify(manifest, null, 2)}\n`, { encoding: 'utf8', flag: 'w' });
  return Object.freeze({ archivePath: path.join(outputDir, archiveName), manifestPath: path.join(outputDir, manifestName), manifest });
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const result = await buildRuntimePack({
    runtimeDir: args['--runtime-dir'], outputDir: args['--output-dir'], profile: args['--profile'], version: args['--version'],
    platform: args['--platform'], architecture: args['--architecture'], pythonVersion: args['--python-version'],
  });
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url))) {
  main().catch((error) => {
    process.stderr.write(`${error.code ? `${error.code}: ` : ''}${error.message}\n`);
    process.exitCode = 1;
  });
}
