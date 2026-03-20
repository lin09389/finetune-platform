import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { Card, Button, Space, Tooltip, Select, message, Modal, Spin } from 'antd'
import {
  CopyOutlined,
  SaveOutlined,
  FullscreenOutlined,
  FullscreenExitOutlined,
  CheckOutlined,
  UnorderedListOutlined,
  CompressOutlined,
  CodeOutlined,
} from '@ant-design/icons'
import hljs from 'highlight.js/lib/core'
import 'highlight.js/styles/atom-one-dark.css'

// 注册常用语言
import javascript from 'highlight.js/lib/languages/javascript'
import python from 'highlight.js/lib/languages/python'
import typescript from 'highlight.js/lib/languages/typescript'
import json from 'highlight.js/lib/languages/json'
import xml from 'highlight.js/lib/languages/xml'
import bash from 'highlight.js/lib/languages/bash'
import yaml from 'highlight.js/lib/languages/yaml'
import markdown from 'highlight.js/lib/languages/markdown'
import plaintext from 'highlight.js/lib/languages/plaintext'

hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('python', python)
hljs.registerLanguage('typescript', typescript)
hljs.registerLanguage('json', json)
hljs.registerLanguage('xml', xml)
hljs.registerLanguage('bash', bash)
hljs.registerLanguage('yaml', yaml)
hljs.registerLanguage('markdown', markdown)
hljs.registerLanguage('plaintext', plaintext)
hljs.registerLanguage('text', plaintext)

export interface CodePreviewProps {
  /** 代码内容 */
  code: string
  /** 编程语言，可自动检测 */
  language?: string
  /** 是否显示行号 */
  showLineNumbers?: boolean
  /** 是否可折叠 */
  collapsible?: boolean
  /** 是否显示全屏按钮 */
  showFullscreen?: boolean
  /** 是否显示保存按钮 */
  showSave?: boolean
  /** 默认文件名（保存时使用） */
  defaultFilename?: string
  /** 最大高度（px） */
  maxHeight?: number
  /** 自定义类名 */
  className?: string
  /** 代码块标题 */
  title?: string
}

const LANGUAGE_OPTIONS = [
  { value: 'auto', label: '自动检测' },
  { value: 'python', label: 'Python' },
  { value: 'javascript', label: 'JavaScript' },
  { value: 'typescript', label: 'TypeScript' },
  { value: 'json', label: 'JSON' },
  { value: 'xml', label: 'XML/HTML' },
  { value: 'bash', label: 'Bash/Shell' },
  { value: 'yaml', label: 'YAML' },
  { value: 'markdown', label: 'Markdown' },
  { value: 'text', label: '纯文本' },
]

const FILE_EXTENSIONS: Record<string, string> = {
  python: '.py',
  javascript: '.js',
  typescript: '.ts',
  json: '.json',
  xml: '.xml',
  bash: '.sh',
  yaml: '.yaml',
  markdown: '.md',
  text: '.txt',
}

/**
 * 自动检测代码语言
 */
const detectLanguage = (code: string): string => {
  const trimmed = code.trim()
  
  // 通过特征检测
  if (trimmed.startsWith('<?xml') || trimmed.startsWith('<!DOCTYPE')) {
    return 'xml'
  }
  if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
    try {
      JSON.parse(trimmed)
      return 'json'
    } catch {
      // 不是有效 JSON，继续检测
    }
  }
  if (/^import\s+[\w\s{},*]+\s+from\s+['"]/.test(trimmed)) {
    return 'typescript'
  }
  if (/^(import|export|function|const|let|var)\s+/.test(trimmed)) {
    return 'javascript'
  }
  if (/^(import|from|def|class|if|elif|else|for|while|with|try|except)\s+/.test(trimmed)) {
    return 'python'
  }
  if (/^(echo|cd|ls|mkdir|rm|cp|mv|pip|npm|yarn)\s+/.test(trimmed)) {
    return 'bash'
  }
  if (/^[\w-]+:\s*[\w-]/.test(trimmed)) {
    return 'yaml'
  }
  if (/^#+\s+/.test(trimmed) || /^\*\*.*\*\*/.test(trimmed)) {
    return 'markdown'
  }
  
  return 'text'
}

/**
 * 获取文件扩展名
 */
const getFileExtension = (language: string): string => {
  return FILE_EXTENSIONS[language] || '.txt'
}

/**
 * 生成行号
 */
const generateLineNumbers = (code: string): string => {
  const lines = code.split('\n').length
  return Array.from({ length: lines }, (_, i) => i + 1).join('\n')
}

/**
 * 代码预览组件
 * 
 * 功能：
 * - 语法高亮（highlight.js）
 * - 一键复制
 * - 保存为文件
 * - 全屏预览
 * - 行号显示
 * - 语言选择
 * - 代码折叠
 */
const CodePreview: React.FC<CodePreviewProps> = ({
  code,
  language: propLanguage,
  showLineNumbers = true,
  collapsible = true,
  showFullscreen = true,
  showSave = true,
  defaultFilename = 'code',
  maxHeight = 500,
  className = '',
  title,
}) => {
  const [selectedLanguage, setSelectedLanguage] = useState<string>('auto')
  const [detectedLanguage, setDetectedLanguage] = useState<string>('text')
  const [copied, setCopied] = useState(false)
  const [collapsed, setCollapsed] = useState(false)
  const [fullscreenOpen, setFullscreenOpen] = useState(false)
  const [highlightedCode, setHighlightedCode] = useState('')
  const [isVisible, setIsVisible] = useState(false)
  const codeRef = useRef<HTMLPreElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

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
      {
        rootMargin: '100px',
        threshold: 0.01,
      }
    )

    observer.observe(container)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (propLanguage && propLanguage !== 'auto') {
      setDetectedLanguage(propLanguage)
    } else {
      setDetectedLanguage(detectLanguage(code))
    }
  }, [code, propLanguage])

  useEffect(() => {
    if (!isVisible) return

    const lang = selectedLanguage === 'auto' ? detectedLanguage : selectedLanguage
    try {
      const result = hljs.highlight(code, {
        language: lang,
        ignoreIllegals: true,
      })
      setHighlightedCode(result.value)
    } catch {
      setHighlightedCode(code)
    }
  }, [code, selectedLanguage, detectedLanguage, isVisible])

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
      message.success('代码已复制')
      setTimeout(() => setCopied(false), 2000)
    } catch {
      message.error('复制失败')
    }
  }, [code])

  const handleSave = useCallback(() => {
    try {
      const lang = selectedLanguage === 'auto' ? detectedLanguage : selectedLanguage
      const ext = getFileExtension(lang)
      const filename = defaultFilename + ext
      
      const blob = new Blob([code], { type: 'text/plain;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)
      
      message.success(`已保存为 ${filename}`)
    } catch {
      message.error('保存失败')
    }
  }, [code, selectedLanguage, detectedLanguage, defaultFilename])

  const handleToggleCollapse = useCallback(() => {
    setCollapsed(!collapsed)
  }, [collapsed])

  const currentLanguage = selectedLanguage === 'auto' ? detectedLanguage : selectedLanguage

  const lineCount = code.split('\n').length

  const lineNumbers = useMemo(() => generateLineNumbers(code), [code])

  const renderPlaceholder = () => (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: 80,
        background: '#1e293b',
        borderRadius: 8,
        gap: 8,
      }}
    >
      <CodeOutlined style={{ fontSize: 20, color: '#64748b' }} />
      <span style={{ color: '#64748b', fontSize: 13 }}>
        {lineCount} 行代码 · {currentLanguage}
      </span>
    </div>
  )

  const renderLoading = () => (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: 80,
        background: '#1e293b',
        borderRadius: 8,
      }}
    >
      <Spin size="small" />
    </div>
  )

  return (
    <>
      <Card
        ref={containerRef as any}
        className={`code-preview ${className}`}
        title={title}
        size="small"
        style={{
          borderRadius: 12,
          overflow: 'hidden',
        }}
        styles={{
          body: { padding: 0 },
        }}
        extra={
          <Space size="small">
            <Select
              value={selectedLanguage}
              onChange={setSelectedLanguage}
              options={LANGUAGE_OPTIONS}
              size="small"
              style={{ width: 110 }}
              placeholder="选择语言"
            />
            
            <Tooltip title={copied ? '已复制' : '复制代码'}>
              <Button
                type="text"
                size="small"
                icon={copied ? <CheckOutlined style={{ color: 'var(--success)' }} /> : <CopyOutlined />}
                onClick={handleCopy}
              />
            </Tooltip>
            
            {showSave && (
              <Tooltip title="保存为文件">
                <Button
                  type="text"
                  size="small"
                  icon={<SaveOutlined />}
                  onClick={handleSave}
                />
              </Tooltip>
            )}
            
            {collapsible && (
              <Tooltip title={collapsed ? '展开' : '折叠'}>
                <Button
                  type="text"
                  size="small"
                  icon={collapsed ? <CompressOutlined /> : <UnorderedListOutlined />}
                  onClick={handleToggleCollapse}
                />
              </Tooltip>
            )}
            
            {showFullscreen && (
              <Tooltip title="全屏预览">
                <Button
                  type="text"
                  size="small"
                  icon={<FullscreenOutlined />}
                  onClick={() => setFullscreenOpen(true)}
                />
              </Tooltip>
            )}
          </Space>
        }
      >
        {!collapsed && (
          !isVisible ? (
            renderPlaceholder()
          ) : highlightedCode ? (
            <div
              className="code-preview-container"
              style={{
                display: 'flex',
                maxHeight,
                overflow: 'auto',
                background: '#1e293b',
                borderRadius: 8,
                opacity: 1,
                transform: 'translateY(0)',
                transition: 'opacity 0.3s ease, transform 0.3s ease',
              }}
            >
              {showLineNumbers && (
                <div
                  className="code-line-numbers"
                  style={{
                    padding: '16px 8px',
                    textAlign: 'right',
                    background: '#0f172a',
                    color: '#64748b',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 13,
                    lineHeight: 1.6,
                    userSelect: 'none',
                    borderRight: '1px solid #334155',
                    minWidth: 50,
                  }}
                >
                  <pre style={{ margin: 0 }}>{lineNumbers}</pre>
                </div>
              )}
              
              <div
                style={{
                  flex: 1,
                  overflow: 'auto',
                  padding: 16,
                }}
              >
                <pre
                  ref={codeRef}
                  style={{
                    margin: 0,
                    padding: 0,
                    background: 'transparent',
                    fontSize: 13,
                    lineHeight: 1.6,
                    fontFamily: 'var(--font-mono)',
                    color: '#e2e8f0',
                  }}
                  dangerouslySetInnerHTML={{ __html: highlightedCode }}
                />
              </div>
            </div>
          ) : (
            renderLoading()
          )
        )}
        
        {!collapsed && (
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              padding: '8px 12px',
              background: 'var(--bg-secondary)',
              borderTop: '1px solid var(--border-color)',
              fontSize: 12,
              color: 'var(--text-tertiary)',
            }}
          >
            <span>{lineCount} 行</span>
            <span>{currentLanguage}</span>
          </div>
        )}
      </Card>

      <Modal
        open={fullscreenOpen}
        onCancel={() => setFullscreenOpen(false)}
        footer={null}
        width="90vw"
        style={{ top: '5%' }}
        styles={{
          body: {
            padding: 0,
            background: '#1e293b',
            borderRadius: 12,
            overflow: 'hidden',
          },
        }}
        title={
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ color: '#e2e8f0' }}>{title || defaultFilename}</span>
            <Space>
              <span style={{ color: '#64748b', fontSize: 12 }}>
                {currentLanguage} · {lineCount} 行
              </span>
              <Button
                type="text"
                size="small"
                icon={<FullscreenExitOutlined />}
                onClick={() => setFullscreenOpen(false)}
                style={{ color: '#94a3b8' }}
              />
            </Space>
          </div>
        }
      >
        <div
          style={{
            display: 'flex',
            maxHeight: '70vh',
            overflow: 'auto',
            background: '#1e293b',
          }}
        >
          {showLineNumbers && (
            <div
              className="code-line-numbers"
              style={{
                padding: '16px 8px',
                textAlign: 'right',
                background: '#0f172a',
                color: '#64748b',
                fontFamily: 'var(--font-mono)',
                fontSize: 13,
                lineHeight: 1.6,
                userSelect: 'none',
                borderRight: '1px solid #334155',
                minWidth: 50,
              }}
            >
              <pre style={{ margin: 0 }}>{lineNumbers}</pre>
            </div>
          )}
          <div
            style={{
              flex: 1,
              overflow: 'auto',
              padding: 16,
            }}
          >
            <pre
              style={{
                margin: 0,
                padding: 0,
                background: 'transparent',
                fontSize: 14,
                lineHeight: 1.6,
                fontFamily: 'var(--font-mono)',
                color: '#e2e8f0',
              }}
              dangerouslySetInnerHTML={{ __html: highlightedCode }}
            />
          </div>
        </div>
      </Modal>

      <style>{`
        .code-preview-container::-webkit-scrollbar {
          width: 10px;
          height: 10px;
        }

        .code-preview-container::-webkit-scrollbar-track {
          background: #0f172a;
        }

        .code-preview-container::-webkit-scrollbar-thumb {
          background: #475569;
          border-radius: 5px;
        }

        .code-preview-container::-webkit-scrollbar-thumb:hover {
          background: #64748b;
        }

        .code-line-numbers pre {
          font-family: var(--font-mono);
        }

        /* 深色模式适配 */
        .dark-theme .code-preview-container {
          background: #1e293b;
        }

        .dark-theme .code-line-numbers {
          background: #0f172a;
        }
      `}</style>
    </>
  )
}

export default CodePreview
