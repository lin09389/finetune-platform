/**
 * antd 主题种子色板 - variables.css 的 TS 镜像层
 *
 * 为什么需要这个文件：
 * antd 的 theme algorithm 需要具体 hex 值来派生 hover/active/disabled 等状态色，
 * 无法直接消费 `var(--accent-primary)` 这样的 CSS 变量字符串。
 * 因此把种子色集中在这里，App.tsx 不再散落 ~60 处 `theme === 'dark' ? A : B` 三元。
 *
 * ⚠️ 同步义务：修改本文件任何色值时，必须同步 `src/styles/variables.css`
 * （明色 `:root` / 暗色 `.dark-theme`），二者语义一一对应。
 */

export interface SeedPalette {
  /** 品牌主色 = --accent-primary */
  accentPrimary: string;
  /** 品牌主色 hover = --accent-secondary */
  accentHover: string;
  /** 成功 = --success */
  success: string;
  /** 警告 = --warning */
  warning: string;
  /** 错误 = --error（antd 种子，允许与语义令牌略有差异） */
  error: string;
  /** 信息 = --info */
  info: string;
  /** 页面底色 = --bg-primary */
  bgBase: string;
  /** 容器底色 = --bg-secondary */
  bgContainer: string;
  /** 浮层底色 = --bg-elevated */
  bgElevated: string;
  /** 主边框 = --border-color */
  border: string;
  /** 次级边框（分割线） */
  borderSecondary: string;
  /** 主文字 = --text-primary */
  textPrimary: string;
  /** 次级文字 = --text-secondary */
  textSecondary: string;
  /** 三级文字 = --text-tertiary */
  textTertiary: string;
  /** 四级文字 = --text-disabled */
  textQuaternary: string;
  /** 反色文字 = --text-inverse */
  textInverse: string;
  /** 输入框底色 */
  inputBg: string;
  /** 行 hover 底色 = --bg-hover */
  hoverBg: string;
  /** Slider 轨道辅助色 */
  sliderBorder: string;
}

export const lightPalette: SeedPalette = {
  accentPrimary: '#b35433',
  accentHover: '#b0562f',
  success: '#65754e',
  warning: '#916909',
  error: '#d64545',
  info: '#5B7B9A',
  bgBase: '#faf9f5',
  bgContainer: '#f5f4ef',
  bgElevated: '#ede9de',
  border: '#dad9d4',
  borderSecondary: '#ede9de',
  textPrimary: '#3d3929',
  textSecondary: '#6e6d68',
  textTertiary: '#9b988c',
  textQuaternary: '#c2c0b6',
  textInverse: '#ffffff',
  inputBg: '#ffffff',
  hoverBg: '#f5f4ef',
  sliderBorder: '#e0a892',
};

export const darkPalette: SeedPalette = {
  accentPrimary: '#d97757',
  accentHover: '#e08d6f',
  success: '#8ca06f',
  warning: '#d4a033',
  error: '#ef4444',
  info: '#7b9bb8',
  bgBase: '#262624',
  bgContainer: '#2c2c2b',
  bgElevated: '#30302e',
  border: '#3e3e38',
  borderSecondary: '#30302e',
  textPrimary: '#f1f1ef',
  textSecondary: '#b7b5a9',
  textTertiary: '#908e84',
  textQuaternary: '#6e6d68',
  textInverse: '#141413',
  inputBg: '#30302e',
  hoverBg: '#3e3e38',
  sliderBorder: '#8a5740',
};

export const getSeedPalette = (mode: 'light' | 'dark'): SeedPalette =>
  mode === 'dark' ? darkPalette : lightPalette;
