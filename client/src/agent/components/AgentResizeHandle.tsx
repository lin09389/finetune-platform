import { type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent } from 'react';
import type { PanelResizeHandlers, AgentResizeTarget } from '../workbench/usePanelResize';

interface AgentResizeHandleProps {
  target: AgentResizeTarget;
  /** aria-valuenow 当前值 */
  valueNow: number;
  /** aria-valuemin */
  valueMin: number;
  /** aria-valuemax */
  valueMax: number;
  /** 桌面端可交互；移动端隐藏并退出 tab 顺序 */
  isDesktop: boolean;
  /** 该 handle 是否需要渲染（如 workspace-split 仅在双面板都展开时显示） */
  visible?: boolean;
  resize: PanelResizeHandlers;
  className: string | undefined;
}

const RESIZE_META: Record<AgentResizeTarget, { label: string; orientation: 'vertical' | 'horizontal'; title: string }> = {
  session: { label: '调整会话栏宽度', orientation: 'vertical', title: '拖动调整，双击恢复默认宽度' },
  dock: { label: '调整工作区宽度', orientation: 'vertical', title: '拖动调整，双击恢复默认宽度' },
  terminal: { label: '调整终端高度', orientation: 'horizontal', title: '拖动调整，双击恢复默认高度' },
  'workspace-split': { label: '调整工作区与任务中心比例', orientation: 'horizontal', title: '拖动调整，双击恢复默认比例' },
};

/**
 * 面板 resize 分隔条。把 Page 里四处逐行重复的 separator 收敛为单一组件，
 * 保留 role/aria-valuenow/pointer capture/键盘/双击恢复的全部 a11y 行为。
 */
export default function AgentResizeHandle({
  target,
  valueNow,
  valueMin,
  valueMax,
  isDesktop,
  visible = true,
  resize,
  className,
}: AgentResizeHandleProps) {
  if (!visible) return null;
  const meta = RESIZE_META[target];
  return (
    <div
      className={className}
      role="separator"
      aria-label={meta.label}
      aria-orientation={meta.orientation}
      aria-valuemin={valueMin}
      aria-valuemax={valueMax}
      aria-valuenow={valueNow}
      tabIndex={isDesktop ? 0 : -1}
      title={meta.title}
      onDoubleClick={() => resize.resetPanelSize(target)}
      onKeyDown={(event: ReactKeyboardEvent<HTMLDivElement>) => resize.resizePanelWithKeyboard(target, event)}
      onPointerDown={(event: ReactPointerEvent<HTMLDivElement>) => resize.beginResize(target, event)}
      onPointerMove={resize.resizePanel}
      onPointerUp={resize.endResize}
      onPointerCancel={resize.endResize}
    />
  );
}
