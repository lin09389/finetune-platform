import { act, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import AgentRunTimeline from '../agent/components/AgentRunTimeline';
import {
  AgentCommandExecutor,
  AgentCommandFailure,
} from '../agent/commands/agentCommands';
import AgentWorkbenchShell from '../agent/workbench/AgentWorkbenchShell';
import { selectAttentionItems } from '../agent/attention/selectAttentionItems';
import {
  applyEventToSession,
  decodeAgentSessionEvent,
  isKnownAgentEvent,
} from '../agent/protocol/agentProtocol';
import {
  agentRuntimeReducer,
  initialAgentRuntimeState,
} from '../agent/runtime/agentRuntime';
import {
  persistAgentRuntime,
  readPersistedAgentRuntime,
} from '../agent/runtime/sessionPersistence';
import { useAgentWorkbench } from '../agent/runtime/useAgentWorkbench';
import type { AgentTransport } from '../agent/transport/agentTransport';
import type {
  AgentSession,
  AgentSessionEvent,
  AgentSessionUiTimelineItem,
  AgentWorkspace,
} from '../services/api';
import {
  FLOW_NAMES,
  createFlowScenario,
} from '../agent/testing/agentFlowScenarios';
import {
  projectLegacyFixture,
  projectNewRuntime,
} from '../agent/testing/canonicalProjection';
import { routeAgentNextAction } from '../agent/commands/nextActionRouting';

const session: AgentSession = {
  id: 'ags_test',
  agent_id: 'build',
  status: 'running',
  title: 'Runtime test',
  project_path: 'C:/workspace/test',
  metadata: {},
  parts: [],
  created_at: '2026-06-19T08:00:00Z',
  updated_at: '2026-06-19T08:00:00Z',
};

const workspace: AgentWorkspace = {
  session,
  status_text: { current_phase: 'executing' },
  timeline: [],
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
};

const event: AgentSessionEvent = {
  id: 'agevt_1',
  session_id: session.id,
  event_type: 'tool_call_started',
  chunk_type: 'tool_call',
  message: 'Calling read_file',
  payload: {},
  created_at: '2026-06-19T08:00:01Z',
  session_status: 'running',
  part: {
    id: 'agp_1',
    session_id: session.id,
    type: 'tool_call',
    status: 'running',
    title: 'read_file',
    content: '',
    payload: { tool: 'read_file' },
    created_at: '2026-06-19T08:00:01Z',
  },
};

function fakeTransport(overrides: Partial<AgentTransport> = {}): AgentTransport {
  return {
    listAgents: vi.fn().mockResolvedValue([{ id: 'build', name: 'Build', mode: 'primary' }]),
    listSessions: vi.fn().mockResolvedValue([]),
    createSession: vi.fn().mockResolvedValue(session),
    getSession: vi.fn().mockResolvedValue(session),
    getWorkspace: vi.fn().mockResolvedValue(workspace),
    prompt: vi.fn().mockResolvedValue(session),
    interrupt: vi.fn().mockResolvedValue({ ...session, status: 'interrupted' }),
    decidePermission: vi.fn(),
    approvePermission: vi.fn(),
    rejectPermission: vi.fn(),
    recoverNode: vi.fn(),
    startAsyncTask: vi.fn(),
    cancelAsyncTask: vi.fn(),
    reportDiagnostics: vi.fn().mockResolvedValue({ accepted: 1 }),
    connectStream: vi.fn().mockReturnValue({ close: vi.fn() }),
    ...overrides,
  } as AgentTransport;
}

describe('Agent protocol and runtime', () => {
  it('rejects malformed envelopes and retains unknown valid events', () => {
    expect(decodeAgentSessionEvent({ id: 'broken' })).toBeNull();
    const decoded = decodeAgentSessionEvent({
      id: 'agevt_unknown',
      session_id: session.id,
      event_type: 'future_event',
      message: 'Future payload',
      payload: { version: 2 },
      created_at: session.updated_at,
    });
    expect(decoded).not.toBeNull();
    expect(isKnownAgentEvent(decoded!.event_type)).toBe(false);
  });

  it.each([
    'chain_completed',
    'session_blocked',
    'task_plan_created',
    'part_created',
    'agent_chain_failed',
  ])('recognizes the compatible %s event without raising protocol attention', (eventType) => {
    expect(isKnownAgentEvent(eventType)).toBe(true);
    const loaded = agentRuntimeReducer(initialAgentRuntimeState, { type: 'session_loaded', session });
    const next = agentRuntimeReducer(loaded, {
      type: 'stream_event',
      event: { ...event, id: `compat:${eventType}`, event_type: eventType, part: null },
    });
    expect(next.unknownEvents).toEqual([]);
    expect(selectAttentionItems(next)).toEqual([]);
  });

  it('merges event parts and ignores duplicate event ids', () => {
    const loaded = agentRuntimeReducer(initialAgentRuntimeState, { type: 'session_loaded', session });
    const first = agentRuntimeReducer(loaded, { type: 'stream_event', event });
    const duplicate = agentRuntimeReducer(first, { type: 'stream_event', event });
    expect(first.session?.parts).toHaveLength(1);
    expect(duplicate).toBe(first);
  });

  it('uses session snapshots as authoritative state', () => {
    const completed = { ...session, status: 'completed' as const, title: 'Authoritative snapshot' };
    const next = applyEventToSession(session, {
      ...event,
      id: 'snap_1',
      event_type: 'session_snapshot',
      session_snapshot: completed,
    });
    expect(next).toEqual(completed);
  });

  it('records unknown events without corrupting session state', () => {
    const loaded = agentRuntimeReducer(initialAgentRuntimeState, { type: 'session_loaded', session });
    const next = agentRuntimeReducer(loaded, {
      type: 'stream_event',
      event: { ...event, id: 'future_1', event_type: 'future_event', part: null },
    });
    expect(next.unknownEvents).toHaveLength(1);
    expect(next.session?.id).toBe(session.id);
  });

  it('keeps other operations visible when one concurrent command finishes', () => {
    const first = agentRuntimeReducer(initialAgentRuntimeState, {
      type: 'operation_started',
      operation: { key: 'refresh:a', label: 'refresh', startedAt: 1 },
    });
    const second = agentRuntimeReducer(first, {
      type: 'operation_started',
      operation: { key: 'permission:b', label: 'permission', startedAt: 2 },
    });
    const next = agentRuntimeReducer(second, { type: 'operation_finished', key: 'refresh:a' });
    expect(next.activeOperation?.key).toBe('permission:b');
    expect(next.operations['permission:b']).toBeDefined();
  });

  it('keeps another concurrent operation visible when a command reports an error', () => {
    const running = agentRuntimeReducer(initialAgentRuntimeState, {
      type: 'operation_started',
      operation: { key: 'permission:b', label: 'permission', startedAt: 2 },
    });
    const failed = agentRuntimeReducer(running, { type: 'error', message: 'refresh failed' });
    expect(failed.activeOperation?.key).toBe('permission:b');
    expect(failed.operations['permission:b']).toBeDefined();
    expect(failed.error).toBe('refresh failed');
  });

  it('persists a versioned and bounded recent-session index', () => {
    let storedValue = '';
    const storage: Pick<Storage, 'getItem' | 'setItem'> = {
      getItem: vi.fn((): string => storedValue),
      setItem: vi.fn((_key: string, value: string): void => { storedValue = value; }),
    };
    persistAgentRuntime({
      activeSessionId: session.id,
      sessions: [{
        id: session.id,
        title: session.title,
        status: session.status,
        agentId: session.agent_id,
        updatedAt: session.updated_at,
      }],
    }, storage);
    expect(readPersistedAgentRuntime(storage)).toMatchObject({
      version: 1,
      activeSessionId: session.id,
      sessions: [{ id: session.id }],
    });
  });
});

describe('Agent Phase 7 feature contract gates', () => {
  it.each(FLOW_NAMES)('%s produces the same canonical projection for legacy and new stores', (flowName) => {
    const {
      session: flowSession,
      workspace: flowWorkspace,
      initialWorkspace,
      events,
    } = createFlowScenario(flowName);
    const loaded = agentRuntimeReducer(initialAgentRuntimeState, {
      type: 'workspace_loaded',
      workspace: initialWorkspace,
    });
    const state = events.reduce(
      (current, streamEvent) => agentRuntimeReducer(current, {
        type: 'stream_event',
        event: streamEvent,
      }),
      loaded,
    );

    expect(projectNewRuntime(state)).toEqual(projectLegacyFixture(flowSession, flowWorkspace));
  });

  it('creates actionable attention items with cause, impact, recommendation and actions', () => {
    const { workspace: permissionWorkspace } = createFlowScenario('permission');
    const permissionState = agentRuntimeReducer(initialAgentRuntimeState, {
      type: 'workspace_loaded',
      workspace: permissionWorkspace,
    });
    const items = selectAttentionItems(permissionState, new Date('2026-06-20T00:05:00Z').getTime());

    expect(items[0]).toMatchObject({
      kind: 'permission',
      status: 'open',
    });
    expect(items[0]?.whatHappened).toBeTruthy();
    expect(items[0]?.impactScope).toBeTruthy();
    expect(items[0]?.recommendedAction).toBeTruthy();
    expect(items[0]?.actions.map((action) => action.id)).toEqual(['approve', 'reject']);
  });

  it('marks stale permissions as expired and only offers refresh', () => {
    const { workspace: permissionWorkspace } = createFlowScenario('permission');
    const state = agentRuntimeReducer(initialAgentRuntimeState, {
      type: 'workspace_loaded',
      workspace: permissionWorkspace,
    });
    const items = selectAttentionItems(state, new Date('2026-06-20T01:00:00Z').getTime());
    expect(items[0]).toMatchObject({
      kind: 'expired_permission',
      status: 'expired',
    });
    expect(items[0]?.actions.map((action) => action.id)).toEqual(['refresh']);
  });

  it('removes resolved tool and loop failures from the Attention Center', () => {
    const { workspace: loopWorkspace } = createFlowScenario('loop_guard');
    const recoveredWorkspace = {
      ...loopWorkspace,
      session: {
        ...loopWorkspace.session,
        metadata: {
          ...loopWorkspace.session.metadata,
          loop_guard: { blocked: false, history: [{ recovered_at: '2026-06-20T00:01:00Z' }] },
        },
      },
      recent_events: [
        ...loopWorkspace.recent_events,
        {
          id: 'evt_recovered',
          event_type: 'node_recovery_completed',
          message: 'Recovered',
          created_at: '2026-06-20T00:01:00Z',
          payload: {},
        },
      ],
    };
    const state = agentRuntimeReducer(initialAgentRuntimeState, {
      type: 'workspace_loaded',
      workspace: recoveredWorkspace,
    });
    expect(selectAttentionItems(state)).toEqual([]);
  });

  it('surfaces a child Agent pending permission as an actionable item', () => {
    const { workspace: subagentWorkspace } = createFlowScenario('subagent');
    subagentWorkspace.async_tasks.tasks[0] = {
      ...subagentWorkspace.async_tasks.tasks[0]!,
      status: 'running',
      health_status: 'waiting',
      has_pending_permission: true,
      pending_permission_part_id: 'part_child_permission',
      updated_at: '2026-06-20T00:00:00Z',
    };
    const state = agentRuntimeReducer(initialAgentRuntimeState, {
      type: 'workspace_loaded',
      workspace: subagentWorkspace,
    });
    const items = selectAttentionItems(state, new Date('2026-06-20T00:05:00Z').getTime());
    expect(items[0]).toMatchObject({
      kind: 'permission',
      title: 'review 等待审批',
    });
    expect(items[0]?.actions.map((action) => action.id)).toEqual(['approve', 'reject']);
  });

  it.each([
    ['resolve_permission', 'open_attention'],
    ['review_risks', 'open_tab'],
    ['run_tests', 'submit_prompt'],
    ['start_explore', 'start_subagent'],
    ['start_review', 'start_subagent'],
    ['continue_build', 'submit_prompt'],
    ['inspect_file', 'open_tab'],
    ['restart_failed_task', 'start_subagent'],
  ] as const)('routes %s to an executable %s intent', (actionType, intentType) => {
    const task = createFlowScenario('subagent').workspace.async_tasks.tasks[0]!;
    const intent = routeAgentNextAction({
      id: `action:${actionType}`,
      action_type: actionType,
      title: actionType,
      summary: `${actionType} summary`,
      priority: 'medium',
      source_task_id: actionType === 'restart_failed_task' ? task.task_id : undefined,
      payload: actionType === 'inspect_file'
        ? { path: 'src/app.ts' }
        : actionType.startsWith('start_')
          ? { subagent_type: actionType === 'start_review' ? 'review' : 'explore' }
          : {},
    }, [task]);
    expect(intent.type).toBe(intentType);
  });
});

describe('Agent command executor', () => {
  it('deduplicates the same in-flight command by semantic key', async () => {
    let resolveWorkspace: ((value: AgentWorkspace) => void) | undefined;
    const workspacePromise = new Promise<AgentWorkspace>((resolve) => {
      resolveWorkspace = resolve;
    });
    const transport = fakeTransport({
      getWorkspace: vi.fn(() => workspacePromise),
    });
    const executor = new AgentCommandExecutor(transport);
    const command = { type: 'refresh' as const, sessionId: session.id };

    const first = executor.execute(command);
    const second = executor.execute(command);

    expect(first).toBe(second);
    expect(transport.getWorkspace).toHaveBeenCalledTimes(1);
    resolveWorkspace?.(workspace);
    await expect(first).resolves.toMatchObject({ type: 'refresh', workspace });
  });

  it('preserves a created session when prompt submission fails', async () => {
    const transport = fakeTransport({
      prompt: vi.fn().mockRejectedValue(new Error('provider offline')),
    });
    const executor = new AgentCommandExecutor(transport);

    await expect(executor.execute({
      type: 'submit',
      currentSession: null,
      options: { content: 'Inspect the repository' },
    })).rejects.toMatchObject({
      name: 'AgentCommandFailure',
      partialSession: session,
    });
  });

  it('rejects empty permission decisions before transport', async () => {
    const transport = fakeTransport();
    const executor = new AgentCommandExecutor(transport);

    await expect(executor.execute({
      type: 'decide_permission',
      partId: 'perm_empty',
      decisions: [],
    })).rejects.toBeInstanceOf(AgentCommandFailure);
    expect(transport.decidePermission).not.toHaveBeenCalled();
  });
});

describe('Agent Workbench orchestration', () => {
  it('creates a session, submits the prompt once, and refreshes the workspace', async () => {
    localStorage.clear();
    const transport = fakeTransport();
    const { result } = renderHook(() => useAgentWorkbench(transport));

    await waitFor(() => expect(result.current.state.hydrated).toBe(true));
    await act(async () => {
      await result.current.actions.submitTask({ content: 'Inspect the repository', agentId: 'build' });
    });

    expect(transport.createSession).toHaveBeenCalledTimes(1);
    expect(transport.prompt).toHaveBeenCalledTimes(1);
    expect(transport.getWorkspace).toHaveBeenCalledWith(session.id);
    expect(result.current.state.activeOperation).toBeNull();
  });

  it('restores the active session and reconnects its event stream after refresh', async () => {
    const persisted = {
      activeSessionId: session.id,
      sessions: [{
        id: session.id,
        title: session.title,
        status: session.status,
        agentId: session.agent_id,
        updatedAt: session.updated_at,
      }],
    };
    const persistence = {
      read: vi.fn(() => ({ version: 1 as const, ...persisted })),
      write: vi.fn(),
    };
    const transport = fakeTransport();
    const { result } = renderHook(() => useAgentWorkbench(transport, persistence));

    await waitFor(() => expect(result.current.state.activeSessionId).toBe(session.id));
    await waitFor(() => expect(transport.getWorkspace).toHaveBeenCalledWith(session.id));
    await waitFor(() => expect(transport.connectStream).toHaveBeenCalledWith(
      session.id,
      '',
      expect.any(Object),
    ));
  });

  it('deduplicates concurrent decisions for the same permission', async () => {
    let resolveDecision: ((value: { session: AgentSession; part: AgentSession['parts'][number] }) => void) | undefined;
    const decisionPromise = new Promise<{ session: AgentSession; part: AgentSession['parts'][number] }>((resolve) => {
      resolveDecision = resolve;
    });
    const permissionPart: AgentSession['parts'][number] = {
      id: 'perm_1',
      session_id: session.id,
      type: 'permission',
      status: 'pending',
      title: 'Approve edit',
      content: '',
      payload: {},
      created_at: session.created_at,
    };
    const transport = fakeTransport({
      decidePermission: vi.fn(() => decisionPromise),
    });
    const persistence = {
      read: vi.fn(() => ({
        version: 1 as const,
        activeSessionId: session.id,
        sessions: [{
          id: session.id,
          title: session.title,
          status: session.status,
          agentId: session.agent_id,
          updatedAt: session.updated_at,
        }],
      })),
      write: vi.fn(),
    };
    const { result } = renderHook(() => useAgentWorkbench(transport, persistence));
    await waitFor(() => expect(result.current.state.activeSessionId).toBe(session.id));

    let first!: Promise<unknown>;
    let second!: Promise<unknown>;
    act(() => {
      first = result.current.actions.decidePermission('perm_1', [{ type: 'approve' }]);
      second = result.current.actions.decidePermission('perm_1', [{ type: 'approve' }]);
    });
    expect(transport.decidePermission).toHaveBeenCalledTimes(1);
    resolveDecision?.({ session, part: permissionPart });
    await act(async () => {
      await Promise.all([first, second]);
    });
  });

  it('retains a newly created session when the first prompt fails', async () => {
    localStorage.clear();
    const transport = fakeTransport({
      prompt: vi.fn().mockRejectedValue(new Error('provider offline')),
    });
    const { result } = renderHook(() => useAgentWorkbench(transport));
    await waitFor(() => expect(result.current.state.hydrated).toBe(true));

    await act(async () => {
      await expect(result.current.actions.submitTask({
        content: 'Keep the session',
        agentId: 'build',
      })).rejects.toThrow('会话已保留');
    });

    expect(result.current.state.session?.id).toBe(session.id);
    expect(result.current.state.activeSessionId).toBe(session.id);
    expect(result.current.state.error).toContain('会话已保留');
  });

  it('restarts SSE when a terminal session receives a follow-up prompt', async () => {
    const completedSession = { ...session, status: 'completed' as const };
    const completedWorkspace = { ...workspace, session: completedSession };
    const persistence = {
      read: vi.fn(() => ({
        version: 1 as const,
        activeSessionId: session.id,
        sessions: [{
          id: session.id,
          title: session.title,
          status: completedSession.status,
          agentId: session.agent_id,
          updatedAt: session.updated_at,
        }],
      })),
      write: vi.fn(),
    };
    const transport = fakeTransport({
      getWorkspace: vi.fn().mockResolvedValue(completedWorkspace),
      prompt: vi.fn().mockResolvedValue({ ...session, status: 'running' }),
    });
    const { result } = renderHook(() => useAgentWorkbench(transport, persistence));
    await waitFor(() => expect(transport.connectStream).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(result.current.state.session?.status).toBe('completed'));

    await act(async () => {
      await result.current.actions.submitTask({ content: 'Continue the task', agentId: 'build' });
    });

    await waitFor(() => expect(transport.connectStream).toHaveBeenCalledTimes(2));
  });

  it('virtualizes a 10,000 item timeline and keeps the latest content reachable', async () => {
    const timeline: AgentSessionUiTimelineItem[] = Array.from({ length: 10_000 }, (_, index) => ({
      id: `part_${index}`,
      part_id: `part_${index}`,
      type: 'text',
      status: 'completed',
      title: `Step ${index}`,
      content: `Output ${index}`,
      created_at: new Date(index * 1000).toISOString(),
    }));
    render(<div style={{ height: 600 }}><AgentRunTimeline timeline={timeline} /></div>);
    expect(screen.queryAllByRole('article').length).toBeLessThan(200);
  });

  it('restores composer text when submission fails', async () => {
    const AgentTaskComposer = (await import('../agent/components/AgentTaskComposer')).default;
    render(
      <AgentTaskComposer
        agents={[]}
        session={null}
        busy={false}
        onInterrupt={vi.fn()}
        onSubmit={vi.fn().mockRejectedValue(new Error('offline'))}
      />,
    );
    const input = screen.getByLabelText('任务目标');
    fireEvent.change(input, { target: { value: 'Keep my draft' } });
    fireEvent.click(screen.getByRole('button', { name: '提交任务' }));
    await waitFor(() => expect(input).toHaveValue('Keep my draft'));
  });

  it('exposes mobile shell drawers for sessions and attention', async () => {
    render(
      <AgentWorkbenchShell
        title="Task"
        subtitle="Workspace"
        connection="open"
        connectionLabel="实时连接"
        attentionCount={2}
        desktopSessionRail={<div>desktop sessions</div>}
        mobileSessionRail={<div>mobile sessions</div>}
        desktopAttentionRail={<div>desktop attention</div>}
        mobileAttentionRail={<div>mobile attention</div>}
        toolbar={null}
      >
        <main>workbench content</main>
      </AgentWorkbenchShell>,
    );

    fireEvent.click(screen.getByRole('button', { name: '打开会话' }));
    expect(await screen.findByText('mobile sessions')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    fireEvent.click(screen.getByRole('button', { name: '打开注意事项' }));
    expect(await screen.findByText('mobile attention')).toBeInTheDocument();
  });
});
