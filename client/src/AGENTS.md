# client/src AGENTS.md

本文件只覆盖 `client/src/` 子树的约定、禁止事项与本地验证命令。项目级概述、命令面与安全边界见根 [`AGENTS.md`](../../AGENTS.md)；目录树详解与设计模式见 [`docs/architecture-reference.md`](../../docs/architecture-reference.md)。

## 子树约定

- **能力分层对齐**：`capability/tiers.ts`（`ROUTE_CAPABILITY` 路径 → capability id）+ `ExperimentalRouteGuard.tsx` + Sidebar 徽章。运行时权威是后端 `/api/info` 的 `capability_tiers` / `experimental_enabled`。
- **API 客户端收敛（阶段 4）**：REST 请求统一走 `services/*`（`api.ts` 主 Axios 或领域 `*Api.ts`）。`API_BASE_URL` 解析顺序：Electron → `import.meta.env.VITE_API_URL` → `http://{hostname}:8010`。
- **流式/SSE 例外**：允许通过 `API_BASE_URL` + `EventSource` / `StreamManager` / `utils/agentSessionStream.ts` 拼 URL（非 REST CRUD）。Agent SSE 连接逻辑集中在 `utils/agentSessionStream.ts`，断线退避重连由其统一负责。
- **错误信息**：优先 `extractApiErrorMessage` / `getApiErrorMessage`；非 2xx 由 Axios 拦截抛错。
- **Agent Workbench**：`agent/` + `/agent` 路由是唯一生产 Agent 界面，也是 `/` 的默认跳转目标；协议解析在 `agent/protocol/`，归一化 reducer 与传输在 `agent/runtime/`、`agent/transport/`。
- **聊天隔离**：`pages/ChatNew.tsx`（`/chat`）只负责普通聊天（含消息虚拟化）。
- **样式入口**：全局 CSS 与设计 token 唯一入口是 `styles/index.css`（`main.tsx` 导入），不是根 `index.css`。动效封装在 `components/motion/`，token 在 `theme/motion-tokens.ts`。
- **状态管理**：Zustand（`store/`）。`chatStore` 的 `partialize` 必须剥离 `cloudConfig.config.api_key`，禁止持久化 API key。
- **XSS 防护**：训练日志渲染先 HTML 转义再高亮（`pages/Training/components/highlightLog.ts`），改动须保留转义顺序。
- **测试位置**：Vitest 测试位于 `test/`（React Testing Library）；Agent 业务门控用 `agent/testing/` 的脱敏事件夹具对比最终 Store 投影。

## 禁止事项

- 禁止在页面/组件新增散落 `fetch()`（REST 一律走 `services/*`）。
- 禁止手写与后端漂移的静态 capability tier 字典（以 `/api/info` 为准）。
- 禁止在 `pages/ChatNew.tsx` 导入 Agent Session 创建、SSE、审批、恢复、子任务、文件编辑或终端逻辑。
- 禁止绕过 `ExperimentalRouteGuard` 直挂 experimental 页面路由。
- 禁止在 store 持久化任何 API key 或凭据。

## 本地验证命令

```bash
cd client
npm run lint               # eslint src --ext .ts,.tsx
npm run typecheck          # tsc --noEmit
npx vitest run             # 单次全量测试（npm test 是 watch 模式）
npm run test:smoke         # Sidebar + beta + experimental + ga 页面 smoke
npm run test:runtime       # RuntimeContext + RuntimeWorkflows
npm run test:agent-foundation   # Agent Workbench 基础回归
npm run build              # tsc && vite build（提交前确认可构建）
```
