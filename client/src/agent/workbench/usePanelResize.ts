import { useCallback, useEffect, useRef } from 'react';
import type { CSSProperties, KeyboardEvent as ReactKeyboardEvent, PointerEvent as ReactPointerEvent } from 'react';
import {
  DEFAULT_AGENT_PANEL_LAYOUT,
  MAX_DOCK_WIDTH,
  MAX_SESSION_WIDTH,
  MAX_TERMINAL_HEIGHT,
  MAX_WORKSPACE_SPLIT,
  MIN_DOCK_WIDTH,
  MIN_SESSION_WIDTH,
  MIN_TERMINAL_HEIGHT,
  MIN_WORKSPACE_SPLIT,
  type AgentPanelLayout,
} from '../config/panelLayout';

export type AgentResizeTarget = 'session' | 'dock' | 'terminal' | 'workspace-split';

interface ResizeState {
  type: AgentResizeTarget;
  startX: number;
  startY: number;
  startValue: number;
  containerSize: number;
}

export interface PanelResizeHandlers {
  beginResize: (type: AgentResizeTarget, event: ReactPointerEvent<HTMLDivElement>) => void;
  resizePanel: (event: ReactPointerEvent<HTMLDivElement>) => void;
  endResize: (event: ReactPointerEvent<HTMLDivElement>) => void;
  resizePanelWithKeyboard: (
    type: AgentResizeTarget,
    event: ReactKeyboardEvent<HTMLDivElement>,
  ) => void;
  resetPanelSize: (type: AgentResizeTarget) => void;
}

interface UsePanelResizeArgs {
  panelLayout: AgentPanelLayout;
  setPanelLayout: React.Dispatch<React.SetStateAction<AgentPanelLayout>>;
  rightDockRef: React.RefObject<HTMLElement | null>;
  isDesktop: boolean;
}

/**
 * 把 AgentWorkbenchPage 中四套面板 resize 逻辑（session / dock / terminal /
 * workspace-split）收敛到单一 hook。
 *
 * - 指针拖拽经 rAF 合并写入，避免高频 setState
 * - 键盘 Arrow 调整走 setPanelLayout 直接更新（步长 16，Shift 步长 40）
 * - 双击恢复默认尺寸
 * - 卸载时取消 rAF 并清理 body 上的 data-agent-resizing 标记
 */
export function usePanelResize({
  panelLayout,
  setPanelLayout,
  rightDockRef,
  isDesktop,
}: UsePanelResizeArgs): PanelResizeHandlers {
  const resizeFrameRef = useRef<number | null>(null);
  const pendingResizeRef = useRef<Partial<AgentPanelLayout> | null>(null);
  const resizeStateRef = useRef<ResizeState | null>(null);

  useEffect(() => () => {
    if (resizeFrameRef.current !== null) cancelAnimationFrame(resizeFrameRef.current);
    delete document.body.dataset.agentResizing;
  }, []);

  const scheduleResize = useCallback((next: Partial<AgentPanelLayout>) => {
    pendingResizeRef.current = { ...pendingResizeRef.current, ...next };
    if (resizeFrameRef.current !== null) return;
    resizeFrameRef.current = requestAnimationFrame(() => {
      const pending = pendingResizeRef.current;
      resizeFrameRef.current = null;
      pendingResizeRef.current = null;
      if (pending) setPanelLayout((current) => ({ ...current, ...pending }));
    });
  }, [setPanelLayout]);

  const beginResize = useCallback((type: AgentResizeTarget, event: ReactPointerEvent<HTMLDivElement>) => {
    if (!isDesktop) return;
    const startValue = type === 'session'
      ? panelLayout.sessionWidth
      : type === 'dock'
        ? panelLayout.dockWidth
        : type === 'terminal'
          ? panelLayout.terminalHeight
          : panelLayout.workspaceSplit;
    event.currentTarget.setPointerCapture(event.pointerId);
    resizeStateRef.current = {
      type,
      startX: event.clientX,
      startY: event.clientY,
      startValue,
      containerSize: rightDockRef.current?.clientHeight || 1,
    };
    event.currentTarget.dataset.dragging = 'true';
    document.body.dataset.agentResizing = type;
  }, [isDesktop, panelLayout, rightDockRef]);

  const resizePanel = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    const resize = resizeStateRef.current;
    if (!resize) return;
    switch (resize.type) {
      case 'session': {
        const visibleDockWidth = panelLayout.workspaceOpen || panelLayout.taskCenterOpen
          ? Math.max(MIN_DOCK_WIDTH, Math.min(panelLayout.dockWidth, window.innerWidth * 0.46))
          : 0;
        const maximum = Math.min(
          MAX_SESSION_WIDTH,
          Math.max(MIN_SESSION_WIDTH, window.innerWidth - visibleDockWidth - 320),
        );
        const sessionWidth = Math.min(
          maximum,
          Math.max(MIN_SESSION_WIDTH, resize.startValue + event.clientX - resize.startX),
        );
        scheduleResize({ sessionWidth: Math.round(sessionWidth) });
        break;
      }
      case 'dock': {
        const maximum = Math.min(
          MAX_DOCK_WIDTH,
          Math.max(MIN_DOCK_WIDTH, window.innerWidth - panelLayout.sessionWidth - 320),
        );
        const dockWidth = Math.min(
          maximum,
          Math.max(MIN_DOCK_WIDTH, resize.startValue + resize.startX - event.clientX),
        );
        scheduleResize({ dockWidth: Math.round(dockWidth) });
        break;
      }
      case 'terminal': {
        const terminalHeight = Math.min(
          MAX_TERMINAL_HEIGHT,
          Math.max(MIN_TERMINAL_HEIGHT, resize.startValue + resize.startY - event.clientY),
        );
        scheduleResize({ terminalHeight: Math.round(terminalHeight) });
        break;
      }
      case 'workspace-split': {
        const workspaceSplit = Math.min(
          MAX_WORKSPACE_SPLIT,
          Math.max(
            MIN_WORKSPACE_SPLIT,
            resize.startValue + ((event.clientY - resize.startY) / resize.containerSize) * 100,
          ),
        );
        scheduleResize({ workspaceSplit: Math.round(workspaceSplit) });
        break;
      }
    }
  }, [panelLayout, scheduleResize]);

  const endResize = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    if (!resizeStateRef.current) return;
    resizeStateRef.current = null;
    delete event.currentTarget.dataset.dragging;
    delete document.body.dataset.agentResizing;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }, []);

  const resizePanelWithKeyboard = useCallback((
    type: AgentResizeTarget,
    event: ReactKeyboardEvent<HTMLDivElement>,
  ) => {
    const step = event.shiftKey ? 40 : 16;
    if (type === 'session' && (event.key === 'ArrowLeft' || event.key === 'ArrowRight')) {
      event.preventDefault();
      const direction = event.key === 'ArrowRight' ? 1 : -1;
      setPanelLayout((current) => {
        const visibleDockWidth = current.workspaceOpen || current.taskCenterOpen
          ? Math.max(MIN_DOCK_WIDTH, Math.min(current.dockWidth, window.innerWidth * 0.46))
          : 0;
        const maximum = Math.min(
          MAX_SESSION_WIDTH,
          Math.max(MIN_SESSION_WIDTH, window.innerWidth - visibleDockWidth - 320),
        );
        return {
          ...current,
          sessionWidth: Math.round(Math.min(
            maximum,
            Math.max(MIN_SESSION_WIDTH, current.sessionWidth + direction * step),
          )),
        };
      });
    }
    if (type === 'dock' && (event.key === 'ArrowLeft' || event.key === 'ArrowRight')) {
      event.preventDefault();
      const direction = event.key === 'ArrowLeft' ? 1 : -1;
      setPanelLayout((current) => {
        const maximum = Math.min(
          MAX_DOCK_WIDTH,
          Math.max(MIN_DOCK_WIDTH, window.innerWidth - current.sessionWidth - 320),
        );
        return {
          ...current,
          dockWidth: Math.round(Math.min(
            maximum,
            Math.max(MIN_DOCK_WIDTH, current.dockWidth + direction * step),
          )),
        };
      });
    }
    if (type === 'terminal' && (event.key === 'ArrowUp' || event.key === 'ArrowDown')) {
      event.preventDefault();
      const direction = event.key === 'ArrowUp' ? 1 : -1;
      setPanelLayout((current) => ({
        ...current,
        terminalHeight: Math.round(Math.min(
          MAX_TERMINAL_HEIGHT,
          Math.max(MIN_TERMINAL_HEIGHT, current.terminalHeight + direction * step),
        )),
      }));
    }
    if (type === 'workspace-split' && (event.key === 'ArrowUp' || event.key === 'ArrowDown')) {
      event.preventDefault();
      const splitStep = event.shiftKey ? 10 : 2;
      const direction = event.key === 'ArrowDown' ? 1 : -1;
      setPanelLayout((current) => ({
        ...current,
        workspaceSplit: Math.min(
          MAX_WORKSPACE_SPLIT,
          Math.max(MIN_WORKSPACE_SPLIT, current.workspaceSplit + direction * splitStep),
        ),
      }));
    }
  }, [setPanelLayout]);

  const resetPanelSize = useCallback((type: AgentResizeTarget) => {
    setPanelLayout((current) => ({
      ...current,
      ...(type === 'session' && { sessionWidth: DEFAULT_AGENT_PANEL_LAYOUT.sessionWidth }),
      ...(type === 'dock' && { dockWidth: DEFAULT_AGENT_PANEL_LAYOUT.dockWidth }),
      ...(type === 'terminal' && { terminalHeight: DEFAULT_AGENT_PANEL_LAYOUT.terminalHeight }),
      ...(type === 'workspace-split' && {
        workspaceSplit: DEFAULT_AGENT_PANEL_LAYOUT.workspaceSplit,
      }),
    }));
  }, [setPanelLayout]);

  return {
    beginResize,
    resizePanel,
    endResize,
    resizePanelWithKeyboard,
    resetPanelSize,
  };
}

/**
 * 由 panelLayout 派生注入到 mainSurface 的 CSS 变量样式。
 */
export function buildPanelSurfaceStyle(panelLayout: AgentPanelLayout): CSSProperties {
  return {
    '--agent-dock-width': `${panelLayout.dockWidth}px`,
    '--agent-terminal-height': `${panelLayout.terminalHeight}px`,
    '--agent-workspace-split': `${panelLayout.workspaceSplit}%`,
  } as CSSProperties;
}
