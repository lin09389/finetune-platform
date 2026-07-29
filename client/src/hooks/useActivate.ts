import type { KeyboardEvent } from 'react';

/**
 * useActivate: 为非原生按钮的可点击元素（div/卡片）补齐键盘可访问性。
 *
 * 返回可直接 spread 到元素上的 props：role/tabIndex/onClick/onKeyDown，
 * Enter 与空格键均触发 action（与原生 button 行为一致）。
 *
 * 用法：
 *   <div {...useActivate(() => navigate('/xx'))} aria-label="..." />
 */
export function useActivate(action: () => void) {
  return {
    role: 'button' as const,
    tabIndex: 0,
    onClick: action,
    onKeyDown: (event: KeyboardEvent) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        action();
      }
    },
  };
}

export default useActivate;
