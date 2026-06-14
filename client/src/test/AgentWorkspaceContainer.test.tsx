import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import AgentWorkspaceContainer from '../components/chat/AgentWorkspaceContainer';
import type { UseAgentAsyncTasksResult } from '../hooks/chat/useAgentAsyncTasks';
import type { UseAgentWorkspaceResult } from '../hooks/chat/useAgentWorkspace';
import type { UseAgentWorkspaceSelectionResult } from '../hooks/chat/useAgentWorkspaceSelection';
import { recoverAgentExecutionPlanNode } from '../services/api';
import type { AgentAsyncTask, AgentAsyncTaskMetrics, AgentWorkspace } from '../services/api';

vi.mock('../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/api')>();
  return {
    ...actual,
    recoverAgentExecutionPlanNode: vi.fn(async (_sessionId: string, _nodeId: string) => ({ workspace: workspace() })),
  };
});

vi.mock('../components/chat/AgentInspector', () => ({
  default: ({ workspace }: { workspace: AgentWorkspace | null }) => (
    <div data-testid="inspector">{workspace?.session.id}</div>
  ),
}));

vi.mock('../components/chat/AgentAsyncTasksPanel', () => ({
  default: ({ tasks, metrics }: { tasks: AgentAsyncTask[]; metrics: AgentAsyncTaskMetrics | null }) => (
    <div data-testid="async-tasks">{tasks.length}:{metrics?.total ?? 0}</div>
  ),
}));

function workspace(): AgentWorkspace {
  return {
    session: {
      id: 'ags_parent',
      agent_id: 'build',
      status: 'running',
      title: 'Build',
      metadata: {},
      parts: [],
      created_at: '2026-01-01T00:00:00',
      updated_at: '2026-01-01T00:00:00',
    },
    status_text: {},
    timeline: [],
    pending_permission: {
      part_id: 'part_permission',
      status: 'pending',
      title: 'edit_file',
      actions: [{
        index: 0,
        name: 'edit_file',
        args: { file_path: '/workspace/app.py' },
        allowed_decisions: ['approve', 'reject'],
      }],
    },
    diagnostics: {},
    async_tasks: {
      tasks: [{
        task_id: 'agt_1',
        parent_session_id: 'ags_parent',
        child_session_id: 'ags_child',
        previous_child_session_ids: [],
        agent_name: 'explore',
        status: 'running',
        input: {},
        result: {},
        diagnostics: {},
        duration_ms: null,
        queue_wait_ms: null,
        health_status: 'waiting',
        child_status: 'waiting_permission',
        has_pending_permission: true,
        pending_permission_part_id: 'child_permission',
        restart_count: 0,
        created_at: '2026-01-01T00:00:00',
        updated_at: '2026-01-01T00:00:00',
      }],
      metrics: {
        total: 1,
        by_status: { running: 1 },
        running: 1,
        failed: 0,
        cancelled: 0,
        completed: 0,
        attention: 0,
        recovery_count: 0,
        event_count: 0,
        last_event: null,
      },
    },
    artifacts: [{
      id: 'artifact_1',
      artifact_type: 'finding',
      type: 'finding',
      title: 'Key finding',
      summary: 'Project entry found',
      status: 'ready',
      source: { kind: 'task', id: 'agt_1', label: 'explore' },
      payload: {},
      source_task_id: 'agt_1',
      producer_agent: 'explore',
      created_at: '2026-01-01T00:00:00',
    }],
    changed_files: [],
    next_actions: [],
    execution_timeline: [{
      id: 'exec:part_tool',
      type: 'tool_call',
      title: 'read_file',
      status: 'completed',
      summary: 'Read file',
      source_part_id: 'part_tool',
      created_at: '2026-01-01T00:00:00',
      duration_ms: null,
      payload_excerpt: { tool: 'read_file' },
    }],
    recent_events: [],
    execution_plan: {
      schema_version: 'agent.execution.plan.v1',
      runtime: 'deepagents',
      backend_mode: 'workspace',
      thread_id: 'agent_session:ags_parent:deepagents',
      recursion_limit: 20,
      checkpointer: true,
      state_machine: 'agent_session.v1',
      plan_id: 'plan_ags_parent',
      session_id: 'ags_parent',
      goal: 'Build',
      status: 'running',
      current_node_id: 'tool:part_tool',
      nodes: [
        {
          id: 'understand_task',
          title: '理解任务与运行约束',
          description: '读取 runtime contract',
          agent_id: 'build',
          kind: 'agent',
          status: 'completed',
          depends_on: [],
        },
        {
          id: 'execute_primary_agent',
          title: '执行主 Agent 任务',
          description: '调用工具并产出结果',
          agent_id: 'build',
          kind: 'agent',
          status: 'running',
          depends_on: ['understand_task'],
          approval_policy: { requires_approval: true, tools: ['edit_file'] },
          retry_policy: { max_attempts: 1 },
        },
        {
          id: 'tool:part_tool',
          title: '工具调用：edit_file',
          description: '运行时工具调用节点。',
          agent_id: 'build',
          kind: 'tool',
          status: 'blocked',
          depends_on: ['execute_primary_agent'],
          source_part_id: 'part_tool',
          source_permission_part_id: 'part_permission',
          tool: 'edit_file',
          blocked_reason: '等待文件修改审批',
          recoverable: true,
          recovery_action: 'resume_node',
          recovery_reason: '审批被拒绝后可恢复',
          recovery_attempts: 0,
          started_at: '2026-01-01T00:00:00',
        },
        {
          id: 'subagent:agt_1',
          title: '子 Agent：explore',
          description: '探索项目结构',
          agent_id: 'explore',
          kind: 'subagent',
          status: 'failed',
          depends_on: ['execute_primary_agent'],
          source_task_id: 'agt_1',
          recoverable: true,
          recovery_action: 'restart_subagent',
          recovery_error: 'child failed',
          recovery_attempts: 1,
          last_recovery_at: '2026-01-01T00:01:00',
          output: {
            recovery_history: [{
              recovery_id: 'rec_1',
              action: 'restart_subagent',
              status: 'started',
              new_task_id: 'agt_2',
            }],
          },
          started_at: '2026-01-01T00:00:00',
        },
      ],
      edges: [
        { from: 'understand_task', to: 'execute_primary_agent', type: 'depends_on' },
        { from: 'execute_primary_agent', to: 'tool:part_tool', type: 'depends_on' },
        { from: 'execute_primary_agent', to: 'subagent:agt_1', type: 'depends_on' },
      ],
      created_at: '2026-01-01T00:00:00',
      updated_at: '2026-01-01T00:00:00',
      lifecycle: ['idle', 'running', 'completed'],
    },
    runtime: {
      workspace_root: 'C:/workspace',
      vfs_mounts: [{
        path: '/workspace/',
        kind: 'workspace',
        label: 'Project workspace',
        writable: true,
        description: 'Project files',
      }],
      skill_sources: [{
        name: 'builtin',
        virtual_path: '/skills/builtin/',
        priority: 10,
        available: true,
      }],
      memory_files: ['/memories/user.md'],
      execution_plan: {
        schema_version: 'agent.execution.plan.v1',
        runtime: 'deepagents',
        backend_mode: 'workspace',
        thread_id: 'agent_session:ags_parent:deepagents',
        recursion_limit: 20,
        checkpointer: true,
        state_machine: 'agent_session.v1',
        plan_id: 'plan_ags_parent',
        session_id: 'ags_parent',
        goal: 'Build',
        status: 'running',
        current_node_id: 'execute_primary_agent',
        nodes: [],
        edges: [],
        created_at: '2026-01-01T00:00:00',
        updated_at: '2026-01-01T00:00:00',
        lifecycle: ['idle', 'running', 'completed'],
      },
    },
    vfs_mounts: [{
      path: '/workspace/',
      kind: 'workspace',
      label: 'Project workspace',
      writable: true,
      description: 'Project files',
    }],
    skill_sources: [{
      name: 'builtin',
      virtual_path: '/skills/builtin/',
      priority: 10,
      available: true,
    }],
  };
}

describe('AgentWorkspaceContainer', () => {
  it('passes one workspace-derived data source to inspector and async task panel', async () => {
    const currentWorkspace = workspace();
    const agentWorkspace = {
      workspace: currentWorkspace,
      loading: false,
      error: null,
      refresh: vi.fn(),
      startTask: vi.fn(),
      cancelTask: vi.fn(),
      restartTask: vi.fn(),
      runNextAction: vi.fn(),
    } satisfies UseAgentWorkspaceResult;
    const asyncTasks = {
      tasks: currentWorkspace.async_tasks.tasks,
      metrics: currentWorkspace.async_tasks.metrics,
      loading: false,
      statusFilter: 'all',
      focusedTaskId: null,
      expandedTaskId: null,
      setStatusFilter: vi.fn(),
      focusTask: vi.fn(),
      expandTask: vi.fn(),
      refresh: agentWorkspace.refresh,
      startTask: agentWorkspace.startTask,
      cancelTask: agentWorkspace.cancelTask,
      restartTask: agentWorkspace.restartTask,
    } satisfies UseAgentAsyncTasksResult;
    const workspaceSelection = {
      selection: { type: 'run', sessionId: 'ags_parent' },
      selectRun: vi.fn(),
      selectTimelineItem: vi.fn(),
      selectAsyncTask: vi.fn(),
      selectPermission: vi.fn(),
      selectArtifact: vi.fn(),
      selectFile: vi.fn(),
      selectCommand: vi.fn(),
    } satisfies UseAgentWorkspaceSelectionResult;

    const props = {
      onActiveKeyChange: vi.fn(),
      changedFiles: 0,
      runContent: <div>run</div>,
      configContent: <div>config</div>,
      progressContent: <div>progress</div>,
      fileTreeContent: <div>files</div>,
      agentWorkspace,
      asyncTasks,
      workspaceSelection,
      sessionId: 'ags_parent',
      onSubmitPermission: vi.fn(),
      onOpenFile: vi.fn(),
      onRunNextAction: vi.fn(),
    };
    const { rerender } = render(<AgentWorkspaceContainer activeKey="execution" {...props} />);

    expect(screen.getByTestId('inspector')).toHaveTextContent('ags_parent');
    rerender(<AgentWorkspaceContainer activeKey="subagents" {...props} />);
    expect(screen.getByTestId('async-tasks')).toHaveTextContent('1:1');
    rerender(<AgentWorkspaceContainer activeKey="plan" {...props} />);
    expect(screen.getByText('Agent Orchestration')).toBeInTheDocument();
    expect(screen.getAllByText('执行主 Agent 任务').length).toBeGreaterThan(0);
    expect(screen.getByText('tool edit_file')).toBeInTheDocument();
    expect(screen.getAllByText('part part_tool').length).toBeGreaterThan(0);
    expect(screen.getAllByText('permission part_permission').length).toBeGreaterThan(0);
    expect(screen.getAllByText('task agt_1').length).toBeGreaterThan(0);
    expect(screen.getAllByText('等待文件修改审批').length).toBeGreaterThan(0);
    expect(screen.getByText('审批被拒绝后可恢复')).toBeInTheDocument();
    expect(screen.getByText('recovery started -> agt_2')).toBeInTheDocument();
    expect(screen.getByText('重启子任务')).toBeInTheDocument();
    fireEvent.click(screen.getByText('恢复执行'));
    await waitFor(() => expect(recoverAgentExecutionPlanNode).toHaveBeenCalledWith('ags_parent', 'tool:part_tool', { action: 'resume_node' }));
    expect(agentWorkspace.refresh).toHaveBeenCalled();
    expect(asyncTasks.refresh).toHaveBeenCalled();
    rerender(<AgentWorkspaceContainer activeKey="artifacts" {...props} />);
    expect(screen.getByText('Key finding')).toBeInTheDocument();
    rerender(<AgentWorkspaceContainer activeKey="approvals" {...props} />);
    expect(screen.getByText('Approval Inbox')).toBeInTheDocument();
    rerender(<AgentWorkspaceContainer activeKey="execution" {...props} />);
    expect(screen.getByText('Execution Console')).toBeInTheDocument();
    rerender(<AgentWorkspaceContainer activeKey="runtime" {...props} />);
    expect(screen.getByText('/workspace/')).toBeInTheDocument();
  });
});
