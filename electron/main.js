const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const { spawn, exec } = require('child_process');
const fs = require('fs');
const http = require('http');

let mainWindow;
let pythonProcess;
const isDev = !app.isPackaged;
const DEV_FRONTEND_URL = process.env.ELECTRON_RENDERER_URL || 'http://127.0.0.1:5173';

function getServerPath() {
  if (isDev) {
    return path.join(__dirname, '..', 'server');
  }
  return path.join(process.resourcesPath, 'server');
}

function getPythonCommand() {
  return process.platform === 'win32' ? 'python' : 'python3';
}

async function checkPythonAndDeps() {
  const pythonCmd = getPythonCommand();

  return new Promise((resolve, reject) => {
    exec(`${pythonCmd} --version`, (error) => {
      if (error) {
        reject(new Error('Python not found. Please install Python 3.8+'));
        return;
      }

      exec(`${pythonCmd} -c "import fastapi; import torch; import transformers; import peft"`, (depError) => {
        if (depError) {
          console.warn('Python dependencies may be missing:', depError.message);
          console.warn('Please run: pip install -r requirements.txt');
          resolve({ installed: false, message: 'Dependencies missing. Run: pip install -r requirements.txt' });
          return;
        }
        resolve({ installed: true });
      });
    });
  });
}

function startBackend() {
  const serverPath = getServerPath();
  const pythonCmd = getPythonCommand();

  pythonProcess = spawn(pythonCmd, ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', '8000'], {
    cwd: serverPath,
    stdio: ['pipe', 'pipe', 'pipe'],
    env: {
      ...process.env,
      PYTHONPATH: serverPath,
      PYTHONIOENCODING: 'utf-8',
      PYTHONUTF8: '1',
    },
  });

  pythonProcess.stdout.setEncoding('utf8');
  pythonProcess.stderr.setEncoding('utf8');

  pythonProcess.stdout.on('data', (data) => {
    console.log('[Python]', data);
  });

  pythonProcess.stderr.on('data', (data) => {
    console.error('[Python Error]', data);
  });

  pythonProcess.on('close', (code) => {
    console.log(`Backend process exited with code ${code}`);
  });
}

function probeHttp(url, timeoutMs = 2000) {
  return new Promise((resolve) => {
    const req = http.get(url, { timeout: timeoutMs }, (res) => {
      res.resume();
      resolve(res.statusCode >= 200 && res.statusCode < 500);
    });
    req.on('error', () => resolve(false));
    req.on('timeout', () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function loadDevRendererWithRetry(window, url, maxRetries = 120, intervalMs = 1000) {
  for (let i = 0; i < maxRetries; i++) {
    if (!window || window.isDestroyed()) return false;

    const ready = await probeHttp(url, 1500);
    if (ready) {
      try {
        await window.loadURL(url);
        return true;
      } catch (e) {
        // Keep retrying while dev server stabilizes.
      }
    }

    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return false;
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1200,
    minHeight: 700,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
    title: 'Finetune Platform - 大模型微调平台',
  });

  if (isDev) {
    // Keep a safe origin to avoid landing on chrome-error:// pages.
    mainWindow.loadURL('about:blank');
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, '../client/dist/index.html'));
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(async () => {
  try {
    console.log('Checking Python environment...');
    const pythonStatus = await checkPythonAndDeps();

    if (!pythonStatus.installed) {
      dialog.showErrorBox(
        'Python 依赖缺失',
        pythonStatus.message || '请先安装 Python 依赖：pip install -r requirements.txt'
      );
    }

    startBackend();

    createWindow();
    if (isDev && mainWindow) {
      const loaded = await loadDevRendererWithRetry(mainWindow, DEV_FRONTEND_URL, 120, 1000);
      if (!loaded) {
        console.warn(`Failed to load frontend at ${DEV_FRONTEND_URL} after retries`);
      }
    }
  } catch (error) {
    console.error('Failed to start application:', error);
    dialog.showErrorBox('启动失败', error.message);
    app.quit();
  }
});

app.on('window-all-closed', () => {
  if (pythonProcess) {
    pythonProcess.kill();
  }
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

ipcMain.handle('select-folder', async (_event, defaultPath) => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory'],
    defaultPath: defaultPath || app.getPath('documents'),
  });
  return result.filePaths[0] || null;
});

ipcMain.handle('select-file', async (_event, filters) => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile'],
    filters: filters || [{ name: 'All Files', extensions: ['*'] }],
  });
  return result.filePaths[0] || null;
});

ipcMain.handle('read-file', async (_event, filePath) => {
  try {
    const buffer = await fs.promises.readFile(filePath);
    const base64 = buffer.toString('base64');
    const fileName = path.basename(filePath);
    return { data: base64, name: fileName };
  } catch (error) {
    console.error('Error reading file:', error);
    return null;
  }
});

ipcMain.handle('get-backend-url', () => 'http://127.0.0.1:8000');

ipcMain.handle('restart-backend', () => {
  if (pythonProcess) {
    pythonProcess.kill();
  }
  startBackend();
  return true;
});

ipcMain.handle('open-folder', async (_event, folderPath) => {
  await shell.openPath(folderPath);
});

ipcMain.handle('get-app-path', () => app.getAppPath());
