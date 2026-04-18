import React, { useEffect, useMemo, useState, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import rehypeRaw from 'rehype-raw';
import CodePreview from './CodePreview';
import ThinkingProcess from './ThinkingProcess';

interface StreamingMessageProps {
  content: string;
  isStreaming: boolean;
  speed?: number; // Target characters per second, default 60
  onTypingComplete?: () => void;
  className?: string;
  thinkingContent?: string;
}

const MarkdownMemo = React.memo(({ content, components, rehypePlugins }: any) => (
  <ReactMarkdown
    rehypePlugins={rehypePlugins}
    components={components}
  >
    {content}
  </ReactMarkdown>
));

const StreamingMessage: React.FC<StreamingMessageProps> = ({
  content,
  isStreaming,
  speed = 45,
  className,
  thinkingContent,
  onTypingComplete,
}) => {
  const [displayContent, setDisplayContent] = useState('');
  
  // Use refs to track state without triggering re-renders during the animation loop
  const contentRef = useRef(content);
  const displayContentRef = useRef('');
  const lastUpdateTimeRef = useRef(performance.now());
  const requestRef = useRef<number>();
  const revealedFractionRef = useRef(0); // For liquid sub-character reveal

  // Keep contentRef in sync with the incoming prop
  useEffect(() => {
    contentRef.current = content;
  }, [content]);

  useEffect(() => {
    // Keep animating until we catch up to contentRef, regardless of isStreaming
    const animate = (time: number) => {
      const targetContent = contentRef.current;
      const currentDisplay = displayContentRef.current;
      
      // Check if we're done typing
      if (currentDisplay.length >= targetContent.length) {
        if (!isStreaming) {
          // Both stream and animation finished
          if (onTypingComplete) onTypingComplete();
          return; // Stop animation loop
        }
        // Stream still active but we're caught up, just wait for next chunk
        lastUpdateTimeRef.current = time;
        requestRef.current = requestAnimationFrame(animate);
        return;
      }

      const timeDelta = time - lastUpdateTimeRef.current;
      const gap = targetContent.length - currentDisplay.length;
      
      // Liquid Smoothness Strategy:
      // 1. Calculate base speed (chars per ms)
      // 2. Add adaptive smoothing: faster when gap is large, but with ease-in/out
      let targetSpeed = speed / 1000; // chars per ms
      
      if (gap > 50) {
        // Significantly speed up if we are far behind, but capped to prevent "explosions"
        targetSpeed = Math.min(0.5, targetSpeed + (gap - 50) * 0.005);
      }
      
      // Increment fractional revealed characters
      revealedFractionRef.current += targetSpeed * timeDelta;
      
      const charsToReveal = Math.floor(revealedFractionRef.current);
      
      if (charsToReveal > 0) {
        const nextContent = targetContent.substring(0, currentDisplay.length + charsToReveal);
        displayContentRef.current = nextContent;
        setDisplayContent(nextContent);
        
        // Subtract only the integer part we just revealed
        revealedFractionRef.current -= charsToReveal;
        lastUpdateTimeRef.current = time;
      } else {
        // If we didn't reveal anything this frame, don't update lastUpdateTimeRef
        // so that the fraction keeps accumulating correctly in the next frame
      }
      
      requestRef.current = requestAnimationFrame(animate);
    };

    lastUpdateTimeRef.current = performance.now();
    requestRef.current = requestAnimationFrame(animate);

    return () => {
      if (requestRef.current) {
        cancelAnimationFrame(requestRef.current);
      }
    };
  }, [isStreaming, speed, onTypingComplete]);

  // Remove the old separate onTypingComplete effect as it's now integrated
  
  // Pre-process content to fix unclosed markdown and add streaming cursor
  const processedContent = useMemo(() => {
    let text = displayContent;
    if (isStreaming) {
      const codeBlockCount = (text.match(/```/g) || []).length;
      if (codeBlockCount % 2 !== 0) {
        // Unclosed code block: put cursor inside the code block and auto-close it
        // We use a CSS animated cursor instead of a block character for a more Gemini-like feel
        text += '<span class="gemini-cursor"></span>\n```';
      } else {
        // Normal text: just append the cursor
        text += '<span class="gemini-cursor"></span>';
      }
    }
    return text;
  }, [displayContent, isStreaming]);

  // Stable reference for custom components to prevent unnecessary remounts
  const components = useMemo(
    () => ({
      code({ inline, className: _className, children, ...props }: any) {
        const match = /language-(\w+)/.exec(_className || '');
        const language = match ? match[1] : 'text';
        
        if (!inline) {
          const codeText = String(children).replace(/\n$/, '');
          
          // Optimization: while typing or streaming, use a lightweight code block
          // to prevent the heavy CodePreview component from causing jank
          const isActuallyTyping = displayContent.length < content.length || isStreaming;
          
          if (isActuallyTyping) {
            return (
              <pre style={{
                background: 'var(--bg-elevated)',
                padding: '12px 16px',
                borderRadius: '8px',
                overflowX: 'auto',
                border: '1px solid var(--border-color)',
                margin: '12px 0'
              }}>
                <code style={{ fontFamily: 'var(--font-mono)', fontSize: '13px' }}>
                  {codeText}
                </code>
              </pre>
            );
          }

          return (
            <CodePreview
              code={codeText}
              language={language}
              showLineNumbers={true}
              collapsible={codeText.split('\n').length > 10}
              showFullscreen={true}
              showSave={true}
              defaultFilename={`code_${language}`}
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
        <MarkdownMemo 
          rehypePlugins={[rehypeRaw]} 
          components={components}
          content={processedContent}
        />
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
