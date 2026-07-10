# 前端审查补充：计划合理性审计与漏点补遗

> 对象：`client/` · 日期：2026-07-08 · 性质：对首版报告 `frontend-review-2026-07-08.md` 的二次深度校验
> 结论先行：**首版方向正确，但有 1 处修复假设被证伪、2 处方案技术细节缺失、6 个维度完全漏掉。** 本文档给出修正与补遗。

---

## 一、原计划合理性审计

### ❌ 1. vendor-markdown 预载修复——假设被证伪（必须修正）
- **原计划写**：「排查 react-markdown 为何进入入口静态图，将其移出 manualChunks」。
- **实测根因（已确认）**：源码中仅 `ChatMessage.tsx:16`、`AgentMarkdownRenderer.tsx:2`、`ThinkingProcess.tsx:3` 静态导入 react-markdown，**三者全在 `lazy()` 路由之后，不存在从入口到 react-markdown 的静态导入链**。真正原因是 `vite.config.ts:35` 的 `manualChunks` 没有 react 匹配规则 → Rollup 默认算法把 `react/jsx-runtime` **塞进了 vendor-markdown chunk** → 入口为获取 JSX 运行时必须静态 import vendor-markdown → Vite 生成 modulepreload。
- **正确修复**：在 manualChunks 中 react-markdown 规则**之前**加 `if (id.includes('/react/') || id.includes('react-dom') || id.includes('react-jsx-runtime')) return 'vendor-react'`，或对所有未匹配 node_modules 加 `return 'vendor'` 兜底。**这是 1 行配置改动（S），原计划把它当成"排查"是误判。**

### ⚠️ 2. antd 令牌统一方案——技术细节缺失
- **原计划写**：「用令牌驱动 ConfigProvider 颜色，避免双份硬编码」。
- **实测**：`App.tsx:278-361` 的 ConfigProvider **未启用 `cssVar: true`**（antd v5 特性），意味着无法直接用 CSS 变量覆盖 antd token；且 `theme={{...}}` 对象**每次渲染都重建**（未 `useMemo`），导致 antd 每次 AppContent 重渲染都重新处理主题。
- **修正方案**：① `useMemo` 包裹 theme 对象；② 启用 `cssVar: true` 让 antd token 落地为 CSS 变量；③ 再让 `variables.css` 与 antd token 共享同一来源。原计划把"令牌统一"当一句话带过，实际是 3 步。

### ⚠️ 3. 删除 `src/index.css`——需先验证导入
- 首版认定 `src/index.css`（34KB，Inter/Outfit 体系）是死代码。实测 `main.tsx:7` 导入的是 `./styles/index.css`（含 @tailwind），**不是** `src/index.css`。删除前必须 grep 确认无任何 `import.*index\.css` 指向根目录那份，避免误删。**加一道验证步骤。**

### ⚠️ 4. Phase 1 对比度修复 与 Phase 3 hex 替换 存在依赖
- 对比度修复（Phase 1）若在 token 层（`variables.css`）改值，Phase 3 再把硬编码 hex 映射到 token 时自动继承正确对比度——**顺序正确**，但需明确「对比度一律在 token 层修，不在组件内打补丁」，否则两阶段会重复劳动甚至冲突。**补一条约束。**

### ⚠️ 5. 缺少验证门禁
- 原计划只提了 Lighthouse + bundle budget。漏掉：① **axe-core 自动化扫描**（`@storybook/addon-a11y` 已装，可在 Storybook 跑 a11y 检查）；② **`npm audit`** 依赖漏洞；③ TrainingDashboard XSS 修复的回归用例。**补进各阶段验收。**

### ⚠️ 6. 工作量误判
- **i18n** 是首版完全没提的隐藏大坑（130 文件中文硬编码 + 装饰性 i18n 系统），不应归入任何现有阶段，需独立决策。
- **聊天列表虚拟化**是 L 级重构（改聊天渲染方式），原计划 Phase 2 未单列，风险被低估。

---

## 二、漏掉的优化维度与点

### 🔴 A. 安全（首版完全未覆盖——新增维度）

| 级别 | 问题 | 证据 | 修复 |
|------|------|------|------|
| **High** | 训练日志 XSS：`dangerouslySetInnerHTML` 注入未转义 HTML | `TrainingDashboard.tsx:210`，`highlightLog()`(`:66-79`) 仅做 `.replace()` 注 `<span>`，未先 HTML 转义；若日志回显数据集名/路径含 `<img onerror>` 即执行 | `highlightLog` 开头先 `& < >` 转义再做标签替换 |
| Medium | 无 CSP | `index.html` 无 `http-equiv` CSP，vite.config 无 header 配置 | 加 `<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; ...">` |
| Medium | API key 持久化到 localStorage | `chatStore.ts:205` persist（name `'chat-storage'`）持久化 `cloudConfig`，其 `config.api_key?: string`(`:141`) 若被赋真实 key 则 XSS 可窃取 | persist `partialize` 中排除 `cloudConfig.config.api_key` |
| Low | 后端地址泄露控制台 | `api.ts:18` `console.log('[API] Base URL:', ...)` | 删除 |
| 架构 | 全应用无认证机制 | axios 拦截器无 Authorization 头，无 httpOnly cookie/JWT | 架构决策，需明确是否需要 |

**Markdown 管道本身安全**：`ChatMessage.tsx:440,466` 的 `rehype-raw + rehype-sanitize`（自定义 schema 基于 defaultSchema，顺序正确）当前安全；`AgentMarkdownRenderer.tsx:70` 无 rehype-raw（react-markdown v10 默认转义）安全但脆弱。生产 sourcemap 默认关闭（安全）。

### 🟠 B. 性能补遗（首版漏的点）

1. **聊天消息列表未虚拟化（重要）**：`ChatNew.tsx:157` 用 `messages.map` 全量渲染，每条含 react-markdown+katex+highlight.js。长对话性能崩塌。`react-virtuoso` 已是依赖却只用于 `AgentRunTimeline.tsx:689`。→ 用 Virtuoso 改造聊天列表（L 级，需处理流式追加+自动滚动+变高消息）。
2. **useStreamResponse 资源泄漏**：`useStreamResponse.ts` 的 StreamManager heartbeat/chunkTimeout/partialSave 定时器与 fetch reader 在组件卸载后仍活跃（cleanup 仅退订监听器 `:207-209`，未 `streamManager.stop()`）。→ effect cleanup 加 `streamManager.stop()`。
3. **ConfigProvider theme 每次渲染重建**：`App.tsx:278-360` theme 对象未 memo。→ `useMemo`。
4. **字体负载过重**：`index.html:10` 一次加载 4 字族 **18 个变体**（Newsreader 6 / Poppins 4 / Lora 5 / Geist Mono 3，估算 270–720KB woff2），但 `App.tsx:298` ConfigProvider 只用 Poppins。→ 审计 Newsreader/Lora/Geist Mono 实际 CSS 引用，删未用族；保留族减到必要字重；自托管+preload 关键字重。
5. **图片缺 lazy/尺寸**：3 处 `<img>`（`ImageUpload.tsx:249`、`CUAControl.tsx:330`、`Sidebar.tsx:223`）无 `loading="lazy"`、无 width/height（CLS）。→ 补属性。
6. **dayjs 疑似冗余直接依赖**：src 中零导入（antd 5 自带 dayjs）。→ 移除直接依赖。
7. **流式渲染未用并发特性**：聊天流式每个 token 触发整列表同步重渲染，无 `useTransition`/`useDeferredValue`。→ 流式 token 更新用 `useDeferredValue` 或 `startTransition`。

### 🟠 C. i18n（首版完全未覆盖——新增维度，决策项）

- **现状**：`src/i18n/index.ts` 是自研系统（zustand+persist），但**全仓零消费**（无任何组件 import/调用），`t()` 用非响应式 `useI18n.getState()` 即便接入也不重渲染，无语言切换 UI（`MobileNav/index.tsx:310` 文案提到"语言"但无入口）。
- **中文硬编码遍布**：约 **130 个 ts/tsx/css 文件**含中文字面量（`routeTitles`、所有 Form label、通知文案等）。
- **决策**：二选一——① 真做：迁 react-i18next，抽 130 文件文案到资源文件，加切换器（XL，跨多阶段）；② 明确不做：删除 `src/i18n` 脚手架以免误导（S）。**建议先决策再排期，不要悬而未决。**

### 🟠 D. 移动端深水区（首版只提了触控区）

1. **iOS 输入框聚焦缩放**：antd `fontSize:14`（`App.tsx:299`）+ `--text-base` 下限 15px，均 <16px，iOS 聚焦自动放大。→ `@media(max-width:768px){ input,textarea,.ant-input{font-size:16px} }`。
2. **安全区未覆盖**：`index.html:5` viewport 无 `viewport-fit=cover` → `env(safe-area-inset-*)` 全为 0；仅 `MobileNav/index.tsx:400` 用了 bottom，**top/left/right 未处理**，刘海/灵动岛遮挡。→ 加 `viewport-fit=cover` + 四向 safe-area。
3. **100vh 移动地址栏问题**：`100vh` 出现 **20+ 处**（`App.tsx:74/370/381/399/400`、`index.css` 多处、`SharedChat.tsx` 等），**全仓无 `dvh/svh`**。→ 改 `100dvh`（回退 `100vh`）。

### 🟠 E. 可访问性补遗（首版只覆盖了导航+对比度）

1. **标题层级混乱**：多数页面**无 h1**（Dashboard、Deployment、History、MemoryPage、MCPTools、GatewayPage 等从 h2 起，`HeaderBar.tsx:103`）；`ChatMessage.tsx:307` 从 markdown 渲染 `<h1>` → 聊天页可能多 h1。→ 每页唯一 h1，ChatMessage markdown 降级 h1→h2。
2. **9+ 图标按钮无 aria-label**：`Deployment.tsx:275`、`History.tsx:1021`、`Evaluation.tsx:554`、`ChatBranchManager.tsx:296`、`chat/ChatHeader.tsx:168`、`SwiftChecker.tsx:75`、`UserGuide.tsx:103,203`、`ModelManager.tsx:324`。读屏静音。→ 补 `aria-label`/`title`。
3. **12-15+ 可点击 div/motion.div 缺语义**（除已知导航外）：`DatasetManager`、`HeartbeatPage`、`MCPTools`、`MotionWrapper` 等 `<div onClick>` 无 role/tabIndex/onKeyDown。→ 补 `role="button" tabIndex={0} onKeyDown`。
4. **antd cssVar 未启用**：影响主题与令牌统一策略（见合理性#2）。

### 🟢 F. 配置/依赖
- 无 `browserslist`（现代应用可接受，无需 polyfill，记录即可）。
- Storybook 资源 `addon-library.png` 467KB 在 `src/stories/assets/`——需确认 Storybook 构建独立、不进生产 bundle（Vite tree-shaking 通常排除未引用资源，但建议验证 `dist` 不含该图）。

---

## 三、修正后的路线图

> 在首版 6 阶段基础上：**插入安全阶段、前置 i18n 决策、修正 vendor-markdown 修复、补全验证门禁。**

### Phase 0 — 死代码/基础收口 + 安全快修（S，低风险）
- [ ] 验证后删除 `src/index.css`（先 grep 确认无导入）
- [ ] 统一 ESLint 配置（删 `.eslintrc.yml`/`package.json.eslintConfig`，先确认 CI 未引用），开 `no-console:error`
- [ ] 清理 11 处 `console.log`（含 `api.ts:18`）
- [ ] **【新】TrainingDashboard XSS 修复**（`highlightLog` 加转义）+ 回归用例
- [ ] **【新】chatStore persist partialize 排除 `cloudConfig.config.api_key`**
- [ ] `index.html` 补 `meta description`/`theme-color`/`viewport-fit=cover`；生成 `robots.txt`
- [ ] **【新】移除疑似冗余 `dayjs` 直接依赖**（确认 antd 自带满足）
- [ ] 更新 `design-tokens.md`

### Phase 1 — 可访问性硬伤（M，含首版+补遗）
- [ ] 导航菜单项语义化 + 外壳地标 role（首版）
- [ ] 对比度在 **token 层** 修正（`variables.css`），约束"组件内不打补丁"
- [ ] **【新】9+ 图标按钮补 aria-label**
- [ ] **【新】12-15+ 可点击 div 补 role/tabIndex/onKeyDown**
- [ ] **【新】每页唯一 h1；ChatMessage markdown h1→h2**
- [ ] 聊天/训练进度 aria-live（首版）
- [ ] 路由切换焦点移动 + 404 路由 + ErrorBoundary componentDidCatch（首版）
- [ ] **验收：axe-core 扫描 0 critical**

### Phase 2 — 首屏性能（M–L，修正后）
- [ ] **【修正】manualChunks 加 `vendor-react` 规则**（1 行，根治 vendor-markdown 误预载）
- [ ] antd 按需 import + 图标按需（首版）
- [ ] **【新】ConfigProvider theme `useMemo`**
- [ ] **【新】字体精简**：审计 4 族实际引用，删未用，减字重，自托管+preload
- [ ] **【新】`useStreamResponse` cleanup 加 `streamManager.stop()`**
- [ ] **【新】3 处 `<img>` 补 `loading="lazy"`+width/height**
- [ ] 引入 `vite-plugin-pwa` + index.html 内联骨架（首版）
- [ ] **【新，L 级单列】聊天列表 Virtuoso 虚拟化**（处理流式追加/自动滚动/变高）
- [ ] **【新】流式 token 用 `useDeferredValue`**
- [ ] **验收：Lighthouse TBT/INP + bundle budget 覆盖 entry/vendor-react/vendor-charts**

### Phase 3 — 视觉一致性（M–L，修正后）
- [ ] **【修正】antd theme 启用 `cssVar: true`**，令牌单一来源
- [ ] Tailwind fontSize/spacing 映射令牌（首版）
- [ ] 渐进替换硬编码 hex（296+277）/任意 px（2611）为 `var(--…)`
- [ ] 裸 `monospace`→`var(--font-mono)`；清理 Storybook 残留字体（首版）

### Phase 4 — 状态与代码治理（L，首版）
- [ ] 拆 chatStore、收敛服务层、拆 useChatStream（首版）
- [ ] **【新】收敛 backend/activeFileContext 单一真相源**（首版已提，确认保留）

### Phase 4.5 — i18n 决策（阻塞项，先决策）
- [ ] **决策**：真做（react-i18next，XL，后续多阶段） or 删除脚手架（S）
- [ ] 据决策执行（若删：删 `src/i18n` + 移除 `MobileNav` 语言文案；若做：立项单列）

### Phase 5 — 移动端深水区 + SEO（M）
- [ ] **【新】移动端 input `font-size:16px`**；四向 safe-area；`100vh`→`100dvh`
- [ ] react-helmet-async per-route meta；OG/Twitter；JSON-LD；sitemap（首版+补）

### Phase 6 — 加固
- [ ] **【新】加 CSP meta**
- [ ] **【新】`npm audit` 清零高危**
- [ ] **【新】验证 Storybook 大图不进生产 bundle**

---

## 四、优先级重排要点
1. **安全快修进 Phase 0**：XSS（High）+ token 持久化（Medium）必须最先，因风险最高、改动最小。
2. **vendor-markdown 修复降级为 S**：1 行 vite 配置，原计划"排查"是误判，立即修。
3. **i18n 是阻塞决策**：130 文件硬编码不解决，未来任何本地化都是重写；先决策再排期，别悬着。
4. **聊天虚拟化单列 L**：是 Phase 2 最大风险点，需独立验证流式体验。
5. **验证门禁补 axe-core + npm audit**：没有自动化的 a11y/安全门禁，人工修容易回退。

---
*UI Designer · 计划合理性审计与补遗 · 2026-07-08*
