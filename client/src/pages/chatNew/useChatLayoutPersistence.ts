import { useCallback, useEffect, useState, type PointerEvent as ReactPointerEvent } from 'react';

import {
  CHAT_PANEL_OPEN_STORAGE_KEY,
  CHAT_PANE_WIDTH_STORAGE_KEY,
  CHAT_SIDE_PANEL_OPEN_STORAGE_KEY,
  CHAT_SIDE_PANEL_WIDTH_STORAGE_KEY,
} from './chatNewUtils';

const TERMINAL_DOCK_HEIGHT_STORAGE_KEY = 'terminal_dock_height';

export function useChatLayoutPersistence(params: {
  resizingClassName?: string;
}) {
  const { resizingClassName } = params;
  const [sidePanelWidth, setSidePanelWidth] = useState(() => {
    if (typeof window === 'undefined') return 360;
    const stored = Number(localStorage.getItem(CHAT_SIDE_PANEL_WIDTH_STORAGE_KEY));
    return Number.isFinite(stored) && stored >= 280 ? stored : 360;
  });
  const [resizingSidePanel, setResizingSidePanel] = useState(false);
  const [chatPaneWidth, setChatPaneWidth] = useState(() => {
    if (typeof window === 'undefined') return 380;
    const stored = Number(localStorage.getItem(CHAT_PANE_WIDTH_STORAGE_KEY));
    return Number.isFinite(stored) && stored >= 240 ? stored : 380;
  });
  const [resizingChatPane, setResizingChatPane] = useState(false);
  const [sidePanelOpen, setSidePanelOpen] = useState(() => {
    if (typeof window === 'undefined') return true;
    return localStorage.getItem(CHAT_SIDE_PANEL_OPEN_STORAGE_KEY) !== '0';
  });
  const [chatPanelOpen, setChatPanelOpen] = useState(() => {
    if (typeof window === 'undefined') return true;
    return localStorage.getItem(CHAT_PANEL_OPEN_STORAGE_KEY) !== '0';
  });
  const [terminalHeight, setTerminalHeight] = useState(() => {
    if (typeof window === 'undefined') return 240;
    const stored = Number(localStorage.getItem(TERMINAL_DOCK_HEIGHT_STORAGE_KEY));
    return Number.isFinite(stored) && stored >= 120 ? stored : 240;
  });
  const [resizingTerminal, setResizingTerminal] = useState(false);

  useEffect(() => {
    if (typeof document === 'undefined') return;
    const resizingRowClass = 'resizingTerminal';
    if (resizingClassName) {
      document.body.classList.toggle(resizingClassName, resizingSidePanel || resizingChatPane);
    }
    document.body.classList.toggle(resizingRowClass, resizingTerminal);
    return () => {
      if (resizingClassName) document.body.classList.remove(resizingClassName);
      document.body.classList.remove(resizingRowClass);
    };
  }, [resizingChatPane, resizingClassName, resizingSidePanel, resizingTerminal]);

  useEffect(() => {
    localStorage.setItem(CHAT_SIDE_PANEL_WIDTH_STORAGE_KEY, String(sidePanelWidth));
  }, [sidePanelWidth]);

  useEffect(() => {
    localStorage.setItem(CHAT_PANE_WIDTH_STORAGE_KEY, String(chatPaneWidth));
  }, [chatPaneWidth]);

  useEffect(() => {
    localStorage.setItem(CHAT_SIDE_PANEL_OPEN_STORAGE_KEY, sidePanelOpen ? '1' : '0');
  }, [sidePanelOpen]);

  useEffect(() => {
    localStorage.setItem(CHAT_PANEL_OPEN_STORAGE_KEY, chatPanelOpen ? '1' : '0');
  }, [chatPanelOpen]);

  useEffect(() => {
    localStorage.setItem(TERMINAL_DOCK_HEIGHT_STORAGE_KEY, String(terminalHeight));
  }, [terminalHeight]);

  const handleSplitterPointerDown = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = sidePanelWidth;
    const minSideWidth = 280;
    const maxSideWidth = Math.max(320, window.innerWidth - 520);
    setResizingSidePanel(true);
    let pendingX = startX;
    let rafId: number | null = null;

    const handlePointerMove = (moveEvent: PointerEvent) => {
      pendingX = moveEvent.clientX;
      if (rafId !== null) return;
      rafId = requestAnimationFrame(() => {
        rafId = null;
        setSidePanelWidth(Math.min(maxSideWidth, Math.max(minSideWidth, startWidth - (pendingX - startX))));
      });
    };

    const handlePointerUp = () => {
      if (rafId !== null) { cancelAnimationFrame(rafId); rafId = null; }
      setResizingSidePanel(false);
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
    };

    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
  }, [sidePanelWidth]);

  const handleChatSplitterPointerDown = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = chatPaneWidth;
    const minChatWidth = 240;
    const maxChatWidth = Math.max(280, window.innerWidth - 720);
    setResizingChatPane(true);
    let pendingX = startX;
    let rafId: number | null = null;

    const handlePointerMove = (moveEvent: PointerEvent) => {
      pendingX = moveEvent.clientX;
      if (rafId !== null) return;
      rafId = requestAnimationFrame(() => {
        rafId = null;
        setChatPaneWidth(Math.min(maxChatWidth, Math.max(minChatWidth, startWidth + (pendingX - startX))));
      });
    };

    const handlePointerUp = () => {
      if (rafId !== null) { cancelAnimationFrame(rafId); rafId = null; }
      setResizingChatPane(false);
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
    };

    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
  }, [chatPaneWidth]);

  const handleTerminalSplitterPointerDown = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startY = event.clientY;
    const startHeight = terminalHeight;
    const minHeight = 120;
    const maxHeight = Math.max(180, window.innerHeight * 0.6);
    setResizingTerminal(true);
    let pendingY = startY;
    let rafId: number | null = null;

    const handlePointerMove = (moveEvent: PointerEvent) => {
      pendingY = moveEvent.clientY;
      if (rafId !== null) return;
      rafId = requestAnimationFrame(() => {
        rafId = null;
        setTerminalHeight(Math.min(maxHeight, Math.max(minHeight, startHeight - (pendingY - startY))));
      });
    };

    const handlePointerUp = () => {
      if (rafId !== null) { cancelAnimationFrame(rafId); rafId = null; }
      setResizingTerminal(false);
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
    };

    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
  }, [terminalHeight]);

  return {
    sidePanelWidth,
    resizingSidePanel,
    chatPaneWidth,
    resizingChatPane,
    sidePanelOpen,
    setSidePanelOpen,
    chatPanelOpen,
    setChatPanelOpen,
    terminalHeight,
    resizingTerminal,
    handleSplitterPointerDown,
    handleChatSplitterPointerDown,
    handleTerminalSplitterPointerDown,
  };
}
