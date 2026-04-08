/**
 * 增强版记忆系统 API 服务
 * 支持知识图谱、短期记忆、MCP协议
 */
import axios from 'axios'
import { API_BASE_URL } from './api'

const API_BASE = `${API_BASE_URL}/memory`

export interface Entity {
  id: string
  name: string
  entity_type: string
  attributes: Record<string, unknown>
  confidence: number
  created_at: string
  updated_at: string
  access_count: number
}

export interface Relation {
  id: string
  source_id: string
  target_id: string
  relation_type: string
  weight: number
  evidence: string
  confidence: number
}

export interface Memory {
  id: string
  content: string
  type: string
  importance: number
  created_at: string
  last_accessed: string
  access_count: number
  relevance?: number
}

export interface ProcessResult {
  message_stored: boolean
  entities_extracted: Entity[]
  relations_extracted: Relation[]
  facts_extracted: Memory[]
  active_entities: string[]
  context: string
}

export interface GraphStats {
  total_entities: number
  total_relations: number
  entity_types: Record<string, number>
  relation_types: Record<string, number>
}

export interface SessionSummary {
  session_duration: number
  message_count: number
  active_entities: string[]
  active_topics: string[]
  key_facts_count: number
  average_importance: number
}

export interface MCPResource {
  uri: string
  name: string
  description: string
  mimeType: string
  type: string
}

export interface MCPSearchResult {
  uri: string
  name: string
  description: string
  score: number
  contentPreview: string
}

export const memoryApi = {
  processMessage: async (message: string, userId = 'default', sessionId?: string): Promise<ProcessResult> => {
    const response = await axios.post(`${API_BASE}/process`, {
      message,
      role: 'user',
      user_id: userId,
      session_id: sessionId,
      extract_memories: true
    })
    return response.data.result
  },

  extractMemories: async (message: string): Promise<{
    entities: Entity[]
    relations: Relation[]
    facts: Memory[]
  }> => {
    const response = await axios.post(`${API_BASE}/extract`, {
      message,
      role: 'user'
    })
    return response.data.extraction
  },

  recall: async (query: string, userId = 'default', topK = 10, memoryType?: string): Promise<Memory[]> => {
    const response = await axios.post(`${API_BASE}/recall`, {
      query,
      user_id: userId,
      top_k: topK,
      memory_type: memoryType
    })
    return response.data.memories
  },

  listMemories: async (userId = 'default', memoryType?: string, limit = 50): Promise<{
    memories: Memory[]
    count: number
  }> => {
    const params = new URLSearchParams({ user_id: userId, limit: String(limit) })
    if (memoryType) params.append('memory_type', memoryType)
    const response = await axios.get(`${API_BASE}/?${params}`)
    return {
      memories: response.data.memories || [],
      count: response.data.total || 0
    }
  },

  deleteMemory: async (memoryId: string, userId = 'default'): Promise<boolean> => {
    const response = await axios.delete(`${API_BASE}/${memoryId}?user_id=${userId}`)
    return response.data.success
  },

  clearAll: async (userId = 'default'): Promise<boolean> => {
    const response = await axios.delete(`${API_BASE}/clear?user_id=${userId}`)
    return response.data.success
  },

  getSummary: async (userId = 'default'): Promise<{
    total_count: number
    by_type: Record<string, string[]>
    knowledge_graph: GraphStats
  }> => {
    const response = await axios.get(`${API_BASE}/summary?user_id=${userId}`)
    return response.data.summary
  },

  getContext: async (query: string, userId = 'default', sessionId?: string): Promise<string> => {
    const params = new URLSearchParams({ query, user_id: userId })
    if (sessionId) params.append('session_id', sessionId)
    const response = await axios.get(`${API_BASE}/context?${params}`)
    return response.data.context
  },

  getStats: async (userId = 'default'): Promise<{
    total_memories: number
    knowledge_graph: GraphStats
    short_term_memory: SessionSummary
  }> => {
    const response = await axios.get(`${API_BASE}/stats/summary?user_id=${userId}`)
    return response.data
  },

  exportState: async (userId = 'default'): Promise<Record<string, unknown>> => {
    const response = await axios.get(`${API_BASE}/export?user_id=${userId}`)
    return response.data.state
  },

  importState: async (state: Record<string, unknown>, userId = 'default'): Promise<boolean> => {
    const response = await axios.post(`${API_BASE}/import?user_id=${userId}`, state)
    return response.data.success
  }
}

export const graphApi = {
  addEntity: async (name: string, entityType: string, attributes?: Record<string, unknown>, confidence = 0.5): Promise<{
    entityId: string
    isNew: boolean
  }> => {
    const response = await axios.post(`${API_BASE}/graph/entities`, {
      name,
      entity_type: entityType,
      attributes: attributes || {},
      confidence
    })
    return {
      entityId: response.data.entity_id,
      isNew: response.data.is_new
    }
  },

  addRelation: async (sourceName: string, targetName: string, relationType: string, evidence = ''): Promise<string> => {
    const response = await axios.post(`${API_BASE}/graph/relations`, {
      source_name: sourceName,
      target_name: targetName,
      relation_type: relationType,
      evidence
    })
    return response.data.relation_id
  },

  getEntity: async (entityId: string): Promise<Entity> => {
    const response = await axios.get(`${API_BASE}/graph/entities/${entityId}`)
    return response.data.entity
  },

  getEntityContext: async (entityId: string, depth = 2): Promise<{
    entity: Entity
    relations: Relation[]
    related_entities: Entity[]
  }> => {
    const response = await axios.post(`${API_BASE}/graph/context`, {
      entity_id: entityId,
      depth
    })
    return response.data.context
  },

  findPath: async (sourceId: string, targetId: string, maxDepth = 4): Promise<Relation[][]> => {
    const response = await axios.post(`${API_BASE}/graph/path`, {
      source_id: sourceId,
      target_id: targetId,
      max_depth: maxDepth
    })
    return response.data.paths
  },

  search: async (query: string, entityTypes?: string[], limit = 10): Promise<Entity[]> => {
    const response = await axios.post(`${API_BASE}/graph/search`, {
      query,
      entity_types: entityTypes,
      limit
    })
    return response.data.results
  },

  getStats: async (): Promise<GraphStats> => {
    const response = await axios.get(`${API_BASE}/graph/stats`)
    return response.data.stats
  },

  deleteEntity: async (entityId: string): Promise<boolean> => {
    const response = await axios.delete(`${API_BASE}/graph/entities/${entityId}`)
    return response.data.success
  },

  getAllEntities: async (): Promise<Entity[]> => {
    const stats = await graphApi.getStats()
    const allEntities: Entity[] = []
    for (const type of Object.keys(stats.entity_types)) {
      const results = await graphApi.search('', [type], 100)
      allEntities.push(...results)
    }
    return allEntities
  },

  getAllRelations: async (): Promise<Relation[]> => {
    const response = await axios.get(`${API_BASE}/graph/relations`)
    return response.data.relations || []
  }
}

export const sessionApi = {
  list: async (): Promise<string[]> => {
    const response = await axios.get(`${API_BASE}/sessions`)
    return response.data.sessions
  },

  getContext: async (sessionId: string, maxTokens = 4000): Promise<{
    context: string
    summary: SessionSummary
  }> => {
    const response = await axios.get(`${API_BASE}/sessions/${sessionId}?max_tokens=${maxTokens}`)
    return {
      context: response.data.context,
      summary: response.data.summary
    }
  },

  addMessage: async (sessionId: string, role: string, content: string, entities?: string[]): Promise<boolean> => {
    const response = await axios.post(`${API_BASE}/sessions/${sessionId}/messages`, {
      session_id: sessionId,
      role,
      content,
      entities
    })
    return response.data.success
  },

  clear: async (sessionId: string): Promise<boolean> => {
    const response = await axios.delete(`${API_BASE}/sessions/${sessionId}`)
    return response.data.success
  },

  getActiveEntities: async (sessionId: string, threshold = 0.3): Promise<string[]> => {
    const response = await axios.get(`${API_BASE}/sessions/${sessionId}/active-entities?threshold=${threshold}`)
    return response.data.entities
  }
}

export const mcpApi = {
  listResources: async (type?: string, limit = 50): Promise<MCPResource[]> => {
    const params = new URLSearchParams({ limit: String(limit) })
    if (type) params.append('type', type)
    const response = await axios.get(`${API_BASE}/mcp/resources?${params}`)
    return response.data.resources
  },

  readResource: async (uri: string): Promise<{
    uri: string
    mimeType: string
    text: string
    metadata: Record<string, unknown>
  }> => {
    const response = await axios.get(`${API_BASE}/mcp/resources/${encodeURIComponent(uri)}`)
    return response.data.content
  },

  search: async (query: string, types?: string[], limit = 10): Promise<MCPSearchResult[]> => {
    const response = await axios.post(`${API_BASE}/mcp/search`, {
      query,
      types,
      limit
    })
    return response.data.results
  },

  queryGraph: async (entityId: string, depth = 2, relationTypes?: string[]): Promise<Record<string, unknown>> => {
    const response = await axios.post(`${API_BASE}/mcp/graph/query`, {
      entity_id: entityId,
      depth,
      relation_types: relationTypes
    })
    return response.data.result
  },

  addMemory: async (content: string, memoryType = 'knowledge', entities?: string[], userId = 'default'): Promise<{
    success: boolean
    memoryId?: string
    entitiesCreated: number
    relationsCreated: number
  }> => {
    const response = await axios.post(`${API_BASE}/mcp/memories`, {
      content,
      memory_type: memoryType,
      entities,
      user_id: userId
    })
    return response.data.result
  },

  getStats: async (): Promise<{
    resourcesAvailable: number
    handlersRegistered: number
    knowledgeGraph?: GraphStats
  }> => {
    const response = await axios.get(`${API_BASE}/mcp/stats`)
    return response.data.stats
  }
}

export const ENTITY_TYPES: Record<string, { label: string; color: string; icon: string }> = {
  person: { label: '人物', color: '#52c41a', icon: '👤' },
  project: { label: '项目', color: '#722ed1', icon: '📁' },
  skill: { label: '技能', color: '#fa8c16', icon: '⚡' },
  concept: { label: '概念', color: '#13c2c2', icon: '💡' },
  tool: { label: '工具', color: '#eb2f96', icon: '🔧' },
  organization: { label: '组织', color: '#2f54eb', icon: '🏢' },
  location: { label: '地点', color: '#1890ff', icon: '📍' },
  event: { label: '事件', color: '#f5222d', icon: '📅' },
  preference: { label: '偏好', color: '#faad14', icon: '❤️' },
  habit: { label: '习惯', color: '#a0d911', icon: '🔄' }
}

export const RELATION_TYPES: Record<string, { label: string; color: string }> = {
  knows: { label: '知道', color: '#52c41a' },
  works_on: { label: '从事', color: '#722ed1' },
  uses: { label: '使用', color: '#fa8c16' },
  prefers: { label: '偏好', color: '#eb2f96' },
  has_skill: { label: '拥有技能', color: '#13c2c2' },
  related_to: { label: '相关', color: '#1890ff' },
  part_of: { label: '属于', color: '#faad14' },
  located_at: { label: '位于', color: '#2f54eb' },
  happened_at: { label: '发生于', color: '#f5222d' },
  causes: { label: '导致', color: '#a0d911' }
}

export const MEMORY_TYPES: Record<string, { label: string; color: string; icon: string }> = {
  personal: { label: '个人信息', color: 'green', icon: '👤' },
  preference: { label: '偏好', color: 'blue', icon: '❤️' },
  project: { label: '项目', color: 'purple', icon: '📁' },
  skill: { label: '技能', color: 'orange', icon: '⚡' },
  habit: { label: '习惯', color: 'cyan', icon: '🔄' },
  history: { label: '历史', color: 'default', icon: '📜' },
  knowledge: { label: '知识', color: 'gold', icon: '📚' },
  fact: { label: '事实', color: 'geekblue', icon: '📌' }
}
