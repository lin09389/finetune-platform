import axios from 'axios';
import { API_BASE_URL } from './api';

const API_BASE = `${API_BASE_URL}/memory`;

export interface Memory {
  id: string;
  content: string;
  type: string;
  importance: number;
  created_at: string;
  last_accessed: string;
  access_count: number;
  relevance?: number;
  vector_state?: string;
  storage_mode?: string;
}

export interface MemoryStats {
  total_memories: number;
  vector_collection_count: number;
  collection_name: string;
}

export interface MemorySummary {
  total_count: number;
  by_type: Record<string, string[]>;
  recent_memories: Memory[];
}

export const memoryApi = {
  recall: async (
    query: string,
    userId = 'default',
    topK = 10,
    memoryType?: string,
  ): Promise<Memory[]> => {
    const response = await axios.post(`${API_BASE}/recall?user_id=${userId}`, {
      query,
      top_k: topK,
      memory_type: memoryType,
    });
    return response.data.memories;
  },

  listMemories: async (
    userId = 'default',
    memoryType?: string,
    limit = 50,
  ): Promise<{
    memories: Memory[];
    count: number;
  }> => {
    const params = new URLSearchParams({ user_id: userId, limit: String(limit) });
    if (memoryType) params.append('memory_type', memoryType);
    const response = await axios.get(`${API_BASE}/?${params}`);
    return {
      memories: response.data.memories || [],
      count: response.data.total || 0,
    };
  },

  addMemory: async (
    content: string,
    memoryType = 'knowledge',
    importance = 0.5,
    metadata: Record<string, unknown> = {},
    userId = 'default',
  ): Promise<Memory> => {
    const response = await axios.post(`${API_BASE}/?user_id=${userId}`, {
      content,
      memory_type: memoryType,
      importance,
      metadata,
    });
    return response.data;
  },

  updateMemory: async (
    memoryId: string,
    payload: {
      content?: string;
      importance?: number;
      metadata?: Record<string, unknown>;
    },
    userId = 'default',
  ): Promise<Memory> => {
    const response = await axios.put(`${API_BASE}/${memoryId}?user_id=${userId}`, payload);
    return response.data;
  },

  deleteMemory: async (memoryId: string, userId = 'default'): Promise<boolean> => {
    const response = await axios.delete(`${API_BASE}/${memoryId}?user_id=${userId}`);
    return response.data.success;
  },

  clearAll: async (userId = 'default'): Promise<boolean> => {
    const response = await axios.delete(`${API_BASE}/clear?user_id=${userId}`);
    return response.data.success;
  },

  getSummary: async (userId = 'default'): Promise<MemorySummary> => {
    const response = await axios.get(`${API_BASE}/summary?user_id=${userId}`);
    return response.data.summary;
  },

  getStats: async (userId = 'default'): Promise<MemoryStats> => {
    const response = await axios.get(`${API_BASE}/stats/summary?user_id=${userId}`);
    return response.data;
  },

  exportState: async (userId = 'default'): Promise<Record<string, unknown>> => {
    const response = await axios.get(`${API_BASE}/export?user_id=${userId}`);
    return response.data.state;
  },

  importState: async (state: Record<string, unknown>, userId = 'default'): Promise<boolean> => {
    const response = await axios.post(`${API_BASE}/import?user_id=${userId}`, state);
    return response.data.success;
  },
};

export const MEMORY_TYPES: Record<string, { label: string; color: string; icon: string }> = {
  personal: { label: '个人信息', color: 'green', icon: '👤' },
  preference: { label: '偏好', color: 'blue', icon: '❤️' },
  project: { label: '项目', color: 'purple', icon: '📁' },
  skill: { label: '技能', color: 'orange', icon: '⚡' },
  habit: { label: '习惯', color: 'cyan', icon: '🔄' },
  history: { label: '历史', color: 'default', icon: '📜' },
  knowledge: { label: '知识', color: 'gold', icon: '📚' },
};
