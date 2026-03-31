import React, { useCallback } from 'react'
import { Button, Space, Select, Dropdown, Tooltip, Modal, message } from 'antd'
import { 
  PlusOutlined, 
  HistoryOutlined, 
  ExportOutlined, 
  MoreOutlined, 
  ClearOutlined,
  CloudOutlined,
  BookOutlined,
  BulbOutlined,
  SunOutlined,
  MoonOutlined,
} from '@ant-design/icons'
import { motion } from 'framer-motion'
import { transitions } from '../../theme/animations'

interface BackendInfo {
  id: string
  name: string
  available: boolean
}

interface ChatHeaderProps {
  onNewChat: () => void
  onOpenHistory: () => void
  onOpenMemory: () => void
  onClearChat: () => void
  onExportChat: (format: 'markdown' | 'json') => void
  
  currentBackend: string
  backends: BackendInfo[]
  onBackendChange: (backend: string) => void
  
  currentModel: string | undefined
  models: { id: string; name: string }[]
  onModelChange: (model: string) => void
  
  useCloudAI: boolean
  onToggleCloudAI: () => void
  cloudAIConfigured: boolean
  onOpenCloudAIConfig: () => void
  
  useKnowledge: boolean
  onToggleKnowledge: () => void
  collectionsCount: number
  
  useMemory: boolean
  onToggleMemory: () => void
  
  theme: 'light' | 'dark'
  onToggleTheme: () => void
  
  messageCount: number
  isLoading: boolean
  isStreaming: boolean
}

const ChatHeader: React.FC<ChatHeaderProps> = ({
  onNewChat,
  onOpenHistory,
  onOpenMemory,
  onClearChat,
  onExportChat,
  currentBackend,
  backends,
  onBackendChange,
  currentModel,
  models,
  onModelChange,
  useCloudAI,
  onToggleCloudAI,
  cloudAIConfigured,
  onOpenCloudAIConfig,
  useKnowledge,
  onToggleKnowledge,
  collectionsCount,
  useMemory,
  onToggleMemory,
  theme,
  onToggleTheme,
  messageCount,
  isLoading,
  isStreaming,
}) => {
  const handleExport = useCallback((format: 'markdown' | 'json') => {
    if (messageCount === 0) {
      message.warning('暂无对话内容')
      return
    }
    onExportChat(format)
  }, [messageCount, onExportChat])

  const handleClear = useCallback(() => {
    if (messageCount === 0) return
    
    Modal.confirm({
      title: '确认清空',
      content: '确定要清空当前对话吗？',
      okText: '清空',
      okButtonProps: { danger: true },
      onOk: onClearChat,
    })
  }, [messageCount, onClearChat])

  const backendOptions = backends.map(b => ({
    value: b.id,
    label: b.available ? b.name : `${b.name} (不可用)`,
    disabled: !b.available,
  }))

  const modelOptions = models.map(m => ({
    value: m.id,
    label: m.name,
  }))

  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1, ...transitions.base }}
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '12px 24px',
        background: 'var(--bg-secondary)',
        borderBottom: '1px solid var(--border-color)',
        flexShrink: 0,
      }}
    >
      <Space>
        <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={onNewChat}
            style={{ borderRadius: 8, height: 36 }}
          >
            新对话
          </Button>
        </motion.div>
        
        <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
          <Button
            icon={<HistoryOutlined />}
            onClick={onOpenHistory}
            style={{ borderRadius: 8, height: 36 }}
          >
            历史
          </Button>
        </motion.div>
        
        <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
          <Button
            icon={<BulbOutlined />}
            onClick={onOpenMemory}
            style={{ borderRadius: 8, height: 36 }}
          >
            记忆
          </Button>
        </motion.div>
        
        <Tooltip title={!cloudAIConfigured ? '点击配置云端 AI' : useCloudAI ? '当前使用云端 AI' : '切换到云端 AI'}>
          <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
            <Button
              icon={<CloudOutlined />}
              onClick={() => {
                if (!cloudAIConfigured) {
                  onOpenCloudAIConfig()
                } else {
                  onToggleCloudAI()
                }
              }}
              type={useCloudAI ? 'primary' : 'default'}
              style={{ borderRadius: 8, height: 36 }}
            >
              {useCloudAI ? '☁️ 云端' : '🤖 本地'}
            </Button>
          </motion.div>
        </Tooltip>
        
        <Tooltip title={collectionsCount === 0 ? '请先在知识库页面上传文档' : useKnowledge ? '禁用知识库检索' : '启用知识库检索'}>
          <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
            <Button
              icon={<BookOutlined />}
              onClick={onToggleKnowledge}
              type={useKnowledge ? 'primary' : 'default'}
              style={{ borderRadius: 8, height: 36 }}
              disabled={collectionsCount === 0}
            >
              知识库
            </Button>
          </motion.div>
        </Tooltip>
        
        <Tooltip title={useMemory ? '禁用记忆系统' : '启用记忆系统'}>
          <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
            <Button
              icon={<BulbOutlined />}
              onClick={onToggleMemory}
              type={useMemory ? 'primary' : 'default'}
              style={{ borderRadius: 8, height: 36 }}
            >
              记忆
            </Button>
          </motion.div>
        </Tooltip>
      </Space>

      <Space>
        <Tooltip title={theme === 'light' ? '切换到深色模式' : '切换到浅色模式'}>
          <motion.div 
            whileHover={{ scale: 1.05, rotate: 15 }} 
            whileTap={{ scale: 0.95 }}
          >
            <Button
              icon={theme === 'light' ? <MoonOutlined /> : <SunOutlined />}
              onClick={onToggleTheme}
              style={{ borderRadius: 8, height: 36 }}
            />
          </motion.div>
        </Tooltip>
        
        {!useCloudAI && (
          <>
            <Select
              value={currentBackend}
              onChange={onBackendChange}
              style={{ width: 130, borderRadius: 8 }}
              options={backendOptions}
            />
            
            <Select
              placeholder={currentBackend === 'ollama' ? '选择 Ollama 模型' : '选择模型'}
              value={currentModel}
              onChange={onModelChange}
              style={{ width: 180, borderRadius: 8 }}
              options={modelOptions}
              disabled={isLoading || isStreaming}
              loading={models.length === 0}
            />
          </>
        )}
        
        <Dropdown
          menu={{
            items: [
              { 
                key: 'md', 
                label: '导出 Markdown', 
                icon: <ExportOutlined />, 
                onClick: () => handleExport('markdown'),
                disabled: messageCount === 0,
              },
              { 
                key: 'json', 
                label: '导出 JSON', 
                icon: <ExportOutlined />, 
                onClick: () => handleExport('json'),
                disabled: messageCount === 0,
              },
              { type: 'divider' },
              { 
                key: 'clear', 
                label: '清空对话', 
                icon: <ClearOutlined />, 
                danger: true, 
                onClick: handleClear,
                disabled: messageCount === 0,
              },
            ],
          }}
        >
          <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
            <Button 
              icon={<MoreOutlined />} 
              style={{ borderRadius: 8, height: 36 }} 
            />
          </motion.div>
        </Dropdown>
      </Space>
    </motion.div>
  )
}

export default ChatHeader
