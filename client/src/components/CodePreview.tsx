import {
  CheckOutlined,
  CodeOutlined,
  CopyOutlined,
  FullscreenExitOutlined,
  FullscreenOutlined,
  SaveOutlined,
} from '@ant-design/icons';
import { Button, message, Modal, Space, Spin, Tooltip } from 'antd';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';

// 只引入核心类型
import type { HLJSApi } from 'highlight.js';
import 'highlight.js/styles/github.css'; // 使用浅色主题

export interface CodePreviewProps {
  /** 代码内容 */
  code: string;
  /** 编程语言，可自动检测 */
  language?: string;
  /** 是否显示行号 */
  showLineNumbers?: boolean;
  /** 是否可折叠 */
  collapsible?: boolean;
  /** 是否显示全屏按钮 */
  showFullscreen?: boolean;
  /** 是否显示保存按钮 */
  showSave?: boolean;
  /** 默认文件名（保存时使用） */
  defaultFilename?: string;
  /** 最大高度（px） */
  maxHeight?: number;
  /** 自定义类名 */
  className?: string;
  /** 代码块标题 */
  title?: string;
}

/**
 * 自动检测代码语言
 */
const detectLanguage = (code: string): string => {
  const trimmed = code.trim();

  // 通过特征检测
  if (trimmed.startsWith('<?xml') || trimmed.startsWith('<!DOCTYPE')) {
    return 'xml';
  }
  if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
    try {
      JSON.parse(trimmed);
      return 'json';
    } catch {
      // 不是有效 JSON，继续检测
    }
  }
  if (/^import\s+[\w\s{},*]+\s+from\s+['"]/.test(trimmed)) {
    return 'typescript';
  }
  if (/^(import|export|function|const|let|var)\s+/.test(trimmed)) {
    return 'javascript';
  }
  if (/^(import|from|def|class|if|elif|else|for|while|with|try|except)\s+/.test(trimmed)) {
    return 'python';
  }
  if (/^(echo|cd|ls|mkdir|rm|cp|mv|pip|npm|yarn)\s+/.test(trimmed)) {
    return 'bash';
  }
  if (/^[\w-]+:\s*[\w-]/.test(trimmed)) {
    return 'yaml';
  }
  if (/^#+\s+/.test(trimmed) || /^\*\*.*\*\*/.test(trimmed)) {
    return 'markdown';
  }

  return 'text';
};

/**
 * 生成行号
 */
const generateLineNumbers = (code: string): string => {
  const lines = code.split('\n').length;
  return Array.from({ length: lines }, (_, i) => i + 1).join('\n');
};

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
  showFullscreen = true,
  showSave = true,
  defaultFilename = 'code',
  maxHeight = 500,
  className = '',
  title,
}) => {
  const [selectedLanguage] = useState<string>('auto');
  const [detectedLanguage, setDetectedLanguage] = useState<string>('text');
  const [copied, setCopied] = useState(false);
  const [collapsed] = useState(false);
  const [fullscreenOpen, setFullscreenOpen] = useState(false);
  const [highlightedCode, setHighlightedCode] = useState('');
  const [isVisible, setIsVisible] = useState(false);
  const [hljsInstance, setHljsInstance] = useState<HLJSApi | null>(null);
  const codeRef = useRef<HTMLPreElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          setIsVisible(true);
          observer.disconnect();
        }
      },
      {
        rootMargin: '100px',
        threshold: 0.01,
      },
    );

    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (propLanguage && propLanguage !== 'auto') {
      setDetectedLanguage(propLanguage);
    } else {
      setDetectedLanguage(detectLanguage(code));
    }
  }, [code, propLanguage]);

  useEffect(() => {
    if (!isVisible) return;

    const lang = selectedLanguage === 'auto' ? detectedLanguage : selectedLanguage;

    let isMounted = true;

    const loadHighlightJs = async () => {
      try {
        if (!hljsInstance) {
          // 动态引入 hljs core
          const hljsModule = await import('highlight.js/lib/core');
          const hljs = hljsModule.default;
          
          // 动态引入对应语言包
          try {
            let langModule;
            switch (lang) {
              case 'javascript':
                langModule = await import('highlight.js/lib/languages/javascript');
                break;
              case 'python':
                langModule = await import('highlight.js/lib/languages/python');
                break;
              case 'typescript':
                langModule = await import('highlight.js/lib/languages/typescript');
                break;
              case 'json':
                langModule = await import('highlight.js/lib/languages/json');
                break;
              case 'xml':
                langModule = await import('highlight.js/lib/languages/xml');
                break;
              case 'bash':
                langModule = await import('highlight.js/lib/languages/bash');
                break;
              case 'yaml':
                langModule = await import('highlight.js/lib/languages/yaml');
                break;
              case 'markdown':
                langModule = await import('highlight.js/lib/languages/markdown');
                break;
              case 'text':
              case 'plaintext':
              default:
                langModule = await import('highlight.js/lib/languages/plaintext');
                break;
            }
            hljs.registerLanguage(lang, langModule.default);
          } catch (e) {
            console.warn(`Failed to load language module for ${lang}`, e);
          }
          
          if (isMounted) {
            setHljsInstance(hljs);
          }
        } else {
          // 如果实例已存在，检查语言是否已注册
          if (!hljsInstance.getLanguage(lang)) {
            try {
              let langModule;
              switch (lang) {
                case 'javascript':
                  langModule = await import('highlight.js/lib/languages/javascript');
                  break;
                case 'python':
                  langModule = await import('highlight.js/lib/languages/python');
                  break;
                case 'typescript':
                  langModule = await import('highlight.js/lib/languages/typescript');
                  break;
                case 'json':
                  langModule = await import('highlight.js/lib/languages/json');
                  break;
                case 'xml':
                  langModule = await import('highlight.js/lib/languages/xml');
                  break;
                case 'bash':
                  langModule = await import('highlight.js/lib/languages/bash');
                  break;
                case 'yaml':
                  langModule = await import('highlight.js/lib/languages/yaml');
                  break;
                case 'markdown':
                  langModule = await import('highlight.js/lib/languages/markdown');
                  break;
                case 'text':
                case 'plaintext':
                default:
                  langModule = await import('highlight.js/lib/languages/plaintext');
                  break;
              }
              hljsInstance.registerLanguage(lang, langModule.default);
            } catch (e) {
              console.warn(`Failed to load language module for ${lang}`, e);
            }
          }
        }
      } catch (error) {
        console.error('Failed to load highlight.js core', error);
      }
    };

    loadHighlightJs();

    return () => {
      isMounted = false;
    };
  }, [isVisible, selectedLanguage, detectedLanguage, hljsInstance]);

  useEffect(() => {
    if (!isVisible || !hljsInstance) return;

    const lang = selectedLanguage === 'auto' ? detectedLanguage : selectedLanguage;
    try {
      const result = hljsInstance.highlight(code, {
        language: lang,
        ignoreIllegals: true,
      });
      setHighlightedCode(result.value);
    } catch {
      setHighlightedCode(code);
    }
  }, [code, selectedLanguage, detectedLanguage, isVisible, hljsInstance]);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      message.success('代码已复制');
      setTimeout(() => setCopied(false), 2000);
    } catch {
      message.error('复制失败');
    }
  }, [code]);

  const handleSave = useCallback(() => {
    const blob = new Blob([code], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${defaultFilename}.${detectedLanguage === 'text' ? 'txt' : detectedLanguage}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    message.success('代码已保存');
  }, [code, defaultFilename, detectedLanguage]);

  const currentLanguage = selectedLanguage === 'auto' ? detectedLanguage : selectedLanguage;

  const lineCount = code.split('\n').length;

  const lineNumbers = useMemo(() => generateLineNumbers(code), [code]);

  const renderPlaceholder = () => (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: 80,
        background: '#f4f4f5',
        borderRadius: 8,
        gap: 8,
      }}
    >
      <CodeOutlined style={{ fontSize: 20, color: '#999' }} />
      <span style={{ color: '#999', fontSize: 13 }}>
        {lineCount} 行代码 · {currentLanguage}
      </span>
    </div>
  );

  const renderLoading = () => (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: 80,
        background: '#f4f4f5',
        borderRadius: 8,
      }}
    >
      <Spin size="small" />
    </div>
  );

  return (
    <>
      <div
        ref={containerRef as any}
        className={`code-preview ${className}`}
        style={{
          borderRadius: 12,
          overflow: 'hidden',
          background: '#f4f4f5',
          margin: '12px 0',
        }}
      >
        {!collapsed && (
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '6px 16px',
              background: '#ececec',
              color: '#666',
              fontSize: 12,
              fontFamily: 'var(--font-mono)',
              borderBottom: '1px solid #e5e5e5',
            }}
          >
            <Space>
              <CodeOutlined style={{ color: '#999' }} />
              <span style={{ fontWeight: 600 }}>{title || currentLanguage}</span>
            </Space>
            
            <Space size={4}>
              {showSave && (
                <Tooltip title="下载代码">
                  <Button
                    type="text"
                    size="small"
                    icon={<SaveOutlined />}
                    onClick={handleSave}
                    style={{ color: '#666', fontSize: 13, display: 'flex', alignItems: 'center' }}
                  />
                </Tooltip>
              )}
              {showFullscreen && (
                <Tooltip title="全屏查看">
                  <Button
                    type="text"
                    size="small"
                    icon={<FullscreenOutlined />}
                    onClick={() => setFullscreenOpen(true)}
                    style={{ color: '#666', fontSize: 13, display: 'flex', alignItems: 'center' }}
                  />
                </Tooltip>
              )}
              <Tooltip title={copied ? '已复制' : '复制代码'}>
                <Button
                  type="text"
                  size="small"
                  icon={copied ? <CheckOutlined style={{ color: 'var(--success)' }} /> : <CopyOutlined />}
                  onClick={handleCopy}
                  style={{ color: copied ? 'var(--success)' : '#666', fontSize: 13, display: 'flex', alignItems: 'center' }}
                >
                  {copied ? '已复制' : '复制'}
                </Button>
              </Tooltip>
            </Space>
          </div>
        )}

        {!collapsed &&
          (!isVisible ? (
            renderPlaceholder()
          ) : highlightedCode ? (
            <div
              className="code-preview-container"
              style={{
                display: 'flex',
                maxHeight,
                overflow: 'auto',
                background: '#f4f4f5',
                opacity: 1,
                transform: 'translateY(0)',
                transition: 'opacity 0.3s ease, transform 0.3s ease',
                paddingTop: 12,
              }}
            >
              {showLineNumbers && (
                <div
                  className="code-line-numbers"
                  style={{
                    padding: '0 8px 16px 16px',
                    textAlign: 'right',
                    background: '#f4f4f5',
                    color: '#999',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 13,
                    lineHeight: 1.6,
                    userSelect: 'none',
                    borderRight: '1px solid #e5e5e5',
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
                  padding: '0 16px 16px 16px',
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
                    color: '#24292e',
                  }}
                  dangerouslySetInnerHTML={{ __html: highlightedCode }}
                />
              </div>
            </div>
          ) : (
            renderLoading()
          ))}
      </div>

      <Modal
        open={fullscreenOpen}
        onCancel={() => setFullscreenOpen(false)}
        footer={null}
        width="90vw"
        style={{ top: '5%' }}
        styles={{
          body: {
            padding: 0,
            background: '#f4f4f5',
            borderRadius: 12,
            overflow: 'hidden',
          },
        }}
        title={
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ color: '#24292e' }}>{title || defaultFilename}</span>
            <Space>
              <span style={{ color: '#666', fontSize: 12 }}>
                {currentLanguage} · {lineCount} 行
              </span>
              <Button
                type="text"
                size="small"
                icon={<FullscreenExitOutlined />}
                onClick={() => setFullscreenOpen(false)}
                style={{ color: '#666' }}
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
            background: '#f4f4f5',
          }}
        >
          {showLineNumbers && (
            <div
              className="code-line-numbers"
              style={{
                padding: '0 8px 16px 16px',
                textAlign: 'right',
                background: '#f4f4f5',
                color: '#999',
                fontFamily: 'var(--font-mono)',
                fontSize: 13,
                lineHeight: 1.6,
                userSelect: 'none',
                borderRight: '1px solid #e5e5e5',
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
              padding: '0 16px 16px 16px',
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
                color: '#24292e',
              }}
              dangerouslySetInnerHTML={{ __html: highlightedCode }}
            />
          </div>
        </div>
      </Modal>

      <style>{`
        .code-preview {
          border: 1px solid #e5e5e5;
          box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);
          transition: border-color 0.2s, box-shadow 0.2s;
        }
        
        .code-preview:hover {
          border-color: #d9d9d9;
          box-shadow: 0 2px 6px rgba(0, 0, 0, 0.05);
        }

        .code-preview-container::-webkit-scrollbar {
          width: 8px;
          height: 8px;
        }

        .code-preview-container::-webkit-scrollbar-track {
          background: transparent;
        }

        .code-preview-container::-webkit-scrollbar-thumb {
          background: #d9d9d9;
          border-radius: 4px;
        }

        .code-preview-container::-webkit-scrollbar-thumb:hover {
          background: #bfbfbf;
        }

        .code-line-numbers pre {
          font-family: var(--font-mono);
        }

        /* 深色模式适配保留原色或使用稍暗一点的浅色 */
        .dark-theme .code-preview-container {
          background: #f4f4f5;
        }

        .dark-theme .code-line-numbers {
          background: #f4f4f5;
        }
      `}</style>
    </>
  );
};

export default CodePreview;
