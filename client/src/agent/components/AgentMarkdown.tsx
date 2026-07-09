import { CheckOutlined, CopyOutlined } from '@ant-design/icons';
import { Button, Tooltip } from 'antd';
import { lazy, Suspense, useCallback, useState } from 'react';
import styles from '../workbench/AgentWorkbench.module.css';

const AgentMarkdownRenderer = lazy(() => import('./AgentMarkdownRenderer'));

async function copyText(content: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(content);
      return;
    } catch {
      // Embedded browsers can expose the API while denying clipboard permission.
    }
  }

  const textarea = document.createElement('textarea');
  textarea.value = content;
  textarea.setAttribute('readonly', '');
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand('copy');
  textarea.remove();
  if (!copied) throw new Error('Clipboard API unavailable');
}

export function CopyResponseButton({ content }: { content: string }) {
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'failed'>('idle');
  const copied = copyState === 'copied';

  const copy = useCallback(async () => {
    try {
      await copyText(content);
      setCopyState('copied');
    } catch {
      setCopyState('failed');
    }
    window.setTimeout(() => setCopyState('idle'), 1600);
  }, [content]);

  const label = copied ? '已复制' : copyState === 'failed' ? '重试' : '复制';
  const ariaLabel = copied ? '回答已复制' : copyState === 'failed' ? '复制失败，请重试' : '复制完整回答';

  return (
    <Tooltip title={copied ? '已复制' : copyState === 'failed' ? '复制失败，请重试' : '复制完整回答'}>
      <Button
        className={`${styles.responseAction} ${copyState === 'failed' ? styles.responseActionError : ''}`}
        type="text"
        size="small"
        icon={copied ? <CheckOutlined /> : <CopyOutlined />}
        aria-label={ariaLabel}
        onClick={copy}
      >
        {label}
      </Button>
    </Tooltip>
  );
}

export default function AgentMarkdown({
  content,
  streaming = false,
}: {
  content: string;
  streaming?: boolean;
}) {
  return (
    <Suspense fallback={<div className={styles.markdownLoading}>正在渲染内容…</div>}>
      <div className={streaming ? styles.markdownStreaming : undefined}>
        <AgentMarkdownRenderer content={content} />
        {streaming ? <span className={styles.streamingCursor} aria-hidden="true" /> : null}
      </div>
    </Suspense>
  );
}
