import {
  BookOutlined,
  CheckOutlined,
  CloseOutlined,
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  ReloadOutlined,
  RobotOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { Avatar, Button, Input, message, Space, Tag, Tooltip } from 'antd';
import { motion, AnimatePresence } from 'framer-motion';
import 'highlight.js/styles/atom-one-dark.css';
import React, { Suspense, lazy, memo, useCallback, useMemo, useState, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';
import rehypeRaw from 'rehype-raw';
import remarkGfm from 'remark-gfm';
import AgentPartMessage from '../components/chat/AgentPartMessage';
import AgentRunCard from '../components/chat/AgentRunCard';
import ThinkingProcess from '../components/ThinkingProcess';

const CodePreview = lazy(() => import('../components/CodePreview'));
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
    const { processedContent, isDoneTyping, splitContent } = useTypewriter(
      content,
      isStreaming && isAssistant && enableTypewriter,
      Math.max(typewriterSpeed, 32)
    );

    const shouldShowStreamingContent = isAssistant && (isStreaming || !isDoneTyping);

    const shouldUseSplitStreaming = shouldShowStreamingContent && splitContent.codeBlocks.length > 0;
    const shouldShowOpenFenceFallback = shouldShowStreamingContent && splitContent.hasOpenFence;

    // Provide a stable ref for isActuallyTyping to the markdown components
    const isActuallyTypingRef = useRef(false);
    isActuallyTypingRef.current = shouldShowStreamingContent;

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

    const isPathLike = useCallback((value: string) => {
      const text = value.trim();
      return (
        /^(client|server|src|docs|tests|tmp|app|components|pages|api)\//.test(text) ||
        /\.(tsx?|py|css|md|json|ya?ml|sql)(:\d+)?$/.test(text)
      );
    }, []);

    // Memoize markdown components to avoid unnecessary remounts
    const markdownComponents = useMemo(
      () => ({
        code({ inline, className, children, ...props }: any) {
          const match = /language-(\w+)/.exec(className || '');
          const language = match ? match[1] : 'text';
          
          if (inline) {
            const inlineText = String(children);
            const pathLike = isPathLike(inlineText);
            return (
              <code className={pathLike ? styles.pathCode : styles.inlineCode} {...props}>
                {children}
              </code>
            );
          }

          const codeText = String(children).replace(/\n$/, '');

          if (shouldUseSplitStreaming) {
            return (
              <Suspense fallback={<div style={{ padding: '10px 12px', color: 'var(--text-secondary)' }}>代码块加载中…</div>}>
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
              </Suspense>
            );
          }

          if (shouldShowOpenFenceFallback) {
            return (
              <div style={{
                background: 'var(--bg-elevated)',
                borderRadius: '8px',
                margin: '8px 0',
                overflow: 'hidden',
                border: '1px solid var(--border-color)'
              }}>
                <div style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '6px 12px',
                  color: 'var(--text-secondary)',
                  fontSize: 11,
                  fontFamily: 'var(--font-mono)',
                  borderBottom: '1px solid var(--border-color)'
                }}>
                  <div style={{ display: 'flex', gap: 4 }}>
                    <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--border-color)' }} />
                    <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--border-color)' }} />
                    <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--border-color)' }} />
                  </div>
                  <span style={{ fontSize: 9, opacity: 0.6, textTransform: 'uppercase' }}>{language}</span>
                </div>
                <pre style={{
                  margin: 0,
                  padding: '10px 12px',
                  background: 'transparent',
                  overflowX: 'auto',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                }}>
                  <code style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', color: 'var(--text-primary)' }}>
                    {codeText}
                  </code>
                </pre>
              </div>
            );
          }

          return isActuallyTypingRef.current ? (
            <div style={{
              background: 'var(--bg-elevated)',
              borderRadius: '8px',
              margin: '8px 0',
              overflow: 'hidden',
              border: '1px solid var(--border-color)'
            }}>
              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '6px 12px',
                color: 'var(--text-secondary)',
                fontSize: 11,
                fontFamily: 'var(--font-mono)',
                borderBottom: '1px solid var(--border-color)'
              }}>
                <div style={{ display: 'flex', gap: 4 }}>
                  <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--border-color)' }} />
                  <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--border-color)' }} />
                  <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--border-color)' }} />
                </div>
                <span style={{ fontSize: 9, opacity: 0.6, textTransform: 'uppercase' }}>{language}</span>
              </div>
              <pre style={{
                margin: 0,
                padding: '10px 12px',
                background: 'transparent',
                overflowX: 'auto',
              }}>
                <code style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', color: 'var(--text-primary)', whiteSpace: 'pre-wrap' }}>
                  {codeText}
                </code>
              </pre>
            </div>
          ) : (
            <Suspense fallback={<div style={{ padding: '10px 12px', color: 'var(--text-secondary)' }}>代码块加载中…</div>}>
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
            </Suspense>
          );
        },
        p: ({ children }: any) => (
          <p>{children}</p>
        ),
        ul: ({ children }: any) => (
          <ul>{children}</ul>
        ),
        ol: ({ children }: any) => (
          <ol>{children}</ol>
        ),
        li: ({ children }: any) => (
          <li>{children}</li>
        ),
        h1: ({ children }: any) => (
          <h1>{children}</h1>
        ),
        h2: ({ children }: any) => (
          <h2>{children}</h2>
        ),
        h3: ({ children }: any) => (
          <h3>{children}</h3>
        ),
        blockquote: ({ children }: any) => (
          <blockquote>{children}</blockquote>
        ),
        table: ({ children }: any) => (
          <table>{children}</table>
        ),
        th: ({ children }: any) => (
          <th>{children}</th>
        ),
        td: ({ children }: any) => (
          <td>{children}</td>
        ),
        tr: ({ children }: any) => (
          <tr className={styles.tableRow}>
            {children}
          </tr>
        ),
      }),
      [isPathLike]
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
        <div className={styles.avatarArea}>
          <Avatar 
            size={28}
            icon={isUser ? <UserOutlined /> : <RobotOutlined />} 
            style={{ 
              background: isUser ? 'var(--bg-secondary)' : 'var(--accent-primary)',
              color: isUser ? 'var(--text-secondary)' : '#fff',
              border: isUser ? '1px solid var(--border-color)' : 'none',
              flexShrink: 0
            }} 
          />
        </div>
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
          {isLoading && !shouldShowStreamingContent ? (
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
            <motion.div
              className={styles.markdownContent}
              initial={isAssistant && isStreaming ? { opacity: 0, y: 4 } : false}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
            >
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
              ) : agent_metadata?.kind === 'agent_part' ? (
                <AgentPartMessage
                  content={content}
                  metadata={agent_metadata}
                  onApproveAction={onApproveAgentAction}
                  onRejectAction={onRejectAgentAction}
                  onExecuteAction={onExecuteAgentAction}
                  onRefreshRun={onRefreshAgentRun}
                />
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
                  
                  {shouldUseSplitStreaming ? (
                    <>
                      {splitContent.plainText.trim() && (
                        <div className="streaming-content progressive-markdown">
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            rehypePlugins={[rehypeRaw, [rehypeSanitize, customSanitizeSchema]]}
                            components={markdownComponents}
                          >
                            {splitContent.plainText}
                          </ReactMarkdown>
                        </div>
                      )}
                      {splitContent.codeBlocks.map((block, index) => (
                        <Suspense key={`${id}-split-code-${index}`} fallback={<div style={{ padding: '10px 12px', color: 'var(--text-secondary)' }}>代码块加载中…</div>}>
                          <CodePreview
                            code={block.replace(/^```[\w-]*\n?/, '').replace(/```$/, '')}
                            language={(block.match(/^```([\w-]+)/)?.[1] || 'text')}
                            showLineNumbers={false}
                            collapsible={false}
                            showFullscreen={false}
                            showSave={false}
                            defaultFilename={`code_${index}`}
                            maxHeight={600}
                          />
                        </Suspense>
                      ))}
                    </>
                  ) : (
                    <div className="streaming-content progressive-markdown">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        rehypePlugins={[rehypeRaw, [rehypeSanitize, customSanitizeSchema]]}
                        components={markdownComponents}
                      >
                        {processedContent}
                      </ReactMarkdown>
                    </div>
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
            </motion.div>
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
