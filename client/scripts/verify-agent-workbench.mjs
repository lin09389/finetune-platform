import { spawn } from 'node:child_process';
import { chromium } from 'playwright';

const baseUrl = 'http://127.0.0.1:5173';
const apiBase = 'http://127.0.0.1:8010';

const session = {
  id: 'ags_e2e',
  agent_id: 'build',
  status: 'completed',
  title: 'Agent product verification',
  project_path: 'C:/workspace/project',
  metadata: {},
  parts: [],
  created_at: '2026-06-21T00:00:00Z',
  updated_at: '2026-06-21T00:03:00Z',
};

const timeline = [
  {
    id: 'part_output',
    part_id: 'part_output',
    session_id: session.id,
    type: 'text',
    status: 'completed',
    title: '实现完成',
    content: 'Agent workbench ready',
    created_at: '2026-06-21T00:01:00Z',
    payload: {},
  },
  {
    id: 'part_command',
    part_id: 'part_command',
    session_id: session.id,
    type: 'command',
    status: 'completed',
    title: 'npm test',
    content: 'alpha complete\nalpha verified',
    created_at: '2026-06-21T00:04:00Z',
    payload: {
      terminal_id: 'terminal_e2e',
      command: 'npm test',
      stdout: 'alpha complete\nalpha verified',
      stderr: '',
      exit_code: 0,
    },
  },
  {
    id: 'part_tool',
    part_id: 'part_tool',
    session_id: session.id,
    type: 'tool_call',
    status: 'completed',
    title: 'read_file',
    content: 'Read package.json',
    created_at: '2026-06-21T00:02:00Z',
    payload: { tool: 'read_file' },
  },
  {
    id: 'part_error',
    part_id: 'part_error',
    session_id: session.id,
    type: 'error',
    status: 'failed',
    title: '验证失败',
    content: 'One retry required',
    created_at: '2026-06-21T00:03:00Z',
    payload: {},
  },
];

const workspace = {
  session,
  status_text: { current_phase: 'completed' },
  timeline,
  pending_permission: null,
  diagnostics: {},
  async_tasks: {
    tasks: [],
    metrics: {
      total: 0,
      by_status: {},
      running: 0,
      failed: 0,
      cancelled: 0,
      completed: 0,
      attention: 0,
      recovery_count: 0,
      event_count: 0,
    },
  },
  artifacts: [],
  changed_files: [],
  next_actions: [],
  recent_events: [],
  execution_plan: null,
};

async function isServerReady() {
  try {
    const response = await fetch(baseUrl);
    return response.ok;
  } catch {
    return false;
  }
}

async function waitForServer(timeoutMs = 20_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await isServerReady()) return;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Vite server did not become ready at ${baseUrl}`);
}

async function launchBrowser() {
  try {
    return await chromium.launch({ headless: true });
  } catch {
    return chromium.launch({ channel: 'chrome', headless: true });
  }
}

function json(route, body) {
  return route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

async function mockBackend(page) {
  await page.route(`${apiBase}/**`, async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path === '/agents') return json(route, [{ id: 'build', name: 'Build Agent', mode: 'primary' }]);
    if (path === '/agent-sessions') return json(route, [
      session,
      { ...session, id: 'ags_second', title: 'Review release', status: 'running' },
    ]);
    if (path === `/agent-sessions/${session.id}/workspace`) return json(route, workspace);
    if (path.includes('/events/stream')) {
      return route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: 'event: agent_session_done\ndata: {"status":"completed"}\n\n',
      });
    }
    if (path === '/runtime/bootstrap') {
      return json(route, { inference: { backends: [], engines: [] }, capabilities: {} });
    }
    if (path === '/health') return json(route, { status: 'ok' });
    if (path.endsWith('/diagnostics/batch')) return json(route, { accepted: 1 });
    return json(route, {});
  });
}

async function seedActiveSession(context) {
  await context.addInitScript((activeSession) => {
    localStorage.setItem('finetune.agent-workbench.sessions.v1', JSON.stringify({
      version: 1,
      activeSessionId: activeSession.id,
      sessions: [{
        id: activeSession.id,
        title: activeSession.title,
        status: activeSession.status,
        agentId: activeSession.agent_id,
        projectPath: activeSession.project_path,
        updatedAt: activeSession.updated_at,
      }],
    }));
  }, session);
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function waitForWorkbench(page) {
  const browserErrors = [];
  page.on('pageerror', (error) => browserErrors.push(error.message));
  try {
    await page.waitForSelector('[aria-label="Agent 执行时间线"]', { timeout: 15_000 });
  } catch (error) {
    const body = (await page.locator('body').innerText()).slice(0, 2000);
    throw new Error([
      error.message,
      `URL: ${page.url()}`,
      `Page: ${body}`,
      `Errors: ${browserErrors.join(' | ') || 'none'}`,
    ].join('\n'));
  }
}

let viteProcess;
let browser;
try {
  if (!(await isServerReady())) {
    const npmCommand = process.platform === 'win32' ? 'npm.cmd' : 'npm';
    viteProcess = spawn(npmCommand, ['run', 'dev', '--', '--host', '127.0.0.1'], {
      cwd: process.cwd(),
      stdio: 'ignore',
      windowsHide: true,
    });
    await waitForServer();
  }

  browser = await launchBrowser();
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await seedActiveSession(context);
  const page = await context.newPage();
  await mockBackend(page);
  await page.goto(`${baseUrl}/`, { waitUntil: 'domcontentloaded' });
  await waitForWorkbench(page);
  assert(page.url().endsWith('/agent'), 'Root route did not redirect to /agent');

  await page.getByLabel('搜索 Agent 会话').fill('Review');
  const sessionRail = page.getByRole('complementary', { name: 'Agent 会话' });
  await sessionRail.getByText('Review release', { exact: true }).waitFor();
  assert(
    await sessionRail.getByText('Agent product verification', { exact: true }).count() === 0,
    'Session search did not filter the session rail',
  );

  await page.getByText('异常', { exact: true }).click();
  await page.getByText('1/4', { exact: true }).waitFor();
  await page.getByLabel('搜索 Agent 会话').press('Alt+2');
  await page.getByRole('region', { name: '变更文件' }).waitFor();
  await page.getByLabel('搜索 Agent 会话').press('Alt+5');
  await page.getByLabel('搜索终端输出').waitFor();
  await page.getByLabel('搜索终端输出').fill('alpha');
  await page.getByText('2 处', { exact: true }).waitFor();

  const desktopMetrics = await page.evaluate(() => ({
    width: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  assert(desktopMetrics.width === desktopMetrics.scrollWidth, 'Desktop layout has horizontal overflow');
  await context.close();

  const mobileContext = await browser.newContext({ viewport: { width: 390, height: 844 } });
  await seedActiveSession(mobileContext);
  const mobile = await mobileContext.newPage();
  await mockBackend(mobile);
  await mobile.goto(`${baseUrl}/agent`, { waitUntil: 'domcontentloaded' });
  await mobile.getByRole('button', { name: '打开会话' }).waitFor();
  await mobile.getByRole('button', { name: '打开会话' }).click();
  await mobile.getByRole('dialog', { name: 'Agent 会话' }).waitFor();
  await mobile.getByRole('button', { name: '置顶 Review release' }).waitFor();
  const mobileMetrics = await mobile.evaluate(() => ({
    width: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  assert(mobileMetrics.width === mobileMetrics.scrollWidth, 'Mobile layout has horizontal overflow');
  await mobileContext.close();

  console.log('[agent-e2e] desktop and mobile workbench flows passed');
} finally {
  await browser?.close();
  if (viteProcess) viteProcess.kill();
}
