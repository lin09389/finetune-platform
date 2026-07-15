/**
 * Pure projection of Step 1/2 session progress metadata for Workbench UI.
 * Source of truth remains session.metadata (tool_metrics / completion_gate / recovery_state).
 */

export interface SessionToolMetricsView {
  toolsTotal: number;
  toolsFailed: number;
  observeTotal: number;
  verifyAttempted: boolean;
  verifyOk: boolean;
  trajectoryBlocks: number;
  hitlCount: number;
  budgetSoftWarned: boolean;
  budgetHardBlocked: boolean;
  lastTool: string | null;
}

export interface SessionCompletionGateView {
  completedOk: boolean;
  hasWrites: boolean;
  diffVisible: boolean;
  verifyAttempted: boolean;
  verifyOk: boolean;
  gaps: string[];
  summary: string;
  writtenPaths: string[];
  status: string | null;
}

export interface SessionRecoveryView {
  requireObservationBeforeRetry: boolean;
  lastFailedCommand: string | null;
  blindRetryBlocks: number;
}

export interface SessionProgressView {
  hasSignal: boolean;
  metrics: SessionToolMetricsView | null;
  gate: SessionCompletionGateView | null;
  recovery: SessionRecoveryView | null;
  /** Compact status chip for activity bar / rail */
  chips: Array<{ key: string; label: string; tone: 'default' | 'ok' | 'warn' | 'danger' }>;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function asNumber(value: unknown, fallback = 0): number {
  const n = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function asBoolFlag(value: unknown): boolean {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') return value !== 0;
  if (typeof value === 'string') return value === '1' || value.toLowerCase() === 'true';
  return false;
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}

export function selectToolMetrics(metadata: Record<string, unknown> | null | undefined): SessionToolMetricsView | null {
  const raw = asRecord(metadata?.tool_metrics);
  if (!raw) return null;
  return {
    toolsTotal: asNumber(raw.tools_total),
    toolsFailed: asNumber(raw.tools_failed),
    observeTotal: asNumber(raw.observe_total),
    verifyAttempted: asBoolFlag(raw.verify_attempted),
    verifyOk: asBoolFlag(raw.verify_ok),
    trajectoryBlocks: asNumber(raw.trajectory_blocks),
    hitlCount: asNumber(raw.hitl_count),
    budgetSoftWarned: asBoolFlag(raw.budget_soft_warned),
    budgetHardBlocked: asBoolFlag(raw.budget_hard_blocked),
    lastTool: asString(raw.last_tool),
  };
}

export function selectCompletionGate(
  metadata: Record<string, unknown> | null | undefined,
): SessionCompletionGateView | null {
  const raw = asRecord(metadata?.completion_gate);
  if (!raw) return null;
  const gaps = Array.isArray(raw.gaps) ? raw.gaps.map(String).filter(Boolean) : [];
  const written = Array.isArray(raw.written_paths)
    ? raw.written_paths.map(String).filter(Boolean)
    : [];
  return {
    completedOk: asBoolFlag(raw.completed_ok),
    hasWrites: asBoolFlag(raw.has_writes),
    diffVisible: raw.diff_visible === undefined ? true : asBoolFlag(raw.diff_visible),
    verifyAttempted: asBoolFlag(raw.verify_attempted),
    verifyOk: asBoolFlag(raw.verify_ok),
    gaps,
    summary: asString(raw.summary) || '',
    writtenPaths: written,
    status: asString(raw.status),
  };
}

export function selectRecoveryState(
  metadata: Record<string, unknown> | null | undefined,
): SessionRecoveryView | null {
  const raw = asRecord(metadata?.recovery_state);
  if (!raw) return null;
  const lastFailed = asRecord(raw.last_failed_execute);
  return {
    requireObservationBeforeRetry: asBoolFlag(raw.require_observation_before_retry),
    lastFailedCommand: asString(lastFailed?.command),
    blindRetryBlocks: asNumber(raw.blind_retry_blocks),
  };
}

export function selectSessionProgress(
  metadata: Record<string, unknown> | null | undefined,
): SessionProgressView {
  const metrics = selectToolMetrics(metadata);
  const gate = selectCompletionGate(metadata);
  const recovery = selectRecoveryState(metadata);
  const chips: SessionProgressView['chips'] = [];

  // Activity bar: keep chips short and quiet (match workbench micro-badges).
  if (metrics) {
    chips.push({
      key: 'tools',
      label: metrics.toolsFailed > 0
        ? `${metrics.toolsTotal} 工具 · ${metrics.toolsFailed} 失败`
        : `${metrics.toolsTotal} 工具`,
      tone: metrics.toolsFailed > 0 ? 'warn' : 'default',
    });
    if (metrics.verifyOk) {
      chips.push({ key: 'verify', label: '已验证', tone: 'ok' });
    } else if (metrics.verifyAttempted) {
      chips.push({ key: 'verify', label: '验证失败', tone: 'danger' });
    }
    if (metrics.budgetHardBlocked) {
      chips.push({ key: 'budget', label: '预算耗尽', tone: 'danger' });
    } else if (metrics.budgetSoftWarned) {
      chips.push({ key: 'budget', label: '探索偏多', tone: 'warn' });
    }
  }

  if (recovery?.requireObservationBeforeRetry) {
    chips.push({ key: 'recovery', label: '先观察', tone: 'warn' });
  }

  if (gate && !gate.completedOk) {
    chips.push({
      key: 'gate',
      label: '完成缺口',
      tone: 'danger',
    });
  } else if (gate?.completedOk) {
    chips.push({
      key: 'gate',
      label: '可收尾',
      tone: 'ok',
    });
  }

  const hasSignal = Boolean(
    metrics
    || gate
    || recovery?.requireObservationBeforeRetry
    || (recovery?.blindRetryBlocks ?? 0) > 0,
  );

  return { hasSignal, metrics, gate, recovery, chips };
}

export function gateGapLabel(gap: string): string {
  switch (gap) {
    case 'verification_required':
      return '验证未通过';
    case 'verification_missing':
      return '缺少验证';
    case 'diff_coverage_required':
      return '缺少可审 diff';
    case 'manual_review':
      return '需人工检查';
    default:
      return gap;
  }
}
