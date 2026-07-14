# Phase 3 完成报告 — 视觉一致性

> 执行日期：2026-07-09 · 执行人：Frontend Developer · 模式：Craft

## 验证门禁（全绿）

| 门禁 | 结果 |
|------|------|
| `tsc --noEmit` | ✅ 0 errors |
| `eslint src` | ✅ 0 errors / 69 warnings |
| 冒烟 + XSS + 虚拟化测试 | ✅ 25 passed |
| `npm run build` + bundle-budget | ✅ 5 项预算全通过 |

## 已完成项

### 1. antd ConfigProvider 启用 cssVar + hashed:false（基础层）
- `antdThemeConfig` 加 `cssVar: true` + `hashed: false`。
- antd 现在把设计令牌发射为 CSS 变量（如 `--ant-color-primary`），可被 `variables.css` 覆盖；主题切换不再需要重新生成 antd CSS。
- `hashed:false` 去除类名 hash 后缀，CSS 更小、易调试。

### 2. 玻璃拟态残留清理
- 移除 3 处 `backdrop-filter: none`（ChatContextPanel.module.css ×2、ChatHeader.module.css ×1）——玻璃拟态清零后的冗余声明。

### 3. Tailwind 令牌映射（核验：已完成）
- `tailwind.config.ts` 已将 colors / fontFamily / borderRadius / boxShadow / zIndex 全部映射到 `var(--*)`。无需改动。

## 关键修正：硬编码 hex/px 规模被原报告夸大

原补充报告称"296+277 处硬编码 hex、2611 处任意 px"。**核验后修正**：

| 来源 | 原报告 | 实测（排除令牌定义文件） |
|------|--------|------------------------|
| CSS hex | 296 | **44**（且几乎全是非令牌故意色） |
| TSX hex | 277 | 215（slate/antd-v4 调色板） |

**核验方法**：写 Python 脚本解析 variables.css 令牌值，扫描 CSS 模块找精确匹配。结果：
- `#b35433`（accent-primary）只在 variables.css 出现——**CSS 模块早已用 `var(--accent-primary)`**。
- CSS 模块的 44 个 hex 是：`#fff`/`#333`/`#000`（通用色）、`#e5e7eb`/`#cbd5e1`/`#94a3b8`（Tailwind slate）、`#4f46e5`/`#818cf8`/`#a855f7`（图表 indigo/violet 系列）、`#ec4899`/`#fbbf24`（装饰色）——**全是故意非令牌色**，无安全令牌替换目标。
- TSX 内联 hex 同理是 slate/antd-v4 调色板，替换=改设计，需评审。

**结论**：语义色早已令牌化，原"296 hex"主要是 variables.css 的令牌定义本身 + 非令牌故意色。**无安全的高价值 hex→令牌批量可做**。

## 关于 px 扫除（3008 处）
- 3000+ px 多为组件布局值（padding/margin/width），大量是合法的具体尺寸。
- 替换需逐值映射到最近令牌（var(--space-*)）+ 逐实例设计核对，**非安全批操作**。
- 定位为**持续重构**，不纳入本批。建议：新代码用令牌（已有 Tailwind 映射支持），存量逐步迁移。

## 改动文件（4 个）
- `client/src/App.tsx`（antd cssVar + hashed:false）
- `client/src/components/chat/ChatContextPanel.module.css`（移除 backdrop-filter:none ×2）
- `client/src/components/chat/ChatHeader.module.css`（移除 backdrop-filter:none ×1）

## 浏览器手测建议
- antd 组件（Button/Input/Modal/Select/Table/Tabs）在 light/dark 下视觉与之前一致（cssVar 改变样式发射方式，值不变，预期无视觉差异）。
- 主题切换响应速度（cssVar 后应更快）。

## 下一步
Phase 3（视觉一致性基础）完成。剩余可选：Phase 4（状态/代码治理：拆 chatStore 767 行 + 收敛 11 处散落 fetch + useChatStream 837 行）、Phase 4.5（i18n 决策：删脚手架 or 真做）、Phase 5（SEO/移动端深水区）。
