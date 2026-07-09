/**
 * Agent 运行时「当前活动」派生逻辑。
 *
 * 后端已发送 tool_call_started / phase_change / context_preparing 等 SSE 事件，
 * 但此前 reducer 只提取 current_phase，丢弃了「正在调用工具 X」「正在准备上下文」
 * 等语义。本模块负责把这些事件转化为用户可读的即时活动摘要。
 */

import type { AgentSessionEvent } from '../../services/api';
import type { AgentRuntimeState } from '../runtime/agentRuntime';

export type AgentActivityKind = 'thinking' | 'tool' | 'command' | 'context' | 'phase' | 'streaming';

export interface AgentActivity {
  /** 用户可读的活动摘要，如「正在调用工具 read_file」 */
  label: string;
  /** 补充信息，如工具参数摘要 */
  detail?: string;
  /** 该活动开始的时间戳（Date.now()），用于计算已耗时 */
  startedAt: number;
  /** 活动类别，用于 CSS 样式与生命周期管理 */
  kind: AgentActivityKind;
}

const PHASE_LABELS: Record<string, string> = {
  planning: '正在规划',
  executing: '正在执行',
  verifying: '正在验证',
  repairing: '正在修复',
  thinking: '正在思考',
  idle: '待命',
};

/**
 * 把后端 phase 值翻译为用户可读的活动文案。
 */
export function phaseLabel(phase: string | undefined): string {
  if (!phase) return '正在处理';
  return PHASE_LABELS[phase] || `正在${phase}`;
}

/**
 * 从工具调用的 payload 中提取简短的参数摘要，用于活动状态栏。
 * 例如 read_file 的 { file_path: '/workspace/a.ts' } -> '/workspace/a.ts'
 */
export function toolInputSummary(payload: Record<string, unknown> | undefined): string | undefined {
  if (!payload) return undefined;
  // 常见工具参数字段，按优先级尝试
  const candidates = ['file_path', 'path', 'command', 'query', 'pattern', 'url', 'name'];
  for (const key of candidates) {
    const value = payload[key];
    if (typeof value === 'string' && value) {
      // 路径只取最后一段，避免过长
      if (key === 'file_path' || key === 'path') {
        const segments = value.replace(/\\/g, '/').split('/').filter(Boolean);
        return segments[segments.length - 1] || value;
      }
      return value.length > 60 ? `${value.slice(0, 57)}...` : value;
    }
  }
  // command 可能是数组
  const command = payload.command;
  if (Array.isArray(command) && command.length > 0) {
    return command.map(String).join(' ').slice(0, 60);
  }
  return undefined;
}

/**
 * 从 SSE 事件派生当前活动状态。
 * 返回 null 表示该事件不产生/不清除活动状态（调用方应保持原值）。
 * 返回 undefined 表示该事件清除当前活动状态。
 * 返回 AgentActivity 表示该事件设置新的活动状态。
 */
export function activityFromEvent(
  event: AgentSessionEvent,
  now: number,
): AgentActivity | null | undefined {
  switch (event.event_type) {
    case 'context_preparing':
      return { label: '正在准备上下文', startedAt: now, kind: 'context' };
    case 'context_ready':
      return undefined; // 清除 context 类活动
    case 'phase_change':
      return { label: phaseLabel(event.phase), startedAt: now, kind: 'phase' };
    case 'model_stream_started':
      return { label: '正在生成回复', startedAt: now, kind: 'streaming' };
    case 'model_stream_completed':
    case 'model_stream_failed':
      return undefined;
    case 'tool_call_started': {
      const toolName = event.tool || String(event.payload?.tool || event.payload?.name || '工具');
      return {
        label: `正在调用工具 ${toolName}`,
        detail: toolInputSummary(event.payload?.input || event.payload),
        startedAt: now,
        kind: 'tool',
      };
    }
    case 'tool_call_completed':
    case 'tool_call_failed':
      return undefined;
    case 'command_started': {
      const cmd = event.payload?.command;
      const detail = Array.isArray(cmd)
        ? cmd.map(String).join(' ').slice(0, 60)
        : typeof cmd === 'string' ? cmd.slice(0, 60) : undefined;
      return { label: '正在执行命令', detail, startedAt: now, kind: 'command' };
    }
    case 'command_completed':
    case 'command_failed':
      return undefined;
    // 会话终态：清除全部活动
    case 'session_completed':
    case 'session_failed':
    case 'session_interrupted':
    case 'session_blocked':
      return undefined;
    default:
      return null; // 不关心的事件，保持原值
  }
}

const RUNNING_STATUSES = new Set([
  'running',
  'planning',
  'executing',
  'verifying',
  'repairing',
]);

/**
 * 返回当前应显示的活动状态。
 * 仅在 session 处于运行态时返回 currentActivity，否则返回 null。
 */
export function selectCurrentActivity(state: AgentRuntimeState): AgentActivity | null {
  if (!state.currentActivity) return null;
  const status = state.session?.status;
  if (status && !RUNNING_STATUSES.has(status)) return null;
  return state.currentActivity;
}
