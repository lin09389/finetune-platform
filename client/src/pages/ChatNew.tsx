import { Modal } from 'antd';
import { motion, useReducedMotion } from 'framer-motion';
import React, { useCallback, useEffect, useMemo, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Virtuoso } from 'react-virtuoso';

import { useChatStream } from '../hooks/chat/useChatStream';
import { useResponsive } from '../hooks/useResponsive';
import { useChatStore } from '../store/chatStore';
import { useTheme } from '../theme';

import ChatHeader from '../components/chat/ChatHeader';
import ChatInput from '../components/chat/ChatInput';
import FollowUpSuggestions from '../components/chat/FollowUpSuggestions';
import ChatHistoryDrawer from '../components/ChatHistoryDrawer';
import ChatMessage from '../components/ChatMessage';
import MemoryManager from '../components/MemoryManager';
import RuntimeContextPanel from '../components/runtime/RuntimeContextPanel';
import APIKeyManager from '../pages/APIKeyManager';

import { useRuntimeContext } from '../runtime/RuntimeContext';
import { API_BASE_URL, createWorkflow, getSavedCloudProviders } from '../services/api';
import type { SavedCloudProvider } from '../services/api';
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

const DEFAULT_SUGGESTIONS = [
  '帮我制定一个学习计划',
  '如何进行大模型微调？',
  '写一段 Python 代码实现数据清洗',
  '分析一下当前的 AI 行业趋势'
];

const extractDynamicSuggestions = (content: string): string[] => {
  if (!content) return [];
  
  // 预处理：移除思考块 (thought blocks)
  const cleanContent = content.replace(/<thought>[\s\S]*?<\/thought>/g, '').trim();
  const lines = cleanContent.split('\n').map((l) => l.trim()).filter(Boolean);
  const suggestions: string[] = [];

  // 1. 寻找明确的建议引导语
  const suggestionMarkers = [
    '您可以尝试这样问',
    '您可以说',
    '例如',
    '可以问',
    '试着问',
    '你可以问',
    '后续建议',
    '猜你想问',
    'Next steps',
    'Follow-up'
  ];

  let markerFoundIndex = -1;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line && suggestionMarkers.some(marker => line.includes(marker))) {
      markerFoundIndex = i;
      break;
    }
  }

  // 如果找到了标记，尝试抓取其后的列表项
  if (markerFoundIndex !== -1) {
    for (let i = markerFoundIndex + 1; i < Math.min(markerFoundIndex + 6, lines.length); i++) {
      const line = lines[i];
      if (!line) continue;
      // 匹配列表项：- 项, * 项, 1. 项
      const listMatch = line.match(/^[*-]\s+(.+)$/) || line.match(/^\d+\.\s+(.+)$/);
      if (listMatch && listMatch[1]) {
        let s = listMatch[1].replace(/^["“]|["”]$/g, '').trim();
        if (s && s.length < 50) suggestions.push(s);
      }
    }
  }

  // 2. 如果没找到标记，尝试寻找末尾带有引号的列表项（常见的大模型输出习惯）
  if (suggestions.length === 0) {
    const lastLines = lines.slice(-8);
    for (const line of lastLines) {
      const quoteMatch = line.match(/^[*-]\s*["“]([^"”]+)["”]/) || line.match(/^\d+\.\s*["“]([^"”]+)["”]/);
      if (quoteMatch && quoteMatch[1]) {
        suggestions.push(quoteMatch[1].trim());
      }
    }
  }

  // 3. 兜底策略：如果内容末尾有问号，可能是一个建议
  if (suggestions.length === 0) {
    const lastLine = lines[lines.length - 1];
    if (lastLine && (lastLine.endsWith('?') || lastLine.endsWith('？')) && lastLine.length < 40) {
      suggestions.push(lastLine.replace(/^[*-]\s*/, '').trim());
    }
  }

  return Array.from(new Set(suggestions)).slice(0, 4);
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
    currentSessionId,
    messages,
    settings,
    isLoading,
    createSession,
    loadSession,
    deleteSession,
    loadSessions,
    deleteMessage,
    clearMessages,
    replaceCurrentSessionMessages,
    updateSettings,
  } = useChatStore();

  const [historyOpen, setHistoryOpen] = useState(false);
  const [memoryManagerOpen, setMemoryManagerOpen] = useState(false);
  const [configModalOpen, setConfigModalOpen] = useState(false);

  const [useCloudAI, setUseCloudAI] = useState(false);
  const [cloudAIConfig, setCloudAIConfig] = useState<APIKeyConfig | null>(null);
  const [cloudProviders, setCloudProviders] = useState<SavedCloudProvider[]>([]);
  const [selectedCloudModel, setSelectedCloudModel] = useState<string>('');
  const [creatingWorkflow, setCreatingWorkflow] = useState(false);
  const navigate = useNavigate();

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const restoredSessionRef = useRef<string | null>(null);
  const scrollToBottom = useCallback(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, []);

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
    if (!currentSessionId || currentSessionId.startsWith('local_')) return;
    if (messages.length > 0) {
      restoredSessionRef.current = currentSessionId;
      return;
    }
    if (restoredSessionRef.current === currentSessionId) return;
    restoredSessionRef.current = currentSessionId;
    loadSession(currentSessionId).catch((error) => {
      const message = error instanceof Error ? error.message : '历史会话恢复失败';
      notify.error(`历史会话恢复失败：${message}`);
    });
  }, [currentSessionId, loadSession, messages.length]);

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

  useEffect(() => {
    scrollToBottom();
  }, [messages, isActivelyStreaming, scrollToBottom]);

  const loadCloudAIConfig = async () => {
    try {
      const data = await getSavedCloudProviders();
      const keys: SavedCloudProvider[] = data.keys || [];
      setCloudProviders(keys);

      if (keys.length > 0) {
        const saved = localStorage.getItem('cloud_ai_config');
        let preferredProvider = '';
        let preferredModel = '';
        if (saved) {
          try {
            const savedConfig = JSON.parse(saved);
            preferredProvider = savedConfig.provider || '';
            preferredModel = savedConfig.model || '';
          } catch {
            preferredProvider = '';
          }
        }

        const firstKey = keys.find((key) => key.provider === preferredProvider) || keys[0];
        if (firstKey) {
          const keyData = await fetch(`${API_BASE_URL}/cloud/api-keys/${firstKey.id}/data`)
            .then((r) => r.json())
            .catch(() => ({}));
          const models = keyData.models || firstKey.models || [];
          const selectedModel =
            preferredModel ||
            keyData.default_model ||
            firstKey.default_model ||
            models[0] ||
            '';

          const config: APIKeyConfig = {
            provider: firstKey.provider,
            api_key: '',
            key_id: firstKey.id,
            model: selectedModel,
            group_id: keyData.group_id || '',
            base_url: keyData.base_url || '',
          };
          setCloudAIConfig(config);
          setUseCloudAI(localStorage.getItem('chat_use_cloud_ai') === '1');
          setSelectedCloudModel(selectedModel);
          localStorage.setItem('cloud_ai_config', JSON.stringify(config));
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

  const handleCreateWorkflow = useCallback(
    async (content: string) => {
      const goal = content.trim();
      if (!goal) {
        notify.warning('请先输入工作流目标');
        return;
      }

      setCreatingWorkflow(true);
      try {
        const workflow = await createWorkflow({
          title: goal.slice(0, 30),
          goal,
          template_id: 'software_delivery',
          provider: cloudAIConfig?.provider || undefined,
          model: selectedCloudModel || cloudAIConfig?.model || undefined,
          approval_mode: 'manual',
        });
        notify.success('工作流已创建');
        navigate(`/workflows?workflow=${workflow.workflow_id || workflow.id}`);
      } catch (error: any) {
        notify.error(error?.response?.data?.detail || '创建工作流失败');
      } finally {
        setCreatingWorkflow(false);
      }
    },
    [cloudAIConfig?.model, cloudAIConfig?.provider, navigate, selectedCloudModel],
  );

  const selectedCloudProvider = useMemo(
    () => cloudProviders.find((provider) => provider.provider === cloudAIConfig?.provider),
    [cloudAIConfig?.provider, cloudProviders],
  );

  const cloudProviderOptions = useMemo(
    () =>
      cloudProviders.map((provider) => ({
        id: provider.provider,
        name: `${provider.name || provider.provider} (${provider.provider})`,
      })),
    [cloudProviders],
  );

  const cloudModelOptions = useMemo(() => {
    const models = selectedCloudProvider?.models?.length
      ? selectedCloudProvider.models
      : selectedCloudProvider?.default_model
        ? [selectedCloudProvider.default_model]
        : [];
    return models.map((model) => ({ id: model, name: model }));
  }, [selectedCloudProvider]);

  const handleCloudProviderChange = useCallback(
    async (provider: string) => {
      const selectedProvider = cloudProviders.find((item) => item.provider === provider);
      if (!selectedProvider) return;

      const keyData = await fetch(`${API_BASE_URL}/cloud/api-keys/${selectedProvider.id}/data`)
        .then((r) => r.json())
        .catch(() => ({}));
      const models = keyData.models || selectedProvider.models || [];
      const nextModel = keyData.default_model || selectedProvider.default_model || models[0] || '';
      const config: APIKeyConfig = {
        provider: selectedProvider.provider,
        api_key: '',
        key_id: selectedProvider.id,
        model: nextModel,
        group_id: keyData.group_id || '',
        base_url: keyData.base_url || '',
      };
      setCloudAIConfig(config);
      setSelectedCloudModel(nextModel);
      localStorage.setItem('cloud_ai_config', JSON.stringify(config));
    },
    [cloudProviders],
  );

  const handleCloudModelChange = useCallback(
    (model: string) => {
      setSelectedCloudModel(model);
      setCloudAIConfig((config) => {
        if (!config) return config;
        const nextConfig = { ...config, model };
        localStorage.setItem('cloud_ai_config', JSON.stringify(nextConfig));
        return nextConfig;
      });
    },
    [],
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
    async (messageId: string, newContent: string) => {
      const msgIndex = messages.findIndex((m) => m.id === messageId);
      if (msgIndex === -1) return;

      // 将对话截断到这根线，并用新内容重新发送
      const newMessages = messages.slice(0, msgIndex);
      try {
        await replaceCurrentSessionMessages(newMessages);
        await handleSend(newContent);
      } catch (error) {
        const message = error instanceof Error ? error.message : '编辑消息失败';
        notify.error(message);
      }
    },
    [handleSend, messages, replaceCurrentSessionMessages],
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
      onOk: async () => {
        try {
          await clearMessages();
          notify.success('对话已清空');
        } catch (error) {
          const message = error instanceof Error ? error.message : '清空会话失败';
          notify.error(message);
          throw error;
        }
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
    
    // 只有当最后一条消息是助手发出的，且没有正在加载时，才显示建议
    const lastMessage = messages[messages.length - 1];
    if (lastMessage && lastMessage.role === 'assistant') {
      const extracted = extractDynamicSuggestions(lastMessage.content);
      if (extracted.length > 0) return extracted;
      
      // 兜底：根据上下文生成一些通用的后续问题
      if (lastMessage.content.length > 100) {
        return ['总结一下核心观点', '还有其他需要注意的吗？', '帮我深入解释一下', '举个实际的例子'];
      }
    }
    
    return [];
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
        currentCloudProvider={cloudAIConfig?.provider}
        cloudProviders={cloudProviderOptions}
        onCloudProviderChange={handleCloudProviderChange}
        currentCloudModel={selectedCloudModel}
        cloudModels={cloudModelOptions}
        onCloudModelChange={handleCloudModelChange}
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
              
              <div className={styles.starterSuggestions}>
                {DEFAULT_SUGGESTIONS.map((s, i) => (
                  <motion.button
                    key={s}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.2 + i * 0.1 }}
                    className={styles.starterBtn}
                    onClick={() => handleSend(s)}
                  >
                    {s}
                  </motion.button>
                ))}
              </div>
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
                  onDelete={() => {
                    deleteMessage(msg.id).catch((error) => {
                      const message = error instanceof Error ? error.message : '删除消息失败';
                      notify.error(message);
                    });
                  }}
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
                  onDelete={() => {
                    deleteMessage(msg.id).catch((error) => {
                      const message = error instanceof Error ? error.message : '删除消息失败';
                      notify.error(message);
                    });
                  }}
                  knowledge_sources={msg.knowledge_sources}
                  retrieval_info={msg.retrieval_info}
                />
              ))}
              
              <FollowUpSuggestions
                suggestions={currentSuggestions}
                isVisible={!isLoading && !isActivelyStreaming && currentSuggestions.length > 0}
                onSuggestionClick={handleSend}
              />

              <div ref={messagesEndRef} style={{ height: 1 }} />
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
        onCreateWorkflow={handleCreateWorkflow}
        creatingWorkflow={creatingWorkflow}
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
          metadata: s.metadata,
          model_id: s.modelId,
        }))}
        onLoadSession={(id) => {
          loadSession(id)
            .then(() => setHistoryOpen(false))
            .catch((error) => {
              const message = error instanceof Error ? error.message : '加载历史会话失败';
              notify.error(message);
            });
        }}
        onDeleteSession={(id) => {
          deleteSession(id).catch((error) => {
            const message = error instanceof Error ? error.message : '删除会话失败';
            notify.error(message);
          });
        }}
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
            setSelectedCloudModel(config.model || '');
            void loadCloudAIConfig();
          }}
          initialConfig={cloudAIConfig}
        />
      </Modal>
    </motion.div>
  );
};

export default ChatPage;
