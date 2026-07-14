# Phase 1 完成报告 — 可访问性硬伤

> 执行日期：2026-07-08 · 执行人：Frontend Developer · 模式：Craft
> 依据：`docs/frontend-review-2026-07-08-supplement.md` 的 Phase 1

## 验证门禁（全绿）

| 门禁 | 结果 |
|------|------|
| `tsc --noEmit` | ✅ 0 errors |
| `eslint src` | ✅ 0 errors / 69 warnings（全为 `no-explicit-any`） |
| 冒烟 + XSS 测试 | ✅ 24 passed |
| `npm run build` + bundle-budget | ✅ built in 13.14s，预算全通过（vendor-ui 407.7/430、AgentWorkbench 29.8/45、ChatNew 69.2/100 KiB gz） |

> a11y 自动化扫描（axe-core）建议在浏览器中手动复测；`@storybook/addon-a11y` 已装可辅助。

## 已完成项

### 1. 对比度 token 修正（variables.css + App.tsx antd token）
- 用 Python 精确计算 WCAG 比率，**修正首轮误判**：深色主题实际全部达标（agent 估算有误），仅浅色主题 4 个 token 不达标。
- 浅色替换（目标 4.7 安全余量，在 bg-primary/白底/卡片均 ≥4.5）：
  - `--text-tertiary` #9b988c → #737064（2.74→4.71）
  - `--accent-primary` #c96442 → #b35433（3.70→4.71，同时白字按钮 3.90→4.96）
  - `--success` #788c5d → #65754e（3.49→4.74）
  - `--warning` #b8860b → #916909（3.09→4.71）
- 同步 `--primary-500` 与 3 个 gradient（gradient-primary/brand/warm）保持品牌色一致；同步 App.tsx ConfigProvider 的 colorPrimary/colorSuccess/colorWarning/inkBarColor 浅色分支。

### 2. 404 路由 + 路由焦点移动 + ErrorBoundary 日志
- App.tsx 新增 `path="*"` → `NotFound`（antd Result + 返回工作台 Link）。
- AppContent 加 `useEffect([location.pathname])` 聚焦 `#main-content`（Content 已有 tabIndex=-1），SPA 导航后键盘/读屏用户落到新内容。
- ErrorBoundary 加 `componentDidCatch`（console.error + componentStack），生产可排查。

### 3. Sidebar 导航语义化 + 外壳地标
- 菜单项/logo/折叠按钮（motion.div onClick）加 `role="button"`/`tabIndex={0}`/`aria-current`/`aria-label`/`onKeyDown`(Enter/Space)。
- Sider 加 `role="navigation" aria-label="主导航"`；Content 加 `role="main"`；HeaderBar 加 `role="banner"`。
- 状态徽章加 `role="status" aria-label`（折叠时不再仅靠颜色传达）。

### 4. MobileNav 导航语义化
- NavItem 与 MobileBottomNav 项加 `role="button"`/`tabIndex`/`aria-current`/`aria-label`/`onKeyDown`。
- 抽屉列表加 `role="navigation"`；底部导航加 `role="navigation" aria-label="底部导航"`；状态徽章加 `role="status" aria-label`。

### 5. 图标按钮 aria-label（核实后 7 处，非首轮 9 处）
- Deployment(刷新版本列表)、Evaluation(复制代码)、ChatBranchManager(更多操作)、ChatHeader(更多操作)、SwiftChecker(重新检查)、UserGuide×2(显示引导/关闭提示)。
- **修正首轮误报**：History:1021 与 ModelManager:324 实际有"删除"文本，非纯图标按钮，跳过。

### 6. 可点击 div 补 role/键盘（5 处交互式）
- DatasetManager dropzone、Evaluation 运行项、GatewayPage 标签（tablist/tab 模式 + roving tabindex）、Inference 后端项、APIKeyManager 配置卡。
- 加 `role="button"`(或 tab)/`tabIndex`/`aria-current`/`aria-label`/`onKeyDown`。
- 模态遮罩（HeartbeatPage/MCPTools backdrop）跳过——键盘路径走 Escape/关闭按钮，属对话框模式另议。
- AgentWorkbenchShell:95 是事件委托容器（非交互元素本身），跳过。

### 7. h1 层级
- HeaderBar 页标题 h2→h1（每页唯一 h1）。
- ChatMessage markdown h1 覆盖改为渲染 `<h2>`（避免 AI 输出多 h1 破坏"每页一个 h1"）。

### 8. aria-live 动态区
- ChatNew 消息列表加 `role="log" aria-live="polite" aria-label="对话消息"`。
- TrainingDashboard 终端日志体加 `role="log" aria-live="polite" aria-label="训练日志"`。

## 改动文件清单（17 个）
- `src/styles/variables.css`（对比度 token + gradient）
- `src/App.tsx`（404/焦点/Content role/antd token 同步）
- `src/components/ErrorBoundary.tsx`（componentDidCatch）
- `src/components/Sidebar.tsx`（nav 语义化 + 地标）
- `src/components/MobileNav/index.tsx`（nav 语义化 + 地标）
- `src/components/HeaderBar.tsx`（h1 + banner + 图标按钮 aria）
- `src/pages/Deployment.tsx`、`Evaluation.tsx`、`GatewayPage.tsx`、`Inference.tsx`、`APIKeyManager.tsx`、`DatasetManager.tsx`（图标按钮 aria / 可点击 div role）
- `src/components/ChatBranchManager.tsx`、`chat/ChatHeader.tsx`、`SwiftChecker.tsx`、`UserGuide.tsx`（图标按钮 aria）
- `src/components/ChatMessage.tsx`（markdown h1→h2）
- `src/pages/ChatNew.tsx`、`pages/Training/components/TrainingDashboard.tsx`（aria-live）

## 修正的首轮误判（trust but verify）
1. 深色主题对比度实际全达标（agent 估算偏低）。
2. History:1021 / ModelManager:324 有"删除"文本，非纯图标按钮。
3. AgentWorkbenchShell:95 是事件委托容器，非交互元素。

## 下一步
Phase 1 全绿，可进入 **Phase 2（首屏性能）**：vendor-react 分包规则（1 行根治 vendor-markdown 误预载）、antd 按需、ConfigProvider theme useMemo、字体精简自托管、useStreamResponse cleanup、img lazy、PWA 缓存、内联骨架、聊天列表虚拟化（L 级单列）、流式 useDeferredValue。
