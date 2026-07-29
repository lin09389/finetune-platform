# 架构参考：目录结构 / 设计模式 / API 端点

> 本文承接自根 `AGENTS.md`（2026-07 指令上下文重构时迁出），收录后端/前端目录树详解、25 条核心设计模式与 API 端点全表。**以代码为准**：若本文与代码冲突，以代码为准并回头修订本文档。后端应用装配与能力边界以 `server/apps/routers.py`、`server/apps/lifespan.py`、`server/apps/capability_registry.py` 和 `/api/info` 为准。
>
> 相关文档：[AGENTS.md](../AGENTS.md)、[capability-truth-table.md](capability-truth-table.md)、[backend-application-profiles.md](backend-application-profiles.md)、[dependency-profiles.md](dependency-profiles.md)

## 后端结构

```
server/
├── main.py                       # 向后兼容入口：导出 combined app，保留 server.main:app
├── apps/                         # 应用装配边界（combined / agent / finetune）
│   ├── capability_registry.py    # GA/beta/experimental 能力目录（单一事实源）
│   ├── factory.py                # FastAPI 工厂、公共中间件、异常处理、健康与 info 端点
│   ├── routers.py                # 分域 Router 所有权与按需注册（含 experimental 双挂载）
│   ├── lifespan.py               # common / Agent / Finetune 生命周期组合 + 服务 close
│   ├── profiles.py               # combined / agent / finetune profile 定义
│   ├── combined.py               # 默认完整应用入口
│   ├── agent.py                  # Agent Workspace 独立入口
│   └── finetune.py               # 训练、模型与本地推理独立入口
├── training_worker/              # SQLite 持久化训练队列 + 独立 GPU Worker
│   ├── repository.py             # job/event/lease/worker 注册表
│   ├── worker.py                 # 领取、续租、取消、崩溃恢复与训练执行
│   └── __main__.py               # python -m server.training_worker
├── inference_server/             # 独立本地推理服务（OpenAI-compatible + internal auth）
│   ├── app.py                     # 原生 scheduler/backend 所有者
│   └── __main__.py               # python -m server.inference_server
├── inference_provider/           # 控制面 HTTP Provider、重试、超时与云端降级
│   ├── client.py
│   ├── fallback.py
│   └── runtime.py
├── api/                          # FastAPI 路由层（由 apps/routers.py 按 profile 注册）
│   ├── __init__.py
│   ├── device.py                 # /device 设备信息（GPU/CPU/内存）
│   ├── models.py                 # /models 模型管理（下载/删除/导出）
│   ├── datasets.py               # /datasets 数据集管理
│   ├── training.py               # /training 训练控制（启动/停止/恢复/SSE 进度）
│   ├── evaluation.py             # /evaluation 模型评估（后台执行/轮询/人工评分）
│   ├── deployment.py             # /deployment 模型部署包管理
│   ├── inference/                # /inference 控制面推理路由（包）
│   │   ├── routes.py / facade.py #   路由 + 服务降级映射（503/504 + Retry-After）
│   │   ├── scheduler.py / pipeline.py / warmer.py / performance.py
│   │   ├── openai_routes.py / openai_schemas.py  # OpenAI 兼容面
│   │   ├── circuit_breaker.py / grpc_server.py
│   │   └── backends/             #   huggingface/ollama/llama_cpp/cloud
│   ├── inference_proxy.py        # 控制面 → 独立 inference_server 代理
│   ├── model_runtime.py          # 模型运行时总览/下载进度等
│   ├── chat.py / chat/           # /chat 兼容 + /chat/sessions
│   ├── chat_branch.py / chat_share.py / chat_agent.py
│   ├── agent_sessions.py         # /agent-sessions 生命周期 + SSE + 异步子任务
│   ├── agent_eval.py             # /agent-eval 本地能力基线、dry-run 与双门禁真实评测
│   ├── agent_terminals.py / agents.py
│   ├── auth.py / cloud_chat.py / code_executor.py / compat.py
│   ├── context.py / cua.py / entity.py / errors.py / file_parser.py
│   ├── gateway_api/ / heartbeat.py / mcp.py / ocr.py
│   ├── inference_engine/         # 引擎选择（已迁 inference_server，主 app 不再注册）
│   ├── knowledge/ / memory/      # RAG 与记忆包路由
│   ├── model_center.py           # /model-center ModelScope/HuggingFace
│   ├── response.py / runtime.py / setup/ / types.py
│   └── workspace.py
├── agent_session/                # 唯一 Agent 执行底座
│   ├── service.py                # AgentSessionService 门面（委托 services/*）
│   ├── services/                 # 会话域服务拆分
│   │   ├── background_task_manager.py  # prompt/resume 后台 task 注册与取消
│   │   ├── session_lifecycle.py  # 创建/状态推进
│   │   ├── recovery_service.py   # 重启恢复 / 节点恢复
│   │   ├── approval_service.py   # 审批决策
│   │   ├── event_broadcast.py    # 事件广播
│   │   ├── model_call_coordinator.py
│   │   └── utils.py
│   ├── repository.py             # 会话/事件/parts 持久化（SQL 聚合统计）
│   ├── models.py / state.py / status.py / events.py
│   ├── session_state_machine.py  # 会话状态机
│   ├── parser.py                 # 多 part 解析
│   ├── diagnostics.py            # 前端诊断聚合
│   ├── trajectory.py             # 轨迹门控评分器
│   ├── failure_guard.py          # 失败收尾门控
│   ├── agent_registry.py         # 加载 Agent Manifest v2
│   ├── agents/                   # 内置 Agent Manifest v2（build/explore/review）
│   ├── execution_plan.py         # 编排事实源（替代旧 task_plan/todos）
│   ├── execution_plan_events.py / execution_context.py / orchestration_planner.py
│   ├── artifact_extractor.py / model_adapter.py / model_capabilities.py
│   ├── runtime.py / runtime_factory.py / runtime_contract.py / runtime_policy.py
│   ├── project_chat.py / workspace_view.py / terminal_manager.py
│   ├── approval.py / permission.py
│   ├── async_subagents.py / async_subagent_policy.py
│   ├── deepagents_runtime.py     # DeepAgents/LangGraph 运行时桥接（含 aclose/WeakSet）
│   ├── deepagents_checkpoint.py  # LangGraph SQLite checkpoint（busy_timeout + WAL）
│   ├── deepagents_compat.py / deepagents_events.py
├── agent_eval/                   # Agent 能力评测 schema/loader/runner/隐私与生产 v1 fixtures
│   ├── models.py / loader.py / runner.py / validators.py / privacy.py
│   ├── real_model.py / agent_session_adapter.py
│   └── resources/v1/             # 版本化 catalog、隐藏 oracle、完整性清单与独立场景
├── chat_agent/                   # 聊天意图分类业务逻辑（API 路由在 api/chat_agent.py）
│   ├── intent.py / service.py / models.py
├── cloud_models/                 # 云端模型访问统一层（repository/resolver/service）
├── core/                         # 核心模块
│   ├── config.py                 # Pydantic 配置（settings + production validators）
│   ├── config_loader.py / logging.py / tracing.py
│   ├── storage.py / storage_worker.py / db_manager.py
│   ├── release_registry.py       # 评估/部署事务注册表、乐观版本与跨进程租约
│   ├── migrations/               # SQL 迁移脚本（001 ~ 016）
│   ├── training_state.py / training_queue.py / training_context.py / training_events_v2.py
│   ├── training_gateway.py       # 控制面 → 训练 worker 网关
│   ├── inference_gateway.py      # 控制面 → 推理服务网关（含 list_models 等降级）
│   ├── model_cache.py            # 模型缓存（LRU）
│   ├── gpu_coordination.py       # 训练/推理跨进程 GPU lease（claim/release）
│   ├── model_warmup.py / runtime_policy.py / agent_run_state.py / state.py
│   ├── performance.py / utils.py / quantization.py / batching.py / kv_cache.py
│   ├── streaming.py / offline_cache.py / distributed_cache.py / memory_monitor.py
│   ├── hardware_profile.py / mirror_manager.py / proxy_config.py
│   ├── conversation_manager.py / entity_recognition.py / context_understanding.py
│   ├── error_handling.py / file_parser.py / tesseract.py / user_experience.py
│   ├── inference/                # 推理引擎实现（hf/llama_cpp/ollama/vllm 等）
│   └── interfaces/               # 抽象接口（vector_store / inference_engine / embedder / cache）
├── training_engine/              # 训练引擎（pipeline/callbacks/checkpoint/loader/strategies）
│   ├── pipeline.py / training_thread.py / callbacks.py
│   ├── checkpoint_manager.py     # 原子 metadata 写（tmp + fsync + replace）
│   ├── config_builder.py / dataset_loader.py / dataset_formatter.py
│   ├── model_loader.py           # 含 GPU lease claim
│   ├── strategies.py / schemas.py / events.py / reporter.py / training_logger.py / errors.py
├── inference_service/            # 推理服务层（service/callbacks/types）
├── ai/                           # AI 网关（统一 HTTP 客户端池）
│   ├── gateway.py                # gateway + close_http_clients（lifespan shutdown）
│   └── providers.py
├── backends/                     # 后端适配（swift_backend.py 等）
├── workspace/                    # 工作区源码包（注意：workspaces/ 是运行时数据目录）
│   ├── file_api.py / task_api.py / file_manager.py / task_manager.py
│   ├── project_manager.py / version_control.py / local_paths.py / models.py
├── gateway/                      # Gateway 统一入口（WebSocket 控制平面，experimental）
│   ├── server.py / router.py / session.py / binding.py
│   ├── agent_isolation.py / device_auth.py / cross_agent.py / models.py
├── heartbeat/                    # Heartbeat 主动唤醒（experimental；task_executor.py）
├── mcp/                          # MCP 工具集成（client/protocol/server_manager/tool_registry）
├── cua/                          # 计算机使用 Agent（screen/keyboard/mouse/ocr/player/recorder/safety）
├── context/                      # 项目上下文理解（scanner/indexer/retriever/builder/pack/budget）
│   ├── project_scanner.py / symbol_extractor.py / code_indexer.py
│   ├── service.py                # ContextService（lifespan 初始化 + close）
│   ├── builder.py / pack.py / budget.py / formatter.py / knowledge_integration.py
│   ├── session_store.py / deepagents.py / models.py / retrievers/
├── rag/                          # RAG 系统（embedder/vector_store 支持 close 资源清理）
│   ├── embedder.py / vector_store.py / document_parser.py / text_chunker.py
│   ├── service.py / evaluator.py / reranker.py / hybrid_retriever.py / models.py
├── memory/                       # 智能记忆系统（memory_service 支持 close）
├── skills/                       # Skills 系统
├── security/                     # 安全功能
│   ├── runtime_policy.py         # 阶段 0 统一策略（生产硬关 / 本地显式 opt-in）
│   ├── rate_limiter.py / rate_limiter_redis.py / file_sandbox.py
│   ├── middleware.py
│   ├── auth_middleware.py        # get_current_user / require_roles / require_cua_admin
│   ├── jwt_auth.py               # JWT fail-closed（禁止静默生成密钥）
│   ├── sandbox.py / prompt_security.py / csrf.py / data_masking.py
│   ├── encryption.py / encryption_storage.py / audit_log.py
├── services/                     # 跨模块服务（如 training/）
├── scripts/                      # 临时调试/运维脚本（非 pytest；禁止生产 import）
├── config/                       # 配置辅助（如 inference.yaml）
├── requirements.txt              # uv export 全量（不要手改）
├── requirements-api.txt          # API/控制面 profile
├── requirements-training.txt     # 训练 worker profile
├── requirements-inference.txt    # 推理服务 profile
└── tests/                        # 正式测试套件（约 92 个 test_*.py，见 AGENTS.md「测试」一节）
```

> 说明：`workspaces/`、`outputs/`、`logs/`、`data/`、`modelscope_cache/`、`agent_kernel/` 等是**运行时数据/缓存目录**，不纳入结构树。

## 前端结构

```
client/src/
├── main.tsx                      # ReactDOM 挂载入口（导入 styles/index.css，非根 index.css）
├── App.tsx                       # 路由表 + 布局壳（/agent 为独立沉浸式路由；ExperimentalRouteGuard）
├── capability/                   # 能力分层前端对齐（读 /api/info）
│   ├── tiers.ts                  # ROUTE_CAPABILITY + experimental_enabled 助手
│   └── ExperimentalRouteGuard.tsx
├── agent/                        # /agent 唯一生产 Agent Workbench；同时是默认应用入口
│   ├── attention/                #   Attention Center 统一介入模型与派生逻辑
│   ├── config/                   #   工作台设置 / 面板布局版本化
│   ├── diagnostics/              #   前端会话级诊断明细与聚合上报
│   ├── protocol/                 #   SSE decoder、协议守卫、未知事件隔离与 part 合并
│   ├── runtime/ / transport/     #   归一化 reducer、刷新恢复、REST/SSE 传输
│   ├── commands/ / selectors/    #   幂等命令、currentActivity/sessionStatus、UI 派生
│   ├── components/               #   时间线、审批、终端 Dock、右栏、ActivityBar、子 Agent 等
│   │   ├── AgentActivityBar.tsx / AgentRightDock.tsx / AgentTerminalDock.tsx
│   │   ├── AgentResizeHandle.tsx / SubagentModal.tsx / WorkbenchSettingsDrawer.tsx
│   │   └── AgentRunTimeline / AgentTaskComposer / AgentWorkspaceView / Agent*Rail ...
│   ├── workbench/                #   AgentWorkbenchPage + usePanelResize + Shell
│   └── testing/                  #   脱敏事件夹具、12 条业务链路与规范化 Store 投影
├── pages/                        # 页面组件（与 App.tsx 路由对应）
│   ├── Dashboard.tsx / DeviceInfo.tsx / DatasetManager.tsx
│   ├── ModelRuntimeCenter.tsx    # /models 唯一模型入口（本地列表/下载/运行时就绪）；/modelhub → 重定向
│   ├── Training/                 # /training（HyperparameterPanel / TrainingDashboard / highlightLog）
│   ├── ChatNew.tsx               # /chat 纯聊天（App lazy 别名 Chat；虚拟化；不含 Agent）
│   ├── Inference.tsx / Evaluation.tsx / KnowledgeBase.tsx
│   ├── ProjectContext.tsx / History.tsx / WorkspaceManager.tsx / MemoryPage.tsx
│   ├── Deployment.tsx / APIKeyManager.tsx
│   ├── CUAControl.tsx / ActionRecorder.tsx / MCPTools.tsx
│   ├── GatewayPage.tsx / HeartbeatPage.tsx
│   ├── DesignSystem.tsx / SharedChat.tsx
├── components/                   # 可复用组件
│   ├── Sidebar.tsx               # 导航 + capability 徽章；后端断开时 clear apiInfo
│   ├── HeaderBar.tsx / ErrorBoundary.tsx / MobileNav/
│   ├── chat/ / motion/ / shared/
│   └── ...（ChatMessage、CodeExecutor、ContextPanel、PerformanceMonitor、SwiftChecker 等）
├── hooks/                        # 通用 hooks
│   ├── useStreamResponse.ts      # 通用流传输层（StreamManager 清理稳定）
│   └── chat/                     # useChatStream / useOllamaConnection / useTypewriter
├── runtime/                      # RuntimeContext（embedder 等状态字段显式映射）
│   └── desktopRuntime.ts         # Electron protocol v1 与服务状态归一化
├── i18n/
├── services/                     # REST API 客户端（Phase-4：页面禁止新增散落 fetch）
│   ├── api.ts                    # 主 Axios；API_BASE_URL = VITE_API_URL 或 http://{hostname}:8010
│   ├── chatSessionApi.ts / conversationTreeApi.ts / chatShareApi.ts
│   ├── knowledgeApi.ts / cloudApi.ts / projectContextApi.ts / contextUnderstandingApi.ts
│   ├── ocrApi.ts / codeApi.ts / performanceApi.ts / swiftApi.ts
│   ├── memoryApi.ts / trainingApi.ts
│   ├── agentEvalApi.ts           # 本地 Agent 能力概览（不触发真实模型运行）
│   └── StreamManager.ts          # 流式传输（chat stream 等可直接拼 API_BASE_URL，属允许例外）
├── store/                        # Zustand（appStore / chatStore / chatExperimentState）
├── utils/                        # agentSessionStream、errorHandler、diffHunks 等
├── theme/                        # ThemeProvider + motion-tokens
├── styles/                       # 全局 CSS 与设计 token（唯一入口 styles/index.css）
├── types/
├── test/                         # Vitest 测试（40 文件，见 AGENTS.md「测试」一节）
└── stories/                      # Storybook 示例
```

## 核心设计模式

**1. 能力分层（ga / beta / experimental）**
- 后端：`apps/capability_registry.py`；前端：`client/src/capability/`。`/api/info` 是运行时权威。

**2. 运行时依赖 profile 拆分**
- 单一仓库 + 单一 `uv.lock`；按进程用 optional extras 安装（`agent`/`rag`/`cua`/`training`/`inference` 等）
- API / training-worker / inference-service 可分镜像；详见 `docs/dependency-profiles.md`

**3. 线程安全训练状态**
- `core/training_state.py` 的 `TrainingState` 使用 `asyncio.Lock` + 后台工作线程
- 基于 `core/training_context.py` 的 `TrainingContext` 单例（lifespan init/shutdown）

**4. 训练队列系统**
- `core/training_queue.py` 的 `TrainingQueue` 管理并发训练任务
- 基于优先级的调度（HIGH/NORMAL/LOW）；完成/失败时自动清理资源

**5. 模型缓存**
- `core/model_cache.py` 的 `ModelCache` 减少重复加载；LRU + 自动 GPU 内存管理

**6. GPU 跨进程互斥（阶段 1）**
- `core/gpu_coordination.py`：文件 lease（原子 tmp + `os.replace`），过期回收崩溃进程
- 训练：model_loader claim / pipeline cleanup + worker finally release
- 推理：scheduler load claim / unload 或 shutdown release
- `GPU_COORDINATION=off` 仅非生产环境

**7. 推理韧性与降级（阶段 1）**
- 阻塞 I/O 经 `asyncio.to_thread` 卸下事件循环（如 deployment target 解析）
- `inference/facade` 与 `core/inference_gateway` 对 list_backends / list_models 等返回 503/504 + `Retry-After`
- RAG/context/memory/chat session 等在 lifespan shutdown 时 `close()` 释放资源
- checkpoint metadata 原子写（tmp + fsync + replace）

**8. SSE 进度流式传输**
- 训练进度：`GET /training/progress/stream`
- Agent Session 事件：`GET /agent-sessions/{id}/events/stream`
- 前端 EventSource 消费，断线退避重连（`utils/agentSessionStream.ts`）

**9. 检查点恢复**
- 训练：`POST /training/resume/{task_id}/{checkpoint}`
- Agent Session 节点级恢复（见 AGENTS.md「Agent 后台任务与恢复」）

**10. Gateway 统一入口（experimental）**
- WebSocket 控制平面（`server/gateway/server.py`）；消息路由、设备配对与认证、事件广播

**11. Binding Router（最具体匹配优先）**
- `gateway/binding.py` 支持 peer/guild/channel/team/account 多维度绑定

**12. Agent 隔离管理**
- 独立 workspace/session/skills；能力权限与路径访问控制

**13. Heartbeat 主动唤醒（experimental）**
- 定期唤醒 Agent，检查/汇报/提醒任务，避免 CPU 空转轮询（`heartbeat/task_executor.py`）

**14. 三层记忆系统**
- 短期（Attention Context）/ 中期（Episodic）/ 长期（Semantic）

**15. Agent Session 生命周期 + SSE**
- 门面：`agent_session.service.AgentSessionService`；实现拆分在 `agent_session/services/*`
- `POST /agent-sessions` 创建，`POST /agent-sessions/{id}/prompt` 触发 background 任务
- `GET /agent-sessions/{id}/events/stream` 通过 SSE 推送 part / status / done
- SSE 端点必须关闭代理缓冲并维持心跳；前端连接逻辑集中在 `client/src/utils/agentSessionStream.ts`
- 终态：`completed/failed/interrupted/needs_manual_review/waiting_approval/waiting_permission`

**16. 审批门控（DeepAgents interrupt 包装）**
- 当前 Agent 执行引擎是第三方 `deepagents` 库（`agent_session/runtime_factory.py` 直接 `create_deep_agent`，`deepagents` 是硬依赖，缺失则抛 `DeepAgentsUnavailable`）。平台不再自研工具循环
- 审批门控建立在 DeepAgents 的 interrupt 机制之上：工具运行前若命中 ask 规则，DeepAgents 触发 interrupt，会话进入 `waiting_permission`/`waiting_approval`
- 决策端点：`/agent-permissions/{id}/approve|reject` 与 `/agent-actions/{id}/approve|reject|execute` 内部都走 `_approve_deepagents_action` / `deepagents_runner.resume`，是 interrupt 的包装，不再是独立的 patch/command action 流程
- Resume 必须通过后台任务继续执行，禁止在 HTTP 审批请求内直接 `await` 长耗时 Agent resume
- Permission part 更新必须使用 pending 状态条件更新，避免重复点击或并发请求排入多个 resume
- **文件操作**：DeepAgents harness 内置 `ls/read_file/glob/grep/write_file/edit_file`，项目挂载在虚拟 `/workspace/`（`runtime.py` 的 `build_deepagents_backend` 用 `FilesystemBackend(root_dir=project_path.resolve(), virtual_mode=True)`）。**路径隔离由 DeepAgents backend 负责，平台层不再有 `patch_engine` 路径校验**（旧 `patch_engine.py` 已删除）
- **命令执行**：走 DeepAgents 官方 sandbox execute 工具，system prompt 明确「命令不需要平台白名单审批」。旧 `agent_session/command_policy.py` 已删除；终端失败输出摘要逻辑已内联到 `terminal_manager.py`，不再存在平台层命令白名单把关机制

**16a. Agent 工具轨迹保障**
- Agent Manifest v2 支持结构化 `FewShotExamples.steps`（`assistant/tool_call/tool_result`）和可选 `TrajectoryPolicy`；旧 `assistant` 文本示例保持兼容
- 内置 Build Agent 开启轨迹门控：已有文件写入前必须成功读取目标文件；新文件创建前必须查看父目录，非空目录还必须读取一个同类文件
- 工具失败或验证失败后，再次修改受影响文件前必须重新读取真实内容；违规写入会被中间件短路并发布 `trajectory_guard_blocked`，不会进入 HITL 审批
- 最终写入后必须存在成功验证；源码/测试/配置使用测试、构建、类型、lint 或语法检查，文档可通过最终重新读取确认
- `edit_file/write_file` 成功后会立即执行低成本静态检查：Python AST、JSON/YAML/TOML 解析、JavaScript `node --check`、TypeScript/TSX transpile 诊断；失败时恢复写前字节或删除无效新文件，并发布 `trajectory_static_validation_failed`

**16b. Controlled 工具编排模式（opt-in，2026-07-19 Task 9A-9D-1）**
- 平台在 `server/tool_platform/` 自建受管工具面（read/search/git-read/write/edit/execute/run_tests），经 `ToolGateway`（`server/tool_platform/gateway.py`）强制 policy/approval/dispatch/redaction/canonical 事件
- 模式由 `orchestration_mode` 决定（`metadata.orchestration_mode` 或 `AGENT_TOOL_ORCHESTRATION_MODE`）：`legacy`（默认，DeepAgents 内置工具）、`shadow`（只读快照绑定，不改执行）、`controlled`（平台受管工具经 Gateway 替换内置）
- controlled 模式下：legacy `execute` 入口被 `PlatformShellBackend(controlled_execute=True)` 硬拒不执行（Task 5 判 execute 对原生 LocalShellBackend UNSUPPORTED；平台 backend 是额外强制层）；`task`/`write_todos` 被排除（子代理留 Task 12）
- 启动守门：controlled 启动前校验全部内置被 exclusion 覆盖；缺失则回退 legacy（`_apply_controlled_cutover` in `deepagents_runtime.py`）
- 回滚：改回 `legacy`（仅新会话；运行中会话保留创建时模式）
- 限制：真实模型编码金路径未端到端回归；`server/scripts/run_controlled_build_smoke.py` 为手动冒烟（非 CI）

**17. 评估与部署发布注册表**
- `core/release_registry.py` 是评估运行与部署版本的持久化事实源，使用应用 SQLite 的 `release_runs` / `release_leases` 表
- `outputs/evaluations/*.json` 与 `outputs/deployment_packages/*.json` 仅作为兼容导出和旧数据导入来源，不允许作为并发状态事实源
- 评估后台任务使用带过期时间和心跳的跨进程租约；进程重启后，`pending/running/recovering` 任务由 lifespan 恢复
- 同一模型别名的部署激活必须通过单事务切换，保证最多只有一个 active 版本
- SQLite 连接池按路径缓存，但会安全淘汰无活跃连接的 LRU 池，避免多工作区或测试环境耗尽全局连接上限
- 完成门控最多自动纠正两次，仍不合规则进入 `needs_manual_review`，不得发布成功摘要
- 轨迹状态持久化在 session metadata 的 `trajectory_guard`，不新增数据库表；纯函数评分器和固定场景位于 `agent_session/trajectory.py` 与对应测试夹具

**18. Agent 后台任务与恢复**
- `BackgroundTaskManagerService`（`agent_session/services/background_task_manager.py`）维护 prompt/resume 后台 task 注册表；`interrupt_session()` 必须同时标记会话和取消对应 `asyncio.Task`
- 后台 prompt/resume 捕获异常后必须把会话推进到终态或 `needs_manual_review`，不能让 session 永久停留在 `running`
- 服务重启后 `recover_active_sessions_after_restart()`（`recovery_service`）扫描 ACTIVE 会话：**running/verifying/repairing** 因失去执行器标为 `needs_manual_review`（`process_restart` / `rerun_prompt`）；**waiting_approval/waiting_permission** 保留状态与 pending permission，并设 `next_action=continue_approval`，用户可继续 HITL + LangGraph `Command(resume)`（方案 A）
- 单次 prompt/resume 墙钟超时由 `AGENT_SESSION_MAX_SECONDS`（默认 3600）约束；超时 → `failure_kind=timeout` + `needs_manual_review`
- `/api/info.agent_ready` 暴露 session/context/memory 就绪快照（session 为硬依赖；context/memory 降级仅记 issues）
- `execution_plan` 是 Agent 编排事实源；旧 `task_plan` / `todos` / `write_todos` 只能作为兼容投影或历史概念，不能恢复为主路径
- 节点级恢复当前是手动触发：失败/中断/被拒绝节点会记录 `recoverable`、`recovery_action`、`recovery_history`，由用户通过 workspace 恢复按钮触发；系统不做自动 retry，也不承诺自动回滚工具副作用
- 恢复动作必须使用 per-node latch 防重复触发，恢复事件进入 execution timeline
- 异步子 Agent task 注册在 `AsyncSubagentService` 实例内；cancel/update/shutdown 都必须取消真实 `asyncio.Task`

**19. Electron 桌面运行时（Phase 9–10）**
- `electron/process-supervisor.js` 只管理自身启动的 control-plane、inference-service、training-worker；启动按依赖顺序，退出按 worker → inference → control-plane
- renderer 只通过 sandboxed preload 暴露的 protocol v1 读取公共状态；内部 JWT/服务密钥绝不进入 renderer
- IPC 文件读取必须来自系统选择器授予的精确文件；打开目录只接受登记工作区或选择器授予目录
- packaged renderer 使用 `app://renderer`，并支持 BrowserRouter fallback；导航来源和 IPC sender 都必须校验

**20. Agent 能力评测（Phase 9）**
- `server/agent_eval/resources/v1/` 是可发布的评测基线，不允许 API 读取 `server/tests/fixtures`
- catalog、每个 fixture 和 validator 均有 SHA-256 完整性校验；真实运行在一次性副本中执行
- `server/agent_eval` 不导入或复制 Agent 循环；live adapter 只能委托现有 `AgentSessionService`
- `POST /agent-eval/real-model/run` 默认 `dry_run=true`；真实调用必须同时满足 `ENABLE_REAL_MODEL_EVALUATION=true` 与 `explicit_opt_in=true`
- 报告禁止保存绝对路径、项目源码、完整 prompt、Authorization 或密钥；blocked 计入覆盖率分母但不计能力分数分母
- 子任务 metrics 使用 SQL 聚合，避免为统计一次加载全部事件历史
- DeepAgents/LangGraph SQLite checkpoint 需要配置 `busy_timeout`、WAL 和 `synchronous=NORMAL`；runtime 对 checkpointer 使用 `aclose()` + WeakSet 跟踪，降低泄漏与 `database is locked` 风险

**21. 聊天意图分类（Chat Agent）**
- **两层结构**：API 路由在 `server/api/chat_agent.py`（`POST /chat-agent/intent`），业务逻辑在 `server/chat_agent/` 包
- 该接口保留为后端兼容能力；当前生产前端不再通过聊天意图隐式创建 Agent Session
- `/chat` 只持久化普通聊天；所有 Agent 运行实体统一从 `/agent` 创建并存储在 `agent_sessions` 表

**22. 异步评估任务**
- `POST /evaluation/runs` 立即创建 pending run，后台补齐推理/指标；前端轮询 + 人工评分写回

**23. 前端动效与体验层**
- Framer Motion 封装在 `client/src/components/motion/`；token 在 `client/src/theme/motion-tokens.ts`
- Agent Workbench 面板拖拽：`agent/workbench/usePanelResize.ts` + Dock 组件

**24. 前端 API 客户端收敛（阶段 4）**
- REST：页面/组件禁止新增散落 `fetch()`；统一走 `client/src/services/*`（`api.ts` 或领域 `*Api.ts`）
- 流式/SSE：允许通过 `API_BASE_URL` + `EventSource`/`StreamManager`/`agentSessionStream` 拼 URL（非 REST CRUD）
- 错误信息优先 `extractApiErrorMessage` / `getApiErrorMessage`；非 2xx 由 Axios 拦截抛错
- 完成记录：`docs/history/phase4-completion-2026-07-09.md`

**25. AI 网关 HTTP 客户端池**
- `server/ai/gateway.py` 维护统一 HTTP 客户端池，lifespan shutdown 时 `close_http_clients()`
- 各 provider 在 `server/ai/providers.py`

## API 端点总表

完整 API 文档：`http://localhost:8010/docs`（Swagger UI）、`/redoc`、`/openapi.json`
元数据端点：`GET /api/info`（含 capability_tiers 分层）

端点按 `server/apps/routers.py` 的 profile 注册表为准，按能力分层分组：

**GA（正式）**
- 设备：`/device/info`、`/device/vram`
- 模型：`/models`、`/models/download`、`/models/{id}`
- 数据集：`/datasets`、`/datasets/upload`、`/datasets/{id}/statistics`
- 训练：`/training/status`、`/training/start`、`/training/stop`、`/training/progress/stream`、`/training/resume/...`
- 推理：`/inference/chat`、`/inference/stream`、`/inference/merge`、`/inference/performance`、`/inference/optimize`
- Chat Session：`/chat/sessions`、`/chat/sessions/{id}`、`/chat/sessions/{id}/messages`
- 知识库：`/knowledge/...`（`/v2/knowledge/...` 为旧前端兼容别名）

**Beta**
- 项目上下文：`/context/scan`、`/context/index`、`/context/retrieve`
- 记忆：`/memory/...`
- 模型中心：`/model-center/suggestions`、`/model-center/download/{task_id}`、`/model-center/local`
- 工作区：`/workspace/...`、`/files/...`、`/tasks/...`
- Agent 能力评测：`GET /agent-eval/overview`、`POST /agent-eval/real-model/run`（默认 dry-run，真实执行需双门禁）

**Agent（横跨 GA/Beta，核心运行时）**
- 兼容意图分类：`POST /chat-agent/intent`（当前生产前端不依赖）
- Agent Session：`/agent-sessions`、`/agent-sessions/{id}/prompt`、`/agent-sessions/{id}/events/stream`、`/agent-sessions/{id}/workspace`
- 前端诊断：`POST /agent-sessions/diagnostics/batch`；管理员摘要 `GET /agent-sessions/diagnostics/summary`
- 权限审批：`/agent-permissions/{id}/approve|reject`
- 动作审批：`/agent-actions/{id}/approve|reject|execute`
- Agent 终端：`/agent-terminals/...`
- Agent 注册表：`/agents`、`/agents/primary`、`/agents/{agent_id}`

**评估与部署**
- 评估：`/evaluation/runs`、`/evaluation/runs/{run_id}`、`/evaluation/runs/{run_id}/score`
- 部署：`/deployment/packages`、`/deployment/packages/{package_id}`

**Experimental**
- CUA：`/cua/...`
- Heartbeat：`/heartbeat/...`
- MCP：`/mcp/...`
- Gateway：`/gateway/status`、`/gateway/devices`、`/gateway/messages`、`/gateway/bindings`、`/gateway/ws`
- OCR：`/ocr/...`
- 动作录制：见前端 `/cua-recorder`

**其他/基础设施**
- 认证：`/auth/...`
- 云端 AI：`/cloud/...`
- 代码执行：`/code/...`
- 文件解析：`/file-parser/...`
- 对话分支/分享：`/chat-branch/...`、`/chat-share/...`
- 兼容层：`/compat/...`
- 实体识别：`/entity/...`
- 推理引擎选择：`/inference-engine/...`（由独立 inference_server 提供，主 app 不再注册）
- 运行时：`/runtime/bootstrap`
- 健康检查：`/`、`/health`、`/api/info`

## 架构收口现状（2026-07-15）

- `Chat` 旧兼容路由由 `api/chat.py`（薄）+ `api/chat/routes.py`（`/chat/sessions`）共同提供；新代码统一用 `/chat/sessions`
- `Training` 根别名 `GET /training` 已下线，统一使用 `/training/status`
- `Evaluation` 为后台执行 + 前端轮询，创建接口不再等待长推理完成
- `Agent Session`（`server/agent_session/` + `services/*`）是当前唯一的 Agent 运行时；`chat_agent/` 仅做意图分类业务逻辑，路由在 `api/chat_agent.py`
- `execution_plan` 是 Agent 编排事实源，旧 `task_plan`/`todos` 已退为兼容投影
- `Gateway / Heartbeat / CUA / MCP` 已是完整模块（不再是纯概念），但仍标记为 experimental，API/UI 可能变动
- 能力分层：后端 `capability_registry.py` + 前端 `client/src/capability/`；以 `/api/info` 为权威
- 阶段 0–2 后端：安全 fail-closed、GPU lease、experimental 路由隔离与降级（`docs/history/phase0-completion-2026-07-08.md` … `phase2-completion-2026-07-08.md`）
- 阶段 3–4 前端：Workbench 视觉一致性、REST fetch 收敛到 `services/*`（`docs/history/phase3-completion-2026-07-09.md`、`phase4-completion-2026-07-09.md`）
- 默认执行模式：`TRAINING_EXECUTION_MODE=worker`、`INFERENCE_EXECUTION_MODE=service`（pytest conftest 与生产默认一致；可用 `in_process` 回退）
- 依赖 profile 拆分：`requirements-{api,training,inference}.txt` + `docs/dependency-profiles.md`
- 临时脚本已迁出 `server/` 根目录 → `server/scripts/`
- Phase 9：Electron 已成为正式桌面运行时边界；Agent 能力评测 v1 与 Workbench 本地记分卡已接入，不改变 Coding Agent + 训练助手的双主线
- Phase 10：Windows x64 受管 Python runtime pack、原子激活/修复、窄 IPC、Workbench 状态卡和打包数据保护策略已接入；真实 Python 制品与签名安装器仍属于发布验收，不得用合成测试冒充
- Phase 11+ 蓝图已按实际进度修订：DeepAgents 保持唯一生产 Agent Loop，Pi 只作为“薄 Session 宿主 + 事件扩展”架构参考；下一阶段先收敛 AgentSession runtime binding、steering/follow-up、结构化 compaction 与统一事件脊柱，再进入沙箱、隔离 worktree、回退账本、复杂 Coding 和 Trace-to-Train（见 `docs/plans/2026-07-13-trusted-local-ai-engineer-roadmap.md` 与 ADR-0011）
