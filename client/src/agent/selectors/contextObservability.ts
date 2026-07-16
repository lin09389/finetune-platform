/**
 * Derive lightweight context observability for Agent Workbench UI.
 * Reads session.metadata written by the backend context pack + trajectory + tool offload.
 */

export type KnowledgeBindingStatus =
  | 'not_configured'
  | 'configured'
  | 'disabled'
  | 'error'
  | 'unknown';

export interface KnowledgeBindingView {
  status: KnowledgeBindingStatus;
  useKnowledge: boolean;
  source: string | null;
  collectionId: string | null;
  label: string;
  detail: string;
  tone: 'neutral' | 'ok' | 'warn' | 'muted';
}

export interface ContextRefreshView {
  changedFiles: string[];
  recentFailures: Array<{ tool: string; path: string | null; reason: string }>;
  changedCount: number;
  failureCount: number;
  toolOffloadCount: number;
  toolTruncateCount: number;
  recentOffloads: Array<{ tool: string; path: string | null; offloaded: boolean; truncated: boolean }>;
  hasSignal: boolean;
}

export interface ContextObservability {
  hasSignal: boolean;
  knowledge: KnowledgeBindingView;
  refresh: ContextRefreshView;
  projectRetrievalStatus: string | null;
  warnings: string[];
  virtualFileCount: number | null;
  secretRedactionHits: number | null;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function shortCollection(id: string | null): string {
  if (!id) return '';
  if (id.length <= 18) return id;
  return `${id.slice(0, 8)}…${id.slice(-6)}`;
}

function knowledgeView(raw: Record<string, unknown>, warnings: string[]): KnowledgeBindingView {
  const statusRaw = String(raw.status || '').trim().toLowerCase();
  const useKnowledge = raw.use_knowledge === true;
  const source = raw.source != null ? String(raw.source) : null;
  const collectionId =
    raw.collection_id != null && String(raw.collection_id).trim()
      ? String(raw.collection_id).trim()
      : null;

  let status: KnowledgeBindingStatus = 'unknown';
  if (
    statusRaw === 'configured'
    || statusRaw === 'disabled'
    || statusRaw === 'not_configured'
    || statusRaw === 'error'
  ) {
    status = statusRaw;
  } else if (useKnowledge && collectionId) {
    status = 'configured';
  } else if (warnings.some((w) => w.includes('knowledge_not_configured'))) {
    status = 'not_configured';
  } else if (warnings.some((w) => w.includes('knowledge_disabled'))) {
    status = 'disabled';
  } else if (warnings.some((w) => w.includes('knowledge'))) {
    status = 'error';
  } else {
    status = 'not_configured';
  }

  if (status === 'configured' && useKnowledge) {
    const src = source === 'session' ? '会话' : source === 'workspace' ? '工作区' : source || '绑定';
    return {
      status,
      useKnowledge: true,
      source,
      collectionId,
      label: `已用 · ${shortCollection(collectionId) || '知识库'}`,
      detail: `来源：${src}${collectionId ? ` · ${collectionId}` : ''}`,
      tone: 'ok',
    };
  }
  if (status === 'disabled') {
    return {
      status,
      useKnowledge: false,
      source,
      collectionId: null,
      label: '已关闭',
      detail: '本会话显式关闭了知识库检索',
      tone: 'muted',
    };
  }
  if (status === 'error') {
    return {
      status,
      useKnowledge: false,
      source,
      collectionId,
      label: '检索异常',
      detail: warnings.find((w) => w.includes('knowledge')) || '知识库检索失败（已降级，不阻断任务）',
      tone: 'warn',
    };
  }
  return {
    status: 'not_configured',
    useKnowledge: false,
    source,
    collectionId: null,
    label: '未绑定（可选）',
    detail: '未配置 knowledge collection；Agent 仍可使用 /workspace 与工具',
    tone: 'neutral',
  };
}

function refreshView(raw: Record<string, unknown>): ContextRefreshView {
  const changedFiles = Array.isArray(raw.changed_files)
    ? raw.changed_files.map((p) => String(p || '').trim()).filter(Boolean).slice(-12)
    : [];
  const recentFailures = Array.isArray(raw.recent_failures)
    ? raw.recent_failures
        .filter((item): item is Record<string, unknown> => !!item && typeof item === 'object')
        .map((item) => ({
          tool: String(item.tool || 'tool'),
          path: item.path != null ? String(item.path) : null,
          reason: String(item.reason || item.summary || '').slice(0, 200),
        }))
        .slice(-8)
    : [];
  const toolOffloadCount = typeof raw.tool_offload_count === 'number' ? raw.tool_offload_count : 0;
  const toolTruncateCount =
    typeof raw.tool_truncate_count === 'number' ? raw.tool_truncate_count : 0;
  const recentOffloads = Array.isArray(raw.recent_offloads)
    ? raw.recent_offloads
        .filter((item): item is Record<string, unknown> => !!item && typeof item === 'object')
        .map((item) => ({
          tool: String(item.tool || 'tool'),
          path: item.path != null ? String(item.path) : null,
          offloaded: item.offloaded === true,
          truncated: item.truncated === true,
        }))
        .slice(-12)
    : [];
  return {
    changedFiles,
    recentFailures,
    changedCount: changedFiles.length,
    failureCount: recentFailures.length,
    toolOffloadCount,
    toolTruncateCount,
    recentOffloads,
    hasSignal:
      changedFiles.length > 0
      || recentFailures.length > 0
      || toolOffloadCount > 0
      || toolTruncateCount > 0,
  };
}

export function selectContextObservability(
  metadata: Record<string, unknown> | null | undefined,
): ContextObservability {
  const meta = asRecord(metadata);
  const deep = asRecord(meta.deep_context);
  const eng = asRecord(deep.context_engineering);
  const knowledgeRaw = asRecord(eng.knowledge_binding || meta.knowledge_binding);
  const warnings: string[] = [];
  for (const bucket of [eng.warnings, meta.context_warnings, deep.warnings]) {
    if (Array.isArray(bucket)) {
      for (const w of bucket) {
        const text = String(w || '').trim();
        if (text && !warnings.includes(text)) warnings.push(text);
      }
    }
  }
  const pr = asRecord(eng.project_retrieval);
  const projectRetrievalStatus = pr.status != null ? String(pr.status) : null;
  const virtualFileCount =
    typeof eng.virtual_file_count === 'number'
      ? eng.virtual_file_count
      : typeof eng.file_count === 'number'
        ? eng.file_count
        : null;
  const secretRedaction = asRecord(eng.secret_redaction);
  const secretRedactionHits =
    typeof secretRedaction.hits === 'number' ? secretRedaction.hits : null;

  const knowledge = knowledgeView(knowledgeRaw, warnings);
  const refresh = refreshView(asRecord(meta.context_refresh));
  const hasEngineering = Object.keys(eng).length > 0 || Object.keys(knowledgeRaw).length > 0;
  const hasSignal = hasEngineering || refresh.hasSignal || warnings.length > 0;

  return {
    hasSignal,
    knowledge,
    refresh,
    projectRetrievalStatus,
    warnings: warnings.slice(0, 8),
    virtualFileCount,
    secretRedactionHits,
  };
}
