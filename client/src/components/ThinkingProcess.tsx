import { AnimatePresence, motion } from 'framer-motion';
import React, { useCallback, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface ThinkingProcessProps {
  content: string;
  defaultExpanded?: boolean;
  isStreaming?: boolean;
}

const ThinkingProcess: React.FC<ThinkingProcessProps> = ({
  content,
  defaultExpanded = false,
  isStreaming = false,
}) => {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  const toggleExpanded = useCallback(() => {
    setIsExpanded((prev) => !prev);
  }, []);

  if (!content) return null;

  return (
    <div className="thinking-process-container">
      <button
        onClick={toggleExpanded}
        className="toggle-thinking-btn"
        aria-expanded={isExpanded}
        aria-controls="thinking-content"
      >
        <span className="toggle-icon">{isExpanded ? '▲' : '▼'}</span>
        <span className="toggle-text">{isExpanded ? '收起思考过程' : '思考过程'}</span>
        {isStreaming && <span className="streaming-indicator">●</span>}
      </button>

      <AnimatePresence initial={false}>
        {isExpanded && (
          <motion.div
            id="thinking-content"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="thinking-content-wrapper"
          >
            <div className="thinking-content">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  p: ({ children }) => <p style={{ margin: '4px 0' }}>{children}</p>,
                  code: ({ children, className }) => {
                    const isInline = !className;
                    if (isInline) {
                      return (
                        <code
                          style={{
                            backgroundColor: 'rgba(0,0,0,0.1)',
                            padding: '1px 4px',
                            borderRadius: '3px',
                            fontSize: '11px',
                          }}
                        >
                          {children}
                        </code>
                      );
                    }
                    return <code>{children}</code>;
                  },
                }}
              >
                {content}
              </ReactMarkdown>
              {isStreaming && <span className="typing-cursor">▋</span>}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <style>{`
        .thinking-process-container {
          margin-bottom: 12px;
        }

        .toggle-thinking-btn {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 4px 10px;
          font-size: 12px;
          color: var(--text-secondary);
          background: transparent;
          border: 1px solid var(--border-color);
          border-radius: 6px;
          cursor: pointer;
          transition: all 0.2s ease;
          font-family: var(--font-sans);
        }

        .toggle-thinking-btn:hover {
          background: var(--bg-hover);
          color: var(--text-secondary);
          border-color: var(--border-hover);
        }

        .toggle-icon {
          font-size: 10px;
          transition: transform 0.2s ease;
        }

        .toggle-text {
          font-weight: 500;
        }

        .streaming-indicator {
          color: var(--success);
          font-size: 8px;
          animation: pulse 1.5s infinite;
        }

        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }

        .thinking-content-wrapper {
          overflow: hidden;
        }

        .thinking-content {
          margin-top: 8px;
          padding: 12px;
          font-size: 12px;
          line-height: 1.6;
          color: var(--text-secondary);
          background: var(--bg-elevated);
          border-radius: 8px;
          border: 1px solid var(--border-subtle);
          font-style: italic;
        }

        .thinking-content p {
          margin: 4px 0;
        }

        .typing-cursor {
          display: inline-block;
          animation: cursor-blink 1s infinite;
          color: var(--accent-primary);
          font-weight: 300;
          margin-left: 2px;
        }

        @keyframes cursor-blink {
          0%, 50% { opacity: 1; }
          51%, 100% { opacity: 0; }
        }

        /* 颜色全部走设计令牌，随 .dark-theme 自动切换，
           不再依赖 prefers-color-scheme（与应用内主题开关不同步） */
      `}</style>
    </div>
  );
};

export default ThinkingProcess;
