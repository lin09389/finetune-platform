'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { PROTOCOL_VERSION } = require('./runtime-contract');
const MAX_RENDERER_FILE_BYTES = 64 * 1024 * 1024;

const CHANNELS = Object.freeze({
  runtime: 'desktop:v1:get-runtime',
  services: 'desktop:v1:get-services',
  serviceStatus: 'desktop:v1:service-status',
  restartService: 'desktop:v1:restart-service',
  selectFolder: 'desktop:v1:select-folder',
  selectFile: 'desktop:v1:select-file',
  readFile: 'desktop:v1:read-file',
  openFolder: 'desktop:v1:open-folder',
});

function sanitizeFilters(filters) {
  if (!Array.isArray(filters)) return [{ name: 'All Files', extensions: ['*'] }];
  return filters.slice(0, 20).map((filter) => ({
    name: String(filter?.name || 'Files').slice(0, 80),
    extensions: Array.isArray(filter?.extensions)
      ? filter.extensions.slice(0, 30).map((value) => String(value).replace(/^\./, '').slice(0, 20))
      : ['*'],
  }));
}

function registerDesktopIpc({
  ipcMain,
  dialog,
  shell,
  getWindow,
  isTrustedEvent,
  authorizer,
  supervisor,
  runtimeDescriptor,
}) {
  const handles = [];
  const handle = (channel, callback) => {
    ipcMain.handle(channel, async (event, ...args) => {
      if (!isTrustedEvent(event)) {
        throw Object.assign(new Error('Untrusted renderer IPC request.'), { code: 'UNTRUSTED_RENDERER' });
      }
      return callback(...args);
    });
    handles.push(channel);
  };

  handle(CHANNELS.runtime, () => ({ ...runtimeDescriptor, protocolVersion: PROTOCOL_VERSION }));
  handle(CHANNELS.services, () => supervisor.listStatuses());
  handle(CHANNELS.restartService, async (id) => {
    await supervisor.restartService(String(id));
    return supervisor.listStatuses();
  });
  handle(CHANNELS.selectFolder, async () => {
    const result = await dialog.showOpenDialog(getWindow(), { properties: ['openDirectory'] });
    if (result.canceled || !result.filePaths[0]) return null;
    return authorizer.grantSelectedDirectory(result.filePaths[0]);
  });
  handle(CHANNELS.selectFile, async (filters) => {
    const result = await dialog.showOpenDialog(getWindow(), {
      properties: ['openFile'],
      filters: sanitizeFilters(filters),
    });
    if (result.canceled || !result.filePaths[0]) return null;
    return authorizer.grantSelectedFile(result.filePaths[0]);
  });
  handle(CHANNELS.readFile, async (filePath) => {
    const authorized = await authorizer.assertReadableFile(filePath);
    const stats = await fs.promises.stat(authorized);
    if (!stats.isFile() || stats.size > MAX_RENDERER_FILE_BYTES) {
      throw Object.assign(new Error('Selected file is not a regular file or exceeds the 64 MiB IPC limit.'), {
        code: 'FILE_TOO_LARGE',
      });
    }
    const buffer = await fs.promises.readFile(authorized);
    authorizer.revokeFile(authorized);
    return { data: buffer.toString('base64'), name: path.basename(authorized) };
  });
  handle(CHANNELS.openFolder, async (folderPath) => {
    const authorized = await authorizer.assertOpenableDirectory(folderPath);
    const errorMessage = await shell.openPath(authorized);
    if (errorMessage) throw new Error(errorMessage);
    return true;
  });

  const statusListener = () => {
    const window = getWindow();
    if (window && !window.isDestroyed()) {
      window.webContents.send(CHANNELS.serviceStatus, supervisor.listStatuses());
    }
  };
  supervisor.on('status', statusListener);

  return () => {
    supervisor.off('status', statusListener);
    for (const channel of handles) ipcMain.removeHandler(channel);
  };
}

module.exports = { CHANNELS, MAX_RENDERER_FILE_BYTES, sanitizeFilters, registerDesktopIpc };
