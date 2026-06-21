export type AgentAttentionKind =
  | 'permission'
  | 'tool_failure'
  | 'loop_guard'
  | 'subagent_manual'
  | 'recovery_failure'
  | 'connection_interruption'
  | 'expired_permission'
  | 'protocol_unknown'
  | 'protocol_malformed'
  | 'operation_error';

export type AgentAttentionSeverity = 'critical' | 'high' | 'medium' | 'low';
export type AgentAttentionStatus = 'open' | 'in_progress' | 'resolved' | 'expired';

export interface AgentAttentionAction {
  id: 'approve' | 'reject' | 'refresh' | 'recover' | 'restart_subagent' | 'dismiss';
  label: string;
  danger?: boolean;
  primary?: boolean;
  payload?: Record<string, unknown>;
}

export interface AgentAttentionItem {
  id: string;
  kind: AgentAttentionKind;
  severity: AgentAttentionSeverity;
  status: AgentAttentionStatus;
  title: string;
  occurredAt: string;
  whatHappened: string;
  impactScope: string;
  recommendedAction: string;
  actions: AgentAttentionAction[];
  sourceEventId?: string;
  sessionId?: string;
  expiresAt?: string;
  resolvedAt?: string;
  dedupeKey: string;
}
