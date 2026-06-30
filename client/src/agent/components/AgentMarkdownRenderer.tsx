import { lazy, Suspense, useMemo } from 'react';
import ReactMarkdown, { type Components, type ExtraProps } from 'react-markdown';
import rehypeKatex from 'rehype-katex';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import 'katex/dist/katex.min.css';
import styles from '../workbench/AgentWorkbench.module.css';

const CodePreview = lazy(() => import('../../components/CodePreview'));
const LANGUAGE_PATTERN = /language-([\w-]+)/;

function normalizeMath(content: string): string {
  return content
    .replace(/\\\[([\s\S]*?)\\\]/g, '$$$$$1$$$$')
    .replace(/\\\(([\s\S]*?)\\\)/g, '$$$1$$');
}

function codeLanguage(className?: string): string {
  return LANGUAGE_PATTERN.exec(className || '')?.[1] || 'text';
}

function MarkdownCode({
  className,
  children,
  node: _node,
  ...props
}: React.ComponentPropsWithoutRef<'code'> & ExtraProps) {
  const value = String(children || '').replace(/\n$/, '');
  const isBlock = Boolean(className) || value.includes('\n');

  if (!isBlock) {
    return <code className={styles.markdownInlineCode} {...props}>{children}</code>;
  }

  return (
    <Suspense fallback={<div className={styles.markdownCodeLoading}>正在准备代码预览…</div>}>
      <CodePreview
        className={styles.markdownCodePreview}
        code={value}
        language={codeLanguage(className)}
        showLineNumbers={value.split('\n').length > 8}
        collapsible={value.split('\n').length > 24}
        showFullscreen={false}
        showSave={false}
        maxHeight={520}
      />
    </Suspense>
  );
}

const MARKDOWN_COMPONENTS: Components = {
  pre: ({ children }) => <>{children}</>,
  code: MarkdownCode,
  a: ({ children, ...props }) => (
    <a {...props} target="_blank" rel="noreferrer noopener">{children}</a>
  ),
  table: ({ children }) => (
    <div className={styles.markdownTableFrame} tabIndex={0}>
      <table>{children}</table>
    </div>
  ),
};

export default function AgentMarkdownRenderer({ content }: { content: string }) {
  const normalized = useMemo(() => normalizeMath(content), [content]);

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[rehypeKatex]}
      components={MARKDOWN_COMPONENTS}
    >
      {normalized}
    </ReactMarkdown>
  );
}
