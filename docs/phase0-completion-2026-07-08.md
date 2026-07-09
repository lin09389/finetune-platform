# Phase 0 完成报告 — 安全快修 + 死代码收口

> 执行日期：2026-07-08 · 执行人：Frontend Developer · 模式：Craft
> 依据：`docs/frontend-review-2026-07-08-supplement.md` 的 Phase 0

## 验证门禁（全绿）

| 门禁 | 结果 |
|------|------|
| `tsc --noEmit` | ✅ 0 errors |
| `eslint src` | ✅ 0 errors / 69 warnings（全为 `no-explicit-any`，可接受） |
| 冒烟测试（Sidebar + beta + experimental + gaSmoke + highlightLog） | ✅ 24 passed |
| `npm run build`（tsc + vite build + bundle-budget） | ✅ built in 13.31s，预算全通过 |

## 已完成项

### 🔴 安全
1. **TrainingDashboard XSS 修复**（High）
   - 问题：`TrainingDashboard.tsx:210` `dangerouslySetInnerHTML` 注入 `highlightLog()` 产物，而 `highlightLog` 未对日志原文做 HTML 转义——训练日志回显的数据集名/路径若含 `<img onerror>` 即执行。
   - 修复：抽纯函数到 `src/pages/Training/components/highlightLog.ts`，`highlightLog` 先 `escapeHtml`（`& < > " '`）再注入自有 `<span>` 标记。组件改为 `import { highlightLog }` 并传 CSS-module 类名映射。
   - 回归测试：新增 `src/test/highlightLog.test.ts`（7 用例，覆盖 `<img onerror>`、`<script>`、`<b>`、`&amp;` 双重转义、正常 token 高亮）。

2. **chatStore persist 剥离 api_key**（Medium）
   - 问题：`chatStore.ts` persist（`'chat-storage'`）原样持久化 `cloudConfig`，其 `config.api_key` 若被赋真实 key 会落入 localStorage 被 XSS 窃取。
   - 修复：`partialize` 中 `cloudConfig.config` 存在时展开并置 `api_key: undefined`（JSON 序列化自动剔除），运行态 state 不受影响。

3. **后端地址泄露控制台**（Low）
   - 删除 `api.ts:18` `console.log('[API] Base URL:', ...)`。

### 🟠 死代码 / 基础收口
4. **清理调试 console.log**：删除 `api.ts` 5 处 `console.log`（18/228/388/2475/2508），并清理随之成为死代码的 `chunkCount` 声明与自增。保留 `console.warn/error`（属错误处理）。
   - 注：`CodeExecutor.tsx` 的 `console.log` 是示例代码模板字符串内容，**非真实调用**，未删（首轮报告此处误判，已修正）。

5. **ESLint 三配置合一**：合并为单一 `.eslintrc.json`（吸收 `.eslintrc.yml` 的 `prettier` extend、`varsIgnorePattern`、`ignorePatterns`），删除 `.eslintrc.yml`，移除 `package.json.eslintConfig`。`no-console` 设为 `['error', { allow: ['warn', 'error'] }]` 拦截回归。warnings 84→69。

6. **删除死代码 `src/index.css`**（34KB，Inter/Outfit 体系）：grep 确认全仓无引用（`main.tsx` 导入的是 `styles/index.css`），git 跟踪可恢复，已删。

7. **index.html meta 补全**：加 `meta description`、`theme-color`（light/dark 双值）、viewport 加 `viewport-fit=cover`；新建 `public/robots.txt`。

8. **移除冗余 dayjs 直接依赖**：src 零引用确认（antd 5 自带 dayjs），`npm uninstall dayjs` 移除并同步 lockfile。

## 未做（Phase 0 内的遗留小项）
- `design-tokens.md` 文档对齐实际令牌（文档更新，非代码，可后续顺手做）。

## 改动文件清单
- `client/src/pages/Training/components/highlightLog.ts`（新增，纯函数）
- `client/src/pages/Training/components/TrainingDashboard.tsx`（XSS 修复 + 引用纯函数）
- `client/src/test/highlightLog.test.ts`（新增，XSS 回归测试）
- `client/src/store/chatStore.ts`（persist 剥离 api_key）
- `client/src/services/api.ts`（删 5 处 console.log + chunkCount 死代码）
- `client/.eslintrc.json`（合并配置）
- `client/.eslintrc.yml`（删除）
- `client/package.json`（移除 eslintConfig + dayjs）
- `client/index.html`（meta 补全）
- `client/public/robots.txt`（新增）
- `client/src/index.css`（删除）

## 下一步
Phase 0 全绿，可进入 **Phase 1（可访问性硬伤）**：导航语义化、对比度 token 修正、图标按钮 aria-label、可点击 div 补 role、h1 层级、路由焦点移动 + 404 路由。验收门禁：axe-core 扫描 0 critical。
