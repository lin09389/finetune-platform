/**
 * Agent 会话状态中文标签的唯一定义。
 *
 * 之前散落在 AgentSessionRail / AgentEnvironmentRail / workbenchSelectors 三处，
 * 维护时容易漂移，现统一收敛到此处。
 */

export const SESSION_STATUS_LABELS: Record<string, string> = {
  idle: '待命',
  running: '运行中',
  planning: '规划中',
  executing: '执行中',
  verifying: '验证中',
  repairing: '修复中',
  waiting_permission: '等待审批',
  waiting_approval: '等待审批',
  completed: '已完成',
  failed: '失败',
  interrupted: '已停止',
  needs_manual_review: '需要复核',
};

/**
 * 返回会话状态的中文标签；未知状态原样回退。
 */
export function sessionStatusLabel(status: string | null | undefined): string {
  if (!status) return '待命';
  const label = SESSION_STATUS_LABELS[status];
  return label ?? status;
}
