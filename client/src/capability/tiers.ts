/**
 * Frontend capability-tier helpers aligned with backend apps.capability_registry.
 */

export type CapabilityTier = 'ga' | 'beta' | 'experimental';

export interface ApiInfoCapabilityPayload {
  capability_tiers?: {
    ga?: string[];
    beta?: string[];
    experimental?: string[];
  };
  experimental_enabled?: boolean;
  experimental_capabilities?: Array<{
    id: string;
    enabled: boolean;
    high_risk?: boolean;
    mounts?: string[];
  }>;
}

/** Map SPA paths to backend capability ids (for badge + guard). */
export const ROUTE_CAPABILITY: Record<string, { id: string; tier: CapabilityTier }> = {
  '/dashboard': { id: 'device', tier: 'ga' },
  '/device': { id: 'device', tier: 'ga' },
  '/models': { id: 'models', tier: 'ga' },
  // Legacy SPA path; App redirects /modelhub → /models
  '/modelhub': { id: 'models', tier: 'ga' },
  '/datasets': { id: 'datasets', tier: 'ga' },
  '/training': { id: 'training', tier: 'ga' },
  '/history': { id: 'training', tier: 'ga' },
  '/training-compare': { id: 'training', tier: 'ga' },
  '/agent': { id: 'chat_sessions', tier: 'ga' },
  '/chat': { id: 'chat_sessions', tier: 'ga' },
  '/inference': { id: 'inference', tier: 'ga' },
  '/evaluation': { id: 'models', tier: 'ga' },
  '/deployment': { id: 'models', tier: 'ga' },
  '/knowledge': { id: 'knowledge_base', tier: 'ga' },
  '/memory': { id: 'memory', tier: 'beta' },
  '/workspace': { id: 'workspace', tier: 'beta' },
  '/project-context': { id: 'project_context', tier: 'beta' },
  '/gateway': { id: 'gateway', tier: 'experimental' },
  '/heartbeat': { id: 'heartbeat', tier: 'experimental' },
  '/mcp': { id: 'mcp', tier: 'experimental' },
  '/cua-control': { id: 'cua', tier: 'experimental' },
  '/cua-recorder': { id: 'action_recorder', tier: 'experimental' },
  // cloud-api maps to always-on api.cloud_chat (AGENT_AUXILIARY), NOT experimental registry
  '/cloud-api': { id: 'cloud_chat', tier: 'beta' },
};

export function tierLabel(tier: CapabilityTier): string {
  if (tier === 'ga') return 'GA';
  if (tier === 'beta') return 'Beta';
  return 'Exp';
}

/**
 * Tooltip copy for capability-tier badges, aligned with docs/capability-truth-table.md.
 * Returns null for GA (no badge shown, no tooltip needed).
 */
export function tierTooltip(tier: CapabilityTier): string | null {
  if (tier === 'ga') return null;
  if (tier === 'beta') return '已可用但接口/UI 可能变动，不建议生产使用';
  return '实验性能力，API/UI 可能变动，依赖缺失时显式失败';
}

export function isExperimentalRoute(path: string): boolean {
  const meta = ROUTE_CAPABILITY[path];
  return meta?.tier === 'experimental';
}

export function isExperimentalEnabled(info: ApiInfoCapabilityPayload | null | undefined): boolean {
  if (!info) {
    // Optimistic default for offline/dev: show experimental until info loads
    return true;
  }
  if (typeof info.experimental_enabled === 'boolean') {
    return info.experimental_enabled;
  }
  return true;
}
