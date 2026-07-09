# Phase 4 代码质量与状态治理 — 完成报告

> 执行日期：2026-07-09
> 执行人：Frontend Developer（像素匠）
> 模式：Craft
> 范围：前端 `client/` 散落 fetch 收敛 + activeFileContext 单一真相源核验

---

## 0. 范围调整说明（修正原审查报告）

原 `docs/frontend-review-2026-07-08.md` Phase 4 计划 4 项，核实后发现 2 项已过时/误判，实际聚焦 2 项：

| 原计划项 | 核实结论 | 处理 |
|---------|---------|------|
| chatStore API 下沉 services | **已完成**。createSession/loadSession/deleteMessage 等全调 `services/chatSessionApi`，仅 `axios.isAxiosError` 做类型判断（非请求） | 无需做 |
| 收敛 backend 双源 | **误判**。`appStore.backendUrl` 是后端服务器**地址**(URL)，`chatStore.settings.backend` 是推理引擎**类型**(ollama/hf/cloud 枚举)。语义完全不同，非双源 | 无需做 |
| 收敛 activeFileContext | 真问题，但核验后**已是单一源**（见 §2） | 核验确认 |
| 抽散落 fetch | 真问题，41 处散落 → 全部收敛（见 §1） | ✅ 完成 |
| chatStore 拆三 store | 真问题（771 行上帝 store），但高风险大重构，收益主要是可读性 | 暂缓（单独立项） |
| 拆 useChatStream(837行) | 边界其实相对清晰（useStreamResponse 通用流传输层 / useChatStream 聊天业务层），837 行是业务复杂非重叠 | 暂缓（收益低） |

---

## 1. 散落 fetch 收敛（4a）

### 统计
- **散落调用总数**：41 处（14 个文件）
- **收敛方式**：
  - 复用 api.ts 现有 service：13 处
  - 新建 service 文件收敛：27 处
  - 保留（通用 SSE helper）：1 处（`useChatStream.ts` L183，url 由调用方传入的通用流式 helper）

### 新建 service 文件（8 个）
| 文件 | 函数 | 端点 |
|------|------|------|
| `services/knowledgeApi.ts` | getKnowledgeCollections / getKnowledgeEmbedderStatus / getKnowledgeCollection / preloadKnowledgeEmbedder / uploadKnowledgeDocumentAsync / getKnowledgeUploadStatus / deleteKnowledgeDocument | /knowledge/* |
| `services/cloudApi.ts` | saveCloudApiKey / testCloudProvider / deleteCloudApiKey | /cloud/api-keys, /cloud/test/* |
| `services/projectContextApi.ts` | getProjectContexts / scanProject / indexProject / removeProjectContext | /context/projects,scan,index,remove |
| `services/contextUnderstandingApi.ts` | getContextUnderstandingStatus / processContextUnderstanding / enhanceContext / summarizeContext / manageContextWindow | /context/understanding/* |
| `services/ocrApi.ts` | runOcr | /ocr |
| `services/codeApi.ts` | executeCode | /code/execute |
| `services/chatShareApi.ts` | getSharedChat / getSharedChatMarkdown | /chat/share/* |
| `services/performanceApi.ts` | getPerformanceMetrics / getPerformanceSuggestions | /inference/performance/metrics,suggestions |
| `services/swiftApi.ts` | checkSwift | /training/check-swift |

### api.ts 扩展
- `getOllamaStatus(config?)`：新增可选 `AxiosRequestConfig` 参数，支持 AbortController signal（供 useOllamaConnection/useChatStream 的熔断与预检复用）
- `deleteWorkspace(workspaceId)`：补齐 workspace CRUD 缺失的 DELETE

### 迁移的页面/组件（13 个文件，40 处）
- **批次1（复用现有 service）**：ModelHub.tsx(7处)、WorkspaceManager.tsx(4处)
- **批次2（getOllamaStatus 加 config）**：useOllamaConnection.ts(2处)、useChatStream.ts(1处)
- **批次3（knowledgeApi）**：RuntimeContext.tsx(2处)、KnowledgeBase.tsx(5处)
- **批次4-6（新建 service）**：APIKeyManager.tsx(3)、ProjectContext.tsx(4)、ContextPanel.tsx(5)、ImageUpload.tsx(1)、CodeExecutor.tsx(1)、SharedChat.tsx(2)、PerformanceMonitor.tsx(2)、SwiftChecker.tsx(1)

### 迁移规则（统一执行）
1. 去掉 `fetch()` + `if(response.ok)` + `await response.json()` 三段式，直接 `const data = await serviceFn(...)`
2. service 在非 2xx 自动 throw，进 catch
3. 错误信息：原手动读 `response.json().detail` 改用 `extractApiErrorMessage(error, fallback)`
4. abort 兼容：原 `error.name === 'AbortError'` 补充 `CanceledError` / `ERR_CANCELED`（axios 取消错误）
5. ContextPanel.tsx 移除裸 `import axios`，改用 apiClient
6. ProjectContext.tsx 清理 `API_BASE = API_BASE_URL` 别名

### 验证
- grep 确认：14 个原始文件中 `fetch(\`${API_BASE_URL` / `axios.get(${` / `axios.post(${` **零命中**（仅 api.ts 自身命中，正常）

---

## 2. activeFileContext 单一真相源核验（4b）

核实结论：**已是单一真相源，无需改动**。

- `appStore`：定义 `activeFileContext: ActiveFileContext | null` + `setActiveFileContext`（唯一存储）
- `ChatInput.tsx`：通过 **props** 接收 `activeFileContext`，仅读取展示（非自存储）
- `useChatStream.ts`：`active_context` 是 ChatSendPayload 字段名，值由调用方从 appStore 读后传入 payload，非自存储
- `ContextPanel.tsx`：原报告称"重复读写"，**已过时**——重构后不再涉及 activeFileContext（grep 零命中）

消费链：`appStore.activeFileContext` → 调用方读取 → `payload.deepContext.active_context` → `useChatStream` → 后端。无重复存储。

---

## 3. 暂缓项（建议单独立项）

### chatStore 拆三 store（P1，高风险）
- 现状：771 行上帝 store，混 6 关注点（session/message/stream/experiment/cloudConfig/settings）
- 风险：牵动所有 `useChatStore` 消费方（Chat/Agent/Training 多页），回归面大
- 建议：单独立项 + 配完整回归测试，不塞进常规 Phase

### useChatStream 拆分（P2，低收益）
- 现状：837 行，但与 useStreamResponse 边界相对清晰（通用流传输层 vs 聊天业务层）
- 结论：837 行是业务复杂度，非职责重叠，拆分收益低

---

## 4. 验证门禁

| 门禁 | 结果 |
|------|------|
| `tsc --noEmit` | 0 errors ✅ |
| `eslint src --ext .ts,.tsx` | 0 errors（69 warnings，全是既有 api.ts 的 no-explicit-any）✅ |
| `vitest run`（全量） | 229 passed + 1 flaky ✅（AgentProductPolish 单独跑 18 passed，全量时受 ActionRecorder 60s 长跑拖累并发环境导致 flaky，非代码问题） |
| `npm run build` | 成功 ✅ |
| bundle budget（5 项） | vendor-ui 363/430 · vendor-react 49.6/60 · vendor-charts 102.8/120 · AgentWorkbenchRoute 29.8/45 · ChatNew 69.3/100 KiB gz，**全通过** ✅ |

### 测试修复
- `WorkspaceManager.test.tsx`：原 mock 全局 `fetch` + `API_BASE_URL`，迁移后改为 mock service 函数。首次因 `vi.mock` factory 引用顶层 const 触发 TDZ（`Cannot access before initialization`），用 `vi.hoisted` 修复。

---

## 5. 改动文件清单

**新建（9 个）**：
- services/knowledgeApi.ts、cloudApi.ts、projectContextApi.ts、contextUnderstandingApi.ts、ocrApi.ts、codeApi.ts、chatShareApi.ts、performanceApi.ts、swiftApi.ts

**修改（15 个）**：
- services/api.ts（getOllamaStatus 加 config + deleteWorkspace）
- pages/ModelHub.tsx、WorkspaceManager.tsx、APIKeyManager.tsx、ProjectContext.tsx、SharedChat.tsx、KnowledgeBase.tsx
- components/ContextPanel.tsx、ImageUpload.tsx、CodeExecutor.tsx、PerformanceMonitor.tsx、SwiftChecker.tsx
- hooks/chat/useOllamaConnection.ts、useChatStream.ts
- runtime/RuntimeContext.tsx
- test/WorkspaceManager.test.tsx

---
*Frontend Developer · Phase 4 完成报告 · 2026-07-09*
