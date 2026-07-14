# Phase 2 完成报告 — 首屏性能

> 执行日期：2026-07-08 → 07-09 · 执行人：Frontend Developer · 模式：Craft
> 依据：`docs/frontend-review-2026-07-08-supplement.md` 的 Phase 2

## 验证门禁（全绿）

| 门禁 | 结果 |
|------|------|
| `tsc --noEmit` | ✅ 0 errors |
| `eslint src` | ✅ 0 errors / 69 warnings（全为 `no-explicit-any`） |
| 冒烟 + XSS 测试 | ✅ 24 passed |
| `npm run build` + bundle-budget | ✅ built in 13.32s，5 项预算全通过 |

## 首屏体积对比（Phase 2 前后）

| 指标 | Phase 1 后 | Phase 2 后 |
|------|-----------|-----------|
| `dist/index.html` modulepreload | vendor-ui(407.7) + vendor-markdown(48.0) | vendor-ui(363.1) + vendor-react(49.6) |
| **vendor-markdown 首屏预载** | 48.0 KiB gz ❌ | **0（已移除）** ✅ |
| vendor-ui | 407.7 KiB gz | 363.1 KiB gz（react 移出） |
| 首屏预载总量 | ~456 KiB gz | ~413 KiB gz（**净省 ~43 KiB gz**） |

## 已完成项

### 1. vendor-react 分包规则（头条修复）
- **根因**（Phase 1 已确认）：`vite.config.ts` manualChunks 无 react 规则 → Rollup 把 `react/jsx-runtime` 塞进 vendor-markdown → 入口为取 JSX 运行时被迫 modulepreload vendor-markdown（48 KiB gz）。
- **修复**：manualChunks 在所有规则前加 `if (id.includes('/react/') || id.includes('/react-dom/') || id.includes('/scheduler/')) return 'vendor-react'`。
- **验证**：`dist/index.html` 不再 modulepreload vendor-markdown；新增 vendor-react chunk。
- **预算门禁扩展**：`check-bundle-budget.mjs` 新增 vendor-react(≤60) 与 vendor-charts(≤120) 预算防回归。

### 2. ConfigProvider theme useMemo
- App.tsx 的 antd theme 对象原每次 AppContent 重渲染都重建（后端状态/路由变化时），强制 antd 重算主题。
- 抽为 `antdThemeConfig = useMemo(() => ({...}), [theme])`，仅随色彩模式变化。

### 3. useStreamResponse 资源泄漏修复
- `useStreamResponse.ts` 订阅 effect 的 cleanup 仅退订监听器，未停止流/定时器 → 卸载后 StreamManager 的 heartbeat / partialSave / chunkTimeout 定时器与 fetch reader 仍活跃。
- 新增独立 unmount effect：`return () => streamManager.stop()`。

### 4. img lazy + 防溢出（按需范围）
- **核实后修正**：3 处 img 中，ImageUpload 是 Modal 内按需预览、Sidebar logo 是 259B 常驻 SVG——两者 lazy 无意义，跳过。
- 仅 CUAControl 截图（页内大图）补 `loading="lazy"` + `maxWidth/maxHeight/height:auto` 防溢出。

### 5. index.html 内联首屏骨架
- 注入内联 `<style>` + `#root` 内骨架（FT logo + "Finetune Platform"/"正在加载工作台..."，带 pulse 动画，含 dark 媒体查询）。
- React 挂载时自动替换，消除 JS 加载前白屏。

### 6. 字体非阻塞加载
- Google Fonts `<link rel="stylesheet">` 原为渲染阻塞。
- 改 `media="print" onload="this.media='all'"` 非阻塞加载（display=swap 保证文字可见）。
- **未裁剪字重**：斜体在 3 处使用，且浏览器只下载实际引用字重——裁剪 URL 收益有限且回归风险高，保留。

## 延后项（含理由，需独立专项）
- **聊天列表虚拟化（L 级）**：`ChatNew.tsx` 全量 map 渲染长对话性能差。但虚拟化需处理流式追加、自动滚动、变高消息，风险高，需独立 PR + 长对话手测，不宜混入本批。
- **流式 useDeferredValue**：与聊天虚拟化同域，需专项验证流式体验，一并延后。
- **PWA（vite-plugin-pwa）**：本应用主为本地/桌面（localhost 后端 + Electron），PWA 缓存对本地工具价值有限，且开发期有 stale-cache 风险，延后。
- **antd 按需 import 核查**：antd 5 已 ESM tree-shake，进一步收益需逐组件验证，优先级低。

## 改动文件清单（7 个）
- `client/vite.config.ts`（vendor-react 分包规则）
- `client/scripts/check-bundle-budget.mjs`（新增 2 项预算）
- `client/src/App.tsx`（theme useMemo）
- `client/src/hooks/useStreamResponse.ts`（unmount stop）
- `client/src/pages/CUAControl.tsx`（img lazy + 尺寸）
- `client/index.html`（内联骨架 + 字体非阻塞）

## 下一步
Phase 2（首屏性能核心项）全绿。剩余 Phase 2 延后项（聊天虚拟化 + useDeferredValue）建议作为独立专项。后续可进入 Phase 3（视觉一致性：antd cssVar + Tailwind 令牌映射 + 硬编码 hex/px 替换）或先做聊天虚拟化专项。
