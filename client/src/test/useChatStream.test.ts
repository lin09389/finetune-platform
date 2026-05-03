import { describe, expect, it } from 'vitest';
import { splitDeltaForDisplay } from '../hooks/chat/useChatStream';

describe('splitDeltaForDisplay', () => {
  it('keeps small streaming deltas intact', () => {
    expect(splitDeltaForDisplay('你好')).toEqual(['你好']);
  });

  it('splits large coalesced cloud deltas for smooth display', () => {
    const longDelta =
      '这是一段很长的云端模型回复内容，用来模拟供应商或代理把流式响应合并成一个大块返回的情况，并确认页面仍然可以像打字机一样逐步显示。';
    const chunks = splitDeltaForDisplay(longDelta);

    expect(chunks.length).toBeGreaterThan(1);
    expect(chunks.join('')).toBe(longDelta);
    expect(chunks.every((chunk) => Array.from(chunk).length <= 3)).toBe(true);
  });
});
