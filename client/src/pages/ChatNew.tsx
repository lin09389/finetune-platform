import { Modal } from 'antd';
import { motion, useReducedMotion } from 'framer-motion';
import React, { useCallback, useEffect, useState } from 'react';
import { Virtuoso } from 'react-virtuoso';

import { useChatStream } from '../hooks/chat/useChatStream';
import { useResponsive } from '../hooks/useResponsive';
import { useChatStore } from '../store/chatStore';
import { useTheme } from '../theme';

import ChatHeader from '../components/chat/ChatHeader';
import ChatInput from '../components/chat/ChatInput';
import ChatHistoryDrawer from '../components/ChatHistoryDrawer';
import ChatMessage from '../components/ChatMessage';
import MemoryManager from '../components/MemoryManager';
import RuntimeContextPanel from '../components/runtime/RuntimeContextPanel';
import APIKeyManager from '../pages/APIKeyManager';

import { useRuntimeContext } from '../runtime/RuntimeContext';
import { API_BASE_URL } from '../services/api';
import { transitions } from '../theme/animations';
import { notify } from '../utils/notify';
import styles from './ChatNew.module.css';

const VIRTUAL_SCROLL_THRESHOLD = 100;

interface APIKeyConfig {
  provider: string;
  api_key?: string;
  key_id?: string;
  model?: string;
  group_id?: string;
  base_url?: string;
}

const DEFAULT_SUGGESTIONS = ['帮我解释一下这个概念', '写一段代码实现...', '分析这个问题', '总结一下要点'];

const extractDynamicSuggestions = (content: string): string[] => {
  if (!content) return [];
  const lines = content.split('\n').map((l) => l.trim()).filter(Boolean);
  const suggestions: string[] = [];

  // 策略1：寻找引号包裹的列表项 (例如: - “帮我解释一下量子力学”)
  for (const line of lines) {
    const match = line.match(/^[*-]\s*["“]([^"”]+)["”]/);
    if (match && match[1]) {
      suggestions.push(match[1].trim());
    }
  }
  if (suggestions.length > 0) return suggestions.slice(0, 4);

  // 策略2：寻找特定关键字后面的列表
  let isSuggesting = false;
  for (const line of lines) {
    if (
      line.includes('你可以说') ||
      line.includes('例如') ||
      line.includes('可以问') ||
      line.includes('试着问') ||
      line.includes('您可以说')
    ) {
      isSuggesting = true;
      continue;
    }

    if (isSuggesting) {
      const match = line.match(/^[*-]\s+(.+)$/);
      if (match && match[1]) {
        let s = match[1].replace(/^["“]|["”]$/g, '').trim();
        if (s) suggestions.push(s);
      }
    }
  }

  if (suggestions.length > 0) return suggestions.slice(0, 4);
  return [];
};

const ChatPage: React.FC = () => {
  const { theme, toggleTheme } = useTheme();
  const { isMobile } = useResponsive();
  const prefersReducedMotion = useReducedMotion();
  const runtime = useRuntimeContext();
  const { actions, derived, observed } = runtime;
  const {
    refreshInference,
    refreshKnowledge,
    setInferenceSelection,
    setKnowledgeSelection,
    syncKnowledgeCollection,
  } = actions;

  const {
    sessions,
    messages,
    settings,
    isLoading,
    createSession,
    loadSession,
    deleteSession,
    loadSessions,
    deleteMessage,
    clearMessages,
    updateSettings,
  } = useChatStore();

  const [historyOpen, setHistoryOpen] = useState(false);
  const [memoryManagerOpen, setMemoryManagerOpen] = useState(false);
  const [configModalOpen, setConfigModalOpen] = useState(false);

  const [useCloudAI, setUseCloudAI] = useState(false);
  const [cloudAIConfig, setCloudAIConfig] = useState<APIKeyConfig | null>(null);
  const [selectedCloudModel, setSelectedCloudModel] = useState<string>('MiniMax-M2.5');

  const {
    sendMessage,
    sendCloudMessage,
    stop: stopStream,
    isStreaming: isActivelyStreaming,
  } = useChatStream({
    onChunk: () => {
      // streaming chunk hook
    },
    onComplete: () => {
      // stream completed
    },
    onError: (error) => {
      notify.error(error);
    },
  });

  useEffect(() => {
    Promise.allSettled([
      refreshInference(),
      loadSessions(),
      loadCloudAIConfig(),
      refreshKnowledge(),
    ]).then((results) => {
      const failed = results.filter((r) => r.status === 'rejected');
      if (failed.length > 0) {
        console.warn(`${failed.length} init requests failed`);
      }
    });
  }, [loadSessions, refreshInference, refreshKnowledge]);

  useEffect(() => {
    localStorage.setItem('chat_use_cloud_ai', useCloudAI ? '1' : '0');
  }, [useCloudAI]);

  useEffect(() => {
    if (settings.knowledgeCollection) {
      setKnowledgeSelection({ collectionId: settings.knowledgeCollection });
    }
  }, [setKnowledgeSelection, settings.knowledgeCollection]);

  useEffect(() => {
    setInferenceSelection({
      backend: settings.backend,
      modelId: settings.modelId || undefined,
    });
  }, [setInferenceSelection, settings.backend, settings.modelId]);

  const loadCloudAIConfig = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/cloud/api-keys`);
      if (response.ok) {
        const data = await response.json();
        if (data.keys && data.keys.length > 0) {
          const firstKey = data.keys[0];
          const keyData = await fetch(`${API_BASE_URL}/cloud/api-keys/${firstKey.id}/data`)
            .then((r) => r.json())
            .catch(() => ({}));

          const config: APIKeyConfig = {
            provider: firstKey.provider,
            api_key: '',
            key_id: firstKey.id,
            model: 'MiniMax-M2.5',
            group_id: keyData.group_id || '',
            base_url: keyData.base_url || '',
          };
          setCloudAIConfig(config);
          setUseCloudAI(localStorage.getItem('chat_use_cloud_ai') === '1');
          setSelectedCloudModel('MiniMax-M2.5');
          return;
        }
      }
    } catch {
      console.log('Failed to load cloud config from backend');
    }

    const saved = localStorage.getItem('cloud_ai_config');
    if (saved) {
      try {
        const config = JSON.parse(saved);
        setCloudAIConfig(config);
        setUseCloudAI(localStorage.getItem('chat_use_cloud_ai') === '1');
        if (config.model) {
          setSelectedCloudModel(config.model);
        }
      } catch (e) {
        console.error('Failed to parse cloud config:', e);
      }
    }
  };

  const handleSend = useCallback(
    async (content: string) => {
      if (!content.trim()) return;

      if (useCloudAI && cloudAIConfig) {
        await sendCloudMessage(
          { prompt: content },
          {
            provider: cloudAIConfig.provider,
            apiKey: cloudAIConfig.api_key,
            keyId: cloudAIConfig.key_id,
            model: selectedCloudModel,
            groupId: cloudAIConfig.group_id,
            baseUrl: cloudAIConfig.base_url,
          },
        );
      } else {
        await sendMessage({ prompt: content });
      }
    },
    [useCloudAI, cloudAIConfig, selectedCloudModel, sendCloudMessage, sendMessage],
  );

  const handleRetry = useCallback(
    (messageId: string) => {
      const msgIndex = messages.findIndex((m) => m.id === messageId);
      if (msgIndex === -1) return;

      const userMessage = messages[msgIndex - 1];
      if (!userMessage || userMessage.role !== 'user') return;

      const newMessages = messages.slice(0, msgIndex - 1);
      useChatStore.setState({ messages: newMessages });

      handleSend(userMessage.content);
    },
    [messages, handleSend],
  );

  const handleEditMessage = useCallback(
    (messageId: string, newContent: string) => {
      const msgIndex = messages.findIndex((m) => m.id === messageId);
      if (msgIndex === -1) return;

      // 将对话截断到这根线，并用新内容重新发送
      const newMessages = messages.slice(0, msgIndex);
      useChatStore.setState({ messages: newMessages });

      handleSend(newContent);
    },
    [messages, handleSend],
  );

  const handleExportChat = useCallback(
    (format: 'markdown' | 'json') => {
      if (messages.length === 0) {
        notify.warning('暂无对话内容');
        return;
      }

      const title = messages.find((m) => m.role === 'user')?.content.slice(0, 20) || '新对话';

      if (format === 'markdown') {
        let content = `# ${title}\n\n`;
        content += `导出时间: ${new Date().toLocaleString('zh-CN')}\n\n---\n\n`;

        for (const msg of messages) {
          const role = msg.role === 'user' ? '用户' : '助手';
          content += `## ${role}\n\n${msg.content}\n\n`;
        }

        const blob = new Blob([content], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${title}_${Date.now()}.md`;
        a.click();
        URL.revokeObjectURL(url);
        notify.success('已导出为 Markdown');
      } else {
        const data = {
          title,
          exportedAt: new Date().toISOString(),
          messages,
        };
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${title}_${Date.now()}.json`;
        a.click();
        URL.revokeObjectURL(url);
        notify.success('已导出为 JSON');
      }
    },
    [messages],
  );

  const handleClearChat = useCallback(() => {
    Modal.confirm({
      title: '确认清空',
      content: '确定要清空当前对话吗？',
      okText: '清空',
      okButtonProps: { danger: true },
      onOk: () => {
        clearMessages();
        notify.success('对话已清空');
      },
    });
  }, [clearMessages]);

  const handleToggleKnowledge = useCallback(() => {
    const nextUseKnowledge = !settings.useKnowledge;
    const fallbackCollection =
      settings.knowledgeCollection ||
      derived.activeKnowledgeCollection ||
      observed.knowledge.collections[0]?.id;

    updateSettings({
      useKnowledge: nextUseKnowledge,
      knowledgeCollection: nextUseKnowledge ? fallbackCollection : settings.knowledgeCollection,
    });

    if (nextUseKnowledge && fallbackCollection) {
      syncKnowledgeCollection(fallbackCollection);
    }
  }, [
    derived.activeKnowledgeCollection,
    observed.knowledge.collections,
    settings.knowledgeCollection,
    settings.useKnowledge,
    syncKnowledgeCollection,
    updateSettings,
  ]);

  const handleKnowledgeCollectionChange = useCallback(
    (collectionId: string) => {
      updateSettings({ useKnowledge: true });
      syncKnowledgeCollection(collectionId);
    },
    [syncKnowledgeCollection, updateSettings],
  );

  const enableVirtualScroll = messages.length > VIRTUAL_SCROLL_THRESHOLD;

  const currentSuggestions = React.useMemo(() => {
    if (messages.length === 0) return DEFAULT_SUGGESTIONS;
    
    // 从后往前找最后一个 assistant 消息
    for (let i = messages.length - 1; i >= 0; i--) {
      const msg = messages[i];
      if (msg && msg.role === 'assistant') {
        const extracted = extractDynamicSuggestions(msg.content);
        if (extracted.length > 0) return extracted;
        break;
      }
    }
    
    return DEFAULT_SUGGESTIONS;
  }, [messages]);

  const modelOptions =
    settings.backend === 'ollama'
      ? observed.inference.ollamaModels.map((m) => ({ id: m.id, name: m.name }))
      : observed.inference.huggingfaceModels.map((m) => ({ id: m.id, name: m.name }));

  useEffect(() => {
    if (settings.modelId) return;

    if (settings.backend === 'ollama' && observed.inference.ollamaModels.length > 0) {
      const firstOllamaModel = observed.inference.ollamaModels[0];
      if (firstOllamaModel) {
        updateSettings({ modelId: firstOllamaModel.id });
      }
      return;
    }

    if (settings.backend !== 'ollama' && observed.inference.huggingfaceModels.length > 0) {
      const firstHfModel = observed.inference.huggingfaceModels[0];
      if (firstHfModel) {
        updateSettings({ modelId: firstHfModel.id });
      }
    }
  }, [
    observed.inference.huggingfaceModels,
    observed.inference.ollamaModels,
    settings.backend,
    settings.modelId,
    updateSettings,
  ]);

  return (
    <motion.div
      className={styles.chatContainer}
      initial={prefersReducedMotion ? false : { opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={prefersReducedMotion ? { duration: 0 } : transitions.slower}
      style={isMobile ? { height: 'calc(100vh - 64px)' } : undefined}
    >
      <ChatHeader
        onNewChat={() => createSession()}
        onOpenHistory={() => setHistoryOpen(true)}
        onOpenMemory={() => setMemoryManagerOpen(true)}
        onClearChat={handleClearChat}
        onExportChat={handleExportChat}
        currentBackend={settings.backend}
        backends={observed.inference.backends}
        onBackendChange={async (backend) => {
          setUseCloudAI(false);
          localStorage.setItem('chat_use_cloud_ai', '0');
          updateSettings({ backend: backend as 'ollama' | 'huggingface' | 'cloud', modelId: '' });
          setInferenceSelection({ backend, modelId: undefined });
          await refreshInference();
        }}
        currentModel={settings.modelId}
        models={modelOptions}
        onModelChange={(model) => {
          updateSettings({ modelId: model });
          setInferenceSelection({ backend: settings.backend, modelId: model });
        }}
        useCloudAI={useCloudAI}
        onToggleCloudAI={() => {
          if (!cloudAIConfig?.api_key && !cloudAIConfig?.key_id) {
            setConfigModalOpen(true);
          } else {
            setUseCloudAI(!useCloudAI);
          }
        }}
        cloudAIConfigured={!!(cloudAIConfig?.api_key || cloudAIConfig?.key_id)}
        onOpenCloudAIConfig={() => setConfigModalOpen(true)}
        useKnowledge={settings.useKnowledge}
        onToggleKnowledge={handleToggleKnowledge}
        collectionsCount={observed.knowledge.collections.length}
        currentKnowledgeCollection={derived.activeKnowledgeCollection}
        knowledgeCollections={observed.knowledge.collections}
        onKnowledgeCollectionChange={handleKnowledgeCollectionChange}
        useMemory={settings.useMemory}
        onToggleMemory={() => updateSettings({ useMemory: !settings.useMemory })}
        theme={theme}
        onToggleTheme={toggleTheme}
        messageCount={messages.length}
        isLoading={isLoading}
        isStreaming={isActivelyStreaming}
      />
      <motion.div
        className={styles.chatMessagesArea}
        initial={prefersReducedMotion ? false : { opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={prefersReducedMotion ? { duration: 0 } : { delay: 0.16, ...transitions.base }}
      >
        <div className={styles.messagesInner}>
          <div style={{ marginBottom: 20 }}>
            <RuntimeContextPanel page="chat" />
          </div>
          {messages.length === 0 ? (
            <motion.div
              initial={prefersReducedMotion ? false : { opacity: 0, scale: 0.94 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={prefersReducedMotion ? { duration: 0 } : transitions.spring}
              className={styles.emptyState}
            >
              <div className={styles.emptyOrb}>AI</div>
              <h3 className={styles.emptyTitle}>开始新的对话</h3>
              <p className={styles.emptyDesc}>选择模型后，输入你的问题并开始探索。</p>
            </motion.div>
          ) : enableVirtualScroll ? (
            <Virtuoso
              data={messages}
              itemContent={(index, msg) => (
                <ChatMessage
                  key={msg.id}
                  role={msg.role as 'user' | 'assistant'}
                  content={msg.content}
                  timestamp={msg.timestamp}
                  isLoading={msg.isLoading}
                  isStreaming={
                    isActivelyStreaming && index === messages.length - 1 && msg.role === 'assistant'
                  }
                  onRetry={msg.role === 'assistant' ? () => handleRetry(msg.id) : undefined}
                  onEdit={
                    msg.role === 'user'
                      ? (newContent) => handleEditMessage(msg.id, newContent)
                      : undefined
                  }
                  onDelete={() => deleteMessage(msg.id)}
                  knowledge_sources={msg.knowledge_sources}
                  retrieval_info={msg.retrieval_info}
                />
              )}
              followOutput="smooth"
              style={{ height: isMobile ? 'calc(100vh - 240px)' : 'calc(100vh - 280px)' }}
              alignToBottom
            />
          ) : (
            <>
              {messages.map((msg) => (
                <ChatMessage
                  key={msg.id}
                  role={msg.role as 'user' | 'assistant'}
                  content={msg.content}
                  timestamp={msg.timestamp}
                  isLoading={msg.isLoading}
                  isStreaming={
                    isActivelyStreaming &&
                    msg.id === messages[messages.length - 1]?.id &&
                    msg.role === 'assistant'
                  }
                  onRetry={msg.role === 'assistant' ? () => handleRetry(msg.id) : undefined}
                  onEdit={
                    msg.role === 'user'
                      ? (newContent) => handleEditMessage(msg.id, newContent)
                      : undefined
                  }
                  onDelete={() => deleteMessage(msg.id)}
                  knowledge_sources={msg.knowledge_sources}
                  retrieval_info={msg.retrieval_info}
                />
              ))}
            </>
          )}
        </div>
      </motion.div>

      <ChatInput
        onSend={handleSend}
        onStop={stopStream}
        onClear={handleClearChat}
        disabled={!settings.modelId && !useCloudAI}
        loading={isLoading}
        isStreaming={isActivelyStreaming}
        modelId={useCloudAI ? selectedCloudModel : settings.modelId}
        suggestions={currentSuggestions}
      />

      <ChatHistoryDrawer
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        sessions={sessions.map((s) => ({
          id: s.id,
          title: s.title,
          created_at: s.createdAt,
          updated_at: s.updatedAt,
          message_count: s.messageCount,
        }))}
        onLoadSession={(id) => loadSession(id)}
        onDeleteSession={(id) => deleteSession(id)}
      />

      <MemoryManager open={memoryManagerOpen} onClose={() => setMemoryManagerOpen(false)} />

      <Modal
        open={configModalOpen}
        onCancel={() => setConfigModalOpen(false)}
        footer={null}
        width={600}
      >
        <APIKeyManager
          onConfigChange={(config: APIKeyConfig) => {
            setCloudAIConfig(config);
            if (config.model) {
              setSelectedCloudModel(config.model);
            }
          }}
          initialConfig={cloudAIConfig}
        />
      </Modal>
    </motion.div>
  );
};

export default ChatPage;
