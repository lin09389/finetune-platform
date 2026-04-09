import type { AgentPendingConfirmation, AgentTaskStatus, AgentTimelineEvent } from '../types'

export interface ChatAgentState {
  agentMode: boolean
  agentTaskStatus: AgentTaskStatus
  agentTimeline: AgentTimelineEvent[]
  pendingAgentConfirmation: AgentPendingConfirmation | null
  agentWorkspaceRoot: string
  autoApproveSafeTools: boolean
}

export const initialChatAgentState: ChatAgentState = {
  agentMode: false,
  agentTaskStatus: 'idle',
  agentTimeline: [],
  pendingAgentConfirmation: null,
  agentWorkspaceRoot: '',
  autoApproveSafeTools: false,
}

export function appendAgentTimelineEvent(
  events: AgentTimelineEvent[],
  event: AgentTimelineEvent,
  limit = 200
) {
  return [...events, event].slice(-limit)
}

export function replaceAgentTimelineEvents(events: AgentTimelineEvent[], limit = 200) {
  return events.slice(-limit)
}

export function resetAgentRuntimeState(): Pick<
  ChatAgentState,
  'agentTaskStatus' | 'agentTimeline' | 'pendingAgentConfirmation'
> {
  return {
    agentTaskStatus: 'idle',
    agentTimeline: [],
    pendingAgentConfirmation: null,
  }
}
