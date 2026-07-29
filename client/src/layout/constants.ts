/**
 * 布局常量单一事实源
 *
 * Sidebar 是浮动式（fixed + 四周留白），主内容区的 margin-left 必须等于
 * 「侧栏宽度 + 两侧留白」。此前 App.tsx 里的 104 / 272 是魔数，与
 * Sidebar.tsx 的 72 / 240 各写一份，改宽度时容易漂移，故收口到这里。
 */

/** 侧栏展开宽度 */
export const SIDEBAR_WIDTH = 240;

/** 侧栏收起宽度 */
export const SIDEBAR_COLLAPSED_WIDTH = 72;

/** 浮动侧栏与视口边缘的间距（左/上/下各留一份） */
export const SIDEBAR_FLOAT_OFFSET = 16;

/** 主内容区左边距 = 侧栏宽度 + 左右两侧留白 */
export const getContentMarginLeft = (collapsed: boolean): number =>
  (collapsed ? SIDEBAR_COLLAPSED_WIDTH : SIDEBAR_WIDTH) + SIDEBAR_FLOAT_OFFSET * 2;

/** 移动端抽屉导航宽度 */
export const MOBILE_DRAWER_WIDTH = 280;

/** 移动端底部导航栏高度（不含 safe-area 内边距） */
export const MOBILE_BOTTOM_NAV_HEIGHT = 56;
