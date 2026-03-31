import React, { useCallback } from 'react'
import { Space, Select, Dropdown, Tooltip, Modal, message } from 'antd'
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
import NeumorphicButton from '../../../components/shared/NeumorphicButton'
import styles from './ChatHeader.module.css'

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
    <div className={styles.header}>
      <Space size="middle">
        <NeumorphicButton
          variant="primary"
          size="sm"
          onClick={onNewChat}
          icon={<PlusOutlined />}
        >
          新对话
        </NeumorphicButton>
        
        <Space size="small">
          <Tooltip title="历史记录">
            <NeumorphicButton size="sm" variant="ghost" onClick={onOpenHistory}>
              <HistoryOutlined />
            </NeumorphicButton>
          </Tooltip>
          
          <Tooltip title="智能记忆">
            <NeumorphicButton size="sm" variant="ghost" onClick={onOpenMemory}>
              <BulbOutlined />
            </NeumorphicButton>
          </Tooltip>
        </Space>

        <div className={styles.divider} />

        <Space size="small">
          <Tooltip title={!cloudAIConfigured ? '点击配置云端 AI' : useCloudAI ? '当前使用云端 AI' : '切换到云端 AI'}>
            <NeumorphicButton
              size="sm"
              variant={useCloudAI ? 'primary' : 'ghost'}
              active={useCloudAI}
              onClick={() => {
                if (!cloudAIConfigured) {
                  onOpenCloudAIConfig()
                } else {
                  onToggleCloudAI()
                }
              }}
            >
              <CloudOutlined />
              <span className={styles.btnText}>{useCloudAI ? '云端' : '本地'}</span>
            </NeumorphicButton>
          </Tooltip>
          
          <Tooltip title={collectionsCount === 0 ? '请先在知识库页面上传文档' : useKnowledge ? '禁用知识库检索' : '启用知识库检索'}>
            <NeumorphicButton
              size="sm"
              variant={useKnowledge ? 'primary' : 'ghost'}
              active={useKnowledge}
              onClick={onToggleKnowledge}
              disabled={collectionsCount === 0}
            >
              <BookOutlined />
              <span className={styles.btnText}>知识库</span>
            </NeumorphicButton>
          </Tooltip>
          
          <Tooltip title={useMemory ? '禁用记忆系统' : '启用记忆系统'}>
            <NeumorphicButton
              size="sm"
              variant={useMemory ? 'primary' : 'ghost'}
              active={useMemory}
              onClick={onToggleMemory}
            >
              <BulbOutlined />
              <span className={styles.btnText}>记忆</span>
            </NeumorphicButton>
          </Tooltip>
        </Space>
      </Space>

      <Space size="middle">
        <Tooltip title={theme === 'light' ? '切换到深色模式' : '切换到浅色模式'}>
          <motion.div whileTap={{ scale: 0.9 }}>
            <NeumorphicButton
              size="sm"
              variant="ghost"
              onClick={onToggleTheme}
            >
              {theme === 'light' ? <MoonOutlined /> : <SunOutlined />}
            </NeumorphicButton>
          </motion.div>
        </Tooltip>
        
        {!useCloudAI && (
          <Space size="small">
            <Select
              value={currentBackend}
              onChange={onBackendChange}
              className={styles.select}
              options={backendOptions}
              bordered={false}
            />
            
            <Select
              placeholder={currentBackend === 'ollama' ? '选择模型' : '选择模型'}
              value={currentModel}
              onChange={onModelChange}
              className={styles.modelSelect}
              options={modelOptions}
              disabled={isLoading || isStreaming}
              loading={models.length === 0}
              bordered={false}
            />
          </Space>
        )}
        
        <Dropdown
          trigger={['click']}
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
          <NeumorphicButton size="sm" variant="ghost">
            <MoreOutlined />
          </NeumorphicButton>
        </Dropdown>
      </Space>
    </div>
  )
}

export default ChatHeader
