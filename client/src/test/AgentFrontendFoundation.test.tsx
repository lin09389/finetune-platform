import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import fs from 'node:fs';
import path from 'node:path';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AgentTaskContextBar from '../agent/components/AgentTaskContextBar';
import AgentSessionRail from '../agent/components/AgentSessionRail';
import AgentWorkbenchRoute from '../agent/workbench/AgentWorkbenchRoute';
import {
  decodeAgentSessionEvent,
  selectTrainingActivity,
} from '../agent/protocol/agentProtocol';
import { agentRuntimeReducer, initialAgentRuntimeState, type RecentAgentSession } from '../agent/runtime/agentRuntime';
import { selectTimeline } from '../agent/selectors/workbenchSelectors';
import type { AgentTransport } from '../agent/transport/agentTransport';
import type { AgentSession, AgentSessionCreate, AgentWorkspace } from '../services/api';
import baselineFixture from '../agent/testing/fixtures/agent-session-baseline.json';
import {
  AGENT_PROTOCOL_BASELINE_VERSION,
  REQUIRED_STREAM_ENVELOPE_FIELDS,
  type AgentProtocolBaselineFixture,
} from '../agent/protocol/foundation';

const workspaceApiMocks = vi.hoisted(() => ({
  listWorkspaces: vi.fn(),
  validateWorkspacePath: vi.fn(),
}));

vi.mock('../services/api', async (importOriginal) => ({
  ...await importOriginal<typeof import('../services/api')>(),
  listWorkspaces: workspaceApiMocks.listWorkspaces,
  validateWorkspacePath: workspaceApiMocks.validateWorkspacePath,
}));

const agentRoot = path.resolve(process.cwd(), 'src/agent');
const forbiddenImports = [
  /pages\/ChatNew/,
  /pages\/chatNew/,
  /hooks\/chat/,
  /components\/chat/,
  /store\/chatStore/,
];

function isolatedTransport(): AgentTransport {
  return {
    listAgents: vi.fn().mockResolvedValue([]),
    listSessions: vi.fn().mockResolvedValue([]),
    createSession: vi.fn(),
    getSession: vi.fn(),
    updateSessionPreferences: vi.fn(),
    getWorkspace: vi.fn(),
    prompt: vi.fn(),
    interrupt: vi.fn(),
    decidePermission: vi.fn(),
    approvePermission: vi.fn(),
    rejectPermission: vi.fn(),
    recoverNode: vi.fn(),
    startAsyncTask: vi.fn(),
    cancelAsyncTask: vi.fn(),
    reportDiagnostics: vi.fn().mockResolvedValue({ accepted: 0 }),
    connectStream: vi.fn().mockReturnValue({ close: vi.fn() }),
    connectGlobalStream: vi.fn().mockReturnValue({ close: vi.fn() }),
  } as AgentTransport;
}

function agentSessionFixture(): AgentSession {
  return {
    id: 'session-demo',
    agent_id: 'build',
    status: 'idle',
    title: 'Demo task',
    project_path: 'C:/repo/demo',
    workspace_id: 'ws_demo',
    task_mode: 'hybrid',
    parts: [],
    preferences: { pinned: false, archived: false },
    created_at: '2026-07-10T00:00:00Z',
    updated_at: '2026-07-10T00:00:00Z',
  };
}

function sourceFiles(directory: string): string[] {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) return sourceFiles(target);
    return /\.(ts|tsx)$/.test(entry.name) ? [target] : [];
  });
}

describe('Agent frontend Phase 1 foundation', () => {
  beforeEach(() => {
    localStorage.clear();
    workspaceApiMocks.validateWorkspacePath.mockResolvedValue({
      ok: true,
      resolved_path: 'C:/repo/demo',
      allowed: true,
      exists: true,
      is_dir: true,
      needs_register: false,
      message: null,
      error_code: null,
    });
    workspaceApiMocks.listWorkspaces.mockResolvedValue([
      { id: 'ws_demo', name: 'Demo project', local_path: 'C:/repo/demo', status: 'active' },
    ]);
  });

  it('shows the selected Workspace and task mode before creating a task', () => {
    const onWorkspaceChange = vi.fn();
    const onModeChange = vi.fn();
    render(
      <AgentTaskContextBar
        workspace={{ id: 'ws_demo', label: 'Demo project', projectPath: 'C:/repo/demo' }}
        mode="hybrid"
        onWorkspaceChange={onWorkspaceChange}
        onModeChange={onModeChange}
      />,
    );

    expect(screen.getByRole('button', { name: /Demo project/ })).toBeInTheDocument();
    expect(screen.getByLabelText('任务模式')).toHaveValue('hybrid');
    fireEvent.change(screen.getByLabelText('任务模式'), { target: { value: 'train' } });
    expect(onModeChange).toHaveBeenCalledWith('train');
  });

  it('exposes the workspace task-context client contract', () => {
    const request: AgentSessionCreate = {
      agent_id: 'build',
      workspace_id: 'ws_demo',
      task_mode: 'hybrid',
    };
    const response = {
      id: 'session-demo',
      agent_id: 'build',
      status: 'idle',
      title: 'Demo',
      workspace_id: request.workspace_id,
      task_mode: request.task_mode,
      parts: [],
      preferences: { pinned: false, archived: false },
      created_at: '2026-07-10T00:00:00',
      updated_at: '2026-07-10T00:00:00',
    } satisfies AgentSession;

    expect(response.workspace_id).toBe('ws_demo');
    expect(response.task_mode).toBe('hybrid');
  });

  it('renders the independent Workbench shell when enabled', async () => {
    const transport = isolatedTransport();
    render(
      <MemoryRouter
        initialEntries={['/agent']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <AgentWorkbenchRoute
          transport={transport}
          persistence={{
            read: () => ({ version: 1, activeSessionId: null, sessions: [] }),
            write: vi.fn(),
          }}
        />
      </MemoryRouter>,
    );

    await waitFor(() => expect(transport.listAgents).toHaveBeenCalledTimes(1));
    expect(screen.getByText('Agent 工作台')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '新建任务' })).toBeInTheDocument();
    expect(screen.getByLabelText('任务目标')).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: '工作台面板' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: '任务中心' })).toBeInTheDocument();
    const sessionResizeHandle = screen.getByRole('separator', { name: '调整会话栏宽度' });
    expect(sessionResizeHandle).toBeInTheDocument();
    expect(screen.getByRole('separator', { name: '调整工作区宽度' })).toBeInTheDocument();
    expect(screen.getByRole('separator', { name: '调整终端高度' })).toBeInTheDocument();
    expect(screen.getByRole('separator', { name: '调整工作区与任务中心比例' })).toBeInTheDocument();
    fireEvent.keyDown(sessionResizeHandle, { key: 'ArrowLeft' });
    expect(sessionResizeHandle).toHaveAttribute('aria-valuenow', '216');
    fireEvent.click(screen.getByRole('button', { name: '环境' }));
    expect(screen.getByText('环境信息')).toBeInTheDocument();
  });

  it('creates a session with the confirmed Workspace path, id, and selected mode', async () => {
    localStorage.setItem('finetune.agent-workbench.settings.v1', JSON.stringify({
      projectPath: 'C:/repo/demo',
      workspaceId: 'ws_demo',
      taskMode: 'hybrid',
      autonomyMode: 'safe_auto',
    }));
    const transport = isolatedTransport();
    const session = agentSessionFixture();
    vi.mocked(transport.createSession).mockResolvedValue(session);
    vi.mocked(transport.prompt).mockResolvedValue(session);
    vi.mocked(transport.getWorkspace).mockResolvedValue({
      session,
      timeline: [],
      artifacts: [],
      changed_files: [],
      next_actions: [],
      recent_events: [],
      status_text: {},
      plan: { todos: [], source: 'empty' },
      todos: [],
      diagnostics: {},
      async_tasks: { tasks: [], metrics: {} },
    } as unknown as AgentWorkspace);

    render(
      <MemoryRouter initialEntries={['/agent']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AgentWorkbenchRoute transport={transport} persistence={{ read: () => ({ version: 1, activeSessionId: null, sessions: [] }), write: vi.fn() }} />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByRole('button', { name: /Demo project/ })).toBeInTheDocument(), { timeout: 5000 });
    fireEvent.change(screen.getByLabelText('任务模式'), { target: { value: 'hybrid' } });
    expect(screen.getByLabelText('任务模式')).toHaveValue('hybrid');
    fireEvent.change(screen.getByLabelText('任务目标'), { target: { value: '训练并验证 LoRA' } });
    fireEvent.click(screen.getByRole('button', { name: '提交任务' }));

    await waitFor(() => expect(transport.createSession).toHaveBeenCalledWith(expect.objectContaining({
      workspace_id: 'ws_demo',
      project_path: 'C:/repo/demo',
      task_mode: 'hybrid',
    })), { timeout: 5000 });
  }, 15000);

  it('blocks a new Build task until a Workspace has been confirmed', async () => {
    workspaceApiMocks.validateWorkspacePath.mockResolvedValueOnce({
      ok: false,
      resolved_path: null,
      allowed: false,
      exists: false,
      is_dir: false,
      needs_register: false,
      message: '路径不存在。',
      error_code: 'path_missing',
    });
    const transport = isolatedTransport();
    render(
      <MemoryRouter initialEntries={['/agent']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AgentWorkbenchRoute transport={transport} persistence={{ read: () => ({ version: 1, activeSessionId: null, sessions: [] }), write: vi.fn() }} />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText('请先确认工作区，才能创建 Build、Train 或 Hybrid 任务。')).toBeInTheDocument(), { timeout: 5000 });
    fireEvent.change(screen.getByLabelText('任务目标'), { target: { value: '构建项目' } });
    await waitFor(() => expect(screen.getByRole('button', { name: '提交任务' })).toBeDisabled(), { timeout: 5000 });
    expect(transport.createSession).not.toHaveBeenCalled();
  }, 15000);

  it('decodes task context as a compact timeline item without exposing the project path', () => {
    const session = agentSessionFixture();
    const event = decodeAgentSessionEvent({
      id: 'evt-context',
      session_id: session.id,
      event_type: 'task_context_initialized',
      message: 'Task context initialized',
      payload: {
        workspace_id: 'ws_demo',
        workspace_label: 'Demo project',
        task_mode: 'hybrid',
      },
      created_at: '2026-07-10T00:00:01Z',
      session_status: 'idle',
    });

    expect(event).not.toBeNull();
    const next = agentRuntimeReducer(
      { ...initialAgentRuntimeState, activeSessionId: session.id, session },
      { type: 'stream_event', event: event! },
    );
    const context = selectTimeline(next).find((item) => item.type === 'task_context');

    expect(next.unknownEvents).toEqual([]);
    expect(context).toMatchObject({
      title: '任务上下文',
      content: '工作区：Demo project · Hybrid',
      payload: { workspace_id: 'ws_demo', workspace_label: 'Demo project', task_mode: 'hybrid' },
    });
    expect(JSON.stringify(context)).not.toContain('C:/repo/demo');
  });

  it('shows a mode badge only for sessions that carry task context', () => {
    const oldSession: RecentAgentSession = {
      id: 'legacy-session',
      title: 'Legacy session',
      displayTitle: 'Legacy session',
      status: 'completed',
      agentId: 'build',
      updatedAt: '2026-07-10T00:00:00Z',
      preferences: { pinned: false, archived: false },
    };
    const contextualSession: RecentAgentSession = {
      ...oldSession,
      id: 'contextual-session',
      title: 'Contextual session',
      displayTitle: 'Contextual session',
      taskMode: 'hybrid',
    };

    render(
      <AgentSessionRail
        sessions={[oldSession, contextualSession]}
        activeSessionId={null}
        onNew={vi.fn()}
        onSelect={vi.fn()}
      />,
    );

    expect(screen.getByText('Hybrid')).toBeInTheDocument();
    expect(screen.getAllByText('Legacy session')).toHaveLength(1);
    expect(screen.queryAllByText('Build')).toHaveLength(0);
  });

  it('keeps the sanitized baseline fixture aligned with the stream envelope', () => {
    const fixture = baselineFixture as AgentProtocolBaselineFixture;
    expect(fixture.fixture_version).toBe(AGENT_PROTOCOL_BASELINE_VERSION);
    expect(fixture.source.sanitized).toBe(true);
    expect(fixture.events.length).toBeGreaterThanOrEqual(4);
    for (const event of [fixture.snapshot, ...fixture.events]) {
      for (const field of REQUIRED_STREAM_ENVELOPE_FIELDS) {
        expect(event).toHaveProperty(field);
      }
    }
    expect(fixture.events.some((event) => event.event_type === 'permission_asked')).toBe(true);
    expect(fixture.events.some((event) => event.event_type === 'loop_guard_triggered')).toBe(true);
  });

  it('decodes only complete, display-safe training activity projections', () => {
    const base = {
      id: 'part-training',
      type: 'tool_result',
      status: 'completed',
      payload: {},
    };

    expect(selectTrainingActivity({
      ...base,
      payload: {
        training_activity: {
          kind: 'proposal',
          source_tool: 'propose_training',
          proposal_id: 'proposal-1',
          status: 'warning',
          summary: '显存余量有限，但可以开始训练。',
          model_id: 'tiny-model',
          dataset_id: 'tiny-dataset',
          blockers: [],
          warnings: ['建议降低 batch size'],
        },
      },
    })).toMatchObject({
      kind: 'proposal', proposalId: 'proposal-1', status: 'warning', modelId: 'tiny-model',
    });

    expect(selectTrainingActivity({
      ...base,
      payload: {
        training_activity: {
          kind: 'submission',
          source_tool: 'submit_training',
          proposal_id: 'proposal-1',
          task_id: 'task-1',
          status: 'submitted',
          summary: '已提交训练任务。',
        },
      },
    })).toMatchObject({
      kind: 'submission', proposalId: 'proposal-1', taskId: 'task-1', status: 'submitted',
    });

    expect(selectTrainingActivity({
      ...base,
      payload: {
        training_activity: {
          kind: 'run_summary',
          source_tool: 'get_training_summary',
          task_id: 'task-1',
          status: 'completed',
          summary: '训练已完成。',
          final_loss: 0.18,
          elapsed_seconds: 125,
        },
      },
    })).toMatchObject({
      kind: 'run_summary', taskId: 'task-1', finalLoss: 0.18, elapsedSeconds: 125,
    });
  });

  it('falls back to generic tool activity when a training projection is malformed', () => {
    const item = {
      id: 'part-untrusted-training',
      type: 'tool_result',
      status: 'completed',
      payload: {
        training_activity: {
          kind: 'proposal',
          source_tool: 'submit_training',
          proposal_id: 42,
          status: 'ready',
          summary: ['not a safe summary'],
          output_path: 'C:/private/output',
        },
      },
    };

    expect(selectTrainingActivity(item)).toBeNull();
  });

  it('prevents the rewrite foundation from importing legacy Agent orchestration', () => {
    const violations = sourceFiles(agentRoot).flatMap((file) => {
      const source = fs.readFileSync(file, 'utf8').replace(/\\/g, '/');
      return forbiddenImports
        .filter((pattern) => pattern.test(source))
        .map((pattern) => `${path.relative(agentRoot, file)} -> ${pattern}`);
    });

    expect(violations).toEqual([]);
  });
});
