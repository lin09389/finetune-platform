import React from 'react'
import { Virtuoso } from 'react-virtuoso'
import { motion } from 'framer-motion'
import ChatMessageComponent from '../../../components/ChatMessage'
import type { ChatMessage } from '../../../types'
import styles from './ChatMessageList.module.css'

interface ChatMessageListProps {
  messages: ChatMessage[]
  isStreaming: boolean
  enableVirtualScroll: boolean
  onRetry: (id: string) => void
  onDelete: (id: string) => void
}

const ChatMessageList: React.FC<ChatMessageListProps> = ({
  messages,
  isStreaming,
  enableVirtualScroll,
  onRetry,
  onDelete
}) => {
  if (messages.length === 0) {
    return (
      <div className={styles.emptyContainer}>
        <motion.div
          initial={{ opacity: 0, scale: 0.9, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          transition={{ type: 'spring', damping: 20, stiffness: 100 }}
          className={styles.emptyContent}
        >
          <div className={styles.emptyIcon}>🤖</div>
          <h3 className={styles.emptyTitle}>开始新的对话</h3>
          <p className={styles.emptySubtitle}>选择模型后，输入您的问题开始对话</p>
        </motion.div>
      </div>
    )
  }

  const renderMessage = (index: number, msg: ChatMessage) => (
    <div className={styles.messageWrapper}>
      <ChatMessageComponent
        key={msg.id}
        role={msg.role as 'user' | 'assistant'}
        content={msg.content}
        timestamp={msg.timestamp}
        isLoading={msg.isLoading}
        isStreaming={isStreaming && index === messages.length - 1 && msg.role === 'assistant'}
        onRetry={msg.role === 'assistant' ? () => onRetry(msg.id) : undefined}
        onDelete={() => onDelete(msg.id)}
        knowledge_sources={msg.knowledge_sources}
        retrieval_info={msg.retrieval_info}
      />
    </div>
  )

  return (
    <div className={styles.container}>
      <div className={styles.inner}>
        {enableVirtualScroll ? (
          <Virtuoso
            data={messages}
            itemContent={renderMessage}
            followOutput="smooth"
            className={styles.virtuoso}
            alignToBottom
          />
        ) : (
          <div className={styles.messageList}>
            {messages.map((msg, index) => renderMessage(index, msg))}
          </div>
        )}
      </div>
    </div>
  )
}

export default ChatMessageList
