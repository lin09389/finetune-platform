const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  selectFolder: (defaultPath) => ipcRenderer.invoke('select-folder', defaultPath),
  selectFile: (filters) => ipcRenderer.invoke('select-file', filters),
  readFile: (filePath) => ipcRenderer.invoke('read-file', filePath),
  getBackendUrl: () => ipcRenderer.invoke('get-backend-url'),
  restartBackend: () => ipcRenderer.invoke('restart-backend'),
  openFolder: (folderPath) => ipcRenderer.invoke('open-folder', folderPath),
  getAppPath: () => ipcRenderer.invoke('get-app-path'),
  
  onTrainingProgress: (callback) => {
    ipcRenderer.on('training-progress', (event, data) => callback(data));
  },
  onTrainingComplete: (callback) => {
    ipcRenderer.on('training-complete', (event, data) => callback(data));
  },
  onTrainingError: (callback) => {
    ipcRenderer.on('training-error', (event, data) => callback(data));
  },
  
  removeTrainingListeners: () => {
    ipcRenderer.removeAllListeners('training-progress');
    ipcRenderer.removeAllListeners('training-complete');
    ipcRenderer.removeAllListeners('training-error');
  }
});
