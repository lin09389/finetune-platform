import { describe, expect, it } from 'vitest'

import { mergeLoadedSessionRecord, parseAgentSessionState } from '../store/chatSessionState'

describe('chatSessionState helpers', () => {
  it('parses agent session metadata into store-ready state', () => {
    const parsed = parseAgentSessionState({
      last_agent_goal: 'Refactor chat flow',
      agent_mode: true,
      agent_status: 'running',
      execution_timeline: [
        {
          id: 'evt-1',
          type: 'tool_call',
          title: 'Read file',
          status: 'completed',
          tool_name: 'file_read',
          payload: { path: 'a.ts' },
          timestamp: '2026-04-09T10:00:00.000Z',
        },
      ],
      pending_confirmation: {
        action: 'file_patch',
        description: 'Apply patch',
        params: { patch: '...' },
        riskLevel: 'medium',
      },
      workspace_root: 'C:/workspace',
      auto_approve_safe_tools: true,
    })

    expect(parsed.promptDraft).toBe('Refactor chat flow')
    expect(parsed.agentMode).toBe(true)
    expect(parsed.agentTaskStatus).toBe('running')
    expect(parsed.agentTimeline[0]?.tool_name).toBe('file_read')
    expect(parsed.pendingAgentConfirmation?.riskLevel).toBe('medium')
    expect(parsed.agentWorkspaceRoot).toBe('C:/workspace')
    expect(parsed.autoApproveSafeTools).toBe(true)
  })

  it('merges loaded session data without dropping existing frontend fields', () => {
    const merged = mergeLoadedSessionRecord(
      {
        id: 'session-1',
        title: 'Old title',
        modelId: 'qwen',
        backend: 'ollama',
        createdAt: '2026-04-09T09:00:00.000Z',
        updatedAt: '2026-04-09T09:10:00.000Z',
        messageCount: 1,
        metadata: { branch: 'main' },
      },
      {
        id: 'session-1',
        title: 'New title',
        modelId: 'qwen2.5',
        backend: 'cloud',
        createdAt: '2026-04-09T09:00:00.000Z',
        updatedAt: '2026-04-09T10:00:00.000Z',
        messageCount: 3,
        metadata: { branch: 'feature' },
      }
    )

    expect(merged.title).toBe('New title')
    expect(merged.modelId).toBe('qwen2.5')
    expect(merged.backend).toBe('cloud')
    expect(merged.messageCount).toBe(3)
    expect(merged.metadata?.branch).toBe('feature')
  })
})
