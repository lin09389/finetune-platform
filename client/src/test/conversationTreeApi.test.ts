import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../services/api', () => ({
  API_BASE_URL: 'http://localhost:8000',
}));

import {
  createConversationBranch,
  fetchConversationTreeState,
  saveConversationMessage,
  switchConversationToMainTimeline,
} from '../services/conversationTreeApi';

describe('conversationTreeApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('loads tree and branches through the canonical endpoints', async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          nodes: {
            'msg-1': {
              id: 'msg-1',
              role: 'user',
              content: 'hello',
              timestamp: '2026-04-09T00:00:00.000Z',
              parent_id: null,
              children_ids: [],
            },
          },
          root_id: 'msg-1',
          current_branch_id: null,
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          branches: [
            {
              id: 'branch-1',
              session_id: 'session-1',
              name: 'alt',
              created_at: '2026-04-09T00:00:00.000Z',
              root_message_id: 'msg-1',
              message_count: 2,
            },
          ],
        }),
      } as Response) as typeof fetch;

    const state = await fetchConversationTreeState('session-1');

    expect(String(vi.mocked(global.fetch).mock.calls[0]?.[0])).toBe(
      'http://localhost:8000/chat/session-1/tree',
    );
    expect(String(vi.mocked(global.fetch).mock.calls[1]?.[0])).toBe(
      'http://localhost:8000/chat/session-1/branches',
    );
    expect(state.tree.root_id).toBe('msg-1');
    expect(state.branches[0]?.id).toBe('branch-1');
  });

  it('creates branches, switches to main line, and saves messages with canonical payloads', async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          branch: { id: 'branch-2' },
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          session_id: 'session-1',
          metadata: { current_branch_id: null },
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 'msg-2',
          session_id: 'session-1',
          role: 'assistant',
          content: 'saved reply',
        }),
      } as Response) as typeof fetch;

    const branch = await createConversationBranch('session-1', 'msg-1', 'Reply 10:00');
    const switched = await switchConversationToMainTimeline('session-1');
    const saved = await saveConversationMessage('session-1', 'assistant', 'saved reply', {
      source: 'playground',
    });

    expect(branch.branch?.id).toBe('branch-2');
    expect(switched.metadata.current_branch_id).toBeNull();
    expect(saved.id).toBe('msg-2');

    expect(vi.mocked(global.fetch).mock.calls[0]?.[1]).toMatchObject({
      method: 'POST',
    });
    expect(JSON.parse(String(vi.mocked(global.fetch).mock.calls[0]?.[1]?.body))).toEqual({
      session_id: 'session-1',
      from_message_id: 'msg-1',
      branch_name: 'Reply 10:00',
    });

    expect(vi.mocked(global.fetch).mock.calls[1]?.[1]).toMatchObject({
      method: 'PUT',
    });
    expect(JSON.parse(String(vi.mocked(global.fetch).mock.calls[2]?.[1]?.body))).toEqual({
      role: 'assistant',
      content: 'saved reply',
      metadata: { source: 'playground' },
    });
  });
});
