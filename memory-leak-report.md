# 内存泄漏风险扫描报告

**扫描时间：** 2026-05-27  
**扫描范围：** server/ (Python 后端) + client/src/ (React/TypeScript 前端)

---

## 一、后端 Python 风险点

### 1. 🔴 高风险 — `_upload_tasks` 全局字典永不清理

**文件：** `server/api/knowledge/routes.py` 第 24 行  
**代码：**
```python
_upload_tasks: dict[str, dict[str, Any]] = {}
```
**问题：** 每次异步文档上传都会往 `_upload_tasks` 写入一条记录（含 status、progress、result 等），但整个代码库中没有任何地方对已完成或失败的任务做清理。随着用户不断上传文档，这个字典会无限增长，且每条记录还持有文件名、上传结果等字符串数据。

**建议修复：** 在 `_process_upload` 的 finally 块中加入延迟清理逻辑，或启动一个定时任务淘汰超过 1 小时的旧条目。

---

### 2. 🔴 高风险 — `AsyncOCRService.cleanup_old_tasks()` 定义但从未调用

**文件：** `server/cua/async_ocr.py` 第 251 行  
**问题：** `AsyncOCRService` 定义了 `TASK_MAX_AGE_SECONDS = 3600` 和 `cleanup_old_tasks()` 方法，但通过 grep 确认该方法在全代码库中没有任何调用点。`self._tasks` 字典（第 72 行）会无限积累所有 OCR 任务记录。

**建议修复：** 在 `submit_task` 或 `_run_ocr_task` 完成时触发清理，或在 `__init__` 中启动定时清理协程。

---

### 3. 🔴 高风险 — `RateLimiter._storage` 字典无自动清理

**文件：** `server/security/rate_limiter.py` 第 86 行  
**代码：**
```python
self._storage: dict[str, RateLimitEntry] = storage if storage is not None else {}
```
**问题：** `RateLimiter` 有 `cleanup()` 方法（第 242 行），但从未被调度调用。每个唯一的 `identifier:endpoint` 组合都会创建一个 `RateLimitEntry`，其中的 `timestamps` 列表虽有窗口清理，但 key 本身永不过期。在生产环境中，不同 IP/用户的请求会持续累积 entry。

**建议修复：** 在 `main.py` 的 startup 事件中注册一个后台定时任务，定期调用 `get_rate_limiter().cleanup()`。

---

### 4. 🟡 中风险 — `ConversationManager` 全量加载到内存

**文件：** `server/core/conversation_manager.py` 第 228-234 行  
**代码：**
```python
self._messages: dict[str, MessageNode] = {}
self._branches: dict[str, ConversationBranch] = {}
self._shares: dict[str, ShareLink] = {}
self._groups: dict[str, ConversationGroup] = {}
self._session_branches: dict[str, list[str]] = {}
self._session_messages: dict[str, list[str]] = {}
```
**问题：** `ConversationManager` 启动时将所有历史消息、分支、分享链接、分组全部加载到内存（`_load_data`）。随着对话量增长，这些字典会持续膨胀，没有 LRU 淘汰或分页加载机制。

**建议修复：** 改为按需加载（lazy loading），或对不活跃的 session 数据做 LRU 淘汰。

---

### 5. 🟡 中风险 — `BatchScheduler._results` 字典无清理

**文件：** `server/core/batching.py` 第 102 行  
**代码：**
```python
self._results: dict[str, BatchResult] = {}
```
**问题：** `_pending` 在请求完成/超时后会 `pop`（第 183 行），但 `_results` 字典只进不出，每个批处理请求的结果都会永久保留。

**建议修复：** 在 `_process_batch` 完成后清理对应结果，或使用有容量上限的 LRU 缓存。

---

### 6. 🟡 中风险 — `EventBus` 订阅者列表可能无限增长

**文件：** `server/core/event_bus.py` 第 72 行  
**代码：**
```python
self._handlers: dict[EventType, list[EventHandler]] = {}
self._async_handlers: dict[EventType, list[AsyncEventHandler]] = {}
```
**问题：** `subscribe()` 装饰器（第 350 行）和运行时调用都会向 handler 列表追加条目。虽然有 `unsubscribe` 方法，但大量使用 `@subscribe` 装饰器的模块在热重载时不会清理旧 handler，导致重复注册。`_filters` 和 `_middleware` 列表同样只增不减。

**建议修复：** `subscribe` 时做去重检查；对装饰器注册加模块级去重或在重载时调用 `clear_all()`。

---

### 7. 🟡 中风险 — `TrainingQueue._history` 字典无上限强制

**文件：** `server/core/training_queue.py` 第 109 行  
**代码：**
```python
self._history: dict[str, TrainingTask] = {}
```
**问题：** 虽然定义了 `MAX_HISTORY_SIZE = 100`，但需要检查 `_history` 的实际写入逻辑是否有截断。`_all_tasks`（第 117 行）和 `_cancelled_tasks`（第 118 行）也会随任务增多而增长。

**建议修复：** 确保所有字典在写入时都有上限检查和淘汰逻辑。

---

### 8. 🟡 中风险 — `AsyncOCRService._tasks` 中持有 `image_data` 引用

**文件：** `server/cua/async_ocr.py` 第 72、164 行  
**问题：** `OCRTask` 对象在 `_tasks` 字典中持久存在，而 OCR 任务可能持有大尺寸图像的处理结果。配合问题 #2（cleanup 未调用），大量图像 OCR 结果会驻留内存。

**建议修复：** 与问题 #2 一起修复，及时清理已完成任务。

---

### 9. 🟢 低风险 — SSE 连接中 `seen` 集合随连接时间增长

**文件：** `server/api/agent_sessions.py` 第 139 行  
**代码：**
```python
seen: set[str] = {since_event_id} if since_event_id else set()
```
**问题：** 每个 SSE 连接维护一个 `seen` 集合用于去重。长连接场景下（如 agent session 执行数小时），该集合会持续增长。但由于连接断开后会被 GC 回收，风险有限。

---

### 10. 🟢 低风险 — 大量全局单例无 shutdown hook

**涉及文件：** 超过 20 个模块使用 `global _xxx` 单例模式  
**关键模块：**
- `server/core/event_bus.py` → `_event_bus`
- `server/gateway/session.py` → `_session_manager`
- `server/gateway/binding.py` → `_binding_manager`
- `server/gateway/cross_agent.py` → `_communicator`
- `server/core/distributed_cache.py` → `_cache`
- `server/core/memory_monitor.py` → `_memory_monitor`
- `server/heartbeat/__init__.py` → `_scheduler`

**问题：** 这些单例在进程生命周期内不会释放，且 `main.py` 中未注册统一的 shutdown hook 来调用各模块的 cleanup 方法。如果单例内部持有循环引用或大对象，进程退出前不会被回收。

**建议修复：** 在 `main.py` 的 `shutdown` 事件中统一调用各模块的 cleanup/stop 方法。

---

## 二、前端 React/TypeScript 风险点

### 11. 🔴 高风险 — `FileUpload.tsx` 模拟上传 interval 组件卸载后继续执行

**文件：** `client/src/components/FileUpload.tsx` 第 171 行  
**代码：**
```typescript
const interval = setInterval(() => {
  currentStep++;
  // ... setState ...
  if (currentStep >= totalSteps) {
    clearInterval(interval);
  }
}, 100);
```
**问题：** `simulateUpload` 是一个 `useCallback`，内部的 `setInterval` 没有绑定到任何 ref 或 useEffect cleanup。如果组件在模拟上传过程中卸载，interval 会继续执行并调用已卸载组件的 `setFileList`，导致 React 内存泄漏警告和潜在的内存泄漏。

**建议修复：** 将 interval ID 存入 ref，在 useEffect cleanup 中清除。

---

### 12. 🔴 高风险 — `ChatMessage.tsx` / `CodeBlock.tsx` / `CodePreview.tsx` setTimeout 未清理

**文件：**
- `client/src/components/ChatMessage.tsx` 第 111 行
- `client/src/components/CodeBlock.tsx` 第 314 行
- `client/src/components/CodePreview.tsx` 第 275 行

**代码（典型模式）：**
```typescript
const handleCopy = async () => {
  await navigator.clipboard.writeText(text);
  setCopied(true);
  setTimeout(() => setCopied(false), 2000); // ← 未清理
};
```
**问题：** 复制操作后设置 2 秒延迟重置状态，但这个 setTimeout 没有在组件卸载时清理。如果用户复制后立即导航离开页面，setTimeout 回调仍会尝试 setState。

**建议修复：** 将 timer ID 存入 ref，在 useEffect cleanup 中 `clearTimeout`。

---

### 13. 🟡 中风险 — `StopButton.tsx` interval + setTimeout 未清理

**文件：** `client/src/components/StopButton.tsx` 第 37、46 行  
**代码：**
```typescript
const interval = setInterval(() => { /* progress animation */ }, 100);
// ...
setTimeout(() => setIsStopping(false), 500);
```
**问题：** 两个定时器都没有在组件卸载时清理。

**建议修复：** 将 timer ID 存入 refs，在 useEffect cleanup 中清除。

---

### 14. 🟡 中风险 — `KnowledgeBase.tsx` pollUploadStatus 无取消机制

**文件：** `client/src/pages/KnowledgeBase.tsx` 第 194-222 行  
**代码：**
```typescript
const pollUploadStatus = async (taskId: string) => {
  let finished = false;
  while (!finished) {
    // fetch + await 1200ms
  }
};
```
**问题：** 轮询循环没有 AbortController 或 cancelled flag。如果组件在轮询过程中卸载，循环会继续执行，持续发起网络请求和 setState。

**建议修复：** 使用 AbortController 或在 useEffect cleanup 中设置 cancelled flag 终止循环。

---

### 15. 🟡 中风险 — `ProjectContext.tsx` setTimeout 未清理

**文件：** `client/src/pages/ProjectContext.tsx` 第 99 行  
**代码：**
```typescript
setTimeout(() => setIndexingStatus({ status: 'idle', message: '', progress: 0 }), 3000);
```
**问题：** 索引完成后 3 秒重置状态，但 setTimeout 未在卸载时清理。

---

### 16. 🟡 中风险 — `ModelHub.tsx` 递归 setTimeout 无取消机制

**文件：** `client/src/pages/ModelHub.tsx` 第 183、190 行  
**代码：**
```typescript
setTimeout(poll, 2000); // 递归调用自身
```
**问题：** 轮询函数通过递归 setTimeout 实现，没有 cancelled flag 或 AbortController。组件卸载后轮询会继续。

---

### 17. 🟡 中风险 — `Evaluation.tsx` 递归 setTimeout 通过 ref 但缺少 cleanup

**文件：** `client/src/pages/Evaluation.tsx` 第 270、282 行  
**代码：**
```typescript
pollingRef.current = window.setTimeout(() => pollEvaluationStatus(runId), 2000);
```
**问题：** 虽然用了 ref 存储 timer ID，但需要确认 useEffect cleanup 是否清除了该 ref。如果 cleanup 不完整，递归轮询会在卸载后继续。

---

### 18. 🟢 低风险 — `ChatNew.tsx` localStorage 使用过多

**文件：** `client/src/pages/ChatNew.tsx` 第 744、748、752、815 行  
**代码：**
```typescript
useEffect(() => { localStorage.setItem('chat_primary_agent', selectedPrimaryAgent); }, [...]);
useEffect(() => { localStorage.setItem('chat_routing_mode', routingMode); }, [...]);
// ...
```
**问题：** 虽然不是内存泄漏，但多个 useEffect 在每次状态变化时写入 localStorage，频繁的序列化操作在高频更新场景下可能造成性能问题。此外，`scrollMapRef` 和 `streamingDeltaRef` 等 ref 中积累的数据在会话内不会清理。

---

### 19. ✅ 已正确处理 — 以下模块的定时器清理做得较好

| 文件 | 模式 | 状态 |
|------|------|------|
| `useOllamaConnection.ts` | useEffect cleanup 中 clearInterval + abort | ✅ |
| `HeartbeatPage.tsx` | `return () => clearInterval(interval)` | ✅ |
| `GatewayPage.tsx` | `return () => clearInterval(interval)` | ✅ |
| `PerformanceMonitor.tsx` | `return () => clearInterval(interval)` | ✅ |
| `Training/index.tsx` | `return () => clearInterval(interval)` + unsubscribe ref | ✅ |
| `ModelManager.tsx` | download progress interval 在 try/catch 中 clearInterval | ✅ |
| `useTypewriter.ts` | useEffect cleanup 中 clearInterval + cancelled flag | ✅ |
| `ChatNew.tsx` EventSource | 组件卸载时 `source.close()` + 终端状态时 close | ✅ |

---

## 三、修复优先级建议

| 优先级 | 编号 | 模块 | 修复难度 |
|--------|------|------|----------|
| P0 | #1 | knowledge/routes.py `_upload_tasks` | 简单 — 加 TTL 清理 |
| P0 | #2 | cua/async_ocr.py cleanup 未调用 | 简单 — 接入定时调用 |
| P0 | #3 | rate_limiter.py `_storage` 无自动清理 | 简单 — 注册定时任务 |
| P0 | #11 | FileUpload.tsx interval 泄漏 | 简单 — ref + cleanup |
| P1 | #12 | ChatMessage/CodeBlock setTimeout | 简单 — ref + cleanup |
| P1 | #14 | KnowledgeBase.tsx poll 无取消 | 中等 — 加 AbortController |
| P1 | #16 | ModelHub.tsx 递归 setTimeout | 中等 — 加 cancelled flag |
| P1 | #4 | ConversationManager 全量加载 | 较难 — 需重构为按需加载 |
| P1 | #5 | BatchScheduler._results 无清理 | 简单 — 加 pop 或 LRU |
| P2 | #6 | EventBus handler 去重 | 简单 — subscribe 时检查 |
| P2 | #13 | StopButton.tsx timers | 简单 — ref + cleanup |
| P2 | #15 | ProjectContext.tsx setTimeout | 简单 — ref + cleanup |
| P2 | #17 | Evaluation.tsx 轮询 cleanup | 中等 — 检查 cleanup 完整性 |
| P3 | #7 | TrainingQueue._history 上限 | 简单 — 确认截断逻辑 |
| P3 | #9 | SSE seen 集合 | 低 — 连接断开即回收 |
| P3 | #10 | 全局单例 shutdown hook | 中等 — 统一注册 |
