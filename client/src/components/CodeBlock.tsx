import React, { useState, useEffect, useRef, useMemo, useCallback, memo } from 'react'
import { Button, Tooltip, message, Space } from 'antd'
import { CopyOutlined, CheckOutlined, CodeOutlined, FileTextOutlined } from '@ant-design/icons'
import hljs from 'highlight.js/lib/core'
import 'highlight.js/styles/atom-one-dark.css'

import javascript from 'highlight.js/lib/languages/javascript'
import typescript from 'highlight.js/lib/languages/typescript'
import python from 'highlight.js/lib/languages/python'
import java from 'highlight.js/lib/languages/java'
import cpp from 'highlight.js/lib/languages/cpp'
import csharp from 'highlight.js/lib/languages/csharp'
import go from 'highlight.js/lib/languages/go'
import rust from 'highlight.js/lib/languages/rust'
import php from 'highlight.js/lib/languages/php'
import ruby from 'highlight.js/lib/languages/ruby'
import swift from 'highlight.js/lib/languages/swift'
import kotlin from 'highlight.js/lib/languages/kotlin'
import scala from 'highlight.js/lib/languages/scala'
import sql from 'highlight.js/lib/languages/sql'
import bash from 'highlight.js/lib/languages/bash'
import powershell from 'highlight.js/lib/languages/powershell'
import yaml from 'highlight.js/lib/languages/yaml'
import json from 'highlight.js/lib/languages/json'
import xml from 'highlight.js/lib/languages/xml'
import html from 'highlight.js/lib/languages/xml'
import css from 'highlight.js/lib/languages/css'
import scss from 'highlight.js/lib/languages/scss'
import less from 'highlight.js/lib/languages/less'
import markdown from 'highlight.js/lib/languages/markdown'
import dockerfile from 'highlight.js/lib/languages/dockerfile'
import nginx from 'highlight.js/lib/languages/nginx'
import ini from 'highlight.js/lib/languages/ini'
import toml from 'highlight.js/lib/languages/ini'
import plaintext from 'highlight.js/lib/languages/plaintext'

hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('typescript', typescript)
hljs.registerLanguage('python', python)
hljs.registerLanguage('java', java)
hljs.registerLanguage('cpp', cpp)
hljs.registerLanguage('csharp', csharp)
hljs.registerLanguage('go', go)
hljs.registerLanguage('rust', rust)
hljs.registerLanguage('php', php)
hljs.registerLanguage('ruby', ruby)
hljs.registerLanguage('swift', swift)
hljs.registerLanguage('kotlin', kotlin)
hljs.registerLanguage('scala', scala)
hljs.registerLanguage('sql', sql)
hljs.registerLanguage('bash', bash)
hljs.registerLanguage('shell', bash)
hljs.registerLanguage('powershell', powershell)
hljs.registerLanguage('yaml', yaml)
hljs.registerLanguage('yml', yaml)
hljs.registerLanguage('json', json)
hljs.registerLanguage('xml', xml)
hljs.registerLanguage('html', html)
hljs.registerLanguage('css', css)
hljs.registerLanguage('scss', scss)
hljs.registerLanguage('less', less)
hljs.registerLanguage('markdown', markdown)
hljs.registerLanguage('md', markdown)
hljs.registerLanguage('dockerfile', dockerfile)
hljs.registerLanguage('nginx', nginx)
hljs.registerLanguage('ini', ini)
hljs.registerLanguage('toml', toml)
hljs.registerLanguage('text', plaintext)
hljs.registerLanguage('plaintext', plaintext)

export interface CodeBlockProps {
  code: string
  language?: string
  showLineNumbers?: boolean
  showCopyButton?: boolean
  showLanguage?: boolean
  maxHeight?: number | string
  className?: string
  theme?: 'light' | 'dark'
}

const LANGUAGE_DISPLAY_NAMES: Record<string, string> = {
  javascript: 'JavaScript',
  typescript: 'TypeScript',
  python: 'Python',
  java: 'Java',
  cpp: 'C++',
  csharp: 'C#',
  go: 'Go',
  rust: 'Rust',
  php: 'PHP',
  ruby: 'Ruby',
  swift: 'Swift',
  kotlin: 'Kotlin',
  scala: 'Scala',
  sql: 'SQL',
  bash: 'Bash',
  shell: 'Shell',
  powershell: 'PowerShell',
  yaml: 'YAML',
  yml: 'YAML',
  json: 'JSON',
  xml: 'XML',
  html: 'HTML',
  css: 'CSS',
  scss: 'SCSS',
  less: 'Less',
  markdown: 'Markdown',
  md: 'Markdown',
  dockerfile: 'Dockerfile',
  nginx: 'Nginx',
  ini: 'INI',
  toml: 'TOML',
  text: 'Text',
  plaintext: 'Plain Text',
}

const LANGUAGE_ALIASES: Record<string, string> = {
  js: 'javascript',
  ts: 'typescript',
  py: 'python',
  sh: 'bash',
  yml: 'yaml',
  md: 'markdown',
  docker: 'dockerfile',
}

const detectLanguage = (code: string): string => {
  const trimmed = code.trim()
  
  if (trimmed.startsWith('<?xml') || trimmed.startsWith('<!DOCTYPE') || /^<[a-zA-Z][^>]*>/.test(trimmed)) {
    if (/<\/?[a-zA-Z][^>]*>/g.test(trimmed) && !trimmed.includes('<?php')) {
      return 'html'
    }
    return 'xml'
  }
  
  if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
    try {
      JSON.parse(trimmed)
      return 'json'
    } catch {}
  }
  
  if (/^(import|export|function|const|let|var|async|class)\s+/.test(trimmed)) {
    if (/:\s*(string|number|boolean|any|void|interface|type)\b/.test(trimmed) || /<[A-Z]/.test(trimmed)) {
      return 'typescript'
    }
    return 'javascript'
  }
  
  if (/^(import|from|def |class |if __name__|print\(|@)/.test(trimmed) || /^\s*(def|class|if|elif|else|for|while|with|try|except|finally)\s*[:\(]/.test(trimmed)) {
    return 'python'
  }
  
  if (/^(package|import|public|private|protected)\s+/.test(trimmed) || /class\s+\w+\s*(extends|implements|\{)/.test(trimmed)) {
    if (/\b(func|var|let|:?\s*\[\]|\bmap\[|\bchan\s)/.test(trimmed)) {
      return 'go'
    }
    if (/\bfn\s+\w+/.test(trimmed) || /\blet\s+mut\s+/.test(trimmed)) {
      return 'rust'
    }
    if (/\bval\s+\w+/.test(trimmed) || /\bfun\s+\w+/.test(trimmed)) {
      return 'kotlin'
    }
    if (/\bdef\s+\w+/.test(trimmed) || /\bclass\s+\w+\s*\(/.test(trimmed)) {
      return 'python'
    }
    return 'java'
  }
  
  if (/^(func\s+|package\s+main|import\s*\(|fmt\.|go\s)/.test(trimmed)) {
    return 'go'
  }
  
  if (/^(fn\s+|let\s+mut|impl\s+|pub\s+fn|use\s+std::)/.test(trimmed)) {
    return 'rust'
  }
  
  if (/^(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|WITH)\s+/i.test(trimmed)) {
    return 'sql'
  }
  
  if (/^(#!\/bin\/|#!\/usr\/bin\/|echo\s|cd\s|ls\s|mkdir\s|rm\s|cp\s|mv\s|chmod\s|export\s)/.test(trimmed)) {
    return 'bash'
  }
  
  if (/^\s*[\w-]+:\s*[\w-]+/.test(trimmed) && !trimmed.includes('{')) {
    return 'yaml'
  }
  
  if (/^FROM\s+\w+|^RUN\s+|^COPY\s+|^WORKDIR\s+|^EXPOSE\s+/im.test(trimmed)) {
    return 'dockerfile'
  }
  
  if (/^#+\s+/.test(trimmed) || /^\*\*.*\*\*/.test(trimmed) || /^\s*[-*+]\s+/.test(trimmed)) {
    return 'markdown'
  }
  
  if (/^\s*\.[\w-]+\s*\{|^\s*#[\w-]+\s*\{|^\s*@[\w-]+\s*\(/.test(trimmed)) {
    return 'scss'
  }
  
  if (/^\s*[\w-]+\s*\{[\s\S]*\}/.test(trimmed) && /:\s*[\w-]+\s*;/.test(trimmed)) {
    return 'css'
  }
  
  return 'text'
}

const normalizeLanguage = (lang: string): string => {
  const normalized = lang.toLowerCase().trim()
  return LANGUAGE_ALIASES[normalized] || normalized
}

const getLanguageDisplayName = (lang: string): string => {
  return LANGUAGE_DISPLAY_NAMES[lang] || lang.toUpperCase()
}

const generateLineNumbers = (code: string): number[] => {
  const lines = code.split('\n')
  return Array.from({ length: lines.length }, (_, i) => i + 1)
}

const CodeBlock: React.FC<CodeBlockProps> = memo(({
  code,
  language,
  showLineNumbers = true,
  showCopyButton = true,
  showLanguage = true,
  maxHeight = 500,
  className = '',
  theme = 'dark',
}) => {
  const [copied, setCopied] = useState(false)
  const [highlightedCode, setHighlightedCode] = useState('')
  const [detectedLanguage, setDetectedLanguage] = useState<string>('text')
  const codeRef = useRef<HTMLElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [isVisible, setIsVisible] = useState(false)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          setIsVisible(true)
          observer.disconnect()
        }
      },
      { rootMargin: '200px', threshold: 0.01 }
    )

    observer.observe(container)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (language && language !== 'auto') {
      setDetectedLanguage(normalizeLanguage(language))
    } else {
      setDetectedLanguage(detectLanguage(code))
    }
  }, [code, language])

  useEffect(() => {
    if (!isVisible) return

    const lang = detectedLanguage
    try {
      if (hljs.getLanguage(lang)) {
        const result = hljs.highlight(code, {
          language: lang,
          ignoreIllegals: true,
        })
        setHighlightedCode(result.value)
      } else {
        const result = hljs.highlightAuto(code)
        setHighlightedCode(result.value)
        if (!language || language === 'auto') {
          setDetectedLanguage(result.language || 'text')
        }
      }
    } catch {
      setHighlightedCode(code.replace(/</g, '&lt;').replace(/>/g, '&gt;'))
    }
  }, [code, detectedLanguage, language, isVisible])

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
      message.success('代码已复制到剪贴板', 1.5)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      message.error('复制失败，请手动复制')
    }
  }, [code])

  const lineNumbers = useMemo(() => generateLineNumbers(code), [code])
  const lineCount = lineNumbers.length

  const containerStyle: React.CSSProperties = {
    position: 'relative',
    borderRadius: 12,
    overflow: 'hidden',
    background: theme === 'dark' ? '#1e293b' : '#f8fafc',
    border: `1px solid ${theme === 'dark' ? '#334155' : '#e2e8f0'}`,
    fontFamily: 'var(--font-mono)',
    fontSize: 13,
    lineHeight: 1.6,
    margin: '12px 0',
  }

  const headerStyle: React.CSSProperties = {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '8px 16px',
    background: theme === 'dark' ? '#0f172a' : '#f1f5f9',
    borderBottom: `1px solid ${theme === 'dark' ? '#334155' : '#e2e8f0'}`,
    fontSize: 12,
  }

  const codeContainerStyle: React.CSSProperties = {
    display: 'flex',
    maxHeight: maxHeight,
    overflow: 'auto',
  }

  const lineNumbersStyle: React.CSSProperties = {
    padding: '16px 12px',
    textAlign: 'right',
    background: theme === 'dark' ? '#0f172a' : '#f1f5f9',
    color: theme === 'dark' ? '#64748b' : '#94a3b8',
    userSelect: 'none',
    borderRight: `1px solid ${theme === 'dark' ? '#334155' : '#e2e8f0'}`,
    minWidth: 50,
    flexShrink: 0,
  }

  const codeStyle: React.CSSProperties = {
    flex: 1,
    overflow: 'auto',
    padding: '16px 16px 16px 20px',
    margin: 0,
    background: 'transparent',
    color: theme === 'dark' ? '#e2e8f0' : '#1e293b',
  }

  const footerStyle: React.CSSProperties = {
    display: 'flex',
    justifyContent: 'space-between',
    padding: '6px 16px',
    background: theme === 'dark' ? '#0f172a' : '#f1f5f9',
    borderTop: `1px solid ${theme === 'dark' ? '#334155' : '#e2e8f0'}`,
    fontSize: 11,
    color: theme === 'dark' ? '#64748b' : '#94a3b8',
  }

  const renderPlaceholder = () => (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: 60,
      background: theme === 'dark' ? '#1e293b' : '#f8fafc',
      gap: 8,
    }}>
      <CodeOutlined style={{ fontSize: 16, color: theme === 'dark' ? '#64748b' : '#94a3b8' }} />
      <span style={{ color: theme === 'dark' ? '#64748b' : '#94a3b8', fontSize: 13 }}>
        {lineCount} 行代码 · {getLanguageDisplayName(detectedLanguage)}
      </span>
    </div>
  )

  return (
    <div ref={containerRef} className={`code-block ${className}`} style={containerStyle}>
      {(showLanguage || showCopyButton) && (
        <div style={headerStyle}>
          <Space size={8}>
            {showLanguage && (
              <span style={{
                color: theme === 'dark' ? '#94a3b8' : '#64748b',
                fontWeight: 500,
                display: 'flex',
                alignItems: 'center',
                gap: 6,
              }}>
                <FileTextOutlined style={{ fontSize: 14 }} />
                {getLanguageDisplayName(detectedLanguage)}
              </span>
            )}
          </Space>
          
          {showCopyButton && (
            <Tooltip title={copied ? '已复制' : '复制代码'}>
              <Button
                type="text"
                size="small"
                icon={copied ? <CheckOutlined style={{ color: 'var(--success)' }} /> : <CopyOutlined />}
                onClick={handleCopy}
                style={{
                  color: copied ? 'var(--success)' : (theme === 'dark' ? '#94a3b8' : '#64748b'),
                  padding: '2px 8px',
                  height: 28,
                  fontSize: 12,
                }}
              >
                {copied ? '已复制' : '复制'}
              </Button>
            </Tooltip>
          )}
        </div>
      )}

      {!isVisible ? (
        renderPlaceholder()
      ) : (
        <div style={codeContainerStyle} className="code-block-content">
          {showLineNumbers && (
            <div style={lineNumbersStyle} className="code-line-numbers" aria-hidden="true">
              {lineNumbers.map(num => (
                <div key={num} style={{ lineHeight: '1.6' }}>{num}</div>
              ))}
            </div>
          )}
          
          <code
            ref={codeRef}
            style={codeStyle}
            dangerouslySetInnerHTML={{ __html: highlightedCode }}
          />
        </div>
      )}

      <div style={footerStyle}>
        <span>{lineCount} 行</span>
        <span>{getLanguageDisplayName(detectedLanguage)}</span>
      </div>

      <style>{`
        .code-block-content::-webkit-scrollbar {
          width: 8px;
          height: 8px;
        }
        
        .code-block-content::-webkit-scrollbar-track {
          background: ${theme === 'dark' ? '#0f172a' : '#f1f5f9'};
        }
        
        .code-block-content::-webkit-scrollbar-thumb {
          background: ${theme === 'dark' ? '#475569' : '#cbd5e1'};
          border-radius: 4px;
        }
        
        .code-block-content::-webkit-scrollbar-thumb:hover {
          background: ${theme === 'dark' ? '#64748b' : '#94a3b8'};
        }
        
        .code-block-content::-webkit-scrollbar-corner {
          background: ${theme === 'dark' ? '#0f172a' : '#f1f5f9'};
        }
        
        .code-line-numbers {
          font-family: var(--font-mono);
        }
        
        .code-block code {
          font-family: var(--font-mono);
        }
        
        .code-block .hljs-comment,
        .code-block .hljs-quote {
          color: ${theme === 'dark' ? '#6a9955' : '#6a737d'};
          font-style: italic;
        }
        
        .code-block .hljs-keyword,
        .code-block .hljs-selector-tag,
        .code-block .hljs-addition {
          color: ${theme === 'dark' ? '#c586c0' : '#d73a49'};
        }
        
        .code-block .hljs-number,
        .code-block .hljs-string,
        .code-block .hljs-meta .hljs-meta-string,
        .code-block .hljs-literal,
        .code-block .hljs-doctag,
        .code-block .hljs-regexp {
          color: ${theme === 'dark' ? '#ce9178' : '#032f62'};
        }
        
        .code-block .hljs-title,
        .code-block .hljs-section,
        .code-block .hljs-name,
        .code-block .hljs-selector-id,
        .code-block .hljs-selector-class {
          color: ${theme === 'dark' ? '#dcdcaa' : '#6f42c1'};
        }
        
        .code-block .hljs-attribute,
        .code-block .hljs-attr,
        .code-block .hljs-variable,
        .code-block .hljs-template-variable,
        .code-block .hljs-class .hljs-title,
        .code-block .hljs-type {
          color: ${theme === 'dark' ? '#4ec9b0' : '#e36209'};
        }
        
        .code-block .hljs-symbol,
        .code-block .hljs-bullet,
        .code-block .hljs-subst,
        .code-block .hljs-meta,
        .code-block .hljs-meta .hljs-keyword,
        .code-block .hljs-selector-attr,
        .code-block .hljs-selector-pseudo,
        .code-block .hljs-link {
          color: ${theme === 'dark' ? '#d4a373' : '#005cc5'};
        }
        
        .code-block .hljs-built_in,
        .code-block .hljs-deletion {
          color: ${theme === 'dark' ? '#ce9178' : '#b31d28'};
        }
        
        .code-block .hljs-formula {
          background: ${theme === 'dark' ? '#1e293b' : '#f6f8fa'};
        }
        
        .code-block .hljs-emphasis {
          font-style: italic;
        }
        
        .code-block .hljs-strong {
          font-weight: bold;
        }
      `}</style>
    </div>
  )
})

CodeBlock.displayName = 'CodeBlock'

export default CodeBlock
