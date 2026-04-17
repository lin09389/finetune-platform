import React, { useEffect, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import CodePreview from './CodePreview';
import ThinkingProcess from './ThinkingProcess';

interface StreamingMessageProps {
  content: string;
  isStreaming: boolean;
  speed?: number; // Kept for backwards compatibility
  onTypingComplete?: () => void;
  className?: string;
  thinkingContent?: string;
}

const StreamingMessage: React.FC<StreamingMessageProps> = ({
  content,
  isStreaming,
  className,
  thinkingContent,
  onTypingComplete,
}) => {
  // Trigger onTypingComplete when streaming stops
  useEffect(() => {
    if (!isStreaming && onTypingComplete) {
      onTypingComplete();
    }
  }, [isStreaming, onTypingComplete]);

  // Pre-process content to fix unclosed markdown and add streaming cursor
  const processedContent = useMemo(() => {
    let text = content;
    if (isStreaming) {
      const codeBlockCount = (text.match(/```/g) || []).length;
      if (codeBlockCount % 2 !== 0) {
        // Unclosed code block: put cursor inside the code block and auto-close it
        text += ' ▋\n```';
      } else {
        // Normal text: just append the cursor
        text += ' ▋';
      }
    }
    return text;
  }, [content, isStreaming]);

  // Stable reference for custom components to prevent unnecessary remounts
  const components = useMemo(
    () => ({
      code({ inline, className: _className, children, ...props }: any) {
        const match = /language-(\w+)/.exec(_className || '');
        if (!inline) {
          // Replace trailing newline so code preview doesn't add an empty line at the end
          const codeText = String(children).replace(/\n$/, '');
          return (
            <CodePreview
              code={codeText}
              language={match ? match[1] : 'text'}
              showLineNumbers={true}
              collapsible={codeText.split('\n').length > 10}
              showFullscreen={true}
              showSave={true}
              defaultFilename={`code_${match ? match[1] : 'text'}`}
              maxHeight={400}
            />
          );
        }
        return (
          <code
            style={{
              backgroundColor: 'var(--bg-elevated)',
              padding: '3px 8px',
              borderRadius: '6px',
              fontSize: '0.875em',
              color: 'var(--error)',
              fontFamily: 'var(--font-mono)',
            }}
            {...props}
          >
            {children}
          </code>
        );
      },
      p: ({ children }: any) => <p style={{ margin: '10px 0' }}>{children}</p>,
      ul: ({ children }: any) => <ul style={{ margin: '10px 0', paddingLeft: 24 }}>{children}</ul>,
      ol: ({ children }: any) => <ol style={{ margin: '10px 0', paddingLeft: 24 }}>{children}</ol>,
      li: ({ children }: any) => <li style={{ margin: '6px 0' }}>{children}</li>,
      h1: ({ children }: any) => (
        <h1 style={{ margin: '20px 0 12px', fontSize: 24, fontWeight: 700 }}>{children}</h1>
      ),
      h2: ({ children }: any) => (
        <h2 style={{ margin: '18px 0 10px', fontSize: 20, fontWeight: 600 }}>{children}</h2>
      ),
      h3: ({ children }: any) => (
        <h3 style={{ margin: '16px 0 8px', fontSize: 18, fontWeight: 600 }}>{children}</h3>
      ),
      blockquote: ({ children }: any) => (
        <blockquote
          style={{
            margin: '14px 0',
            padding: '12px 16px',
            borderLeft: '4px solid var(--primary-500)',
            background: 'var(--primary-50)',
            borderRadius: '0 10px 10px 0',
            fontStyle: 'italic',
          }}
        >
          {children}
        </blockquote>
      ),
    }),
    [],
  );

  return (
    <div className={`streaming-message ${className || ''}`}>
      {thinkingContent && <ThinkingProcess content={thinkingContent} isStreaming={isStreaming} />}
      <div className="streaming-content progressive-markdown">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
          {processedContent}
        </ReactMarkdown>
      </div>

      <style>{`
        .streaming-message {
          position: relative;
        }

        .progressive-markdown {
          font-size: 15px;
          line-height: 1.7;
          color: var(--text-primary);
        }
        
        .progressive-markdown > *:last-child {
          margin-bottom: 0 !important;
        }

        /* The cursor is a plain text block character ▋, 
           you can add a subtle pulse to it if you like, but solid is often better for fast streaming */
      `}</style>
    </div>
  );
};

export default React.memo(StreamingMessage);
