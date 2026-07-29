import type { ReactNode } from 'react';

/** 工程闭环节点 */
export interface ChainStep {
  title: string;
  value: string;
  ready: boolean;
  action: () => void;
}

/** 下一步建议 */
export interface Suggestion {
  title: string;
  desc: string;
  type: 'warning' | 'info' | 'success';
  action?: () => void;
  buttonText?: string;
}

/** 主要操作入口 */
export interface MainAction {
  title: string;
  icon: ReactNode;
  color: string;
  onClick: () => void;
  description: string;
}
