import axios from 'axios';
import { API_BASE_URL } from './api';

const API_BASE = `${API_BASE_URL}/memory`;

export type MemoryScope = 'user' | 'agent' | 'org';

export interface MemoryFile {
  id: string;
  path: string;
  relative_path: string;
  scope: MemoryScope;
  namespace: string;
  content: string;
  writable: boolean;
  version: number;
  updated_at: string;
  metadata: Record<string, unknown>;
}

export interface MemorySearchResult {
  file_id: string;
  path: string;
  scope: MemoryScope;
  namespace: string;
  snippet: string;
  score: number;
  updated_at: string;
  metadata: Record<string, unknown>;
}

export interface EpisodeEvent {
  session_id: string;
  role: string;
  content: string;
  created_at: string;
  metadata: Record<string, unknown>;
}

export interface ConsolidationResult {
  user_id: string;
  session_id?: string | null;
  episodes_scanned: number;
  memories_written: number;
}

export interface MigrationResult {
  user_id: string;
  migrated: number;
  skipped: number;
  items: Array<{ id?: string; type?: string; target: string }>;
}

export const memoryApi = {
  listFiles: async (scope: MemoryScope, namespace: string): Promise<MemoryFile[]> => {
    const params = new URLSearchParams({ scope, namespace });
    const response = await axios.get(`${API_BASE}/files?${params}`);
    return response.data;
  },

  getFile: async (fileId: string): Promise<MemoryFile> => {
    const response = await axios.get(`${API_BASE}/files/${fileId}`);
    return response.data;
  },

  updateFile: async (
    fileId: string,
    content: string,
    metadata: Record<string, unknown> = {},
  ): Promise<MemoryFile> => {
    const response = await axios.put(`${API_BASE}/files/${fileId}`, { content, metadata });
    return response.data;
  },

  search: async (payload: {
    query: string;
    scope?: MemoryScope;
    namespace?: string;
    user_id?: string;
    top_k?: number;
  }): Promise<MemorySearchResult[]> => {
    const response = await axios.post(`${API_BASE}/search`, {
      user_id: 'default',
      top_k: 10,
      ...payload,
    });
    return response.data;
  },

  consolidate: async (userId = 'default', sessionId?: string): Promise<ConsolidationResult> => {
    const response = await axios.post(`${API_BASE}/consolidate`, {
      user_id: userId,
      session_id: sessionId,
    });
    return response.data;
  },

  listEpisodes: async (userId = 'default', sessionId?: string, limit = 100): Promise<EpisodeEvent[]> => {
    const params = new URLSearchParams({ user_id: userId, limit: String(limit) });
    if (sessionId) params.append('session_id', sessionId);
    const response = await axios.get(`${API_BASE}/episodes?${params}`);
    return response.data.events || [];
  },

  migrateFromItems: async (userId = 'default'): Promise<MigrationResult> => {
    const response = await axios.post(`${API_BASE}/migrate-from-items`, { user_id: userId });
    return response.data;
  },
};

export const MEMORY_SCOPE_LABELS: Record<MemoryScope, string> = {
  user: '用户记忆',
  agent: 'Agent 记忆',
  org: '组织策略',
};
