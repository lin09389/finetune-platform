import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

// ChatNew pulls in many heavy modules; mock them so this test exercises ONLY
// the message-list wiring (Virtuoso mount + itemContent + followOutput) and not
// markdown / katex / monaco / network. jsdom has 0 viewport height, so Virtuoso
// renders no visible items — this test asserts the component mounts without
// throwing and takes the message path (not the empty state).

const mockMessages = [
  { id: 'm1', role: 'user', content: 'hello', timestamp: '', isLoading: false, knowledge_sources: undefined, retrieval_info: undefined },
  { id: 'm2', role: 'assistant', content: 'hi there', timestamp: '', isLoading: false, knowledge_sources: undefined, retrieval_info: undefined },
  { id: 'm3', role: 'user', content: 'second question', timestamp: '', isLoading: false, knowledge_sources: undefined, retrieval_info: undefined },
];

vi.mock('../store/chatStore', () => ({
  useChatStore: () => ({
    sessions: [],
    messages: mockMessages,
    currentSessionId: 's1',
    settings: { backend: 'ollama', modelId: '', useKnowledge: false, useMemory: false },
    isLoading: false,
    isStreaming: false,
    error: null,
    cloudConfig: { useCloudAI: false, config: null, providers: [], selectedModel: '' },
    loadSessions: vi.fn(),
    loadSession: vi.fn(),
    deleteSession: vi.fn(),
    clearMessages: vi.fn(),
    deleteMessage: vi.fn(),
    editMessage: vi.fn(),
    updateSettings: vi.fn(),
    setCloudConfig: vi.fn(),
    createSession: vi.fn(),
  }),
}));

vi.mock('../hooks/chat/useChatStream', () => ({
  useChatStream: () => ({
    sendMessage: vi.fn(),
    sendCloudMessage: vi.fn(),
    stop: vi.fn(),
    isStreaming: false,
  }),
}));

vi.mock('../hooks/useResponsive', () => ({
  useResponsive: () => ({ isMobile: false, isTablet: false }),
}));

vi.mock('../services/api', () => ({
  getSavedCloudProviders: vi.fn(() => Promise.resolve([])),
}));

vi.mock('../components/ChatMessage', () => ({
  default: ({ id }: { id: string }) => <div data-testid={`msg-${id}`}>Mock Chat Message</div>,
}));

vi.mock('../components/chat/ChatHeader', () => ({ default: () => <div>Mock Chat Header</div> }));
vi.mock('../components/chat/ChatInput', () => ({ default: () => <div>Mock Chat Input</div> }));
vi.mock('../components/ChatHistoryDrawer', () => ({ default: () => <div>Mock History</div> }));
vi.mock('../components/MemoryManager', () => ({ default: () => <div>Mock Memory</div> }));
vi.mock('../pages/APIKeyManager', () => ({ default: () => <div>Mock APIKey</div> }));

import ChatNew from '../pages/ChatNew';

describe('ChatNew message-list virtualization', () => {
  it('mounts without throwing when messages exist (message path, not empty state)', () => {
    const { unmount } = render(<ChatNew />);
    // Empty state heading must NOT be present — we are on the message path.
    expect(screen.queryByText('从一个问题开始')).toBeNull();
    // The chat log live region exists.
    expect(screen.getByRole('log')).toBeInTheDocument();
    unmount();
  });
});
