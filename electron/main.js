const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const { spawn, exec } = require('child_process');
const fs = require('fs');

let mainWindow;
let pythonProcess;
const isDev = !app.isPackaged;

function getServerPath() {
  if (isDev) {
    return path.join(__dirname, '..', 'server');
  }
  return path.join(process.resourcesPath, 'server');
}

function getPythonCommand() {
  if (process.platform === 'win32') {
    return 'python';
  }
  return 'python3';
}

async function checkPythonAndDeps() {
  const pythonCmd = getPythonCommand();
  
  return new Promise((resolve, reject) => {
    exec(`${pythonCmd} --version`, (error, stdout, stderr) => {
      if (error) {
        reject(new Error('Python not found. Please install Python 3.8+'));
        return;
      }
      
      exec(`${pythonCmd} -c "import fastapi; import torch; import transformers; import peft"`, (depError, depStdout, depStderr) => {
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
    env: { ...process.env, PYTHONPATH: serverPath }
  });

  pythonProcess.stdout.on('data', (data) => {
    console.log('[Python]', data.toString());
  });

  pythonProcess.stderr.on('data', (data) => {
    console.error('[Python Error]', data.toString());
  });

  pythonProcess.on('close', (code) => {
    console.log(`Backend process exited with code ${code}`);
  });
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
      preload: path.join(__dirname, 'preload.js')
    },
    title: 'Finetune Platform - 大模型微调平台'
  });

  if (isDev) {
    mainWindow.loadURL('http://localhost:5173');
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
    
    setTimeout(() => {
      createWindow();
    }, 3000);
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

ipcMain.handle('select-folder', async (event, defaultPath) => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory'],
    defaultPath: defaultPath || app.getPath('documents')
  });
  return result.filePaths[0] || null;
});

ipcMain.handle('select-file', async (event, filters) => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile'],
    filters: filters || [{ name: 'All Files', extensions: ['*'] }]
  });
  return result.filePaths[0] || null;
});

ipcMain.handle('read-file', async (event, filePath) => {
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

ipcMain.handle('get-backend-url', () => {
  return 'http://127.0.0.1:8000';
});

ipcMain.handle('restart-backend', () => {
  if (pythonProcess) {
    pythonProcess.kill();
  }
  startBackend();
  return true;
});

ipcMain.handle('open-folder', async (event, folderPath) => {
  await shell.openPath(folderPath);
});

ipcMain.handle('get-app-path', () => {
  return app.getAppPath();
});
