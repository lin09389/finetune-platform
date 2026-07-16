'use strict';

const { contextBridge, ipcRenderer } = require('electron');
// Keep sandboxed preload self-contained: Electron's preload require is intentionally limited.
const PROTOCOL_VERSION = 1;
const CHANNELS = Object.freeze({
  runtime: 'desktop:v1:get-runtime',
  services: 'desktop:v1:get-services',
  serviceStatus: 'desktop:v1:service-status',
  restartService: 'desktop:v1:restart-service',
  runtimeManagementStatus: 'desktop:v1:get-managed-runtime-status',
  prepareBaseRuntime: 'desktop:v1:prepare-base-runtime',
  repairBaseRuntime: 'desktop:v1:repair-base-runtime',
  retryRuntimeOperation: 'desktop:v1:retry-runtime-operation',
  revealRuntimeLogs: 'desktop:v1:reveal-runtime-logs',
  selectFolder: 'desktop:v1:select-folder',
  selectFile: 'desktop:v1:select-file',
  readFile: 'desktop:v1:read-file',
  openFolder: 'desktop:v1:open-folder',
});

const API_BASE_URL = 'http://127.0.0.1:8010';

const bridge = Object.freeze({
  protocolVersion: PROTOCOL_VERSION,
  getRuntime: () => ipcRenderer.invoke(CHANNELS.runtime),
  getServiceStatuses: () => ipcRenderer.invoke(CHANNELS.services),
  restartService: (serviceId) => ipcRenderer.invoke(CHANNELS.restartService, serviceId),
  getManagedRuntimeStatus: () => ipcRenderer.invoke(CHANNELS.runtimeManagementStatus),
  prepareBaseRuntime: () => ipcRenderer.invoke(CHANNELS.prepareBaseRuntime),
  repairBaseRuntime: () => ipcRenderer.invoke(CHANNELS.repairBaseRuntime),
  retryRuntimeOperation: () => ipcRenderer.invoke(CHANNELS.retryRuntimeOperation),
  revealRuntimeLogs: () => ipcRenderer.invoke(CHANNELS.revealRuntimeLogs),
  onServiceStatus: (callback) => {
    if (typeof callback !== 'function') throw new TypeError('Service status callback is required.');
    const listener = (_event, status) => callback(status);
    ipcRenderer.on(CHANNELS.serviceStatus, listener);
    return () => ipcRenderer.removeListener(CHANNELS.serviceStatus, listener);
  },
  onManagedRuntimeStatus: (callback) => {
    if (typeof callback !== 'function') throw new TypeError('Managed runtime status callback is required.');
    const listener = (_event, status) => callback(status);
    ipcRenderer.on(CHANNELS.runtimeManagementStatus, listener);
    return () => ipcRenderer.removeListener(CHANNELS.runtimeManagementStatus, listener);
  },

  selectFolder: () => ipcRenderer.invoke(CHANNELS.selectFolder),
  selectFile: (filters) => ipcRenderer.invoke(CHANNELS.selectFile, filters),
  readFile: (filePath) => ipcRenderer.invoke(CHANNELS.readFile, filePath),
  openFolder: (folderPath) => ipcRenderer.invoke(CHANNELS.openFolder, folderPath),

  // Compatibility surface for the existing renderer. New code should use the v1 methods above.
  getBackendUrl: () => Promise.resolve(API_BASE_URL),
  getBackendUrlSync: () => API_BASE_URL,
  restartBackend: () => ipcRenderer.invoke(CHANNELS.restartService, 'control-plane').then(() => true),
});

contextBridge.exposeInMainWorld('electronAPI', bridge);
