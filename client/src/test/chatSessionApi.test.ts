import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../services/api', () => ({
  API_BASE_URL: 'http://localhost:8000',
}));

import {
  clearChatSessionMessages,
  createChatSession,
  deleteChatSessionMessage,
  deleteChatSession,
  getChatSession,
  getChatSessionMessages,
  listChatSessions,
  persistChatRunToSession,
  replaceChatSessionMessages,
  updateChatSessionMessage,
  updateChatSessionMetadata,
} from '../services/chatSessionApi';

describe('chatSessionApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('normalizes session list and session detail through canonical endpoints', async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          sessions: [
            {
              id: 'session-1',
              title: 'Main',
              model_id: 'qwen',
              backend: 'ollama',
              created_at: '2026-04-09T00:00:00.000Z',
              updated_at: '2026-04-09T01:00:00.000Z',
              message_count: 3,
              metadata: { current_branch_id: 'branch-1' },
            },
          ],
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 'session-1',
          title: 'Main',
          model_id: 'qwen',
          backend: 'ollama',
          created_at: '2026-04-09T00:00:00.000Z',
          updated_at: '2026-04-09T01:00:00.000Z',
          message_count: 3,
          metadata: { current_branch_id: 'branch-1' },
        }),
      } as Response) as typeof fetch;

    const sessions = await listChatSessions();
    const session = await getChatSession('session-1');

    expect(String(vi.mocked(global.fetch).mock.calls[0]?.[0])).toBe(
      'http://localhost:8000/chat/sessions?limit=100',
    );
    expect(String(vi.mocked(global.fetch).mock.calls[1]?.[0])).toBe(
      'http://localhost:8000/chat/sessions/session-1',
    );
    expect(sessions[0]?.messageCount).toBe(3);
    expect(session.metadata.current_branch_id).toBe('branch-1');
  });

  it('creates sessions, updates metadata, and loads messages with normalized payloads', async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 'session-2',
          title: 'Follow-up',
          model_id: 'llama3',
          backend: 'cloud',
          created_at: '2026-04-09T02:00:00.000Z',
          updated_at: '2026-04-09T02:00:00.000Z',
          message_count: 0,
          metadata: {},
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          session_id: 'session-2',
          metadata: { agent_mode: true },
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          messages: [
            {
              id: 'msg-1',
              role: 'assistant',
              content: 'hello',
              created_at: '2026-04-09T02:05:00.000Z',
              metadata: {
                knowledge_sources: [
                  {
                    id: 'chunk-1',
                    source: 'guide.md',
                    score: 0.88,
                    content_preview: 'context',
                  },
                ],
                retrieval_info: {
                  query: 'hello',
                  method: 'unified',
                  total_results: 1,
                  retrieval_time: 0.01,
                },
              },
            },
          ],
        }),
      } as Response) as typeof fetch;

    const created = await createChatSession('Follow-up', 'llama3', 'cloud');
    const updated = await updateChatSessionMetadata('session-2', {
      agent_mode: true,
    });
    const messages = await getChatSessionMessages('session-2');

    expect(created.backend).toBe('cloud');
    expect(updated.metadata.agent_mode).toBe(true);
    expect(messages.messages[0]?.timestamp).toBe('2026-04-09T02:05:00.000Z');
    expect(messages.messages[0]?.knowledge_sources?.[0]?.source).toBe('guide.md');
    expect(messages.messages[0]?.retrieval_info?.method).toBe('unified');

    expect(vi.mocked(global.fetch).mock.calls[0]?.[1]).toMatchObject({
      method: 'POST',
    });
    expect(JSON.parse(String(vi.mocked(global.fetch).mock.calls[0]?.[1]?.body))).toEqual({
      title: 'Follow-up',
      model_id: 'llama3',
      backend: 'cloud',
    });
    expect(vi.mocked(global.fetch).mock.calls[1]?.[1]).toMatchObject({
      method: 'PUT',
    });
    expect(JSON.parse(String(vi.mocked(global.fetch).mock.calls[1]?.[1]?.body))).toEqual({
      metadata: { agent_mode: true },
    });
    expect(String(vi.mocked(global.fetch).mock.calls[2]?.[0])).toBe(
      'http://localhost:8000/chat/sessions/session-2/messages?limit=200',
    );
  });

  it('persists canonical user and assistant messages through the session adapter', async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 'msg-user',
          role: 'user',
          content: 'hello',
          created_at: '2026-04-09T03:00:00.000Z',
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 'msg-assistant',
          role: 'assistant',
          content: 'world',
          created_at: '2026-04-09T03:00:02.000Z',
        }),
      } as Response) as typeof fetch;

    const result = await persistChatRunToSession('session-3', 'hello', 'world', {
      userMetadata: { source: 'playground' },
    });

    expect(result.userMessage.id).toBe('msg-user');
    expect(result.assistantMessage.id).toBe('msg-assistant');
    expect(String(vi.mocked(global.fetch).mock.calls[0]?.[0])).toBe(
      'http://localhost:8000/chat/sessions/session-3/messages',
    );
    expect(JSON.parse(String(vi.mocked(global.fetch).mock.calls[0]?.[1]?.body))).toEqual({
      role: 'user',
      content: 'hello',
      metadata: { source: 'playground' },
    });
    expect(JSON.parse(String(vi.mocked(global.fetch).mock.calls[1]?.[1]?.body))).toEqual({
      role: 'assistant',
      content: 'world',
    });
  });

  it('treats delete 404 as idempotent success', async () => {
    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: false,
      status: 404,
      json: async () => ({ detail: 'Session not found' }),
    } as Response) as typeof fetch;

    const result = await deleteChatSession('missing-session');
    expect(result.success).toBe(true);
  });

  it('replaces, updates, deletes, and clears persisted session messages', async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          messages: [
            {
              id: 'msg-1',
              role: 'user',
              content: 'kept',
              created_at: '2026-04-09T03:10:00.000Z',
              metadata: {},
            },
          ],
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 'msg-1',
          role: 'user',
          content: 'edited',
          created_at: '2026-04-09T03:10:00.000Z',
          metadata: { isEdited: true },
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true, session_id: 'session-4', message_id: 'msg-1' }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true, session_id: 'session-4' }),
      } as Response) as typeof fetch;

    const replaced = await replaceChatSessionMessages('session-4', [
      {
        id: 'msg-1',
        role: 'user',
        content: 'kept',
        created_at: '2026-04-09T03:10:00.000Z',
        metadata: {},
      },
    ]);
    const updated = await updateChatSessionMessage('session-4', 'msg-1', {
      content: 'edited',
      metadata: { isEdited: true },
    });
    const deleted = await deleteChatSessionMessage('session-4', 'msg-1');
    const cleared = await clearChatSessionMessages('session-4');

    expect(replaced.messages[0]?.id).toBe('msg-1');
    expect(updated.content).toBe('edited');
    expect(deleted.success).toBe(true);
    expect(cleared.success).toBe(true);
    expect(String(vi.mocked(global.fetch).mock.calls[0]?.[0])).toBe(
      'http://localhost:8000/chat/sessions/session-4/messages',
    );
    expect(vi.mocked(global.fetch).mock.calls[0]?.[1]).toMatchObject({ method: 'PUT' });
    expect(JSON.parse(String(vi.mocked(global.fetch).mock.calls[0]?.[1]?.body))).toEqual({
      messages: [
        {
          id: 'msg-1',
          role: 'user',
          content: 'kept',
          created_at: '2026-04-09T03:10:00.000Z',
          metadata: {},
        },
      ],
    });
    expect(String(vi.mocked(global.fetch).mock.calls[1]?.[0])).toBe(
      'http://localhost:8000/chat/sessions/session-4/messages/msg-1',
    );
    expect(vi.mocked(global.fetch).mock.calls[1]?.[1]).toMatchObject({ method: 'PUT' });
    expect(vi.mocked(global.fetch).mock.calls[2]?.[1]).toMatchObject({ method: 'DELETE' });
    expect(vi.mocked(global.fetch).mock.calls[3]?.[1]).toMatchObject({ method: 'DELETE' });
  });
});
