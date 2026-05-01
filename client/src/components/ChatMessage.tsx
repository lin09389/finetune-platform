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
import React, { memo, useCallback, useMemo, useState, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';
import rehypeRaw from 'rehype-raw';
import remarkGfm from 'remark-gfm';
import CodePreview from '../components/CodePreview';
import AgentRunCard from '../components/chat/AgentRunCard';
import ThinkingProcess from '../components/ThinkingProcess';
import { useTypewriter } from '../hooks/chat/useTypewriter';
import { messageVariants, transitions } from '../theme/animations';
import type { ChatAgentMetadata, KnowledgeSource, RetrievalInfo } from '../types';
import styles from './ChatMessage.module.css';

interface ChatMessageProps {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  thinkingContent?: string;
  timestamp?: string;
  onRetry?: (id: string) => void;
  onDelete?: (id: string) => Promise<void>;
  onEdit?: (id: string, newContent: string) => void;
  isLoading?: boolean;
  isStreaming?: boolean;
  enableTypewriter?: boolean;
  typewriterSpeed?: number;
  knowledge_sources?: KnowledgeSource[];
  retrieval_info?: RetrievalInfo;
  agent_metadata?: ChatAgentMetadata;
  onApproveAgentStep?: (stepId: string) => void | Promise<void>;
  onApproveAgentAction?: (actionId: string) => void | Promise<void>;
  onRejectAgentAction?: (actionId: string) => void | Promise<void>;
  onExecuteAgentAction?: (actionId: string) => void | Promise<void>;
  onRefreshAgentRun?: (runId: string) => void | Promise<void>;
  onOpenAgentDetails?: (url: string) => void;
}

const customSanitizeSchema = {
  ...defaultSchema,
  attributes: {
    ...defaultSchema.attributes,
    span: [...(defaultSchema.attributes?.span || []), 'className'],
  },
};

const ChatMessage: React.FC<ChatMessageProps> = memo(
  ({
    id,
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
    agent_metadata,
    onApproveAgentStep,
    onApproveAgentAction,
    onRejectAgentAction,
    onExecuteAgentAction,
    onRefreshAgentRun,
    onOpenAgentDetails,
  }) => {
    const [copied, setCopied] = useState(false);
    const [showKnowledgeSources, setShowKnowledgeSources] = useState(false);
    const [isEditing, setIsEditing] = useState(false);
    const [editContent, setEditContent] = useState(content);

    const isUser = role === 'user';
    const isAssistant = role === 'assistant';

    // Typewriter effect handles progressive reveal for assistant messages
    const { processedContent, isDoneTyping } = useTypewriter(
      content,
      isStreaming && isAssistant && enableTypewriter,
      typewriterSpeed
    );

    // Provide a stable ref for isActuallyTyping to the markdown components
    const isActuallyTypingRef = useRef(false);
    isActuallyTypingRef.current = isAssistant && enableTypewriter && (isStreaming || !isDoneTyping);

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
        onEdit?.(id, editContent.trim());
      }
      setIsEditing(false);
    }, [id, editContent, content, onEdit]);

    const handleDelete = useCallback(() => {
      if (onDelete) {
        onDelete(id).catch((error) => {
          const errMsg = error instanceof Error ? error.message : '删除消息失败';
          message.error(errMsg);
        });
      }
    }, [id, onDelete]);

    const handleRetry = useCallback(() => {
      onRetry?.(id);
    }, [id, onRetry]);

    const formatTime = useCallback((timeStr?: string) => {
      if (!timeStr) return '';
      return new Date(timeStr).toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
      });
    }, []);

    // Memoize markdown components to avoid unnecessary remounts
    const markdownComponents = useMemo(
      () => ({
        code({ inline, className, children, ...props }: any) {
          const match = /language-(\w+)/.exec(className || '');
          const language = match ? match[1] : 'text';
          
          if (inline) {
            return (
              <code
                style={{
                  backgroundColor: 'color-mix(in srgb, var(--text-primary) 6%, transparent)',
                  padding: '3px 6px',
                  borderRadius: '6px',
                  fontSize: '0.85em',
                  color: 'var(--accent-primary)',
                  fontFamily: 'var(--font-mono)',
                }}
                {...props}
              >
                {children}
              </code>
            );
          }

          const codeText = String(children).replace(/\n$/, '');

          // Use lightweight block during active streaming to prevent UI stutter
          if (isActuallyTypingRef.current) {
            return (
              <div style={{
                background: '#f4f4f5',
                borderRadius: '12px',
                margin: '12px 0',
                overflow: 'hidden'
              }}>
                <div style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '8px 16px',
                  color: '#666',
                  fontSize: 13,
                  fontFamily: 'var(--font-mono)'
                }}>
                  <span>{language}</span>
                  <span className={styles.pulseIndicator}>●</span>
                </div>
                <pre style={{
                  margin: 0,
                  padding: '0 16px 16px 16px',
                  background: 'transparent',
                  overflowX: 'auto',
                  border: 'none'
                }}>
                  <code style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', color: '#24292e', whiteSpace: 'pre' }}>
                    {codeText}
                  </code>
                </pre>
              </div>
            );
          }

          return (
            <CodePreview
              code={codeText}
              language={language}
              showLineNumbers={false}
              collapsible={false}
              showFullscreen={false}
              showSave={false}
              defaultFilename={`code_${language}`}
              maxHeight={600}
            />
          );
        },
        p: ({ children }: any) => (
          <p style={{ margin: 'var(--space-2) 0', lineHeight: 1.7 }}>{children}</p>
        ),
        ul: ({ children }: any) => (
          <ul style={{ margin: 'var(--space-3) 0', paddingLeft: '1.5rem', lineHeight: 1.7 }}>
            {children}
          </ul>
        ),
        ol: ({ children }: any) => (
          <ol style={{ margin: 'var(--space-3) 0', paddingLeft: '1.5rem', lineHeight: 1.7 }}>
            {children}
          </ol>
        ),
        li: ({ children }: any) => (
          <li style={{ margin: '4px 0' }}>{children}</li>
        ),
        h1: ({ children }: any) => (
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
        h2: ({ children }: any) => (
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
        h3: ({ children }: any) => (
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
        blockquote: ({ children }: any) => (
          <blockquote
            style={{
              margin: 'var(--space-3) 0',
              padding: 'var(--space-2) var(--space-4)',
              borderLeft: '4px solid var(--accent-primary)',
              background: 'color-mix(in srgb, var(--accent-primary) 8%, transparent)',
              borderRadius: '0 var(--radius-lg) var(--radius-lg) 0',
              color: 'var(--text-secondary)',
            }}
          >
            {children}
          </blockquote>
        ),
        table: ({ children }: any) => (
          <div
            style={{
              overflowX: 'auto',
              margin: 'var(--space-3) 0',
              borderRadius: 'var(--radius-lg)',
              border: '1px solid var(--border-color)',
            }}
          >
            <table
              style={{
                width: '100%',
                borderCollapse: 'collapse',
                fontSize: '14px',
              }}
            >
              {children}
            </table>
          </div>
        ),
        th: ({ children }: any) => (
          <th style={{ padding: '12px 16px', borderBottom: '1px solid var(--border-color)', background: 'var(--bg-secondary)', fontWeight: 600, textAlign: 'left' }}>
            {children}
          </th>
        ),
        td: ({ children }: any) => (
          <td style={{ padding: '10px 16px', borderBottom: '1px solid var(--border-color)' }}>
            {children}
          </td>
        ),
        tr: ({ children }: any) => (
          <tr className={styles.tableRow}>
            {children}
          </tr>
        ),
      }),
      []
    );

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
              className={styles.shimmeringLoading}
            >
              <div className={styles.shimmerLine} style={{ width: '80%' }} />
              <div className={styles.shimmerLine} style={{ width: '100%' }} />
              <div className={styles.shimmerLine} style={{ width: '60%' }} />
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
              ) : agent_metadata ? (
                <AgentRunCard
                  content={content}
                  metadata={agent_metadata}
                  onApproveStep={onApproveAgentStep}
                  onApproveAction={onApproveAgentAction}
                  onRejectAction={onRejectAgentAction}
                  onExecuteAction={onExecuteAgentAction}
                  onRefreshRun={onRefreshAgentRun}
                  onOpenDetails={onOpenAgentDetails}
                />
              ) : (
                <>
                  {thinkingContent && (
                    <div className={styles.thinkingWrapper}>
                      <ThinkingProcess content={thinkingContent} isStreaming={isStreaming} />
                    </div>
                  )}
                  
                  <div className="streaming-content progressive-markdown">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      rehypePlugins={[rehypeRaw, [rehypeSanitize, customSanitizeSchema]]}
                      components={markdownComponents}
                    >
                      {processedContent}
                    </ReactMarkdown>
                  </div>
                  
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
                {onRetry && !isUser && (
                  <Tooltip title="重新生成">
                    <Button
                      type="text"
                      size="small"
                      icon={<ReloadOutlined />}
                      onClick={handleRetry}
                      className={styles.actionBtn}
                    />
                  </Tooltip>
                )}
                {onDelete && (
                  <Tooltip title="删除消息">
                    <Button
                      type="text"
                      size="small"
                      icon={<DeleteOutlined />}
                      onClick={handleDelete}
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
