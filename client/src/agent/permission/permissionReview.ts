/**
 * Pure helpers for coding-agent HITL review UI.
 * Derives human-readable titles and key fields from pending permission actions
 * (no I/O — same shapes as workspace.pending_permission).
 */

export interface PermissionActionLike {
  index?: number;
  name: string;
  args?: Record<string, unknown> | null;
  description?: string;
  allowed_decisions?: string[];
}

export interface PermissionReviewLike {
  part_id?: string;
  title?: string;
  content?: string;
  actions: PermissionActionLike[];
}

const WRITE_TOOLS = new Set(['write_file', 'edit_file']);
const EXEC_TOOLS = new Set(['execute']);
const TRAINING_TOOLS = new Set(['submit_training', 'resume_training', 'cancel_training']);

export function toolLabel(name: string): string {
  const n = String(name || '').trim();
  if (n === 'write_file') return '创建文件';
  if (n === 'edit_file') return '修改文件';
  if (n === 'execute') return '运行命令';
  if (n === 'submit_training') return '提交训练';
  if (n === 'resume_training') return '恢复训练';
  if (n === 'cancel_training') return '取消训练';
  return n || '工具';
}

export function extractFilePath(args: Record<string, unknown> | null | undefined): string | null {
  if (!args || typeof args !== 'object') return null;
  for (const key of ['file_path', 'path', 'target_file', 'filename']) {
    const value = args[key];
    if (typeof value === 'string' && value.trim()) {
      return value.trim().replace(/^\/workspace\//, '').replace(/^\/workspace$/, '.');
    }
  }
  return null;
}

export function extractCommand(args: Record<string, unknown> | null | undefined): string | null {
  if (!args || typeof args !== 'object') return null;
  for (const key of ['command', 'cmd']) {
    const value = args[key];
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  return null;
}

export function extractPrimaryTarget(action: PermissionActionLike): {
  kind: 'file' | 'command' | 'training' | 'other';
  label: string;
  detail: string | null;
} {
  const name = String(action.name || '');
  const args = (action.args || {}) as Record<string, unknown>;
  if (WRITE_TOOLS.has(name)) {
    const path = extractFilePath(args);
    return { kind: 'file', label: path || '未知文件', detail: path };
  }
  if (EXEC_TOOLS.has(name)) {
    const command = extractCommand(args);
    return { kind: 'command', label: command || '（无命令）', detail: command };
  }
  if (TRAINING_TOOLS.has(name)) {
    const proposal = typeof args.proposal_id === 'string' ? args.proposal_id : null;
    const taskId = typeof args.task_id === 'string' ? args.task_id : null;
    const detail = proposal || taskId;
    return { kind: 'training', label: detail || toolLabel(name), detail };
  }
  const path = extractFilePath(args);
  if (path) return { kind: 'file', label: path, detail: path };
  const command = extractCommand(args);
  if (command) return { kind: 'command', label: command, detail: command };
  return { kind: 'other', label: toolLabel(name), detail: null };
}

/** Short, pairing-style title for the whole permission batch. */
export function permissionReviewTitle(permission: PermissionReviewLike): string {
  const actions = permission.actions || [];
  if (actions.length === 0) {
    return permission.title || '需要你确认后继续';
  }
  if (actions.length === 1) {
    return singleActionTitle(actions[0]!);
  }
  const names = actions.map((a) => toolLabel(a.name));
  const unique = [...new Set(names)];
  if (unique.length === 1) {
    return `确认 ${actions.length} 次${unique[0]}？`;
  }
  return `确认 ${actions.length} 个操作？`;
}

export function singleActionTitle(action: PermissionActionLike): string {
  const name = String(action.name || '');
  const target = extractPrimaryTarget(action);
  if (name === 'edit_file') {
    return target.detail ? `允许修改 \`${target.detail}\`？` : '允许修改文件？';
  }
  if (name === 'write_file') {
    return target.detail ? `允许创建 \`${target.detail}\`？` : '允许创建文件？';
  }
  if (name === 'execute') {
    const cmd = target.detail || '';
    const short = cmd.length > 48 ? `${cmd.slice(0, 48)}…` : cmd;
    return short ? `允许运行 \`${short}\`？` : '允许运行命令？';
  }
  if (TRAINING_TOOLS.has(name)) {
    return `允许${toolLabel(name)}？`;
  }
  return `允许 ${toolLabel(name)}？`;
}

export function formatArgsPreview(
  args: Record<string, unknown> | null | undefined,
  options?: { maxChars?: number; omitKeys?: string[] },
): string | null {
  if (!args || typeof args !== 'object') return null;
  const omit = new Set(options?.omitKeys || []);
  const maxChars = options?.maxChars ?? 280;
  const entries = Object.entries(args).filter(([key]) => !omit.has(key));
  if (entries.length === 0) return null;
  // Prefer human-facing fields first.
  const preferred = ['file_path', 'path', 'command', 'old_string', 'new_string', 'content', 'proposal_id', 'task_id', 'checkpoint_name'];
  const ordered = [
    ...preferred.filter((key) => key in args && !omit.has(key)).map((key) => [key, args[key]] as const),
    ...entries.filter(([key]) => !preferred.includes(key)),
  ];
  const lines: string[] = [];
  for (const [key, value] of ordered) {
    let text: string;
    if (typeof value === 'string') {
      text = value.length > 120 ? `${value.slice(0, 120)}…` : value;
    } else {
      try {
        text = JSON.stringify(value);
      } catch {
        text = String(value);
      }
      if (text.length > 120) text = `${text.slice(0, 120)}…`;
    }
    lines.push(`${key}: ${text}`);
    if (lines.join('\n').length >= maxChars) break;
  }
  const joined = lines.join('\n');
  return joined.length > maxChars ? `${joined.slice(0, maxChars)}…` : joined;
}

export function contentSnippet(
  args: Record<string, unknown> | null | undefined,
  maxLines = 6,
): { label: string; text: string } | null {
  if (!args) return null;
  const content = typeof args.content === 'string' ? args.content : null;
  const newString = typeof args.new_string === 'string' ? args.new_string : null;
  const oldString = typeof args.old_string === 'string' ? args.old_string : null;
  if (newString != null || oldString != null) {
    const parts: string[] = [];
    if (oldString != null) parts.push(`- ${clipLines(oldString, Math.ceil(maxLines / 2))}`);
    if (newString != null) parts.push(`+ ${clipLines(newString, Math.ceil(maxLines / 2))}`);
    return { label: '变更摘要', text: parts.join('\n') };
  }
  if (content != null) {
    return { label: '将写入', text: clipLines(content, maxLines) };
  }
  return null;
}

function clipLines(text: string, maxLines: number): string {
  const lines = String(text).split(/\r?\n/);
  if (lines.length <= maxLines) return lines.join('\n');
  return `${lines.slice(0, maxLines).join('\n')}\n…`;
}

export function allowsDecision(action: PermissionActionLike, decision: string): boolean {
  const allowed = action.allowed_decisions;
  if (!allowed || allowed.length === 0) {
    return ['approve', 'reject', 'edit', 'respond'].includes(decision);
  }
  return allowed.map(String).includes(decision);
}

export function sessionTrustHint(actions: PermissionActionLike[]): string | null {
  const tools = [...new Set(actions.map((a) => String(a.name || '')).filter(Boolean))];
  const trustable = tools.filter((t) => WRITE_TOOLS.has(t) || EXEC_TOOLS.has(t));
  if (trustable.length === 0) return null;
  const labels = trustable.map(toolLabel).join('、');
  return `批准后，本会话内后续「${labels}」将不再反复请示。`;
}
