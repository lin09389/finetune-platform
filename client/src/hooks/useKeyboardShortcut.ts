import { useCallback, useEffect, useRef } from 'react';

interface ShortcutOptions {
  ctrl?: boolean;
  meta?: boolean;
  shift?: boolean;
  alt?: boolean;
  preventDefault?: boolean;
  stopPropagation?: boolean;
}

/**
 * useKeyboardShortcut - 键盘快捷键 Hook
 * @param key 按键（如 'k', 'Enter', 'Escape'）
 * @param callback 回调函数
 * @param options 选项
 *
 * 使用场景：
 * - Ctrl+K 打开搜索
 * - Ctrl+S 保存
 * - Escape 关闭弹窗
 */
export function useKeyboardShortcut(
  key: string,
  callback: () => void,
  options: ShortcutOptions = {},
) {
  const {
    ctrl = false,
    meta = false,
    shift = false,
    alt = false,
    preventDefault = true,
    stopPropagation = false,
  } = options;

  const callbackRef = useRef(callback);
  callbackRef.current = callback;

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const keyMatch = event.key.toLowerCase() === key.toLowerCase();
      const ctrlMatch = ctrl === event.ctrlKey;
      const metaMatch = meta === event.metaKey;
      const shiftMatch = shift === event.shiftKey;
      const altMatch = alt === event.altKey;

      if (keyMatch && ctrlMatch && metaMatch && shiftMatch && altMatch) {
        if (preventDefault) {
          event.preventDefault();
        }
        if (stopPropagation) {
          event.stopPropagation();
        }
        callbackRef.current();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [key, ctrl, meta, shift, alt, preventDefault, stopPropagation]);
}

/**
 * useGlobalShortcuts - 全局快捷键 Hook
 * @param shortcuts 快捷键配置数组
 *
 * 使用场景：
 * - 配置多个快捷键
 */
export function useGlobalShortcuts(
  shortcuts: Array<{
    key: string;
    callback: () => void;
    options?: ShortcutOptions;
  }>,
) {
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      shortcuts.forEach(({ key, callback, options = {} }) => {
        const {
          ctrl = false,
          meta = false,
          shift = false,
          alt = false,
          preventDefault = true,
          stopPropagation = false,
        } = options;

        const keyMatch = event.key.toLowerCase() === key.toLowerCase();
        const ctrlMatch = ctrl === event.ctrlKey;
        const metaMatch = meta === event.metaKey;
        const shiftMatch = shift === event.shiftKey;
        const altMatch = alt === event.altKey;

        if (keyMatch && ctrlMatch && metaMatch && shiftMatch && altMatch) {
          if (preventDefault) {
            event.preventDefault();
          }
          if (stopPropagation) {
            event.stopPropagation();
          }
          callback();
        }
      });
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [shortcuts]);
}

/**
 * useEscapeKey - Escape 键 Hook
 * @param callback 回调函数
 * @param enabled 是否启用
 *
 * 使用场景：
 * - 关闭弹窗
 * - 取消操作
 */
export function useEscapeKey(callback: () => void, enabled: boolean = true) {
  useEffect(() => {
    if (!enabled) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        callback();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [callback, enabled]);
}

/**
 * useEnterKey - Enter 键 Hook
 * @param callback 回调函数
 * @param enabled 是否启用
 *
 * 使用场景：
 * - 提交表单
 * - 确认操作
 */
export function useEnterKey(callback: () => void, enabled: boolean = true) {
  useEffect(() => {
    if (!enabled) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        callback();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [callback, enabled]);
}

/**
 * useArrowKeys - 方向键 Hook
 * @param callbacks 方向键回调
 * @param enabled 是否启用
 *
 * 使用场景：
 * - 列表导航
 * - 图片浏览
 */
export function useArrowKeys(
  callbacks: {
    up?: () => void;
    down?: () => void;
    left?: () => void;
    right?: () => void;
  },
  enabled: boolean = true,
) {
  useEffect(() => {
    if (!enabled) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      switch (event.key) {
        case 'ArrowUp':
          event.preventDefault();
          callbacks.up?.();
          break;
        case 'ArrowDown':
          event.preventDefault();
          callbacks.down?.();
          break;
        case 'ArrowLeft':
          event.preventDefault();
          callbacks.left?.();
          break;
        case 'ArrowRight':
          event.preventDefault();
          callbacks.right?.();
          break;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [callbacks, enabled]);
}

/**
 * useFocusTrap - 焦点陷阱 Hook
 * @param containerRef 容器 Ref
 * @param enabled 是否启用
 *
 * 使用场景：
 * - 模态框焦点管理
 * - 抽屉焦点管理
 */
export function useFocusTrap(containerRef: React.RefObject<HTMLElement>, enabled: boolean = true) {
  useEffect(() => {
    if (!enabled || !containerRef.current) return;

    const container = containerRef.current;
    const focusableElements = container.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    );
    const firstElement = focusableElements[0];
    const lastElement = focusableElements[focusableElements.length - 1];

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Tab') return;

      if (event.shiftKey) {
        if (document.activeElement === firstElement) {
          event.preventDefault();
          lastElement?.focus();
        }
      } else {
        if (document.activeElement === lastElement) {
          event.preventDefault();
          firstElement?.focus();
        }
      }
    };

    container.addEventListener('keydown', handleKeyDown);
    firstElement?.focus();

    return () => container.removeEventListener('keydown', handleKeyDown);
  }, [containerRef, enabled]);
}

/**
 * useKeyPress - 按键状态 Hook
 * @param targetKey 目标按键
 * @returns 按键是否被按下
 *
 * 使用场景：
 * - 按住 Shift 多选
 * - 按住 Ctrl 多选
 */
export function useKeyPress(targetKey: string): boolean {
  const [keyPressed, setKeyPressed] = React.useState(false);

  const downHandler = useCallback(
    ({ key }: KeyboardEvent) => {
      if (key === targetKey) {
        setKeyPressed(true);
      }
    },
    [targetKey],
  );

  const upHandler = useCallback(
    ({ key }: KeyboardEvent) => {
      if (key === targetKey) {
        setKeyPressed(false);
      }
    },
    [targetKey],
  );

  useEffect(() => {
    window.addEventListener('keydown', downHandler);
    window.addEventListener('keyup', upHandler);
    return () => {
      window.removeEventListener('keydown', downHandler);
      window.removeEventListener('keyup', upHandler);
    };
  }, [downHandler, upHandler]);

  return keyPressed;
}

// 导入 React
import React from 'react';

export default useKeyboardShortcut;
