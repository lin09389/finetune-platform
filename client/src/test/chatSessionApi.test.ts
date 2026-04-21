import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../services/api', () => ({
  API_BASE_URL: 'http://localhost:8000',
}));

import {
  createChatSession,
  deleteChatSession,
  getChatSession,
  getChatSessionMessages,
  listChatSessions,
  persistChatRunToSession,
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
      'http://localhost:8000/chat/sessions',
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
    });
    expect(vi.mocked(global.fetch).mock.calls[1]?.[1]).toMatchObject({
      method: 'PUT',
    });
    expect(JSON.parse(String(vi.mocked(global.fetch).mock.calls[1]?.[1]?.body))).toEqual({
      metadata: { agent_mode: true },
    });
    expect(String(vi.mocked(global.fetch).mock.calls[2]?.[0])).toBe(
      'http://localhost:8000/chat/sessions/session-2/messages',
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
});
