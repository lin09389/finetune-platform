import React, { useEffect, useCallback, useState } from 'react'
import { Modal, message } from 'antd'
import { useChatStore } from '../../store/chatStore'
import { useChatStream } from '../../hooks/chat/useChatStream'
import { useAgentExecutor } from '../../hooks/chat/useAgentExecutor'
import { useTheme } from '../../theme'

import ChatHeader from './components/ChatHeader'
import ChatInput from './components/ChatInput'
import ChatMessageList from './components/ChatMessageList'
import AgentStatus from './components/AgentStatus'
import ChatHistoryDrawer from '../../components/ChatHistoryDrawer'
import MemoryManager from '../../components/MemoryManager'
import APIKeyManager from '../../pages/APIKeyManager'
import AnimatedLayout from '../../components/shared/AnimatedLayout'

import { 
  getBackends, 
  getOllamaStatus, 
  getInferenceModels, 
  API_BASE_URL,
} from '../../services/api'

const VIRTUAL_SCROLL_THRESHOLD = 50 // 优化后的阈值

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
  
  const {
    sessions,
    messages,
    settings,
    agentExecution,
    isLoading,
    createSession,
    loadSession,
    deleteSession,
    loadSessions,
    addMessage,
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

  const { 
    sendMessage, 
    sendCloudMessage, 
    stop: stopStream, 
    isStreaming: isActivelyStreaming,
  } = useChatStream({
    onChunk: () => {},
    onComplete: () => {},
    onError: (error) => message.error(error),
  })

  const {
    executeFromMessage,
    confirmExecution,
    cancelExecution,
  } = useAgentExecutor({
    onConfirmRequired: (task, msg) => {
      console.log('需要确认:', task.action, msg)
    },
  })

  useEffect(() => {
    Promise.allSettled([
      loadBackends(),
      loadSessions(),
      loadCloudAIConfig(),
      loadCollections(),
    ]).then((results) => {
      const failed = results.filter(r => r.status === 'rejected')
      if (failed.length > 0) {
        console.warn(`${failed.length} 个初始请求失败`)
      }
    })
  }, [])

  const loadBackends = async () => {
    try {
      const data = await getBackends()
      
      if (data.current === 'ollama') {
        const ollamaStatus = await getOllamaStatus()
        setOllamaModels(ollamaStatus.models.map((m: { name: string }) => ({
          id: m.name,
          name: m.name,
        })))
        if (!settings.modelId && ollamaStatus.models.length > 0) {
          updateSettings({ modelId: ollamaStatus.models[0].name })
        }
      } else {
        const models = await getInferenceModels()
        setHfModels(models.map((m: { id: string; name?: string }) => ({
          id: m.id,
          name: m.name || m.id,
        })))
        if (!settings.modelId && models.length > 0) {
          updateSettings({ modelId: models[0].id })
        }
      }

      setBackends([
        { id: 'ollama', name: 'Ollama', available: data.current === 'ollama' },
        { id: 'huggingface', name: 'HuggingFace', available: data.current === 'huggingface' },
      ])
    } catch (error) {
      console.error('加载后端失败:', error)
    }
  }

  const loadCollections = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/knowledge/collections`)
      if (response.ok) {
        const data = await response.json()
        setCollections(data.collections.map((c: { name: string; count?: number }) => ({
          id: c.name,
          name: c.name,
          count: c.count || 0,
        })))
      }
    } catch (error) {
      console.error('加载知识库列表失败:', error)
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
            .then(r => r.json())
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
          setUseCloudAI(true)
          setSelectedCloudModel('MiniMax-M2.5')
          return
        }
      }
    } catch (e) {
      console.log('从后端加载配置失败')
    }
    
    const saved = localStorage.getItem('cloud_ai_config')
    if (saved) {
      try {
        const config = JSON.parse(saved)
        setCloudAIConfig(config)
        if (config.api_key || config.key_id) {
          setUseCloudAI(true)
        }
        if (config.model) {
          setSelectedCloudModel(config.model)
        }
      } catch (e) {
        console.error('加载云端 AI 配置失败:', e)
      }
    }
  }

  const formatAgentResult = (result: unknown): string => {
    if (!result) return '操作完成'
    if (result && typeof result === 'object' && 'success' in result && result.success === false) {
      return `❌ 操作失败：${'error' in result ? result.error : '未知错误'}`
    }
    const resultObj = result as Record<string, unknown>
    const data = resultObj['data'] as Record<string, unknown> | undefined
    const action = data?.['action'] || resultObj['action'] || ''
    
    const actionMessages: Record<string, () => string> = {
      file_create: () => `✅ 文件已创建：${data?.['path'] || '完成'}`,
      file_read: () => `📄 文件内容：\n\`\`\`\n${data?.['content'] || ''}\n\`\`\``,
      file_write: () => `✅ 文件已更新：${data?.['path'] || '完成'}`,
      file_delete: () => `✅ 文件已删除`,
      file_list: () => {
        const files = (data?.['files'] || []) as Array<{ is_dir?: boolean; name: string }>
        return `📂 找到 ${data?.['count'] || 0} 个项目：\n${files.map((f) => 
          `${f.is_dir ? '📁' : '📄'} ${f.name}`
        ).join('\n')}`
      },
    }
    const formatter = actionMessages[action as string]
    return formatter ? formatter() : `✅ 操作完成：${resultObj['message'] || '成功'}`
  }

  const handleSend = useCallback(async (content: string) => {
    if (!content.trim()) return
    const agentResult = await executeFromMessage(content)
    if (agentResult.executed) {
      if (agentResult.result && typeof agentResult.result === 'object' && 'need_confirm' in agentResult.result) {
        return
      }
      const formattedResult = formatAgentResult(agentResult.result)
      addMessage({ role: 'assistant', content: formattedResult })
      return
    }
    if (useCloudAI && cloudAIConfig) {
      await sendCloudMessage(content, {
        provider: cloudAIConfig.provider,
        apiKey: cloudAIConfig.api_key,
        keyId: cloudAIConfig.key_id,
        model: selectedCloudModel,
        groupId: cloudAIConfig.group_id,
        baseUrl: cloudAIConfig.base_url,
      })
    } else {
      await sendMessage(content)
    }
  }, [executeFromMessage, addMessage, useCloudAI, cloudAIConfig, selectedCloudModel, sendCloudMessage, sendMessage])

  const handleRetry = useCallback((messageId: string) => {
    const msgIndex = messages.findIndex(m => m.id === messageId)
    if (msgIndex === -1) return
    const userMessage = messages[msgIndex - 1]
    if (!userMessage || userMessage.role !== 'user') return
    const newMessages = messages.slice(0, msgIndex - 1)
    useChatStore.setState({ messages: newMessages })
    handleSend(userMessage.content)
  }, [messages, handleSend])

  const handleExportChat = useCallback((format: 'markdown' | 'json') => {
    if (messages.length === 0) {
      message.warning('暂无对话内容')
      return
    }
    const title = messages.find(m => m.role === 'user')?.content.slice(0, 20) || '新对话'
    if (format === 'markdown') {
      let content = `# ${title}\n\n导出时间: ${new Date().toLocaleString('zh-CN')}\n\n---\n\n`
      for (const msg of messages) {
        const role = msg.role === 'user' ? '👤 用户' : '🤖 助手'
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
      const data = { title, exportedAt: new Date().toISOString(), messages }
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${title}_${Date.now()}.json`
      a.click()
      URL.revokeObjectURL(url)
      message.success('已导出为 JSON')
    }
  }, [messages])

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

  const modelOptions = settings.backend === 'ollama'
    ? ollamaModels.map(m => ({ id: m.id, name: m.name }))
    : hfModels.map(m => ({ id: m.id, name: m.name }))

  return (
    <AnimatedLayout animationKey="chat">
      <div style={{ height: 'calc(100vh - 72px)', display: 'flex', flexDirection: 'column' }}>
        <ChatHeader
          onNewChat={() => createSession()}
          onOpenHistory={() => setHistoryOpen(true)}
          onOpenMemory={() => setMemoryManagerOpen(true)}
          onClearChat={handleClearChat}
          onExportChat={handleExportChat}
          currentBackend={settings.backend}
          backends={backends}
          onBackendChange={async (backend) => {
            updateSettings({ backend: backend as 'ollama' | 'huggingface' | 'cloud', modelId: '' })
            await loadBackends()
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

        <AgentStatus
          agentExecution={agentExecution}
          onConfirm={confirmExecution}
          onCancel={cancelExecution}
        />

        <ChatMessageList
          messages={messages}
          isStreaming={isActivelyStreaming}
          enableVirtualScroll={messages.length > VIRTUAL_SCROLL_THRESHOLD}
          onRetry={handleRetry}
          onDelete={deleteMessage}
        />

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
          sessions={sessions.map(s => ({
            id: s.id,
            title: s.title,
            created_at: s.createdAt,
            updated_at: s.updatedAt,
            message_count: s.messageCount,
          }))}
          onLoadSession={(id) => loadSession(id)}
          onDeleteSession={(id) => deleteSession(id)}
        />

        <MemoryManager
          open={memoryManagerOpen}
          onClose={() => setMemoryManagerOpen(false)}
        />

        <Modal
          open={configModalOpen}
          onCancel={() => setConfigModalOpen(false)}
          footer={null}
          width={600}
        >
          <APIKeyManager
            onConfigChange={(config: APIKeyConfig) => {
              setCloudAIConfig(config)
              if (config.api_key || config.key_id) setUseCloudAI(true)
              if (config.model) setSelectedCloudModel(config.model)
            }}
            initialConfig={cloudAIConfig}
          />
        </Modal>
      </div>
    </AnimatedLayout>
  )
}

export default ChatPage
