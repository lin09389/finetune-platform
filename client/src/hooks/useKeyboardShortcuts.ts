/**
 * 键盘快捷键 Hook
 */
import { useCallback, useEffect, useRef } from 'react';

type KeyHandler = () => void;

interface ShortcutConfig {
  key: string;
  ctrl?: boolean;
  shift?: boolean;
  alt?: boolean;
  meta?: boolean;
  handler: KeyHandler;
  description?: string;
  preventDefault?: boolean;
}

export function useKeyboardShortcuts(shortcuts: ShortcutConfig[]): void {
  const shortcutsRef = useRef(shortcuts);
  shortcutsRef.current = shortcuts;

  const handleKeyDown = useCallback((event: KeyboardEvent) => {
    const { key, ctrlKey, shiftKey, altKey, metaKey } = event;

    for (const shortcut of shortcutsRef.current) {
      const keyMatch = shortcut.key.toLowerCase() === key.toLowerCase();
      const ctrlMatch = shortcut.ctrl ? ctrlKey : !ctrlKey;
      const shiftMatch = shortcut.shift ? shiftKey : !shiftKey;
      const altMatch = shortcut.alt ? altKey : !altKey;
      const metaMatch = shortcut.meta ? metaKey : !metaKey;

      if (keyMatch && ctrlMatch && shiftMatch && altMatch && metaMatch) {
        if (shortcut.preventDefault !== false) {
          event.preventDefault();
        }
        shortcut.handler();
        return;
      }
    }
  }, []);

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [handleKeyDown]);
}

export function useChatShortcuts(handlers: {
  onNewSession?: () => void;
  onOpenHistory?: () => void;
  onOpenMemory?: () => void;
  onStop?: () => void;
  onSend?: () => void;
  onClear?: () => void;
}): void {
  const shortcuts: ShortcutConfig[] = [
    {
      key: 'n',
      ctrl: true,
      handler: handlers.onNewSession || (() => {}),
      description: '新建会话',
    },
    {
      key: 'h',
      ctrl: true,
      handler: handlers.onOpenHistory || (() => {}),
      description: '打开历史',
    },
    {
      key: 'k',
      ctrl: true,
      handler: handlers.onOpenMemory || (() => {}),
      description: '打开记忆',
    },
    {
      key: 'Escape',
      handler: handlers.onStop || (() => {}),
      description: '停止',
    },
    {
      key: 'Enter',
      ctrl: true,
      handler: handlers.onSend || (() => {}),
      description: '发送',
    },
    {
      key: 'Delete',
      ctrl: true,
      shift: true,
      handler: handlers.onClear || (() => {}),
      description: '清空会话',
    },
  ];

  useKeyboardShortcuts(shortcuts);
}

export const SHORTCUT_HELP = [
  { key: 'Ctrl+N', description: '新建会话' },
  { key: 'Ctrl+H', description: '打开历史' },
  { key: 'Ctrl+K', description: '打开记忆' },
  { key: 'Ctrl+Enter', description: '发送消息' },
  { key: 'Escape', description: '停止生成' },
  { key: 'Ctrl+Shift+Delete', description: '清空会话' },
];
