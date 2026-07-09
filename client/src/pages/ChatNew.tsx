import { SettingOutlined } from '@ant-design/icons';
import { Button, Drawer, Select, Switch } from 'antd';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Virtuoso, type VirtuosoHandle } from 'react-virtuoso';
import { useShallow } from 'zustand/react/shallow';
import ChatHistoryDrawer from '../components/ChatHistoryDrawer';
import ChatMessage from '../components/ChatMessage';
import MemoryManager from '../components/MemoryManager';
import ChatHeader from '../components/chat/ChatHeader';
import ChatInput from '../components/chat/ChatInput';
import { useChatStream } from '../hooks/chat/useChatStream';
import { useResponsive } from '../hooks/useResponsive';
import APIKeyManager from './APIKeyManager';
import { getSavedCloudProviders, type SavedCloudProvider } from '../services/api';
import { useChatStore } from '../store/chatStore';
import styles from './ChatNew.module.css';

const STARTERS = [
  '解释一个我正在学习的技术概念',
  '帮我整理一份清晰的学习计划',
  '总结并改写一段文字',
];

export default function ChatPage() {
  const { isMobile } = useResponsive();
  const virtuosoRef = useRef<VirtuosoHandle>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [apiKeysOpen, setApiKeysOpen] = useState(false);
  const [savedProviders, setSavedProviders] = useState<SavedCloudProvider[]>([]);
  const {
    sessions,
    messages,
    currentSessionId,
    settings,
    isLoading,
    isStreaming,
    error,
    cloudConfig,
    loadSessions,
    loadSession,
    deleteSession,
    clearMessages,
    deleteMessage,
    editMessage,
    updateSettings,
    setCloudConfig,
  } = useChatStore(useShallow((state) => ({
    sessions: state.sessions,
    messages: state.messages,
    currentSessionId: state.currentSessionId,
    settings: state.settings,
    isLoading: state.isLoading,
    isStreaming: state.isStreaming,
    error: state.error,
    cloudConfig: state.cloudConfig,
    loadSessions: state.loadSessions,
    loadSession: state.loadSession,
    deleteSession: state.deleteSession,
    clearMessages: state.clearMessages,
    deleteMessage: state.deleteMessage,
    editMessage: state.editMessage,
    updateSettings: state.updateSettings,
    setCloudConfig: state.setCloudConfig,
  })));

  const stream = useChatStream();
  const activeModel = cloudConfig.useCloudAI
    ? cloudConfig.selectedModel || cloudConfig.config?.model || '云端模型'
    : settings.modelId || settings.backend;

  const refreshProviders = useCallback(async () => {
    try {
      const response = await getSavedCloudProviders();
      const providers = Array.isArray(response) ? response : response.keys || response.providers || [];
      setSavedProviders(providers);
      setCloudConfig({ providers });
    } catch {
      setSavedProviders([]);
    }
  }, [setCloudConfig]);

  useEffect(() => {
    void Promise.all([loadSessions(), refreshProviders()]);
  }, [loadSessions, refreshProviders]);

  // Jump to the latest message on mount and whenever the active session
  // changes (e.g. loading a history session). Per-token streaming follow is
  // handled by Virtuoso's followOutput, which respects the user scrolling up.
  useEffect(() => {
    virtuosoRef.current?.scrollToIndex({ index: 'LAST', behavior: 'auto' });
  }, [currentSessionId]);

  const send = useCallback(async (content: string) => {
    if (cloudConfig.useCloudAI && cloudConfig.config) {
      await stream.sendCloudMessage(
        { prompt: content },
        {
          provider: cloudConfig.config.provider,
          apiKey: cloudConfig.config.api_key,
          keyId: cloudConfig.config.key_id,
          groupId: cloudConfig.config.group_id,
          baseUrl: cloudConfig.config.base_url,
          model: cloudConfig.selectedModel || cloudConfig.config.model || '',
        },
      );
      return;
    }
    await stream.sendMessage({ prompt: content });
  }, [cloudConfig, stream]);

  const exportChat = useCallback((format: 'markdown' | 'json') => {
    const content = format === 'json'
      ? JSON.stringify(messages, null, 2)
      : messages.map((item) => `## ${item.role === 'user' ? '用户' : '助手'}\n\n${item.content}`).join('\n\n');
    const blob = new Blob([content], { type: format === 'json' ? 'application/json' : 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `chat-${Date.now()}.${format === 'json' ? 'json' : 'md'}`;
    anchor.click();
    URL.revokeObjectURL(url);
  }, [messages]);

  const providerOptions = useMemo(() => savedProviders.map((provider) => ({
    value: provider.id || provider.provider,
    label: provider.name || provider.provider,
  })), [savedProviders]);

  return (
    <div className={styles.chatContainer}>
      <ChatHeader
        onNewChat={() => void useChatStore.getState().createSession('新对话')}
        onOpenHistory={() => setHistoryOpen(true)}
        onOpenMemory={() => setMemoryOpen(true)}
        onOpenContextPanel={() => setSettingsOpen(true)}
        onClearChat={() => void clearMessages()}
        onExportChat={exportChat}
        messageCount={messages.length}
        activeModeLabel="纯聊天"
        activeModelLabel={activeModel}
      />

      <main className={styles.chatMain} aria-label="AI 对话">
        <div className={styles.messages} role="log" aria-live="polite" aria-label="对话消息">
          {messages.length === 0 ? (
            <div className={styles.emptyState}>
              <span>AI 对话</span>
              <h1>从一个问题开始</h1>
              <p>这里专注于对话、解释与内容生成。需要执行开发任务时，请进入 Agent 工作台。</p>
              <div className={styles.starters}>
                {STARTERS.map((starter) => (
                  <button key={starter} type="button" onClick={() => void send(starter)}>
                    {starter}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <Virtuoso
              ref={virtuosoRef}
              data={messages}
              computeItemKey={(_, item) => item.id}
              followOutput={(atBottom) => (atBottom ? 'auto' : false)}
              increaseViewportBy={600}
              style={{ height: '100%' }}
              itemContent={(_, item) => (
                <ChatMessage
                  id={item.id}
                  role={item.role}
                  content={item.content}
                  timestamp={item.timestamp}
                  isLoading={item.isLoading}
                  isStreaming={isStreaming && item.role === 'assistant' && item.isLoading}
                  knowledge_sources={item.knowledge_sources}
                  retrieval_info={item.retrieval_info}
                  onDelete={deleteMessage}
                  onEdit={(id, content) => void editMessage(id, content)}
                  onRetry={(_, content = item.content) => void send(content)}
                />
              )}
            />
          )}
        </div>

        {error ? <div className={styles.errorBanner}>{error}</div> : null}
        <div className={styles.composer}>
          <ChatInput
            onSend={(content) => void send(content)}
            onStop={stream.stop}
            onClear={() => void clearMessages()}
            onNewChat={() => void useChatStore.getState().createSession('新对话')}
            disabled={isLoading}
            loading={isLoading}
            isStreaming={isStreaming}
            modelId={activeModel}
            routingMode="chat"
            placeholder="输入消息"
          />
        </div>
      </main>

      {!isMobile ? (
        <Button
          className={styles.settingsButton}
          type="text"
          icon={<SettingOutlined />}
          onClick={() => setSettingsOpen(true)}
          aria-label="对话设置"
        />
      ) : null}

      <ChatHistoryDrawer
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        sessions={sessions.map((session) => ({
          id: session.id,
          title: session.title,
          model_id: session.modelId,
          created_at: session.createdAt,
          updated_at: session.updatedAt,
          message_count: session.messageCount,
          metadata: session.metadata,
        }))}
        onLoadSession={async (sessionId) => {
          await loadSession(sessionId);
          setHistoryOpen(false);
        }}
        onDeleteSession={deleteSession}
      />
      <MemoryManager open={memoryOpen} onClose={() => setMemoryOpen(false)} />

      <Drawer
        title="对话设置"
        placement="right"
        width={isMobile ? '92vw' : 360}
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
      >
        <div className={styles.settingsForm}>
          <label>
            <span>推理后端</span>
            <Select
              value={settings.backend}
              onChange={(backend) => updateSettings({ backend })}
              options={[
                { value: 'ollama', label: 'Ollama' },
                { value: 'huggingface', label: 'Hugging Face' },
                { value: 'llama-cpp', label: 'llama.cpp' },
                { value: 'cloud', label: '云端 API' },
              ]}
            />
          </label>
          <label>
            <span>模型</span>
            <Select
              showSearch
              value={settings.modelId || undefined}
              placeholder="选择或输入模型"
              onChange={(modelId) => updateSettings({ modelId })}
              options={settings.modelId ? [{ value: settings.modelId, label: settings.modelId }] : []}
            />
          </label>
          <label className={styles.switchRow}>
            <span>知识库检索</span>
            <Switch checked={settings.useKnowledge} onChange={(useKnowledge) => updateSettings({ useKnowledge })} />
          </label>
          <label className={styles.switchRow}>
            <span>记忆</span>
            <Switch checked={settings.useMemory} onChange={(useMemory) => updateSettings({ useMemory })} />
          </label>
          <label className={styles.switchRow}>
            <span>使用云端模型</span>
            <Switch
              checked={cloudConfig.useCloudAI}
              onChange={(useCloudAI) => setCloudConfig({ useCloudAI })}
            />
          </label>
          {cloudConfig.useCloudAI ? (
            <>
              <label>
                <span>云端提供商</span>
                <Select
                  options={providerOptions}
                  value={cloudConfig.config?.key_id}
                  placeholder="选择已保存的 API Key"
                  onChange={(keyId) => {
                    const provider = savedProviders.find((item) => (item.id || item.provider) === keyId);
                    if (!provider) return;
                    setCloudConfig({
                      config: {
                        provider: provider.provider,
                        key_id: keyId,
                        model: provider.default_model || provider.models?.[0] || '',
                        base_url: provider.base_url,
                      },
                      selectedModel: provider.default_model || provider.models?.[0] || '',
                    });
                  }}
                />
              </label>
              <Button onClick={() => setApiKeysOpen(true)}>管理 API Key</Button>
            </>
          ) : null}
        </div>
      </Drawer>

      <Drawer
        title="API Key"
        width={isMobile ? '96vw' : 760}
        open={apiKeysOpen}
        onClose={() => {
          setApiKeysOpen(false);
          void refreshProviders();
        }}
      >
        <APIKeyManager />
      </Drawer>
    </div>
  );
}
