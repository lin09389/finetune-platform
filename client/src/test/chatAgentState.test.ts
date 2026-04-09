import { describe, expect, it } from 'vitest'
import type { AgentTimelineEvent } from '../types'

import {
  appendAgentTimelineEvent,
  initialChatAgentState,
  replaceAgentTimelineEvents,
  resetAgentRuntimeState,
} from '../store/chatAgentState'

describe('chatAgentState helpers', () => {
  it('provides a stable initial agent state contract', () => {
    expect(initialChatAgentState.agentMode).toBe(false)
    expect(initialChatAgentState.agentTaskStatus).toBe('idle')
    expect(initialChatAgentState.agentTimeline).toEqual([])
    expect(initialChatAgentState.pendingAgentConfirmation).toBeNull()
  })

  it('caps appended and replaced timeline events', () => {
    const events: AgentTimelineEvent[] = Array.from({ length: 205 }, (_, index) => ({
      id: `evt-${index}`,
      type: 'task_status' as const,
      title: `Event ${index}`,
      createdAt: `2026-04-09T10:${String(index % 60).padStart(2, '0')}:00.000Z`,
    }))

    const appended = events.reduce(
      (acc, event) => appendAgentTimelineEvent(acc, event, 3),
      [] as AgentTimelineEvent[]
    )
    const replaced = replaceAgentTimelineEvents(events, 5)

    expect(appended).toHaveLength(3)
    expect(appended[0]?.id).toBe('evt-202')
    expect(replaced).toHaveLength(5)
    expect(replaced[0]?.id).toBe('evt-200')
  })

  it('resets only the volatile runtime fields', () => {
    expect(resetAgentRuntimeState()).toEqual({
      agentTaskStatus: 'idle',
      agentTimeline: [],
      pendingAgentConfirmation: null,
    })
  })
})
