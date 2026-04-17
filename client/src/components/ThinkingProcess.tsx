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
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: 'easeInOut' }}
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
          color: #888;
          background: transparent;
          border: 1px solid #ddd;
          border-radius: 6px;
          cursor: pointer;
          transition: all 0.2s ease;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }

        .toggle-thinking-btn:hover {
          background: #f5f5f5;
          color: #666;
          border-color: #ccc;
        }

        .toggle-icon {
          font-size: 10px;
          transition: transform 0.2s ease;
        }

        .toggle-text {
          font-weight: 500;
        }

        .streaming-indicator {
          color: #52c41a;
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
          color: #666;
          background: #fafafa;
          border-radius: 8px;
          border: 1px solid #f0f0f0;
          font-style: italic;
        }

        .thinking-content p {
          margin: 4px 0;
        }

        .typing-cursor {
          display: inline-block;
          animation: cursor-blink 1s infinite;
          color: #1890ff;
          font-weight: 300;
          margin-left: 2px;
        }

        @keyframes cursor-blink {
          0%, 50% { opacity: 1; }
          51%, 100% { opacity: 0; }
        }

        /* 暗色主题 */
        @media (prefers-color-scheme: dark) {
          .toggle-thinking-btn {
            color: #999;
            border-color: #444;
          }

          .toggle-thinking-btn:hover {
            background: #333;
            color: #bbb;
            border-color: #555;
          }

          .thinking-content {
            background: #1a1a1a;
            color: #888;
            border-color: #333;
          }
        }
      `}</style>
    </div>
  );
};

export default ThinkingProcess;
