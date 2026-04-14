import React, { useEffect, useCallback, useState } from 'react'
import { Modal, message } from 'antd'
import { motion, useReducedMotion } from 'framer-motion'
import { Virtuoso } from 'react-virtuoso'

import { useChatStore } from '../store/chatStore'
import { useChatStream } from '../hooks/chat/useChatStream'
import { useTheme } from '../theme'
import { useResponsive } from '../hooks/useResponsive'

import ChatHeader from '../components/chat/ChatHeader'
import ChatMessage from '../components/ChatMessage'
import ChatInput from '../components/chat/ChatInput'
import ChatHistoryDrawer from '../components/ChatHistoryDrawer'
import MemoryManager from '../components/MemoryManager'
import APIKeyManager from '../pages/APIKeyManager'

import { getBackends, getOllamaStatus, getInferenceModels, API_BASE_URL } from '../services/api'
import { transitions } from '../theme/animations'
import styles from './ChatNew.module.css'

const VIRTUAL_SCROLL_THRESHOLD = 100

interface APIKeyConfig {
  provider: string
  api_key?: string
  key_id?: string
  model?: string
  group_id?: string
  base_url?: string
}

const ChatPage: React.FC = () => {
  const { theme, toggleTheme } = useTheme()
  const { isMobile } = useResponsive()
  const prefersReducedMotion = useReducedMotion()

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
  } = useChatStore()

  const [backends, setBackends] = useState<{ id: string; name: string; available: boolean }[]>([])
  const [ollamaModels, setOllamaModels] = useState<{ id: string; name: string }[]>([])
  const [hfModels, setHfModels] = useState<{ id: string; name: string }[]>([])
  const [collections, setCollections] = useState<{ id: string; name: string; count: number }[]>([])

  const [historyOpen, setHistoryOpen] = useState(false)
  const [memoryManagerOpen, setMemoryManagerOpen] = useState(false)
  const [configModalOpen, setConfigModalOpen] = useState(false)

  const [useCloudAI, setUseCloudAI] = useState(false)
  const [cloudAIConfig, setCloudAIConfig] = useState<APIKeyConfig | null>(null)
  const [selectedCloudModel, setSelectedCloudModel] = useState<string>('MiniMax-M2.5')

  const { sendMessage, sendCloudMessage, stop: stopStream, isStreaming: isActivelyStreaming } = useChatStream({
    onChunk: () => {
      // streaming chunk hook
    },
    onComplete: () => {
      // stream completed
    },
    onError: (error) => {
      message.error(error)
    },
  })

  useEffect(() => {
    Promise.allSettled([loadBackends(), loadSessions(), loadCloudAIConfig(), loadCollections()]).then((results) => {
      const failed = results.filter((r) => r.status === 'rejected')
      if (failed.length > 0) {
        console.warn(`${failed.length} init requests failed`)
      }
    })
  }, [])

  useEffect(() => {
    localStorage.setItem('chat_use_cloud_ai', useCloudAI ? '1' : '0')
  }, [useCloudAI])

  const loadBackends = async (preferredBackend?: string) => {
    try {
      const data = await getBackends()
      const activeBackend = preferredBackend || settings.backend || data.current
      const shouldAutoSelectModel = Boolean(preferredBackend) || !settings.modelId

      if (activeBackend === 'ollama') {
        const ollamaStatus = await getOllamaStatus()
        setOllamaModels(
          ollamaStatus.models.map((m: { name: string }) => ({
            id: m.name,
            name: m.name,
          }))
        )
        if (shouldAutoSelectModel && ollamaStatus.models.length > 0) {
          updateSettings({ modelId: ollamaStatus.models[0].name })
        }
      } else {
        const models = await getInferenceModels()
        setHfModels(
          models.map((m: { id: string; name?: string }) => ({
            id: m.id,
            name: m.name || m.id,
          }))
        )
        if (shouldAutoSelectModel && models.length > 0) {
          updateSettings({ modelId: models[0].id })
        }
      }

      if (Array.isArray(data.backends) && data.backends.length > 0) {
        setBackends(
          data.backends.map((backend: { id: string; name: string; available: boolean }) => ({
            id: backend.id,
            name: backend.name,
            available: backend.available,
          }))
        )
      } else {
        setBackends([
          { id: 'ollama', name: 'Ollama', available: data.current === 'ollama' },
          { id: 'huggingface', name: 'HuggingFace', available: data.current === 'huggingface' },
        ])
      }
    } catch (error) {
      console.error('Failed to load backends:', error)
    }
  }

  const loadCollections = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/knowledge/collections`)
      if (response.ok) {
        const data = await response.json()
        setCollections(
          data.collections.map((c: { name: string; count?: number }) => ({
            id: c.name,
            name: c.name,
            count: c.count || 0,
          }))
        )
      }
    } catch (error) {
      console.error('Failed to load knowledge collections:', error)
    }
  }

  const loadCloudAIConfig = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/cloud/api-keys`)
      if (response.ok) {
        const data = await response.json()
        if (data.keys && data.keys.length > 0) {
          const firstKey = data.keys[0]
          const keyData = await fetch(`${API_BASE_URL}/cloud/api-keys/${firstKey.id}/data`)
            .then((r) => r.json())
            .catch(() => ({}))

          const config: APIKeyConfig = {
            provider: firstKey.provider,
            api_key: '',
            key_id: firstKey.id,
            model: 'MiniMax-M2.5',
            group_id: keyData.group_id || '',
            base_url: keyData.base_url || '',
          }
          setCloudAIConfig(config)
          setUseCloudAI(localStorage.getItem('chat_use_cloud_ai') === '1')
          setSelectedCloudModel('MiniMax-M2.5')
          return
        }
      }
    } catch {
      console.log('Failed to load cloud config from backend')
    }

    const saved = localStorage.getItem('cloud_ai_config')
    if (saved) {
      try {
        const config = JSON.parse(saved)
        setCloudAIConfig(config)
        setUseCloudAI(localStorage.getItem('chat_use_cloud_ai') === '1')
        if (config.model) {
          setSelectedCloudModel(config.model)
        }
      } catch (e) {
        console.error('Failed to parse cloud config:', e)
      }
    }
  }

  const handleSend = useCallback(
    async (content: string) => {
      if (!content.trim()) return

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
          }
        )
      } else {
        await sendMessage({ prompt: content })
      }
    },
    [
      useCloudAI,
      cloudAIConfig,
      selectedCloudModel,
      sendCloudMessage,
      sendMessage,
    ]
  )

  const handleRetry = useCallback(
    (messageId: string) => {
      const msgIndex = messages.findIndex((m) => m.id === messageId)
      if (msgIndex === -1) return

      const userMessage = messages[msgIndex - 1]
      if (!userMessage || userMessage.role !== 'user') return

      const newMessages = messages.slice(0, msgIndex - 1)
      useChatStore.setState({ messages: newMessages })

      handleSend(userMessage.content)
    },
    [messages, handleSend]
  )

  const handleExportChat = useCallback(
    (format: 'markdown' | 'json') => {
      if (messages.length === 0) {
        message.warning('暂无对话内容')
        return
      }

      const title = messages.find((m) => m.role === 'user')?.content.slice(0, 20) || '新对话'

      if (format === 'markdown') {
        let content = `# ${title}\n\n`
        content += `导出时间: ${new Date().toLocaleString('zh-CN')}\n\n---\n\n`

        for (const msg of messages) {
          const role = msg.role === 'user' ? '用户' : '助手'
          content += `## ${role}\n\n${msg.content}\n\n`
        }

        const blob = new Blob([content], { type: 'text/markdown' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${title}_${Date.now()}.md`
        a.click()
        URL.revokeObjectURL(url)
        message.success('已导出为 Markdown')
      } else {
        const data = {
          title,
          exportedAt: new Date().toISOString(),
          messages,
        }
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${title}_${Date.now()}.json`
        a.click()
        URL.revokeObjectURL(url)
        message.success('已导出为 JSON')
      }
    },
    [messages]
  )

  const handleClearChat = useCallback(() => {
    Modal.confirm({
      title: '确认清空',
      content: '确定要清空当前对话吗？',
      okText: '清空',
      okButtonProps: { danger: true },
      onOk: () => {
        clearMessages()
        message.success('对话已清空')
      },
    })
  }, [clearMessages])

  const enableVirtualScroll = messages.length > VIRTUAL_SCROLL_THRESHOLD

  const modelOptions =
    settings.backend === 'ollama'
      ? ollamaModels.map((m) => ({ id: m.id, name: m.name }))
      : hfModels.map((m) => ({ id: m.id, name: m.name }))

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
        backends={backends}
        onBackendChange={async (backend) => {
          setUseCloudAI(false)
          localStorage.setItem('chat_use_cloud_ai', '0')
          updateSettings({ backend: backend as 'ollama' | 'huggingface' | 'cloud', modelId: '' })
          await loadBackends(backend)
        }}
        currentModel={settings.modelId}
        models={modelOptions}
        onModelChange={(model) => updateSettings({ modelId: model })}
        useCloudAI={useCloudAI}
        onToggleCloudAI={() => {
          if (!cloudAIConfig?.api_key && !cloudAIConfig?.key_id) {
            setConfigModalOpen(true)
          } else {
            setUseCloudAI(!useCloudAI)
          }
        }}
        cloudAIConfigured={!!(cloudAIConfig?.api_key || cloudAIConfig?.key_id)}
        onOpenCloudAIConfig={() => setConfigModalOpen(true)}
        useKnowledge={settings.useKnowledge}
        onToggleKnowledge={() => updateSettings({ useKnowledge: !settings.useKnowledge })}
        collectionsCount={collections.length}
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
                  isStreaming={isActivelyStreaming && index === messages.length - 1 && msg.role === 'assistant'}
                  onRetry={msg.role === 'assistant' ? () => handleRetry(msg.id) : undefined}
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
                    isActivelyStreaming && msg.id === messages[messages.length - 1]?.id && msg.role === 'assistant'
                  }
                  onRetry={msg.role === 'assistant' ? () => handleRetry(msg.id) : undefined}
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
        suggestions={['帮我解释一下这个概念', '写一段代码实现...', '分析这个问题', '总结一下要点']}
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

      <Modal open={configModalOpen} onCancel={() => setConfigModalOpen(false)} footer={null} width={600}>
        <APIKeyManager
          onConfigChange={(config: APIKeyConfig) => {
            setCloudAIConfig(config)
            if (config.model) {
              setSelectedCloudModel(config.model)
            }
          }}
          initialConfig={cloudAIConfig}
        />
      </Modal>
    </motion.div>
  )
}

export default ChatPage

