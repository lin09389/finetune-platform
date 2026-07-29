# server/agent_session AGENTS.md

本文件只覆盖 `server/agent_session/` 子树（Agent Session 领域包）的约定、禁止事项与本地验证命令。项目级概述、命令面与安全边界见根 [`AGENTS.md`](../../AGENTS.md)；目录树详解、设计模式与 API 端点全表见 [`docs/architecture-reference.md`](../../docs/architecture-reference.md)；关键决策见 ADR-0001（Agent Session 唯一运行时）与 ADR-0011（DeepAgents 唯一执行循环），位于 [`docs/adr/`](../../docs/adr/)。

## 子树约定

- **DeepAgents 运行时边界（ADR-0011）**：DeepAgents 是唯一生产 Agent 执行循环；`DeepAgentsSessionRunner`（`deepagents_runtime.py`）是唯一会话执行器，`AgentSessionService`（`service.py`）只是薄产品宿主。`runtime_factory.DeepAgentsRuntimeFactory` 是平台 `AgentRuntimeContract`（`runtime_contract.py`）到 DeepAgents `create_deep_agent` 的唯一桥；后端路由由 `runtime.py` 构建（`/workspace/` 真实文件系统、`/context/`、`/large_tool_results/`、`/conversation_history/` 状态后端），`project_chat_readonly` 模式用虚拟只读 FilesystemBackend。`deepagents_compat.py` 仅做 torch/transformers pytree 兼容补丁，构建前调用。
- **会话生命周期**：状态全集与分组以 `status.py` 为单一事实源（EXECUTOR_BOUND 重启即丢失；WAITING 保留 checkpoint；TERMINAL 终态）。所有 status/phase/metadata/latch 转换必须经 `AgentSessionStateMachine`（`session_state_machine.py`）的 `mark_*` 方法，每个转换同步 execution plan 状态。生命周期入口在 `service.py` 门面（委派 `services/` 下 Lifecycle/BackgroundTask/Approval/Recovery/EventBroadcast 服务）；重启恢复走 `RecoveryService.recover_active_sessions_after_restart`。
- **持久化**：`repository.py` 写主 SQLite（`core.storage.APP_DB_PATH`）的 `agent_sessions` / `agent_parts` / `agent_events` / `agent_subtasks` / `agent_subtask_events` / `agent_training_links` 表，列级迁移用 PRAGMA 补列。
- **Checkpoint 持久化**：LangGraph checkpoint 用独立 SQLite（默认 app.db 同目录 `langgraph_checkpoints.db`，`LANGGRAPH_CHECKPOINT_DB` 可覆盖），与业务库分离避免争用。`deepagents_checkpoint.get_checkpointer` 是唯一 checkpointer 工厂（AsyncSqliteSaver 单例 + WAL + `LANGGRAPH_SQLITE_BUSY_TIMEOUT` 在此生效，默认 30000ms）。
- **异步子 Agent 隔离**：`AsyncSubagentService`（`async_subagents.py`）为每个子任务创建独立**子会话**并记录 `agent_subtasks`，asyncio.Semaphore 限并发（默认 2），事件经 notify_event 回传父会话（`async_subtask_*` 事件类型）。委派授权以 `async_subagent_policy.py` 为准：父 Agent 须 `can_delegate` 且目标在 `async_subagent_targets` 内、目标须 `can_be_handoff_target`。
- **训练工具路由**：`training_tools.py` 的会话级工具（propose/submit/resume/cancel/get_training_summary）一律经 `agent_training.service.AgentTrainingService` 走控制面，不直接调训练引擎；变更类工具（`TRAINING_MUTATING_TOOL_NAMES`）强制 DeepAgents HITL + 一次性授权；仅 build agent 且 task_mode ∈ {train, hybrid} 启用。训练进度对账走 `training_run_sync.py`：只读读取 Worker store，绝不把 Agent repository 交给 Worker。
- **阶段工具投影**：`phase_tool_router.py` 按阶段（inspect/plan/implement/verify/review/deliver）× 工具类别产出 `PhaseToolProjection`（schema `agent.execution.phase_projection.v1`），叠加 Agent manifest tool_policy 白名单与 goal plan file scope hints。
- **权限与审批**：自治模式（confirm_all / safe_auto / read_only）与文件系统权限档位（build/readonly/deny_all）以 `permission.py` 为准；显式 `metadata.deepagents_interrupt_on` 永远优先于模式默认值；`.env` 等敏感路径文件系统级拒绝。HITL 决策打包用 `approval.py`。失败保护由 `failure_guard.AgentFailureGuard` 观察事件流（连续失败/无进展/无动作阈值触发 `AgentLoopGuardTriggered`）。
- **事件系统分工**：`events.AgentSessionEventBus` 负责进程内 SSE 扇出（有界队列，终态事件挤占）；`deepagents_events.DeepAgentsEventMapper` 把 DeepAgents 流事件映射为持久化 parts/events 并驱动状态机；`execution_plan_events.apply_execution_event_to_session` 把工具/审批/子任务/恢复事件回放进 metadata 中的 execution plan。
- **API 分工**：HTTP 入口在 `server/api/agent_sessions.py`（另有 `agent_eval.py`、`cloud_chat.py` 复用），API 层只做鉴权（`get_agent_session_user`）、请求模型与 HTTP 语义；业务逻辑全部在本包（见 `server/api/AGENTS.md` 薄路由层约定）。

## 禁止事项

- 禁止在 DeepAgents 之外新增第二个 Agent 执行循环，或让平台工作流成为第二个 LLM planner（ADR-0011：两个 harness 不得嵌套；替换须实现显式 `AgentRuntimeProvider` 契约）。
- 禁止绕过 `AgentSessionStateMachine` 直接写会话 status/phase/latch（会造成 execution plan 与状态漂移）。
- 禁止绕过 `deepagents_checkpoint.get_checkpointer` 自建 checkpointer，或把 LangGraph checkpoint 写入业务 app.db。
- 禁止训练工具直接调用 `training_engine/` 或让 Worker 持有 Agent repository（一律走 `AgentTrainingService` 控制面 + `training_run_sync` 只读对账）。
- 禁止将变更类训练工具（submit/resume/cancel）移出 HITL 审批，或绕过 `async_subagent_policy` 的 can_delegate/can_be_handoff_target 校验启动子 Agent。
- 禁止在 `chat_agent/` 或其他模块复活工具执行路径（ADR-0001：`server/agent_session/` 是唯一开发 Agent 运行时，chat_agent 仅做意图分类）。

## 本地验证命令

```bash
# 仓库根目录执行（完整跑需 uv sync --frozen --extra all --extra dev 环境）

# 语法快速检查（Agent 链路核心文件）
python -m py_compile server/agent_session/repository.py server/agent_session/service.py server/agent_session/async_subagents.py server/agent_session/deepagents_runtime.py server/agent_session/deepagents_checkpoint.py server/tests/test_agent_session_deepagents_runtime.py

# 运行时/checkpoint/子 Agent 集成回归（核心）
python -m pytest server/tests/test_agent_session_deepagents_runtime.py -q

# Agent 链路重点回归（与根 AGENTS.md 一致）
python -m pytest server/tests/test_agent_session_deepagents_runtime.py server/tests/test_agent_session_auth_optional.py server/tests/test_agent_frontend_diagnostics.py server/tests/test_agent_execution_plan.py server/tests/test_agent_execution_plan_events.py server/tests/test_agent_execution_plan_recovery.py server/tests/test_agent_trajectory.py -q

# 按改动域选择
python -m pytest server/tests/test_agent_session_deepagents_events.py -q          # 事件映射
python -m pytest server/tests/test_agent_session_training_tools.py -q             # 训练工具路由/HITL
python -m pytest server/tests/test_agent_session_tool_trust.py -q                 # 权限/工具信任
python -m pytest server/tests/test_agent_session_project_chat.py -q               # 只读项目讨论
python -m pytest server/tests/test_agent_session_context_engineering.py -q        # 上下文工程
```
