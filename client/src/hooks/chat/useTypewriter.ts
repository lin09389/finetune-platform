import { useEffect, useMemo, useState } from 'react';

const MIN_TYPEWRITER_STEP_MS = 16;
const CODE_FENCE_PATTERN = /```[\s\S]*?```/g;

function getChunkSize(speed: number, contentLength: number) {
  const base = speed <= 24 ? 1 : speed <= 40 ? 2 : speed <= 60 ? 3 : 4;
  if (contentLength > 3000) return Math.max(base, 6);
  if (contentLength > 1500) return Math.max(base, 5);
  if (contentLength > 800) return Math.max(base, 4);
  return base;
}

export interface StreamingContentSplit {
  plainText: string;
  codeBlocks: string[];
  hasOpenFence: boolean;
}

function splitStreamingContent(content: string): StreamingContentSplit {
  const codeBlocks: string[] = [];
  const segments: string[] = [];
  let lastIndex = 0;

  for (const match of content.matchAll(CODE_FENCE_PATTERN)) {
    const start = match.index ?? 0;
    segments.push(content.slice(lastIndex, start));
    codeBlocks.push(match[0]);
    lastIndex = start + match[0].length;
  }

  segments.push(content.slice(lastIndex));

  const fenceMatches = content.match(/```/g) || [];
  const hasOpenFence = fenceMatches.length % 2 === 1;

  return { plainText: segments.join(''), codeBlocks, hasOpenFence };
}

export function useTypewriter(content: string, isStreaming: boolean, speed: number = 45) {
  const [displayContent, setDisplayContent] = useState(content);

  useEffect(() => {
    setDisplayContent(content);
  }, [content]);

  useEffect(() => {
    if (!isStreaming) {
      setDisplayContent(content);
      return;
    }

    let cancelled = false;
    const target = content;
    const stepMs = Math.max(MIN_TYPEWRITER_STEP_MS, Math.floor(speed));
    const chunkSize = getChunkSize(speed, target.length);

    if (displayContent.length >= target.length) {
      return;
    }

    const timer = setInterval(() => {
      if (cancelled) return;
      setDisplayContent((current) => {
        const nextLength = Math.min(current.length + chunkSize, target.length);
        const next = target.slice(0, nextLength);
        if (nextLength >= target.length) {
          clearInterval(timer);
        }
        return next;
      });
    }, stepMs);

    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [content, displayContent.length, isStreaming, speed]);

  const splitContent = useMemo(() => splitStreamingContent(displayContent), [displayContent]);

  const processedContent = useMemo(() => {
    let text = displayContent;
    if (isStreaming) {
      const codeBlockCount = (text.match(/```/g) || []).length;
      if (codeBlockCount % 2 !== 0) {
        text += '<span class="gemini-cursor"></span>\n```';
      } else {
        text += '<span class="gemini-cursor"></span>';
      }
    }
    return text;
  }, [displayContent, isStreaming]);

  return {
    displayContent,
    processedContent,
    splitContent,
    isDoneTyping: !isStreaming || displayContent.length >= content.length,
  };
}
