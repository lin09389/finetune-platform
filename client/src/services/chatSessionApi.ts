import type { ChatMessage } from '../types'
import { API_BASE_URL } from './api'

export interface ChatSessionRecord {
  id: string
  title: string
  modelId: string
  backend: string
  createdAt: string
  updatedAt: string
  messageCount: number
  metadata: Record<string, unknown>
}

export interface ChatSessionMessagesPayload {
  messages: ChatMessage[]
}

export interface ChatSessionMessageCreatePayload {
  role: 'user' | 'assistant' | 'system'
  content: string
  metadata?: Record<string, unknown>
}

async function requestJson<T>(input: string, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init)
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(
      (errorData as { detail?: string }).detail || `Chat session request failed: ${response.status}`
    )
  }

  return (await response.json()) as T
}

function normalizeChatMessage(message: Record<string, unknown>): ChatMessage {
  return {
    id: String(message.id || ''),
    role: (message.role as ChatMessage['role']) || 'assistant',
    content: String(message.content || ''),
    timestamp:
      typeof message.created_at === 'string'
        ? message.created_at
        : typeof message.timestamp === 'string'
          ? message.timestamp
          : new Date().toISOString(),
    isLoading: Boolean(message.isLoading),
    knowledge_sources: Array.isArray(message.knowledge_sources)
      ? (message.knowledge_sources as ChatMessage['knowledge_sources'])
      : undefined,
    retrieval_info: message.retrieval_info as ChatMessage['retrieval_info'],
    memory_context: message.memory_context as ChatMessage['memory_context'],
    unified_context: message.unified_context as ChatMessage['unified_context'],
    raw_response: message.raw_response,
    attachments: Array.isArray(message.attachments)
      ? (message.attachments as ChatMessage['attachments'])
      : undefined,
    experiment_config: message.experiment_config as ChatMessage['experiment_config'],
    run_metrics: message.run_metrics as ChatMessage['run_metrics'],
    isEdited: Boolean(message.isEdited),
  }
}

export function normalizeChatSession(
  session: Record<string, unknown>,
  fallbackBackend = 'ollama'
): ChatSessionRecord {
  return {
    id: String(session.id || ''),
    title: String(session.title || 'New Chat'),
    modelId: String(session.model_id || session.modelId || ''),
    backend: String(session.backend || fallbackBackend),
    createdAt: String(session.created_at || session.createdAt || new Date().toISOString()),
    updatedAt: String(session.updated_at || session.updatedAt || new Date().toISOString()),
    messageCount: Number(session.message_count ?? session.messageCount ?? 0),
    metadata:
      session.metadata && typeof session.metadata === 'object'
        ? (session.metadata as Record<string, unknown>)
        : {},
  }
}

export async function listChatSessions(fallbackBackend?: string): Promise<ChatSessionRecord[]> {
  const data = await requestJson<{ sessions?: Record<string, unknown>[] }>(
    `${API_BASE_URL}/chat/sessions`
  )

  return (data.sessions || []).map((session) => normalizeChatSession(session, fallbackBackend))
}

export async function createChatSession(
  title: string,
  modelId?: string,
  fallbackBackend?: string
): Promise<ChatSessionRecord> {
  const session = await requestJson<Record<string, unknown>>(`${API_BASE_URL}/chat/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title,
      model_id: modelId,
    }),
  })

  return normalizeChatSession(session, fallbackBackend)
}

export async function getChatSession(
  sessionId: string,
  fallbackBackend?: string
): Promise<ChatSessionRecord> {
  const session = await requestJson<Record<string, unknown>>(
    `${API_BASE_URL}/chat/sessions/${sessionId}`
  )

  return normalizeChatSession(session, fallbackBackend)
}

export async function getChatSessionMessages(
  sessionId: string
): Promise<ChatSessionMessagesPayload> {
  const payload = await requestJson<{ messages?: Record<string, unknown>[] }>(
    `${API_BASE_URL}/chat/sessions/${sessionId}/messages`
  )

  return {
    messages: (payload.messages || []).map((message) => normalizeChatMessage(message)),
  }
}

export async function saveChatSessionMessage(
  sessionId: string,
  payload: ChatSessionMessageCreatePayload
): Promise<ChatMessage> {
  const message = await requestJson<Record<string, unknown>>(
    `${API_BASE_URL}/chat/sessions/${sessionId}/messages`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }
  )

  return normalizeChatMessage(message)
}

export async function persistChatRunToSession(
  sessionId: string,
  userPrompt: string,
  assistantContent: string,
  options?: {
    userMetadata?: Record<string, unknown>
    assistantMetadata?: Record<string, unknown>
  }
) {
  const userMessage = await saveChatSessionMessage(sessionId, {
    role: 'user',
    content: userPrompt,
    metadata: options?.userMetadata,
  })

  const assistantMessage = await saveChatSessionMessage(sessionId, {
    role: 'assistant',
    content: assistantContent,
    metadata: options?.assistantMetadata,
  })

  return {
    userMessage,
    assistantMessage,
  }
}

export async function deleteChatSession(sessionId: string): Promise<{ success: boolean }> {
  return requestJson<{ success: boolean }>(`${API_BASE_URL}/chat/sessions/${sessionId}`, {
    method: 'DELETE',
  })
}

export async function updateChatSessionMetadata(
  sessionId: string,
  metadata: Record<string, unknown>
): Promise<{ success: boolean; session_id: string; metadata: Record<string, unknown> }> {
  return requestJson<{ success: boolean; session_id: string; metadata: Record<string, unknown> }>(
    `${API_BASE_URL}/chat/sessions/${sessionId}/metadata`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        metadata,
      }),
    }
  )
}
