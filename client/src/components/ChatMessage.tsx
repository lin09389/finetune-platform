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
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import ThinkingProcess from '../components/ThinkingProcess';

const CodePreview = lazy(() => import('../components/CodePreview'));
import { useTypewriter } from '../hooks/chat/useTypewriter';
import { messageVariants, transitions } from '../theme/animations';
import type { KnowledgeSource, RetrievalInfo } from '../types';
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
}

const customSanitizeSchema = {
  ...defaultSchema,
  attributes: {
    ...defaultSchema.attributes,
    span: [...(defaultSchema.attributes?.span || []), 'className'],
    div: [...(defaultSchema.attributes?.div || []), 'className'],
    code: [...(defaultSchema.attributes?.code || []), 'className'],
  },
};

const preprocessMath = (content: string) => {
  if (!content) return content;
  // Convert \[ ... \] to $$ ... $$
  let processed = content.replace(/\\\[([\s\S]*?)\\\]/g, '$$$$$1$$$$');
  // Convert \( ... \) to $ ... $
  processed = processed.replace(/\\\(([\s\S]*?)\\\)/g, '$$$1$$');
  return processed;
};

type MarkdownChildProps = {
  children?: React.ReactNode;
};

type MarkdownCodeProps = MarkdownChildProps & {
  inline?: boolean;
  className?: string;
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
  }) => {
    const [copied, setCopied] = useState(false);
    const [showKnowledgeSources, setShowKnowledgeSources] = useState(false);
    const [isEditing, setIsEditing] = useState(false);
    const [editContent, setEditContent] = useState(content);

    const isUser = role === 'user';
    const isAssistant = role === 'assistant';

    const mathProcessedContent = useMemo(() => preprocessMath(content), [content]);

    // Typewriter effect handles progressive reveal for assistant messages
    const { processedContent, isDoneTyping, splitContent } = useTypewriter(
      mathProcessedContent,
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
        code({ inline, className, children, ...props }: MarkdownCodeProps) {
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
                  collapsible={true}
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
                collapsible={true}
                showFullscreen={false}
                showSave={false}
                defaultFilename={`code_${language}`}
                maxHeight={600}
              />
            </Suspense>
          );
        },
        p: ({ children }: MarkdownChildProps) => (
          <p>{children}</p>
        ),
        ul: ({ children }: MarkdownChildProps) => (
          <ul>{children}</ul>
        ),
        ol: ({ children }: MarkdownChildProps) => (
          <ol>{children}</ol>
        ),
        li: ({ children }: MarkdownChildProps) => (
          <li>{children}</li>
        ),
        h1: ({ children }: MarkdownChildProps) => (
          <h1>{children}</h1>
        ),
        h2: ({ children }: MarkdownChildProps) => (
          <h2>{children}</h2>
        ),
        h3: ({ children }: MarkdownChildProps) => (
          <h3>{children}</h3>
        ),
        blockquote: ({ children }: MarkdownChildProps) => (
          <blockquote>{children}</blockquote>
        ),
        table: ({ children }: MarkdownChildProps) => (
          <table>{children}</table>
        ),
        th: ({ children }: MarkdownChildProps) => (
          <th>{children}</th>
        ),
        td: ({ children }: MarkdownChildProps) => (
          <td>{children}</td>
        ),
        tr: ({ children }: MarkdownChildProps) => (
          <tr className={styles.tableRow}>
            {children}
          </tr>
        ),
      }),
      [isPathLike, shouldShowOpenFenceFallback, shouldUseSplitStreaming]
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
              background: isUser ? 'var(--bg-elevated)' : 'var(--accent-primary)',
              color: isUser ? 'var(--text-secondary)' : 'var(--text-inverse)',
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
              initial={false}
              animate={false}
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
                        style={{ color: 'var(--text-inverse)' }}
                      >
                        取消
                      </Button>
                      <Button
                        size="small"
                        type="primary"
                        onClick={handleSaveEdit}
                        icon={<CheckOutlined />}
                        style={{
                          background: 'var(--text-inverse)',
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
                  
                  {shouldUseSplitStreaming ? (
                    <>
                      {splitContent.plainText.trim() && (
                        <div className="streaming-content progressive-markdown">
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm, remarkMath]}
                            rehypePlugins={[rehypeRaw, [rehypeSanitize, customSanitizeSchema], rehypeKatex]}
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
                            collapsible={true}
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
                        remarkPlugins={[remarkGfm, remarkMath]}
                        rehypePlugins={[rehypeRaw, [rehypeSanitize, customSanitizeSchema], rehypeKatex]}
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
