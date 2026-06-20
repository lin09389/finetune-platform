import type {
  AgentPart,
  AgentSession,
  AgentSessionEvent,
  AgentWorkspace,
} from '../../services/api';

const createdAt = '2026-06-20T00:00:00Z';

export const FLOW_NAMES = [
  'session_restore',
  'prompt_output',
  'tool_timeline',
  'execution_plan',
  'interrupt',
  'permission',
  'loop_guard',
  'node_recovery',
  'subagent',
  'files_diff_editor',
  'terminal',
  'artifacts_next_actions',
] as const;

export type AgentFlowName = typeof FLOW_NAMES[number];

function part(type: AgentPart['type'], id: string, title: string, status: AgentPart['status'] = 'completed'): AgentPart {
  return {
    id,
    session_id: 'ags_contract',
    type,
    status,
    title,
    content: title,
    payload: type === 'command' ? { terminal_id: 'term_contract' } : {},
    created_at: createdAt,
  };
}

export interface AgentFlowScenario {
  session: AgentSession;
  workspace: AgentWorkspace;
  initialWorkspace: AgentWorkspace;
  events: AgentSessionEvent[];
}

function eventForPart(item: AgentPart, index: number): AgentSessionEvent {
  const eventType = item.type === 'tool_call'
    ? 'tool_call_started'
    : item.type === 'command'
      ? 'command_completed'
      : 'model_stream_completed';
  return {
    id: `evt_part_${index}`,
    session_id: item.session_id,
    event_type: eventType,
    message: item.title || item.type,
    payload: {},
    created_at: new Date(new Date(createdAt).getTime() + index * 1000).toISOString(),
    session_status: 'running',
    part: item,
  };
}

export function createFlowScenario(name: AgentFlowName): AgentFlowScenario {
  const parts: AgentPart[] = [part('text', 'part_prompt', '用户任务')];
  const status: AgentSession['status'] = name === 'interrupt'
    ? 'interrupted'
    : name === 'permission'
      ? 'waiting_permission'
      : name === 'loop_guard'
        ? 'needs_manual_review'
        : 'running';
  if (['prompt_output', 'tool_timeline'].includes(name)) parts.push(part('text', 'part_output', '模型输出'));
  if (name === 'tool_timeline') parts.push(part('tool_call', 'part_tool', 'read_file'));
  if (name === 'terminal') parts.push(part('command', 'part_command', 'npm test'));

  const session: AgentSession = {
    id: 'ags_contract',
    agent_id: 'build',
    status,
    title: name,
    project_path: 'C:/workspace/project',
    metadata: name === 'loop_guard' ? { loop_guard: { blocked: true, blocked_reason: 'Repeated failure' } } : {},
    parts,
    created_at: createdAt,
    updated_at: createdAt,
  };
  const workspace: AgentWorkspace = {
    session,
    status_text: { current_phase: status },
    timeline: parts.map((item) => ({
      id: item.id,
      part_id: item.id,
      session_id: session.id,
      type: item.type,
      status: item.status,
      title: item.title,
      content: item.content,
      created_at: item.created_at,
      payload: item.payload,
    })),
    pending_permission: name === 'permission' ? {
      part_id: 'part_permission',
      status: 'pending',
      title: '编辑文件',
      content: 'edit_file',
      actions: [{
        index: 0,
        name: 'edit_file',
        args: { path: 'src/app.ts' },
        allowed_decisions: ['approve', 'reject'],
      }],
    } : null,
    diagnostics: {},
    async_tasks: {
      tasks: name === 'subagent' ? [{
        task_id: 'task_review',
        parent_session_id: session.id,
        previous_child_session_ids: [],
        agent_name: 'review',
        status: 'failed',
        input: { description: 'Review changes' },
        result: {},
        error: 'Review failed',
        restart_count: 0,
        created_at: createdAt,
        updated_at: createdAt,
      }] : [],
      metrics: {
        total: name === 'subagent' ? 1 : 0,
        by_status: name === 'subagent' ? { failed: 1 } : {},
        running: 0,
        failed: name === 'subagent' ? 1 : 0,
        cancelled: 0,
        completed: 0,
        attention: name === 'subagent' ? 1 : 0,
        recovery_count: 0,
        event_count: 0,
      },
    },
    artifacts: ['files_diff_editor', 'artifacts_next_actions'].includes(name) ? [{
      id: 'artifact_change',
      artifact_type: 'file_change',
      title: 'src/app.ts',
      summary: 'Updated app',
      payload: { preview: '+ change' },
    }] : [],
    changed_files: name === 'files_diff_editor' ? [{
      path: 'src/app.ts',
      status: 'modified',
      summary: 'Updated app',
    }] : [],
    next_actions: name === 'artifacts_next_actions' ? [{
      id: 'next_review',
      action_type: 'start_review',
      title: 'Review',
      summary: 'Review changes',
      priority: 'medium',
      payload: {},
    }] : [],
    recent_events: name === 'loop_guard' ? [{
      id: 'evt_loop',
      event_type: 'loop_guard_triggered',
      message: 'Repeated failure',
      created_at: createdAt,
      payload: {},
    }] : [],
    execution_plan: ['execution_plan', 'node_recovery'].includes(name) ? {
      schema_version: 'agent.execution.plan.v1',
      runtime: 'deepagents',
      backend_mode: 'filesystem',
      checkpointer: true,
      state_machine: 'agent_session.v1',
      goal: name,
      status: name === 'node_recovery' ? 'blocked' : 'running',
      nodes: [{
        id: 'node_build',
        title: 'Build',
        status: name === 'node_recovery' ? 'failed' : 'running',
        recoverable: name === 'node_recovery',
        recovery_action: name === 'node_recovery' ? 'retry_node' : null,
      }],
      edges: [],
      lifecycle: [],
    } : null,
  };
  const initialSession: AgentSession = {
    ...session,
    status: 'running',
    parts: [],
  };
  const initialWorkspace: AgentWorkspace = {
    ...workspace,
    session: initialSession,
    timeline: [],
  };
  const events: AgentSessionEvent[] = [];
  for (const [index, item] of parts.entries()) {
    if (item.id === 'part_output') {
      events.push(eventForPart({ ...item, content: '' }, index + 1));
      events.push({
        id: 'evt_output_delta',
        session_id: session.id,
        event_type: 'part_delta',
        chunk_type: 'part_delta',
        message: '模型输出增量',
        payload: { part_id: item.id },
        delta: item.content,
        created_at: new Date(new Date(createdAt).getTime() + (index + 1.5) * 1000).toISOString(),
        session_status: 'running',
      });
    } else {
      events.push(eventForPart(item, index + 1));
    }
  }
  events.push({
    id: 'evt_final_status',
    session_id: session.id,
    event_type: status === 'interrupted'
      ? 'session_interrupted'
      : status === 'needs_manual_review'
        ? 'session_failed'
        : status === 'waiting_permission'
          ? 'permission_asked'
          : 'phase_change',
    message: status,
    payload: {},
    created_at: new Date(new Date(createdAt).getTime() + 20_000).toISOString(),
    session_status: status,
  });
  return { session, workspace, initialWorkspace, events };
}
