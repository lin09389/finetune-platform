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
import 'highlight.js/styles/atom-one-dark.css';

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
const LANG_ALIASES: Record<string, string> = {
  js: 'javascript',
  jsx: 'jsx',
  ts: 'typescript',
  tsx: 'tsx',
  sh: 'bash',
  shell: 'bash',
  yml: 'yaml',
  md: 'markdown',
  html: 'xml',
};

const normalizeLanguage = (language?: string): string => {
  if (!language) return 'text';
  const lowered = language.toLowerCase();
  return LANG_ALIASES[lowered] || lowered;
};

const detectLanguage = (code: string): string => {
  const trimmed = code.trim();
  if (!trimmed) return 'text';

  if (trimmed.startsWith('```')) {
    const firstLine = (trimmed.split('\n', 1)[0] ?? '').replace(/^```/, '').trim();
    if (firstLine) return normalizeLanguage(firstLine);
  }

  if (trimmed.startsWith('<?xml') || trimmed.startsWith('<!DOCTYPE') || /<\w+[\s>]/.test(trimmed)) {
    return 'xml';
  }
  if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
    try {
      JSON.parse(trimmed);
      return 'json';
    } catch {
      // continue
    }
  }
  if (/^(diff|index\s+[\w./-]+\s+\.\.|@@\s)/m.test(trimmed)) return 'diff';
  if (/^\s*#!/.test(trimmed) || /\b(curl|wget|npm|pnpm|yarn|pip|python|node|git|docker|kubectl)\b/.test(trimmed)) return 'bash';
  if (/^\s*(import\s+.+\s+from\s+['"].+['"]|export\s+(default\s+)?(const|function|class)|type\s+\w+\s*=|interface\s+\w+\s*\{)/m.test(trimmed)) {
    return /<\w+\s[^>]*\/>|return\s*\(/m.test(trimmed) ? 'tsx' : 'typescript';
  }
  if (/^\s*(import\s+.+\s+from\s+['"].+['"]|export\s+|return\s*\(|const\s+\w+\s*=\s*\()/m.test(trimmed)) {
    return /<\w+\s[^>]*\/>|className=|use(State|Effect|Memo|Callback)/m.test(trimmed) ? 'jsx' : 'javascript';
  }
  if (/^\s*(from\s+\w+\s+import\s+|def\s+\w+\(|class\s+\w+\(|if\s+__name__\s*==\s*['"]__main__['"])/m.test(trimmed)) return 'python';
  if (/^\s*(SELECT|INSERT|UPDATE|DELETE|WITH|CREATE|ALTER|DROP)\s+/im.test(trimmed)) return 'sql';
  if (/^\s*[^:#\n]+:\s*.+$/m.test(trimmed) && /:\s*$/m.test(trimmed) === false) return 'yaml';
  if (/^\s*(#|##|###)\s+/.test(trimmed) || /\[.*\]\(.*\)/.test(trimmed)) return 'markdown';
  return 'text';
};

/**
 * 生成行号
 */
const generateLineNumbers = (code: string): string => {
  const lines = code.split('\n').length;
  const width = String(lines).length;
  return Array.from({ length: lines }, (_, i) => String(i + 1).padStart(width, ' ')).join('\n');
};

/**
 * 代码预览组件
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
  collapsible = false,
}) => {
  const [selectedLanguage] = useState<string>('auto');
  const [detectedLanguage, setDetectedLanguage] = useState<string>('text');
  const [copied, setCopied] = useState(false);
  const [collapsed, setCollapsed] = useState(() => collapsible && code.split('\n').length > 10);
  const [fullscreenOpen, setFullscreenOpen] = useState(false);
  const [highlightedCode, setHighlightedCode] = useState('');
  const [isVisible, setIsVisible] = useState(false);
  const [hljsInstance, setHljsInstance] = useState<HLJSApi | null>(null);
  const [isLoadingHighlight, setIsLoadingHighlight] = useState(false);
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
      setDetectedLanguage(normalizeLanguage(propLanguage));
    } else {
      setDetectedLanguage(detectLanguage(code));
    }
  }, [code, propLanguage]);

  useEffect(() => {
    if (!isVisible) return;

    const lang = normalizeLanguage(selectedLanguage === 'auto' ? detectedLanguage : selectedLanguage);
    let isMounted = true;
    let cancelled = false;

    const loadLanguageModule = async (hljs: HLJSApi, targetLang: string) => {
      if (hljs.getLanguage(targetLang)) return;
      const fallbackOrder = targetLang === 'tsx'
        ? ['tsx', 'typescript', 'javascript']
        : targetLang === 'jsx'
          ? ['jsx', 'javascript']
          : targetLang === 'markdown'
            ? ['markdown']
            : targetLang === 'text'
              ? ['plaintext']
              : [targetLang, 'plaintext'];

      for (const candidate of fallbackOrder) {
        try {
          let langModule;
          switch (candidate) {
            case 'javascript':
              langModule = await import('highlight.js/lib/languages/javascript');
              break;
            case 'jsx':
              langModule = await import('highlight.js/lib/languages/javascript');
              break;
            case 'typescript':
            case 'tsx':
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
            case 'diff':
              langModule = await import('highlight.js/lib/languages/diff');
              break;
            case 'sql':
              langModule = await import('highlight.js/lib/languages/sql');
              break;
            default:
              langModule = await import('highlight.js/lib/languages/plaintext');
              break;
          }
          hljs.registerLanguage(candidate, langModule.default);
          if (candidate !== targetLang && !hljs.getLanguage(targetLang)) {
            hljs.registerLanguage(targetLang, langModule.default);
          }
          return;
        } catch {
          // try next alias
        }
      }
    };

    const loadHighlightJs = async () => {
      try {
        setIsLoadingHighlight(true);
        if (!hljsInstance) {
          const hljsModule = await import('highlight.js/lib/core');
          const hljs = hljsModule.default;
          await loadLanguageModule(hljs, lang);
          if (isMounted && !cancelled) setHljsInstance(hljs);
        } else {
          await loadLanguageModule(hljsInstance, lang);
        }
      } catch (error) {
        console.error('Failed to load highlight.js core', error);
      } finally {
        if (isMounted && !cancelled) setIsLoadingHighlight(false);
      }
    };

    void loadHighlightJs();

    return () => {
      cancelled = true;
      isMounted = false;
    };
  }, [isVisible, selectedLanguage, detectedLanguage, hljsInstance]);

  useEffect(() => {
    if (!isVisible || !hljsInstance) return;

    const lang = normalizeLanguage(selectedLanguage === 'auto' ? detectedLanguage : selectedLanguage);
    try {
      const result = hljsInstance.highlight(code, {
        language: hljsInstance.getLanguage(lang) ? lang : 'plaintext',
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
  const lineNumberWidth = Math.max(32, String(lineCount).length * 8 + 12);
  const isSimpleSnippet = lineCount === 1 && code.length < 30;
  const isStreamingPreview = isVisible && !highlightedCode && isLoadingHighlight;

  const renderPlaceholder = () => (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: 40,
        background: 'var(--bg-elevated)',
        borderRadius: 8,
        gap: 8,
      }}
    >
      <CodeOutlined style={{ fontSize: 16, color: 'var(--text-primary)' }} />
      <span style={{ color: 'var(--text-primary)', fontSize: 12 }}>
        {lineCount} 行代码 · {currentLanguage}
      </span>
    </div>
  );

  return (
    <>
      <div
        ref={containerRef as any}
        className={`code-preview ${className}`}
        style={{
          borderRadius: isSimpleSnippet ? 4 : 14,
          overflow: 'hidden',
          background: isSimpleSnippet ? 'transparent' : 'var(--bg-elevated)',
          margin: isSimpleSnippet ? '0 2px' : '16px 0',
          border: isSimpleSnippet ? 'none' : '1px solid var(--border-color)',
          boxShadow: isSimpleSnippet ? 'none' : 'var(--shadow-md)',
          display: isSimpleSnippet ? 'inline-block' : 'block',
          verticalAlign: 'middle',
        }}
      >
        {!collapsed && !isSimpleSnippet && (
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '10px 14px',
              background: 'linear-gradient(180deg, color-mix(in srgb, var(--bg-elevated) 96%, white 4%), var(--bg-elevated))',
              color: 'var(--text-primary)',
              fontSize: 12,
              fontFamily: 'var(--font-mono)',
              borderBottom: '1px solid color-mix(in srgb, var(--border-color) 70%, transparent)',
            }}
          >
            <Space size={10}>
              <div style={{ display: 'flex', gap: 5, opacity: 0.85 }}>
                <div style={{ width: 9, height: 9, borderRadius: '50%', background: '#ff5f56' }} />
                <div style={{ width: 9, height: 9, borderRadius: '50%', background: '#ffbd2e' }} />
                <div style={{ width: 9, height: 9, borderRadius: '50%', background: '#27c93f' }} />
              </div>
              <span style={{ fontWeight: 700, fontSize: 11, opacity: 0.82, letterSpacing: '0.06em', textTransform: 'uppercase' }}>
                {title || currentLanguage}
              </span>
              <span style={{ color: 'var(--text-tertiary)', fontSize: 11 }}>
                {lineCount} 行
              </span>
            </Space>
            
            <Space size={4}>
              {collapsible && (
                <Button
                  type="text"
                  size="small"
                  onClick={() => setCollapsed((c) => !c)}
                  style={{ color: 'var(--text-primary)', fontSize: 12, display: 'flex', alignItems: 'center', paddingInline: 6, fontWeight: 600 }}
                >
                  {collapsed ? '展开代码' : '折叠代码'}
                </Button>
              )}
              <Tooltip title={copied ? '已复制' : '复制代码'}>
                <Button
                  type="text"
                  size="small"
                  icon={copied ? <CheckOutlined style={{ color: 'var(--success)' }} /> : <CopyOutlined />}
                  onClick={handleCopy}
                  style={{ color: copied ? 'var(--success)' : 'var(--text-tertiary)', fontSize: 12, display: 'flex', alignItems: 'center', paddingInline: 6 }}
                >
                  {copied ? '已复制' : '复制'}
                </Button>
              </Tooltip>
              {showSave && (
                <Tooltip title="保存代码">
                  <Button
                    type="text"
                    size="small"
                    icon={<SaveOutlined />}
                    onClick={handleSave}
                    style={{ color: 'var(--text-tertiary)', fontSize: 12, display: 'flex', alignItems: 'center', paddingInline: 6 }}
                  >
                    保存
                  </Button>
                </Tooltip>
              )}
              {showFullscreen && (
                <Tooltip title="全屏查看">
                  <Button
                    type="text"
                    size="small"
                    icon={<FullscreenOutlined />}
                    onClick={() => setFullscreenOpen(true)}
                    style={{ color: 'var(--text-tertiary)', fontSize: 12, display: 'flex', alignItems: 'center', paddingInline: 6 }}
                  >
                    全屏
                  </Button>
                </Tooltip>
              )}
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
                background: 'var(--bg-elevated)',
                opacity: 1,
                paddingTop: isSimpleSnippet ? 2 : 12,
                paddingBottom: isSimpleSnippet ? 2 : 0,
              }}
            >
              {isStreamingPreview && !isSimpleSnippet && (
                <div style={{
                  position: 'absolute',
                  inset: 'auto 16px 12px auto',
                  color: 'var(--text-tertiary)',
                  fontSize: 12,
                }}>
                  渲染中…
                </div>
              )}
              {showLineNumbers && lineCount > 1 && (
                <div
                  className="code-line-numbers"
                  style={{
                    padding: '0 10px 16px 14px',
                    textAlign: 'right',
                    background: 'var(--bg-elevated)',
                    color: 'color-mix(in srgb, var(--text-tertiary) 75%, transparent)',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 12,
                    lineHeight: 1.66,
                    userSelect: 'none',
                    borderRight: '1px solid color-mix(in srgb, var(--border-color) 70%, transparent)',
                    minWidth: lineNumberWidth,
                    width: lineNumberWidth,
                    boxSizing: 'border-box',
                  }}
                >
                  <pre style={{ margin: 0, letterSpacing: '-0.02em' }}>{lineNumbers}</pre>
                </div>
              )}

              <div
                style={{
                  flex: 1,
                  overflow: 'auto',
                  padding: isSimpleSnippet ? '4px 16px 4px 16px' : '4px 18px 16px 18px',
                }}
              >
                <pre
                  ref={codeRef}
                  style={{
                    margin: 0,
                    padding: 0,
                    background: 'transparent',
                    fontSize: isSimpleSnippet ? 14 : 13.5,
                    lineHeight: 1.68,
                    fontFamily: 'var(--font-mono)',
                    color: isSimpleSnippet ? 'var(--accent-primary)' : 'var(--text-primary)',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                    tabSize: 2,
                  }}
                  dangerouslySetInnerHTML={{ __html: highlightedCode }}
                />
              </div>
            </div>
          ) : (
            <div style={{ padding: 20, textAlign: 'center' }}><Spin size="small" /></div>
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
            background: 'var(--bg-elevated)',
            borderRadius: 12,
            overflow: 'hidden',
          },
        }}
        title={
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ color: 'var(--text-primary)' }}>{title || defaultFilename}</span>
            <Space>
              <span style={{ color: 'var(--text-primary)', opacity: 0.6, fontSize: 12 }}>
                {currentLanguage} · {lineCount} 行
              </span>
              <Button
                type="text"
                size="small"
                icon={<FullscreenExitOutlined />}
                onClick={() => setFullscreenOpen(false)}
                style={{ color: 'var(--text-primary)' }}
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
            background: 'var(--bg-elevated)',
          }}
        >
          {showLineNumbers && (
            <div
              className="code-line-numbers"
              style={{
                padding: '0 8px 16px 16px',
                textAlign: 'right',
                background: 'var(--bg-elevated)',
                color: '#5c6370',
                fontFamily: 'var(--font-mono)',
                fontSize: 13,
                lineHeight: 1.6,
                userSelect: 'none',
                borderRight: '1px solid rgba(255, 255, 255, 0.05)',
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
                color: 'var(--text-primary)',
              }}
              dangerouslySetInnerHTML={{ __html: highlightedCode }}
            />
          </div>
        </div>
      </Modal>

      <style>{`
        .code-preview {
          border: 1px solid rgba(0, 0, 0, 0.1);
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        
        .code-preview:hover {
          border-color: rgba(255, 255, 255, 0.15);
          box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
        }

        .code-preview-container::-webkit-scrollbar {
          width: 8px;
          height: 8px;
        }

        .code-preview-container::-webkit-scrollbar-track {
          background: transparent;
        }

        .code-preview-container::-webkit-scrollbar-thumb {
          background: var(--bg-elevated);
          border-radius: 4px;
        }

        .code-preview-container::-webkit-scrollbar-thumb:hover {
          background: rgba(255, 255, 255, 0.2);
        }

        .code-line-numbers pre {
          font-family: var(--font-mono);
        }
      `}</style>
    </>
  );
};

export default CodePreview;
