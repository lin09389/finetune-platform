import {
  BookOutlined,
  CheckOutlined,
  CloseOutlined,
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { Button, Input, message, Space, Tag, Tooltip } from 'antd';
import { AnimatePresence, motion } from 'framer-motion';
import 'highlight.js/styles/atom-one-dark.css';
import React, { memo, useCallback, useMemo, useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import rehypeSanitize from 'rehype-sanitize';
import remarkGfm from 'remark-gfm';
import CodePreview from '../components/CodePreview';
import StreamingMessage from '../components/StreamingMessage';
import ThinkingProcess from '../components/ThinkingProcess';
import { messageVariants, transitions, typingIndicatorVariants } from '../theme/animations';
import type { KnowledgeSource, RetrievalInfo } from '../types';
import styles from './ChatMessage.module.css';

interface ChatMessageProps {
  role: 'user' | 'assistant' | 'system';
  content: string;
  thinkingContent?: string;
  timestamp?: string;
  onRetry?: () => void;
  onDelete?: () => void;
  onEdit?: (newContent: string) => void;
  isLoading?: boolean;
  isStreaming?: boolean;
  enableTypewriter?: boolean;
  typewriterSpeed?: number;
  knowledge_sources?: KnowledgeSource[];
  retrieval_info?: RetrievalInfo;
}

const ChatMessage: React.FC<ChatMessageProps> = memo(
  ({
    role,
    content,
    thinkingContent,
    timestamp,
    onRetry,
    onDelete,
    onEdit,
    isLoading = false,
    isStreaming = false,
    enableTypewriter = true,
    typewriterSpeed = 50,
    knowledge_sources,
  }) => {
    const [copied, setCopied] = useState(false);
    const [showKnowledgeSources, setShowKnowledgeSources] = useState(false);
    const [isEditing, setIsEditing] = useState(false);
    const [editContent, setEditContent] = useState(content);
    const [isDoneTyping, setIsDoneTyping] = useState(false);

    const isUser = role === 'user';
    const isAssistant = role === 'assistant';

    const shouldUseStreaming = useMemo(() => {
      // Keep using StreamingMessage until both stream is over AND typing is done
      return isAssistant && enableTypewriter && (isStreaming || !isDoneTyping);
    }, [isAssistant, enableTypewriter, isStreaming, isDoneTyping]);

    // Reset isDoneTyping when a new streaming session starts
    useEffect(() => {
      if (isStreaming) {
        setIsDoneTyping(false);
      }
    }, [isStreaming]);

    const handleCopy = useCallback(async () => {
      try {
        await navigator.clipboard.writeText(content);
        setCopied(true);
        message.success('已复制到剪贴板');
        setTimeout(() => setCopied(false), 2000);
      } catch {
        message.error('复制失败');
      }
    }, [content]);

    const handleSaveEdit = useCallback(() => {
      if (editContent.trim() && editContent !== content) {
        onEdit?.(editContent.trim());
      }
      setIsEditing(false);
    }, [editContent, content, onEdit]);

    const formatTime = useCallback((timeStr?: string) => {
      if (!timeStr) return '';
      return new Date(timeStr).toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
      });
    }, []);

    return (
      <motion.div
        className={`${styles.messageContainer} ${isUser ? styles.userContainer : styles.assistantContainer}`}
        role="article"
        aria-label={isUser ? '用户消息' : 'AI 回复'}
        variants={messageVariants}
        initial="initial"
        animate="animate"
        exit="exit"
      >
        <motion.div
          className={`${styles.bubble} ${isUser ? styles.userBubble : styles.assistantBubble} ${
            isLoading && isAssistant ? styles.loadingBubble : ''
          }`}
          role="region"
          aria-live={isUser ? 'off' : 'polite'}
          initial={{ scale: 0.98, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={transitions.springGentle}
          style={isEditing ? { width: '100%', maxWidth: '800px' } : undefined}
        >
          {isLoading ? (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              style={{ display: 'flex', gap: 6, padding: 'var(--space-2) 0', alignItems: 'center' }}
            >
              {[0, 1, 2].map((i) => (
                <motion.span
                  key={i}
                  variants={typingIndicatorVariants}
                  initial="initial"
                  animate="animate"
                  transition={{ delay: i * 0.15 }}
                  style={{
                    width: 6,
                    height: 6,
                    backgroundColor: isUser ? 'rgba(255,255,255,0.6)' : 'var(--text-tertiary)',
                    borderRadius: '50%',
                  }}
                />
              ))}
              <span
                style={{
                  marginLeft: 8,
                  fontSize: '12px',
                  fontWeight: 600,
                  color: isUser ? 'rgba(255,255,255,0.8)' : 'var(--text-secondary)',
                }}
              >
                思考中...
              </span>
            </motion.div>
          ) : (
            <div className={styles.markdownContent}>
              {isUser ? (
                isEditing ? (
                  <div className={styles.editMode}>
                    <Input.TextArea
                      value={editContent}
                      onChange={(e) => setEditContent(e.target.value)}
                      autoSize={{ minRows: 2, maxRows: 10 }}
                      className={styles.editInput}
                      autoFocus
                    />
                    <div className={styles.editActions}>
                      <Button
                        size="small"
                        type="text"
                        onClick={() => {
                          setIsEditing(false);
                          setEditContent(content);
                        }}
                        icon={<CloseOutlined />}
                        style={{ color: 'white' }}
                      >
                        取消
                      </Button>
                      <Button
                        size="small"
                        type="primary"
                        onClick={handleSaveEdit}
                        icon={<CheckOutlined />}
                        style={{
                          background: 'white',
                          color: 'var(--accent-primary)',
                          fontWeight: 600,
                        }}
                      >
                        发送
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div>{content}</div>
                )
              ) : (
                <>
                  {thinkingContent && (
                    <div className={styles.thinkingWrapper}>
                      <ThinkingProcess content={thinkingContent} isStreaming={isStreaming} />
                    </div>
                  )}
                  {shouldUseStreaming ? (
                    <StreamingMessage
                      content={content}
                      isStreaming={isStreaming}
                      speed={typewriterSpeed}
                      onTypingComplete={() => setIsDoneTyping(true)}
                    />
                  ) : (
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      rehypePlugins={[rehypeSanitize]}
                      components={{
                        code({ inline, className, children, ...props }: any) {
                          const match = /language-(\w+)/.exec(className || '');
                          const language = match ? match[1] : 'text';
                          if (inline) {
                            return (
                              <code
                                style={{
                                  backgroundColor: 'rgba(0,0,0,0.05)',
                                  padding: '2px 4px',
                                  borderRadius: '4px',
                                  fontSize: '0.9em',
                                  color: 'var(--error)',
                                  fontFamily: 'var(--font-mono)',
                                }}
                                {...props}
                              >
                                {children}
                              </code>
                            );
                          }
                          return (
                            <CodePreview
                              code={String(children)}
                              language={language}
                              showLineNumbers={true}
                              collapsible={false}
                              showFullscreen={true}
                              showSave={true}
                              defaultFilename={`code_${language}`}
                              maxHeight={400}
                            />
                          );
                        },
                        p: ({ children }) => (
                          <p style={{ margin: 'var(--space-2) 0' }}>{children}</p>
                        ),
                        ul: ({ children }) => (
                          <ul style={{ margin: 'var(--space-2) 0', paddingLeft: 24 }}>
                            {children}
                          </ul>
                        ),
                        ol: ({ children }) => (
                          <ol style={{ margin: 'var(--space-2) 0', paddingLeft: 24 }}>
                            {children}
                          </ol>
                        ),
                        li: ({ children }) => (
                          <li style={{ margin: 'var(--space-1) 0' }}>{children}</li>
                        ),
                        h1: ({ children }) => (
                          <h1
                            style={{
                              margin: 'var(--space-4) 0 var(--space-2)',
                              fontSize: 'var(--text-xl)',
                              fontWeight: 700,
                            }}
                          >
                            {children}
                          </h1>
                        ),
                        h2: ({ children }) => (
                          <h2
                            style={{
                              margin: 'var(--space-3) 0 var(--space-2)',
                              fontSize: 'var(--text-lg)',
                              fontWeight: 600,
                            }}
                          >
                            {children}
                          </h2>
                        ),
                        h3: ({ children }) => (
                          <h3
                            style={{
                              margin: 'var(--space-2) 0 var(--space-1)',
                              fontSize: '15px',
                              fontWeight: 600,
                            }}
                          >
                            {children}
                          </h3>
                        ),
                        blockquote: ({ children }) => (
                          <blockquote
                            style={{
                              margin: 'var(--space-3) 0',
                              padding: 'var(--space-2) var(--space-3)',
                              borderLeft: '4px solid var(--accent-primary)',
                              background: 'rgba(212, 163, 115, 0.05)',
                              borderRadius: '0 var(--radius-md) var(--radius-md) 0',
                              fontStyle: 'italic',
                            }}
                          >
                            {children}
                          </blockquote>
                        ),
                        table: ({ children }) => (
                          <div
                            style={{
                              overflowX: 'auto',
                              margin: 'var(--space-3) 0',
                              borderRadius: 'var(--radius-lg)',
                              border: '1px solid var(--border-color)',
                            }}
                          >
                            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                              {children}
                            </table>
                          </div>
                        ),
                        th: ({ children }) => (
                          <th
                            style={{
                              padding: 'var(--space-2)',
                              background: 'var(--bg-elevated)',
                              fontWeight: 700,
                              borderBottom: '1px solid var(--border-color)',
                              textAlign: 'left',
                            }}
                          >
                            {children}
                          </th>
                        ),
                        td: ({ children }) => (
                          <td
                            style={{
                              padding: 'var(--space-2)',
                              borderBottom: '1px solid var(--border-color)',
                            }}
                          >
                            {children}
                          </td>
                        ),
                      }}
                    >
                      {content}
                    </ReactMarkdown>
                  )}
                  {knowledge_sources && knowledge_sources.length > 0 && showKnowledgeSources && (
                    <div className={styles.knowledgeWrapper}>
                      <AnimatePresence>
                        <motion.div
                          initial={{ opacity: 0, height: 0 }}
                          animate={{ opacity: 1, height: 'auto' }}
                          exit={{ opacity: 0, height: 0 }}
                        >
                          <Space wrap>
                            {knowledge_sources.map((s, i) => (
                              <Tag
                                key={i}
                                color="blue"
                                style={{ borderRadius: 'var(--radius-sm)' }}
                              >
                                [{i + 1}] {s.source}
                              </Tag>
                            ))}
                          </Space>
                        </motion.div>
                      </AnimatePresence>
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </motion.div>

        <div className={styles.footer}>
          <span className={styles.timestamp}>{formatTime(timestamp)}</span>

          {!isLoading && !isEditing && (
            <div className={styles.actions} style={isUser ? { flexDirection: 'row-reverse' } : {}}>
              <Space size={4}>
                {isUser ? (
                  <Tooltip title="编辑此消息">
                    <Button
                      type="text"
                      size="small"
                      icon={<EditOutlined />}
                      onClick={() => setIsEditing(true)}
                      style={{ color: 'var(--text-tertiary)' }}
                    />
                  </Tooltip>
                ) : (
                  <Tooltip title={copied ? '已复制' : '复制内容'}>
                    <Button
                      type="text"
                      size="small"
                      icon={
                        copied ? (
                          <CheckOutlined style={{ color: 'var(--success)' }} />
                        ) : (
                          <CopyOutlined />
                        )
                      }
                      onClick={handleCopy}
                      className={styles.actionBtn}
                    />
                  </Tooltip>
                )}
                {onRetry && (
                  <Tooltip title="重新生成">
                    <Button
                      type="text"
                      size="small"
                      icon={<ReloadOutlined />}
                      onClick={onRetry}
                      className={styles.actionBtn}
                      style={isUser ? { color: 'var(--text-tertiary)' } : undefined}
                    />
                  </Tooltip>
                )}
                {onDelete && (
                  <Tooltip title="删除消息">
                    <Button
                      type="text"
                      size="small"
                      icon={<DeleteOutlined />}
                      onClick={onDelete}
                      className={styles.actionBtn}
                      style={isUser ? { color: 'var(--text-tertiary)' } : undefined}
                      danger={!isUser}
                    />
                  </Tooltip>
                )}
                {knowledge_sources && knowledge_sources.length > 0 && (
                  <Tooltip title="查看知识来源">
                    <Button
                      type="text"
                      size="small"
                      icon={<BookOutlined />}
                      onClick={() => setShowKnowledgeSources(!showKnowledgeSources)}
                      className={styles.actionBtn}
                    >
                      <span style={{ fontSize: 10, marginLeft: 2 }}>
                        {knowledge_sources.length}
                      </span>
                    </Button>
                  </Tooltip>
                )}
              </Space>
            </div>
          )}
        </div>
      </motion.div>
    );
  },
);

ChatMessage.displayName = 'ChatMessage';

export default ChatMessage;
