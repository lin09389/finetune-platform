# 聊天虚拟化专项完成报告

> 执行日期：2026-07-09 · 执行人：Frontend Developer · 模式：Craft
> 性质：Phase 2 延后的 L 级高风险专项

## 验证门禁（全绿）

| 门禁 | 结果 |
|------|------|
| `tsc --noEmit` | ✅ 0 errors |
| `eslint src` | ✅ 0 errors / 69 warnings |
| 冒烟 + XSS + 虚拟化测试 | ✅ 25 passed（新增 `ChatNewVirtualization.test.tsx`） |
| `npm run build` + bundle-budget | ✅ 5 项预算全通过（ChatNew 69.3/100 KiB gz） |

## 问题
`ChatNew.tsx` 用 `messages.map` 全量渲染消息，每条含 react-markdown + katex + highlight.js。长对话（几十上百条）时渲染与滚动性能崩塌。

## 方案：react-virtuoso 虚拟化
`react-virtuoso` 已是项目依赖（AgentRunTimeline 在用）。改造点：

### 1. 消息列表用 Virtuoso 替换 `messages.map`
- `data={messages}`、`computeItemKey={(_, item) => item.id}`（稳定 key）
- `itemContent` 渲染 ChatMessage，保留全部 props（onDelete/onEdit/onRetry/isStreaming/knowledge_sources 等）
- `style={{ height: '100%' }}` 填充 `.messages` 内容盒——继承其 180px 底 padding（给浮动 `.composer` 留位），**无需改 CSS**
- `increaseViewportBy={600}` 预渲染上下 600px，滚动更顺

### 2. 流式自动滚动 + 尊重用户上滚
- `followOutput={(atBottom) => (atBottom ? 'auto' : false)}`：用户在底部时随流式 token 跟随；用户上滚阅读历史时不打断（**改进**——原实现 `messageEndRef.scrollIntoView` 每次 message 变化都强制拉到底，会打断上滚阅读）
- 移除 `messageEndRef` 与旧 `scrollIntoView` effect

### 3. 会话切换跳底
- 新增 `virtuosoRef`，`useEffect([currentSessionId])` → `scrollToIndex({ index: 'LAST' })`：加载/切换历史会话时跳到最新消息（首次挂载也触发）
- selector 新增 `currentSessionId`

### 4. 保留空状态与无障碍
- `messages.length === 0` 仍渲染 starter 空状态（不挂 Virtuoso）
- `role="log" aria-live="polite"` 仍在 `.messages` 容器（Phase 1 加的），Virtuoso 在其内部渲染，新消息仍被读屏播报

## 流程覆盖分析
| 场景 | 行为 |
|------|------|
| 新对话首条消息 | 空→Virtuoso 挂载，单条可见，后续流式 followOutput 跟随 |
| 加载历史会话 | currentSessionId 变 → scrollToIndex('LAST') 跳底 |
| 会话间切换 | 同上 |
| 流式中 | atBottom 时 'auto' 跟随；上滚时不打断 |
| 用户上滚阅读 | 不被新 token 拉回底部（改进） |

## 测试说明
- 新增 `ChatNewVirtualization.test.tsx`：mock store 返回 3 条消息，断言组件挂载不崩、走消息路径（空状态 h1 不存在）、role="log" 存在。
- **jsdom 限制**：0 视口高度下 Virtuoso 渲染 0 可见项，无法验证虚拟化渲染数量与流式滚动行为——这部分**需浏览器手测**（长对话流式追加、上滚打断、会话切换跳底）。代码层（类型/接线/挂载）已由 typecheck + 新测试覆盖。

## 改动文件
- `client/src/pages/ChatNew.tsx`（Virtuoso 重构 + 会话跳底 + 移除 messageEndRef）
- `client/src/test/ChatNewVirtualization.test.tsx`（新增，消息路径冒烟）

## 浏览器手测清单（建议）
1. 长对话（50+ 条含代码/公式）滚动流畅、无卡顿
2. 流式输出时停在底部自动跟随
3. 流式中上滚 → 不被拉回底部
4. 从历史加载长会话 → 自动到底部
5. 消息删除/编辑/重试仍可用
6. 空状态 starter 点击仍可发送
