import type { AgentPendingConfirmation, AgentTaskStatus, AgentTimelineEvent } from '../types'
import type { ChatSessionRecord } from '../services/chatSessionApi'
import type { ChatSession } from './chatStore'

export interface ParsedAgentSessionState {
  promptDraft: string | null
  agentMode: boolean
  agentTaskStatus: AgentTaskStatus
  agentTimeline: AgentTimelineEvent[]
  pendingAgentConfirmation: AgentPendingConfirmation | null
  agentWorkspaceRoot: string
  autoApproveSafeTools: boolean
}

export function parseAgentSessionState(
  metadata: Record<string, unknown> | undefined
): ParsedAgentSessionState {
  const sessionMetadata = metadata || {}

  const agentTaskStatus =
    typeof sessionMetadata.agent_status === 'string'
      ? (sessionMetadata.agent_status as AgentTaskStatus)
      : 'idle'

  const pendingAgentConfirmation =
    sessionMetadata.pending_confirmation &&
    typeof sessionMetadata.pending_confirmation === 'object'
      ? (sessionMetadata.pending_confirmation as AgentPendingConfirmation)
      : null

  const agentWorkspaceRoot =
    typeof sessionMetadata.workspace_root === 'string' ? sessionMetadata.workspace_root : ''

  const promptDraft =
    typeof sessionMetadata.last_agent_goal === 'string' ? sessionMetadata.last_agent_goal : null

  const agentTimeline = Array.isArray(sessionMetadata.execution_timeline)
    ? sessionMetadata.execution_timeline.map((event, index) => {
        const rawEvent = (event || {}) as Record<string, unknown>
        return {
          id:
            typeof rawEvent.id === 'string'
              ? rawEvent.id
              : `session_event_${index}`,
          type:
            typeof rawEvent.type === 'string'
              ? (rawEvent.type as AgentTimelineEvent['type'])
              : 'task_status',
          title:
            typeof rawEvent.title === 'string'
              ? rawEvent.title
              : typeof rawEvent.stage === 'string'
                ? rawEvent.stage
                : 'Session event',
          description:
            typeof rawEvent.description === 'string' ? rawEvent.description : undefined,
          status:
            typeof rawEvent.status === 'string'
              ? (rawEvent.status as AgentTimelineEvent['status'])
              : undefined,
          tool_name:
            typeof rawEvent.tool_name === 'string' ? rawEvent.tool_name : undefined,
          payload:
            rawEvent.payload && typeof rawEvent.payload === 'object'
              ? (rawEvent.payload as Record<string, unknown>)
              : undefined,
          createdAt:
            typeof rawEvent.createdAt === 'string'
              ? rawEvent.createdAt
              : typeof rawEvent.timestamp === 'string'
                ? rawEvent.timestamp
                : new Date().toISOString(),
        }
      })
    : []

  return {
    promptDraft,
    agentMode: Boolean(sessionMetadata.agent_mode),
    agentTaskStatus,
    agentTimeline,
    pendingAgentConfirmation,
    agentWorkspaceRoot,
    autoApproveSafeTools: Boolean(sessionMetadata.auto_approve_safe_tools),
  }
}

export function mergeLoadedSessionRecord(
  existingSession: ChatSession,
  loadedSession: ChatSessionRecord
): ChatSession {
  return {
    ...existingSession,
    title: loadedSession.title || existingSession.title,
    modelId: loadedSession.modelId || existingSession.modelId,
    backend: loadedSession.backend || existingSession.backend,
    messageCount: loadedSession.messageCount ?? existingSession.messageCount,
    updatedAt: loadedSession.updatedAt || existingSession.updatedAt,
    metadata: loadedSession.metadata || existingSession.metadata || {},
  }
}
