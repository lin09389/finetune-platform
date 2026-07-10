# Agent 模块深度诊断报告（终版 · 含修复状态验证）

> 诊断时间：2026-07-09  
> 调查轮次：4 轮（代码审查 + DB 实证 + 日志分析 + 配置解密 + git log 定位 + 修复状态验证）  
> 共定位 **5 个 P0 + 7 个 P1 + 5 个 P2 = 17 个问题**，其中 **0 个已完全修复，15 个仍存在**

---

## 执行摘要

agent 模块**从未成功完成过一次完整开发任务**（涉及文件操作的任务），但**纯对话任务在正确配置下可以成功**——6 月 28 日有一个 `deepseek/deepseek-chat` 的纯对话 session 成功完成（29 分钟 2 轮）。这证明 agent 核心执行链路（DeepAgents + LangGraph + DeepSeek API）是能工作的，失败由外围 5 层阻断叠加导致。

### DB 实证数据（101 个 session 分布在两个分裂的 DB）

| DB 文件 | session 数 | 状态分布 |
|---------|-----------|----------|
| `server/data/app.db` | 78 | needs_manual_review:41, idle:17, completed:8, interrupted:8, failed:2 |
| `data/app.db` | 23 | 含 1 个 6 月 28 日 completed（deepseek-chat 纯对话） |

### 失败原因全量分类（41 个 needs_manual_review）

| 次数 | 原因 | 修复状态 |
|------|------|----------|
| 9 | 服务重启中断（daemon 线程被杀） | ✗ 仍存在 |
| 9 | `'coroutine' object is not iterable` | ⚠️ 可能部分改善 |
| 3 | openai init_chat_model 失败（无 key） | ✗ 仍存在 |
| 2 | 模型未配置 | ✗ 仍存在（靠配 key 规避） |
| 2 | provider/model 格式错误 | ✗ 仍存在 |
| 1 | database is locked | ✗ 仍存在 |

### 成功路径实证

```
provider=deepseek  model=deepseek-chat（正确模型名）
mode=safe_auto  configured=1
29 分钟 2 轮纯对话  0 permission parts（不触发 HITL）
model_stream_started/completed ✓  chain_completed:14 ✓
```

---

## 根因链路总览

```
用户发起 agent 任务
        │
        ▼
[创建 session] ──(P0-4)──▶ DB 路径分裂（相对路径）── 仍存在 ✗
        │
        ▼
[模型配置检查] ──(P0-2)──▶ 无云端 key → AgentConfigurationError ── 仍存在 ✗
        │                  （deepseek 有 key 可规避）
        ▼
[启动 detached 后台线程] ──(P0-3)──▶ daemon=True，服务重启被杀 ── 仍存在 ✗
        │
        ▼
[DeepAgents + LangGraph 执行]
        │
        ├── 选本地模型 ──(P0-1)──▶ tool calling 400 ── 仍存在 ✗
        │
        ├── 选云端但模型名错 ──(P1-6)──▶ deepseek-v4-flash 不存在 ── 仍存在 ✗
        │
        ├── coroutine bug ──(P0-5)──▶ 'coroutine' object is not iterable ── 可能部分改善 ⚠️
        │
        ├── 触发 HITL 审批 ──(P2-4)──▶ 纯对话不触发，文件操作会触发 ── 潜在
        │
        └── 正确模型+纯对话+不重启 ──▶ ✓ 成功（6月28日实证）
```

---

## 问题清单与修复状态

### P0 致命问题（5 个）

#### P0-1：本地推理硬编码拒绝 tool calling【仍存在 ✗】

**定位**：`server/api/inference/openai_routes.py:363-367`
```python
def _validate_supported_features(request: ChatCompletionRequest) -> None:
    if request.tools:
        raise _openai_http_error(400, "Tool calling is not supported...", code="unsupported_tools")
```
**验证**：代码未变，仍硬编码拒绝。
**影响**：选 local/ollama:service 模型时，DeepAgents 的 `bind_tools()` 请求被 400 拒绝，agent 无法调用任何工具。
**修复方案**：本地推理实现 tool calling 解析，或强制 agent 只用云端模型。

#### P0-2：模型未配置（仅限无 key 的 provider）【仍存在 ✗，靠配 key 可规避】

**定位**：`server/agent_session/services/session_lifecycle.py:110-118` + `background_task_manager.py:85-92`
**验证**：判定逻辑未变。`configured = model_call is not None or _has_saved_cloud_model(provider, model)`。
**影响**：openai 无 `cloud_openai_key` → `configured=False` → AgentConfigurationError。deepseek 有 key → 不触发。
**修复方案**：UI 引导配置，或 `/api/info` 暴露 `agent_model_configured` 状态。

#### P0-3：daemon 线程被服务重启杀死【仍存在 ✗】

**定位**：`server/agent_session/services/background_task_manager.py:166`
```python
thread = threading.Thread(..., daemon=True)  # ← 仍为 True
```
**验证**：`daemon=True` 未改。DB 实证 9 次"服务重启中断"失败。
**影响**：服务重启时线程被强杀，finally 不执行，session 卡 running 成僵尸。
**修复方案**：`daemon=False` + lifespan shutdown 优雅中断，或改独立子进程。

#### P0-4：app.db/checkpoint DB 路径分裂【仍存在 ✗】

**定位**：`server/core/storage.py:25`
```python
APP_DB_PATH = os.getenv("FINETUNE_PLATFORM_DB_PATH", "data/app.db")  # ← 仍为相对路径
```
**验证**：未改绝对路径。双 DB 实证：`data/app.db`(23 session) + `server/data/app.db`(78 session)；checkpoint 295M + 370M = 665M。
**影响**：cwd 不同写入不同 DB，恢复时读错 DB → 状态丢失。
**修复方案**：改基于 `settings.base_dir` 的绝对路径，合并双 DB。

#### P0-5：`'coroutine' object is not iterable`【可能部分改善 ⚠️】

**DB 实证**：9 次失败，5 月 24 日后出现。
**git log 定位**：5 月下旬 `5b54bcb Rewrite agent sessions` / `2258b83 add managed async subagents` 引入。
**修复验证**：`6653319 fix: harden agent session background recovery` 改了 `deepagents_runtime.py`（引入 `_open_checkpointer` asynccontextmanager）+ `background_task_manager.py`（229 行变更）+ `events.py`（73 行跨线程改进）。可能改善了 async/sync 边界，但**未确认完全修复**——需实际测试验证。
**修复方案**：重点审查 `2258b83` 的 diff，关注 `asyncio.create_task` 返回值处理。

### P1 严重问题（7 个）

#### P1-1：鉴权 403 身份漂移【仍存在 ✗】

**定位**：`server/security/runtime_policy.py:49` + `server/.env`
**验证**：`.env` 仍只有 `ENABLE_AUTH=false`，**未设** `ALLOW_LOCAL_AGENT_AUTH=true`。
**修复方案**：`.env` 加 `ALLOW_LOCAL_AGENT_AUTH=true`。

#### P1-2：checkpoint 膨胀 665MB【仍存在 ✗】

**验证**：`data/langgraph_checkpoints.db`=295M + `server/data/langgraph_checkpoints.db`=370M，未清理。
**注**：`6653319` 修了 checkpointer 泄漏（每次 prompt 创建独立 checkpointer 并关闭），但**未清理已有膨胀数据**。
**修复方案**：checkpoint TTL 清理脚本。

#### P1-3：inference_server 默认 service 模式但可能未启动【仍存在 ✗】

**定位**：`server/core/config.py:127` `inference_execution_mode` 默认 `"service"`
**验证**：未改默认值。日志有 `All connection attempts failed`。
**修复方案**：启动脚本拉起 inference_server，或改 `in_process`。

#### P1-4：chat_agent 意图分类卡 awaiting_approval【仍存在 ✗】

**定位**：`server/api/chat_agent.py:22` `POST /chat-agent/intent`
**验证**：DB `chat_agent_runs` 6 条全 `awaiting_approval`，未修。
**修复方案**：SSE 推送审批事件 + 前端展示审批入口。

#### P1-5：async subagent waiting 误判为 failed【仍存在 ✗】

**定位**：`server/agent_session/async_subagents.py:314`
```python
status = "completed" if result.get("status") == "completed" else "failed"  # ← 未改
```
**验证**：代码未变。child 等待审批（waiting）被误判为 failed。
**修复方案**：waiting 状态保持 running，不标记 failed。

#### P1-6：预设模型列表含不存在模型【仍存在 ✗】

**定位**：`deepagents_reference/libs/code/deepagents_code/widgets/model_selector.py:67,81,82`
**验证**：`deepseek-v4-flash` 未清理。49 个 session 用了这个错误模型名。
**修复方案**：替换为 `deepseek-chat` / `deepseek-reasoner`。

#### P1-7：database is locked【仍存在 ✗】

**验证**：DB 路径分裂（P0-4）未修，并发锁竞争仍在。DB 实证 1 次 `database is locked`。
**修复方案**：修 P0-4 后自然缓解。

### P2 改进项（5 个）

#### P2-1：日志格式损坏【部分改善 ⚠️】

**定位**：`server/core/logging.py:9-41` 有 `JsonFormatter` + `enable_json` 开关
**验证**：`.env` 有 `LOG_FORMAT=text`，但日志后半段仍出现 JSON 格式损坏。`enable_json` 可能被某处强制开启。
**修复方案**：确认 `enable_json` 默认 False，尊重 `.env` 的 `LOG_FORMAT`。

#### P2-2：初始化容错过度【仍存在 ✗】

**定位**：`server/apps/lifespan.py:89-129`
**验证**：所有初始化仍包在 try/except 里，失败只 warning。
**修复方案**：关键依赖失败应 fail-fast 或标记降级。

#### P2-3：extra_body thinking 硬编码【仍存在 ✗】

**定位**：`server/agent_session/model_adapter.py:149`
```python
if spec.provider == "deepseek":
    kwargs["extra_body"] = {"thinking": {"type": "disabled"}}  # ← 未移除
```
**验证**：代码未变。对 `deepseek-chat` 无意义。
**修复方案**：移除，或改为仅 `deepseek-reasoner` 时添加。

#### P2-4：HITL 审批中断（非主要阻断点）【仍存在 ✗，但影响低】

**定位**：`server/agent_session/permission.py:12`
```python
DEFAULT_DEEPAGENTS_INTERRUPT_ON = {"write_file": True, "edit_file": True, "execute": True}
```
**验证**：DB 实证 0 个 pending permission。纯对话不触发；涉及文件操作会触发但 agent 通常在模型调用阶段就失败了。
**修复方案**：低优先级，暂缓。

#### P2-5：openai init_chat_model 失败【仍存在 ✗】

**验证**：secure_storage 无 `cloud_openai_key`，`init_chat_model("openai:gpt-4o")` 失败。DB 实证 3 次。
**修复方案**：UI 引导配置 openai key，或默认用 deepseek。

---

## 模块审查结论（全部通过）

| 模块 | 文件 | 结论 |
|------|------|------|
| 跨线程事件总线 | `agent_session/events.py` | ✓ `call_soon_threadsafe` 跨线程投递，QueueFull 终态保护。`6653319` 已改进。 |
| 恢复逻辑 | `agent_session/services/recovery_service.py` | ✓ 保守策略（直接标记 needs_manual_review）有意为之。 |
| HITL 审批 | `agent_session/permission.py` | ✓ 纯对话不触发。成功 session 0 permission parts 实证。 |
| secure_storage | `security/encryption.py` | ✓ vault 在 `server/data/.vault`，deepseek 配置正确。 |
| 事件总线 SSE | `agent_sessions.py:470-548` | ✓ 心跳 15s，终态检测正常。 |

---

## 7 月 9 日已修复的相关问题（非本报告 P0）

以下问题在 `6653319`/Phase-0/Phase-1 提交中已修复，**但不直接解决本报告的 P0 问题**：

| 修复 | 提交 | 关联 |
|------|------|------|
| checkpointer 泄漏（每次 prompt 独立 checkpointer） | `6653319` | 改善 P1-2，但未清理已有膨胀 |
| 事件总线跨线程改进 | `6653319` | 改善稳定性，非 P0 |
| 锁字典泄漏（`_session_start_locks.pop`） | `6653319` | 改善 P0-3 的副作用，但 daemon 未改 |
| 推理状态端点降级 | `72e396a` | 改善 P1-3 的容错，但未启动服务 |
| Phase-0 安全加固 | `5dfafe4` | JWT/CUA admin/runtime_policy，非 P0 |
| Phase-1 GPU 协调 | `61a6092` | GPU lease，非 agent P0 |

---

## 修复路线图

### 阶段一：立即可做（恢复基本可用，不改代码）

```bash
# 1. server/.env 增加
ALLOW_LOCAL_AGENT_AUTH=true

# 2. 配置 deepseek（secure_storage 已有正确配置：deepseek-chat + 有效 key）
#    创建 session 时确认 model=deepseek-chat（不是 deepseek-v4-flash）

# 3. agent 执行期间不要重启后端

# 4. 统一从项目根目录启动（避免 DB 分裂）
uv run python -m uvicorn server.main:app --host 127.0.0.1 --port 8010
```

### 阶段二：短期修复（1-2 天，改代码）

| 优先级 | 问题 | 修复 |
|--------|------|------|
| 1 | P0-4 DB 路径 | `APP_DB_PATH` 改绝对路径 + 合并双 DB |
| 2 | P0-3 daemon 线程 | `daemon=False` + lifespan shutdown 优雅中断 |
| 3 | P1-6 模型名 | 清理 `model_selector.py` 预设列表 |
| 4 | P2-3 extra_body | 移除 `model_adapter.py:149` 硬编码 |
| 5 | P1-1 鉴权 | `.env` 加 `ALLOW_LOCAL_AGENT_AUTH=true` |
| 6 | P2-1 日志 | 确认 `enable_json` 默认 False |

### 阶段三：中期修复（1-2 周）

| 优先级 | 问题 | 修复 |
|--------|------|------|
| 1 | P0-5 coroutine | 审查 `2258b83` diff，定位 async/sync 边界 bug |
| 2 | P0-1 tool calling | 本地推理实现 tool calling，或强制云端模型 |
| 3 | P0-3 根治 | detached 执行改独立子进程 + SQLite 队列 |
| 4 | P1-2 checkpoint | TTL 清理脚本 |
| 5 | P1-4/P1-5 审批 | SSE 推送审批事件 + 前端展示 + async subagent waiting 不误判 |
| 6 | P1-3 inference | 启动脚本拉起 inference_server |

---

## 附录：关键代码路径索引

| 组件 | 文件 | 关键行 | 修复状态 |
|------|------|--------|----------|
| 本地推理拒绝 tool | `api/inference/openai_routes.py` | `_validate_supported_features` (L363) | ✗ |
| daemon 线程 | `agent_session/services/background_task_manager.py` | `daemon=True` (L166) | ✗ |
| DB 路径分裂 | `core/storage.py` | `APP_DB_PATH` (L25) | ✗ |
| 模型配置判定 | `agent_session/services/session_lifecycle.py` | `resolve_session_model_availability` (L110) | ✗ |
| extra_body 硬编码 | `agent_session/model_adapter.py` | thinking (L149) | ✗ |
| async subagent 误判 | `agent_session/async_subagents.py` | waiting→failed (L314) | ✗ |
| 预设模型名 | `deepagents_reference/.../model_selector.py` | deepseek-v4-flash (L67) | ✗ |
| 鉴权策略 | `security/runtime_policy.py` | `allow_local_agent_auth` (L49) | ✗ |
| HITL 审批 | `agent_session/permission.py` | `DEFAULT_DEEPAGENTS_INTERRUPT_ON` (L12) | ✗（低优先级） |
| 事件总线 | `agent_session/events.py` | `AgentSessionEventBus` (L21) | ✓ 已改进 |
| 恢复逻辑 | `agent_session/services/recovery_service.py` | `recover_active_sessions_after_restart` (L123) | ✓ 设计合理 |
| checkpointer | `agent_session/deepagents_runtime.py` | `_open_checkpointer` (L639) | ✓ 已改进 |
| secure_storage | `security/encryption.py` | `SecureStorage` (L27) | ✓ 正常 |
| Agent 定义 | `agent_session/agents/build.agent.yaml` | `default_provider: openai` | — |
| 实际配置 | `server/.env` | `ENABLE_AUTH=false` | 需加 ALLOW_LOCAL_AGENT_AUTH |
