import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
  clampMessageIndex,
  getStoredScrollState,
  persistScrollState,
  type StoredChatScrollState,
} from './chatNewUtils';

export function useChatScrollPersistence(params: {
  sessionId: string | null;
  messageCount: number;
}) {
  const { sessionId, messageCount } = params;
  const visibleRangeStartRef = useRef(0);
  const isAutoScrollEnabledRef = useRef(true);
  const [showScrollButton, setShowScrollButton] = useState(false);
  const [isAtBottom, setIsAtBottom] = useState(true);

  const savedScrollState = useMemo(
    () => getStoredScrollState(sessionId),
    [sessionId],
  );

  const shouldRestoreToBottom = savedScrollState?.atBottom !== false;
  const initialTopMostItemIndex = useMemo(() => {
    if (messageCount === 0) return undefined;
    if (shouldRestoreToBottom) return messageCount - 1;
    return clampMessageIndex(savedScrollState?.topIndex ?? messageCount - 1, messageCount);
  }, [messageCount, savedScrollState?.topIndex, shouldRestoreToBottom]);

  const saveCurrentScrollState = useCallback(
    (overrides?: Partial<StoredChatScrollState>) => {
      if (!sessionId || sessionId.startsWith('local_')) return;
      if (messageCount === 0) return;
      persistScrollState(sessionId, {
        topIndex: clampMessageIndex(visibleRangeStartRef.current, messageCount),
        atBottom: isAutoScrollEnabledRef.current,
        updatedAt: new Date().toISOString(),
        ...overrides,
      });
    },
    [messageCount, sessionId],
  );

  useEffect(() => {
    setIsAtBottom(shouldRestoreToBottom);
    isAutoScrollEnabledRef.current = shouldRestoreToBottom;
    setShowScrollButton(messageCount > 0 && !shouldRestoreToBottom);
  }, [messageCount, shouldRestoreToBottom]);

  return {
    visibleRangeStartRef,
    isAutoScrollEnabledRef,
    showScrollButton,
    setShowScrollButton,
    isAtBottom,
    setIsAtBottom,
    savedScrollState,
    shouldRestoreToBottom,
    initialTopMostItemIndex,
    saveCurrentScrollState,
  };
}
