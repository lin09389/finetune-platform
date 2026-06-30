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
    id: 'part_prompt',
    part_id: 'part_prompt',
    session_id: session.id,
    type: 'text',
    status: 'completed',
    title: '我的消息',
    content: '请实现并验证登录接口',
    created_at: '2026-06-21T00:00:30Z',
    payload: { role: 'user', source: 'prompt' },
  },
  {
    id: 'part_output',
    part_id: 'part_output',
    session_id: session.id,
    type: 'summary',
    status: 'completed',
    title: '最终结果',
    content: [
      '# 实现方案',
      '',
      '登录流程已经完成，并通过类型检查。',
      '',
      '> Token 默认有效期为 15 分钟。',
      '',
      '## 验证结果',
      '',
      '- [x] 参数校验',
      '- [x] 错误处理',
      '',
      '| 检查项 | 状态 |',
      '| --- | --- |',
      '| TypeScript | 通过 |',
      '',
      '```ts',
      'export function login(username: string) {',
      '  return { username, authenticated: true };',
      '}',
      '```',
    ].join('\n'),
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

async function dragBy(page, locator, deltaX, deltaY) {
  const box = await locator.boundingBox();
  assert(box, 'Resize handle is not visible');
  const startX = box.x + box.width / 2;
  const startY = box.y + box.height / 2;
  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.mouse.move(startX + deltaX, startY + deltaY, { steps: 6 });
  await page.mouse.up();
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
    const isWindows = process.platform === 'win32';
    const viteCommand = isWindows ? (process.env.ComSpec || 'cmd.exe') : 'npm';
    const viteArgs = isWindows
      ? ['/d', '/s', '/c', 'npm run dev -- --host 127.0.0.1']
      : ['run', 'dev', '--', '--host', '127.0.0.1'];
    viteProcess = spawn(viteCommand, viteArgs, {
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

  await page.getByRole('heading', { name: '实现方案', level: 1 }).waitFor();
  await page.getByRole('table').waitFor();
  await page.getByText('TypeScript', { exact: true }).waitFor();
  const codePreview = page.locator('.code-preview');
  await codePreview.waitFor();
  assert(await codePreview.count() === 1, 'Code preview did not render');
  await page.getByRole('button', { name: '复制完整回答' }).click();
  await page.getByRole('button', { name: '回答已复制' }).waitFor();
  if (process.env.AGENT_E2E_SCREENSHOT) {
    await page.screenshot({ path: process.env.AGENT_E2E_SCREENSHOT, fullPage: false });
  }

  const sessionRailBoxBefore = await sessionRail.boundingBox();
  await dragBy(page, page.getByRole('separator', { name: '调整会话栏宽度' }), 36, 0);
  const sessionRailBoxAfter = await sessionRail.boundingBox();
  assert(
    sessionRailBoxAfter.width > sessionRailBoxBefore.width + 20,
    'Session rail did not resize after pointer drag',
  );

  const rightDock = page.getByRole('complementary', { name: '工作台侧栏' });
  const rightDockBoxBefore = await rightDock.boundingBox();
  await dragBy(page, page.getByRole('separator', { name: '调整工作区宽度' }), -48, 0);
  const rightDockBoxAfter = await rightDock.boundingBox();
  assert(
    rightDockBoxAfter.width > rightDockBoxBefore.width + 30,
    'Right workspace did not resize after pointer drag',
  );

  const terminalRegion = page.getByRole('region', { name: '终端面板' });
  const terminalBoxBefore = await terminalRegion.boundingBox();
  await dragBy(page, page.getByRole('separator', { name: '调整终端高度' }), 0, -44);
  const terminalBoxAfter = await terminalRegion.boundingBox();
  assert(
    terminalBoxAfter.height > terminalBoxBefore.height + 25,
    'Terminal did not resize after pointer drag',
  );

  const workspaceRegion = page.getByRole('region', { name: '工作区' });
  const workspaceBoxBefore = await workspaceRegion.boundingBox();
  await dragBy(page, page.getByRole('separator', { name: '调整工作区与任务中心比例' }), 0, 50);
  const workspaceBoxAfter = await workspaceRegion.boundingBox();
  assert(
    workspaceBoxAfter.height > workspaceBoxBefore.height + 25,
    'Workspace/task center split did not resize after pointer drag',
  );

  const panelToolbar = page.getByRole('navigation', { name: '工作台面板' });
  await panelToolbar.getByRole('button', { name: '隐藏工作区' }).click();
  await panelToolbar.getByRole('button', { name: '显示工作区' }).click();
  await page.getByRole('region', { name: '变更文件' }).waitFor();
  await panelToolbar.getByRole('button', { name: '隐藏任务中心' }).click();
  await panelToolbar.getByRole('button', { name: '显示任务中心' }).click();
  await panelToolbar.getByRole('button', { name: '隐藏终端' }).click();
  await panelToolbar.getByRole('button', { name: '显示终端' }).click();
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
  await mobile.getByRole('heading', { name: '实现方案', level: 1 }).waitFor();
  await mobile.locator('.code-preview').waitFor();
  const mobilePanelToolbar = mobile.getByRole('navigation', { name: '工作台面板' });
  await mobilePanelToolbar.getByRole('button', { name: '显示工作区' }).click();
  await mobile.getByRole('complementary', { name: '工作台侧栏' }).waitFor();
  await mobile.getByRole('button', { name: '关闭工作台侧栏' }).click();
  await mobilePanelToolbar.getByRole('button', { name: '显示终端' }).click();
  await mobile.getByLabel('搜索终端输出').waitFor();
  await mobile.getByRole('region', { name: '终端面板' })
    .getByRole('button', { name: '隐藏终端' }).click();
  const mobileContentMetrics = await mobile.evaluate(() => ({
    width: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  assert(mobileContentMetrics.width === mobileContentMetrics.scrollWidth, 'Mobile output has horizontal overflow');
  await mobile.waitForTimeout(150);
  if (process.env.AGENT_E2E_MOBILE_SCREENSHOT) {
    await mobile.screenshot({ path: process.env.AGENT_E2E_MOBILE_SCREENSHOT, fullPage: false });
  }
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
