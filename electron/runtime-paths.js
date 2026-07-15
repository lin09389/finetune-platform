'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

function isWithin(parent, candidate) {
  const relation = path.relative(parent, candidate);
  return relation === '' || (!relation.startsWith(`..${path.sep}`) && relation !== '..' && !path.isAbsolute(relation));
}

function resolveRuntimePaths({ appPath, resourcesPath, userDataPath, isPackaged, env = process.env }) {
  const projectRoot = path.resolve(isPackaged ? resourcesPath : appPath);
  const dataRoot = path.resolve(env.FINETUNE_USER_DATA_ROOT || path.join(userDataPath, 'runtime'));

  // A packaged application must never create mutable user data below its install resources,
  // even when a manually configured environment variable is incorrect.
  if (isPackaged && isWithin(path.resolve(resourcesPath), dataRoot)) {
    throw Object.assign(new Error('FINETUNE_USER_DATA_ROOT must not be inside the packaged application resources.'), {
      code: 'UNSAFE_RUNTIME_DATA_ROOT',
    });
  }

  return Object.freeze({
    projectRoot,
    serverRoot: path.join(projectRoot, 'server'),
    dataRoot,
    databasePath: path.join(dataRoot, 'data', 'app.db'),
    modelsRoot: path.join(dataRoot, 'models'),
    datasetsRoot: path.join(dataRoot, 'datasets'),
    outputsRoot: path.join(dataRoot, 'outputs'),
    logsRoot: path.join(dataRoot, 'logs'),
    workspacesRoot: path.join(dataRoot, 'workspaces'),
    cacheRoot: path.join(dataRoot, 'cache'),
    runtimeRoot: path.join(dataRoot, 'runtimes'),
    internalSecretPath: path.join(dataRoot, 'data', '.inference-service-key'),
    jwtSecretPath: path.join(dataRoot, 'data', '.jwt-secret-key'),
    checkpointDatabasePath: path.join(dataRoot, 'data', 'langgraph-checkpoints.db'),
  });
}

function ensureRuntimeDirectories(paths, fsApi = fs) {
  for (const directory of [
    paths.dataRoot,
    path.dirname(paths.databasePath),
    paths.modelsRoot,
    paths.datasetsRoot,
    paths.outputsRoot,
    paths.logsRoot,
    paths.workspacesRoot,
    paths.cacheRoot,
    paths.runtimeRoot,
  ]) {
    fsApi.mkdirSync(directory, { recursive: true });
  }
}

function getOrCreateSecret(secretPath, fsApi = fs) {
  try {
    const current = fsApi.readFileSync(secretPath, 'utf8').trim();
    if (current.length >= 32) return current;
    throw Object.assign(new Error(`Runtime secret is corrupt: ${path.basename(secretPath)}`), {
      code: 'INVALID_RUNTIME_SECRET',
    });
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }

  const secret = crypto.randomBytes(32).toString('base64url');
  let descriptor;
  try {
    descriptor = fsApi.openSync(secretPath, 'wx', 0o600);
    fsApi.writeFileSync(descriptor, `${secret}\n`, { encoding: 'utf8' });
    fsApi.fsyncSync(descriptor);
    return secret;
  } catch (error) {
    if (error.code === 'EEXIST') {
      const current = fsApi.readFileSync(secretPath, 'utf8').trim();
      if (current.length >= 32) return current;
    }
    throw error;
  } finally {
    if (descriptor !== undefined) fsApi.closeSync(descriptor);
  }
}

function getOrCreateRuntimeSecrets(paths, fsApi = fs) {
  return Object.freeze({
    internalService: getOrCreateSecret(paths.internalSecretPath, fsApi),
    jwt: getOrCreateSecret(paths.jwtSecretPath, fsApi),
  });
}

function buildServiceEnvironment(paths, secrets, baseEnv = process.env) {
  return {
    ...baseEnv,
    HOST: '127.0.0.1',
    PORT: '8010',
    BASE_DIR: paths.dataRoot,
    MODELS_DIR: paths.modelsRoot,
    DATASETS_DIR: paths.datasetsRoot,
    OUTPUTS_DIR: paths.outputsRoot,
    WORKSPACE_ROOT: paths.workspacesRoot,
    MODELSCOPE_CACHE_DIR: path.join(paths.cacheRoot, 'modelscope'),
    FINETUNE_LOG_DIR: paths.logsRoot,
    FINETUNE_USER_DATA_ROOT: paths.dataRoot,
    FINETUNE_PLATFORM_DB_PATH: paths.databasePath,
    LANGGRAPH_CHECKPOINT_DB: paths.checkpointDatabasePath,
    INFERENCE_SERVICE_HOST: '127.0.0.1',
    INFERENCE_SERVICE_PORT: '8020',
    INFERENCE_SERVICE_URL: 'http://127.0.0.1:8020',
    JWT_SECRET_KEY: secrets.jwt,
    INTERNAL_SERVICE_API_KEY: secrets.internalService,
    INFERENCE_INTERNAL_API_KEY: secrets.internalService,
    PYTHONPATH: paths.projectRoot,
    PYTHONIOENCODING: 'utf-8',
    PYTHONUTF8: '1',
    ALLOWED_ORIGINS: JSON.stringify([
      'app://renderer',
      'http://127.0.0.1:5173',
      'http://localhost:5173',
    ]),
  };
}

module.exports = {
  resolveRuntimePaths,
  ensureRuntimeDirectories,
  getOrCreateSecret,
  getOrCreateRuntimeSecrets,
  buildServiceEnvironment,
};
