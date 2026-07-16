'use strict';

const { EventEmitter } = require('node:events');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { app, BrowserWindow, ipcMain, dialog, shell, protocol, net } = require('electron');
const { PROTOCOL_VERSION, createServiceDescriptors, publicServiceStatus } = require('./runtime-contract');
const {
  resolveRuntimePaths,
  ensureRuntimeDirectories,
  getOrCreateRuntimeSecrets,
  buildServiceEnvironment,
} = require('./runtime-paths');
const { resolvePython, defaultProbe } = require('./python-resolver');
const { ProcessSupervisor, probeHttp, createTrainingWorkerProbe } = require('./process-supervisor');
const { IpcPathAuthorizer } = require('./ipc-path-authorizer');
const { registerDesktopIpc } = require('./desktop-ipc');
const { resolveRendererAsset } = require('./renderer-protocol');
const { ManagedRuntimeStore } = require('./managed-runtime-store');
const { ManagedRuntimeCoordinator } = require('./managed-runtime-coordinator');
const { LocalRuntimeArtifactAdapter } = require('./local-runtime-artifact');

const DEV_FRONTEND_URL = process.env.ELECTRON_RENDERER_URL || 'http://127.0.0.1:5173';
const isDev = !app.isPackaged;
let mainWindow = null;
let supervisor = null;
// Track A supplies this coordinator. Keeping it optional lets the Phase 10 renderer and
// protocol be independently tested while a development shell continues to start normally.
let managedRuntimeCoordinator = null;
let removeIpcHandlers = null;
let quitting = false;
let rendererRoot = null;

protocol.registerSchemesAsPrivileged([{
  scheme: 'app',
  privileges: {
    standard: true,
    secure: true,
    supportFetchAPI: true,
    corsEnabled: true,
  },
}]);

const hasSingleInstanceLock = app.requestSingleInstanceLock();
if (!hasSingleInstanceLock) app.quit();

class UnavailableSupervisor extends EventEmitter {
  constructor(descriptors, error) {
    super();
    const now = new Date().toISOString();
    this.statuses = descriptors.map((descriptor) => publicServiceStatus({
      id: descriptor.id,
      label: descriptor.label,
      state: 'failed',
      pid: null,
      restarts: 0,
      lastError: error.message,
      updatedAt: now,
    }));
  }

  listStatuses() { return this.statuses; }
  async startAll() { return this.statuses; }
  async stopAll() { return this.statuses; }
  async restartService() {
    throw Object.assign(new Error('No compatible Python 3.11 runtime is available.'), {
      code: 'PYTHON_311_NOT_FOUND',
    });
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1100,
    minHeight: 680,
    show: false,
    title: 'Finetune Platform',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  mainWindow.once('ready-to-show', () => mainWindow?.show());
  mainWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  mainWindow.webContents.on('will-navigate', (event, targetUrl) => {
    if (!isAllowedRendererUrl(targetUrl)) event.preventDefault();
  });
  mainWindow.on('closed', () => { mainWindow = null; });

  if (isDev) {
    void loadDevRendererWithRetry(mainWindow, DEV_FRONTEND_URL);
  } else {
    void mainWindow.loadURL('app://renderer/index.html');
  }
}

async function loadDevRendererWithRetry(window, url, maxRetries = 120, intervalMs = 1_000) {
  await window.loadURL('about:blank');
  for (let attempt = 0; attempt < maxRetries; attempt += 1) {
    if (!window || window.isDestroyed()) return false;
    if (await probeHttp(url, 1_500)) {
      try {
        await window.loadURL(url);
        return true;
      } catch (_error) {
        // The dev renderer may still be replacing its initial listener.
      }
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  return false;
}

function isTrustedRendererEvent(event) {
  if (!mainWindow || mainWindow.isDestroyed() || event.sender !== mainWindow.webContents) return false;
  const sourceUrl = event.senderFrame?.url || event.sender.getURL();
  return isAllowedRendererUrl(sourceUrl);
}

function isAllowedRendererUrl(candidate) {
  try {
    const url = new URL(candidate);
    if (isDev) return url.origin === new URL(DEV_FRONTEND_URL).origin;
    return url.protocol === 'app:' && url.hostname === 'renderer';
  } catch (_error) {
    return false;
  }
}

async function initializeDesktopRuntime() {
  const paths = resolveRuntimePaths({
    appPath: app.getAppPath(),
    resourcesPath: process.resourcesPath,
    userDataPath: app.getPath('userData'),
    isPackaged: app.isPackaged,
  });
  ensureRuntimeDirectories(paths);
  rendererRoot = path.join(app.getAppPath(), 'client', 'dist');
  if (app.isPackaged) {
    await protocol.handle('app', (request) => {
      const assetPath = resolveRendererAsset(rendererRoot, request.url);
      if (!assetPath) return new Response('Not found', { status: 404 });
      return net.fetch(pathToFileURL(assetPath).toString());
    });
  }
  const descriptors = createServiceDescriptors(paths);
  const authorizer = new IpcPathAuthorizer({
    storePath: path.join(paths.dataRoot, 'data', 'desktop-directory-grants.json'),
  });
  await authorizer.loadPersistedDirectories();
  // App-owned workspace storage is registered internally; renderer input can never grant itself access.
  await authorizer.registerWorkspace(paths.workspacesRoot);

  const managedRuntimeTarget = Object.freeze({
    platform: process.platform,
    arch: process.arch,
    profile: 'base',
  });
  const managedRuntimeStore = new ManagedRuntimeStore({ root: paths.managedRuntimeRoot });
  const runtimePackDirectory = process.env.FINETUNE_RUNTIME_PACK_DIR
    || (app.isPackaged
      ? path.join(process.resourcesPath, 'runtime-packs')
      : path.join(paths.projectRoot, 'artifacts', 'runtime-packs'));
  const runtimeArtifactAdapter = new LocalRuntimeArtifactAdapter({
    manifestPath: process.env.FINETUNE_RUNTIME_MANIFEST || null,
    manifestDirectory: runtimePackDirectory,
    target: managedRuntimeTarget,
  });
  managedRuntimeCoordinator = new ManagedRuntimeCoordinator({
    store: managedRuntimeStore,
    target: managedRuntimeTarget,
    artifactAdapter: runtimeArtifactAdapter,
    probeAdapter: {
      probe: ({ executablePath }) => defaultProbe({
        source: 'managed-runtime',
        command: executablePath,
        prefixArgs: [],
      }),
    },
  });
  await managedRuntimeCoordinator.check();
  const activeManagedRuntime = await managedRuntimeStore.readActive('base');

  let python = null;
  let pythonError = null;
  try {
    python = await resolvePython({
      explicitPython: process.env.FINETUNE_PYTHON,
      projectRoot: paths.projectRoot,
      managedRuntime: activeManagedRuntime,
      platform: process.platform,
    });
  } catch (error) {
    pythonError = error;
    console.error('[desktop] Python runtime resolution failed', error.diagnostics || error);
  }

  if (python) {
    const secrets = getOrCreateRuntimeSecrets(paths);
    supervisor = new ProcessSupervisor({
      descriptors,
      python,
      environment: buildServiceEnvironment(paths, secrets),
      probeProcess: createTrainingWorkerProbe(python, paths.databasePath),
      log: console,
    });
  } else {
    supervisor = new UnavailableSupervisor(descriptors, pythonError);
  }

  const runtimeDescriptor = Object.freeze({
    protocolVersion: PROTOCOL_VERSION,
    appVersion: app.getVersion(),
    platform: process.platform,
    arch: process.arch,
    packaged: app.isPackaged,
    apiBaseUrl: 'http://127.0.0.1:8010',
  });
  removeIpcHandlers = registerDesktopIpc({
    ipcMain,
    dialog,
    shell,
    getWindow: () => mainWindow,
    isTrustedEvent: isTrustedRendererEvent,
    authorizer,
    supervisor,
    runtimeDescriptor,
    managedRuntimeCoordinator,
    revealRuntimeLogs: async () => {
      const errorMessage = await shell.openPath(paths.logsRoot);
      if (errorMessage) {
        throw Object.assign(new Error('Unable to reveal desktop logs.'), {
          code: 'RUNTIME_LOG_REVEAL_FAILED',
        });
      }
      return true;
    },
  });

  createWindow();
  if (pythonError) {
    console.warn('[desktop] Services are unavailable until the base runtime is prepared.');
  } else {
    await supervisor.startAll();
  }
}

if (hasSingleInstanceLock) app.whenReady().then(initializeDesktopRuntime).catch((error) => {
  console.error('[desktop] initialization failed', error);
  dialog.showErrorBox('启动失败', error.message);
  app.quit();
});

app.on('second-instance', () => {
  if (!mainWindow) return;
  if (mainWindow.isMinimized()) mainWindow.restore();
  mainWindow.show();
  mainWindow.focus();
});

app.on('activate', () => {
  if (!quitting && BrowserWindow.getAllWindows().length === 0) createWindow();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', (event) => {
  event.preventDefault();
  // A second quit request while shutdown is in flight must not bypass the ordered
  // supervisor teardown below.
  if (quitting) return;
  quitting = true;
  supervisor?.beginShutdown?.();
  managedRuntimeCoordinator?.beginShutdown?.();
  Promise.resolve(supervisor?.stopAll())
    .catch((error) => console.error('[desktop] shutdown failed', error))
    .finally(() => {
      removeIpcHandlers?.();
      removeIpcHandlers = null;
      app.exit(0);
    });
});
