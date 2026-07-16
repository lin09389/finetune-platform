'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { execFile } = require('node:child_process');
const { promisify } = require('node:util');

const execFileAsync = promisify(execFile);
const VERSION_SCRIPT = [
  'import json, sys',
  'print(json.dumps({"major": sys.version_info.major, "minor": sys.version_info.minor, "patch": sys.version_info.micro, "executable": sys.executable}))',
].join('; ');

function healthyManagedRuntimeCandidate(managedRuntime) {
  if (!managedRuntime || managedRuntime.health?.status !== 'healthy'
    || typeof managedRuntime.executablePath !== 'string' || !path.isAbsolute(managedRuntime.executablePath)
    || !/^3\.11\.\d+$/.test(managedRuntime.health.pythonVersion || '')) {
    return null;
  }
  return {
    source: 'managed-runtime',
    command: managedRuntime.executablePath,
    prefixArgs: [],
    runtimeVersion: managedRuntime.version || null,
  };
}

function pythonCandidates({ explicitPython, projectRoot, managedRuntime, platform = process.platform }) {
  const windows = platform === 'win32';
  const candidates = [];
  if (explicitPython) {
    candidates.push({ source: 'explicit', command: explicitPython, prefixArgs: [] });
  }

  candidates.push({
    source: 'project-venv',
    command: path.join(projectRoot, '.venv', windows ? 'Scripts/python.exe' : 'bin/python'),
    prefixArgs: [],
  });

  const managedCandidate = healthyManagedRuntimeCandidate(managedRuntime);
  if (managedCandidate) candidates.push(managedCandidate);

  if (windows) {
    candidates.push({ source: 'system', command: 'py', prefixArgs: ['-3.11'] });
    candidates.push({ source: 'system', command: 'python', prefixArgs: [] });
  } else {
    candidates.push({ source: 'system', command: 'python3.11', prefixArgs: [] });
    candidates.push({ source: 'system', command: 'python3', prefixArgs: [] });
  }
  return candidates;
}

function isPathLike(command) {
  return path.isAbsolute(command) || command.includes('/') || command.includes('\\');
}

async function defaultProbe(candidate) {
  if (isPathLike(candidate.command)) {
    await fs.promises.access(candidate.command, fs.constants.X_OK);
  }
  const result = await execFileAsync(
    candidate.command,
    [...candidate.prefixArgs, '-c', VERSION_SCRIPT],
    { windowsHide: true, timeout: 5_000, encoding: 'utf8' },
  );
  return JSON.parse(result.stdout.trim());
}

async function resolvePython(options, probe = defaultProbe) {
  const diagnostics = [];
  for (const candidate of pythonCandidates(options)) {
    try {
      const version = await probe(candidate);
      if (version.major !== 3 || version.minor !== 11) {
        diagnostics.push({
          source: candidate.source,
          command: candidate.command,
          status: 'incompatible',
          version: `${version.major}.${version.minor}.${version.patch ?? 0}`,
        });
        continue;
      }
      return Object.freeze({
        ...candidate,
        executable: version.executable || candidate.command,
        version: `${version.major}.${version.minor}.${version.patch ?? 0}`,
        diagnostics: Object.freeze(diagnostics),
      });
    } catch (error) {
      diagnostics.push({
        source: candidate.source,
        command: candidate.command,
        status: 'unavailable',
        error: error.code || error.message,
      });
    }
  }

  const error = new Error('No compatible Python runtime found; Python >=3.11,<3.12 is required.');
  error.code = 'PYTHON_311_NOT_FOUND';
  error.diagnostics = diagnostics;
  throw error;
}

module.exports = { VERSION_SCRIPT, healthyManagedRuntimeCandidate, pythonCandidates, resolvePython, defaultProbe };
