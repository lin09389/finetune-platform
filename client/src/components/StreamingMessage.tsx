import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import CodePreview from './CodePreview'
import ThinkingProcess from './ThinkingProcess'

interface StreamingMessageProps {
  content: string
  isStreaming: boolean
  speed?: number
  onTypingComplete?: () => void
  className?: string
  thinkingContent?: string
}

interface TypewriterState {
  displayedContent: string
  isPaused: boolean
  isComplete: boolean
}

const StreamingMessage: React.FC<StreamingMessageProps> = ({
  content,
  isStreaming,
  speed = 50,
  onTypingComplete,
  className,
  thinkingContent,
}) => {
  const [state, setState] = useState<TypewriterState>({
    displayedContent: isStreaming ? '' : content,
    isPaused: false,
    isComplete: !isStreaming,
  })

  const animationRef = useRef<number>(0)
  const lastTimeRef = useRef<number>(0)
  const charIndexRef = useRef<number>(0)
  const previousContentRef = useRef<string>('')

  const interval = useMemo(() => 1000 / speed, [speed])

  useEffect(() => {
    if (content !== previousContentRef.current) {
      if (content.startsWith(previousContentRef.current)) {
        // 增量更新，继续打字
      } else {
        // 内容完全改变，重置
        charIndexRef.current = 0
        setState(prev => ({
          ...prev,
          displayedContent: '',
          isComplete: false,
        }))
      }
      previousContentRef.current = content
    }
  }, [content])

  useEffect(() => {
    if (state.isPaused || state.isComplete) {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current)
      }
      return
    }

    const animate = (time: number) => {
      if (state.isPaused || state.isComplete) {
        return
      }

      if (time - lastTimeRef.current >= interval) {
        const targetContent = content
        const currentLength = charIndexRef.current

        if (currentLength < targetContent.length) {
          const nextLength = Math.min(currentLength + 1, targetContent.length)
          charIndexRef.current = nextLength

          setState(prev => ({
            ...prev,
            displayedContent: targetContent.slice(0, nextLength),
          }))

          lastTimeRef.current = time
        } else if (!isStreaming && currentLength >= targetContent.length) {
          setState(prev => ({
            ...prev,
            isComplete: true,
          }))
          onTypingComplete?.()
          return
        }
      }

      animationRef.current = requestAnimationFrame(animate)
    }

    animationRef.current = requestAnimationFrame(animate)

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current)
      }
    }
  }, [content, isStreaming, interval, state.isPaused, state.isComplete, onTypingComplete])

  const togglePause = useCallback(() => {
    setState(prev => ({
      ...prev,
      isPaused: !prev.isPaused,
    }))
  }, [])

  const displayedText = state.displayedContent || content

  return (
    <div className={`streaming-message ${className || ''}`}>
      {thinkingContent && (
        <ThinkingProcess
          content={thinkingContent}
          isStreaming={isStreaming}
        />
      )}
      <div className="streaming-content">
        <ProgressiveMarkdown content={displayedText} />
      </div>

      {isStreaming && !state.isComplete && (
        <div className="streaming-controls">
          <button
            onClick={togglePause}
            className="control-button"
            aria-label={state.isPaused ? '继续' : '暂停'}
          >
            {state.isPaused ? '▶️ 继续' : '⏸️ 暂停'}
          </button>
          <span className="speed-indicator">
            {speed} 字符/秒
          </span>
        </div>
      )}

      <style>{`
        .streaming-message {
          position: relative;
        }

        .streaming-content {
          will-change: transform, opacity;
        }

        .streaming-controls {
          display: flex;
          align-items: center;
          gap: 12px;
          margin-top: 8px;
          padding: 8px 12px;
          background: var(--bg-secondary);
          border-radius: 8px;
          border: 1px solid var(--border-color);
        }

        .control-button {
          padding: 4px 12px;
          font-size: 12px;
          border: none;
          background: var(--bg-elevated);
          color: var(--text-primary);
          border-radius: 6px;
          cursor: pointer;
          transition: all 0.2s ease;
        }

        .control-button:hover {
          background: var(--primary-500);
          color: white;
        }

        .speed-indicator {
          font-size: 11px;
          color: var(--text-tertiary);
        }

        @keyframes cursor-blink {
          0%, 50% { opacity: 1; }
          51%, 100% { opacity: 0; }
        }
      `}</style>
    </div>
  )
}

interface ProgressiveMarkdownProps {
  content: string
}

const ProgressiveMarkdown: React.FC<ProgressiveMarkdownProps> = React.memo(({ content }) => {
  const { completeBlocks, incompleteBlock } = useMemo(() => {
    return parseMarkdownBlocks(content)
  }, [content])

  return (
    <div className="progressive-markdown">
      {completeBlocks.map((block, index) => (
        <MarkdownBlock key={index} block={block} />
      ))}
      {incompleteBlock && (
        <div className="incomplete-block">
          <span className="incomplete-content">{incompleteBlock}</span>
          <span className="typing-cursor">▋</span>
        </div>
      )}

      <style>{`
        .progressive-markdown {
          font-size: 15px;
          line-height: 1.7;
          color: var(--text-primary);
        }

        .incomplete-block {
          display: inline;
        }

        .incomplete-content {
          color: var(--text-primary);
        }

        .typing-cursor {
          display: inline-block;
          animation: cursor-blink 1s infinite;
          color: var(--primary-500);
          font-weight: 300;
        }
      `}</style>
    </div>
  )
})

ProgressiveMarkdown.displayName = 'ProgressiveMarkdown'

interface MarkdownBlock {
  type: 'code' | 'paragraph' | 'heading' | 'list' | 'blockquote' | 'table'
  content: string
  language?: string
}

function parseMarkdownBlocks(content: string): { completeBlocks: string[]; incompleteBlock: string } {
  const lines = content.split('\n')
  const completeBlocks: string[] = []
  let currentBlock: string[] = []
  let inCodeBlock = false
  let codeBlockDelimiter = ''

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i] ?? ''

    if (inCodeBlock) {
      currentBlock.push(line)
      if (line.trim() === codeBlockDelimiter || (line.endsWith('```') && line.trim() !== '```')) {
        inCodeBlock = false
        codeBlockDelimiter = ''
        completeBlocks.push(currentBlock.join('\n'))
        currentBlock = []
      }
    } else if (line.trim().startsWith('```')) {
      if (currentBlock.length > 0) {
        completeBlocks.push(currentBlock.join('\n'))
        currentBlock = []
      }
      inCodeBlock = true
      codeBlockDelimiter = line.trim()
      currentBlock.push(line)
    } else {
      currentBlock.push(line)
      if (line.trim() === '' || i === lines.length - 1) {
        if (currentBlock.some(l => l.trim())) {
          completeBlocks.push(currentBlock.join('\n'))
        }
        currentBlock = []
      }
    }
  }

  const incompleteBlock = currentBlock.length > 0 ? currentBlock.join('\n') : ''

  return { completeBlocks, incompleteBlock }
}

const MarkdownBlock: React.FC<{ block: string }> = React.memo(({ block }) => {
  const isCodeBlock = block.trim().startsWith('```')

  if (isCodeBlock) {
    return <CodeBlockRenderer block={block} />
  }

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        code({ inline, className: _className, children, ...props }: any) {
          if (inline) {
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
            )
          }
          return <code {...props}>{children}</code>
        },
        p: ({ children }) => <p style={{ margin: '10px 0' }}>{children}</p>,
        ul: ({ children }) => <ul style={{ margin: '10px 0', paddingLeft: 24 }}>{children}</ul>,
        ol: ({ children }) => <ol style={{ margin: '10px 0', paddingLeft: 24 }}>{children}</ol>,
        li: ({ children }) => <li style={{ margin: '6px 0' }}>{children}</li>,
        h1: ({ children }) => <h1 style={{ margin: '20px 0 12px', fontSize: 24, fontWeight: 700 }}>{children}</h1>,
        h2: ({ children }) => <h2 style={{ margin: '18px 0 10px', fontSize: 20, fontWeight: 600 }}>{children}</h2>,
        h3: ({ children }) => <h3 style={{ margin: '16px 0 8px', fontSize: 18, fontWeight: 600 }}>{children}</h3>,
        blockquote: ({ children }) => (
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
      }}
    >
      {block}
    </ReactMarkdown>
  )
})

MarkdownBlock.displayName = 'MarkdownBlock'

const CodeBlockRenderer: React.FC<{ block: string }> = React.memo(({ block }) => {
  const lines = block.split('\n')
  const firstLine = (lines[0] ?? '').trim()
  const language = firstLine.slice(3) || 'text'
  const code = lines.slice(1, -1).join('\n')

  return (
    <CodePreview
      code={code}
      language={language}
      showLineNumbers={true}
      collapsible={code.split('\n').length > 10}
      showFullscreen={true}
      showSave={true}
      defaultFilename={`code_${language}`}
      maxHeight={400}
    />
  )
})

CodeBlockRenderer.displayName = 'CodeBlockRenderer'

export default StreamingMessage
