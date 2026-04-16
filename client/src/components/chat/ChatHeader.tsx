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
import { useResponsive } from '../../hooks/useResponsive'
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
  currentKnowledgeCollection?: string
  knowledgeCollections: { id: string; name: string; count: number }[]
  onKnowledgeCollectionChange: (collectionId: string) => void
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
  currentKnowledgeCollection,
  knowledgeCollections,
  onKnowledgeCollectionChange,
  useMemory,
  onToggleMemory,
  theme,
  onToggleTheme,
  messageCount,
  isLoading,
  isStreaming,
}) => {
  const { isMobile } = useResponsive()

  const handleExport = useCallback(
    (format: 'markdown' | 'json') => {
      if (messageCount === 0) {
        message.warning('暂无对话内容')
        return
      }
      onExportChat(format)
    },
    [messageCount, onExportChat]
  )

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

  const backendOptions = backends.map((b) => ({
    value: b.id,
    label: b.available ? b.name : `${b.name} (不可用)`,
    disabled: !b.available,
  }))

  const modelOptions = models.map((m) => ({
    value: m.id,
    label: m.name,
  }))

  const knowledgeCollectionOptions = knowledgeCollections.map((collection) => ({
    value: collection.id,
    label: `${collection.name} (${collection.count})`,
  }))

  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.08, ...transitions.base }}
      className={`${styles.header} ${isMobile ? styles.headerMobile : ''}`}
    >
      <Space wrap>
        <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
          <Button type="primary" icon={<PlusOutlined />} onClick={onNewChat} className={styles.actionButton}>
            新对话
          </Button>
        </motion.div>

        <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
          <Button icon={<HistoryOutlined />} onClick={onOpenHistory} className={styles.actionButton}>
            历史
          </Button>
        </motion.div>

        <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
          <Button icon={<BulbOutlined />} onClick={onOpenMemory} className={styles.actionButton}>
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
              className={styles.actionButton}
            >
              {useCloudAI ? '云端' : '本地'}
            </Button>
          </motion.div>
        </Tooltip>

        <Tooltip title={collectionsCount === 0 ? '请先在知识库页面上传文档' : useKnowledge ? '关闭知识检索' : '开启知识检索'}>
          <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
            <Button
              icon={<BookOutlined />}
              onClick={onToggleKnowledge}
              type={useKnowledge ? 'primary' : 'default'}
              className={styles.actionButton}
              disabled={collectionsCount === 0}
            >
              知识库
            </Button>
          </motion.div>
        </Tooltip>

        {useKnowledge && collectionsCount > 0 && (
          <Select
            value={currentKnowledgeCollection}
            onChange={onKnowledgeCollectionChange}
            style={{ width: isMobile ? 150 : 180, borderRadius: 8 }}
            className={styles.compactSelect}
            options={knowledgeCollectionOptions}
            placeholder="选择知识集合"
          />
        )}

        <Tooltip title={useMemory ? '关闭记忆系统' : '开启记忆系统'}>
          <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
            <Button
              icon={<BulbOutlined />}
              onClick={onToggleMemory}
              type={useMemory ? 'primary' : 'default'}
              className={styles.actionButton}
            >
              记忆
            </Button>
          </motion.div>
        </Tooltip>
      </Space>

      <Space wrap>
        <Tooltip title={theme === 'light' ? '切换到深色模式' : '切换到浅色模式'}>
          <motion.div whileHover={{ scale: 1.05, rotate: 12 }} whileTap={{ scale: 0.95 }}>
            <Button icon={theme === 'light' ? <MoonOutlined /> : <SunOutlined />} onClick={onToggleTheme} className={styles.actionButton} />
          </motion.div>
        </Tooltip>

        {!useCloudAI && (
          <>
            <Select
              value={currentBackend}
              onChange={onBackendChange}
              style={{ width: isMobile ? 120 : 130, borderRadius: 8 }}
              className={styles.compactSelect}
              options={backendOptions}
            />

            <Select
              placeholder={currentBackend === 'ollama' ? '选择 Ollama 模型' : '选择模型'}
              value={currentModel}
              onChange={onModelChange}
              style={{ width: isMobile ? 160 : 180, borderRadius: 8 }}
              className={styles.compactSelect}
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
            <Button icon={<MoreOutlined />} className={styles.actionButton} />
          </motion.div>
        </Dropdown>
      </Space>
    </motion.div>
  )
}

export default ChatHeader
