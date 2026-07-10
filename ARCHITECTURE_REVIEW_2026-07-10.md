# 架构深度评审报告 — Finetune Platform 2.x（总体重写版，勘误修订）

- **评审人**：Software Architect（架构通）
- **评审日期**：2026-07-10
- **修订日期**：2026-07-10（第二轮核查后勘误：修正了"默认关认证/限流"的误判、GitHub star 数据失真、`.env` 行号引用错误、`sandbox.py` 可达路径误导等；详见末尾"修订说明"）
- **评审范围**：`server/`（FastAPI 后端）、`client/`（React 前端）、部署与 CI/CD、安全与可观测性
- **方法**：代码库静态探查（4 条并行线：架构/代码质量、安全、性能/扩展、UX/可观测性）+ GitHub 同领域顶级开源项目对标（Star 数取自 GitHub API，检索日 2026-07-10）
- **状态**：**纯评审，未改动任何代码**（按用户要求；路线图均为"建议排期"，未执行）

---

## 0. 执行摘要

**一句话定位**：这是一个"广度型 AI 平台"——在同一定制化后端里同时承载 **微调（LoRA/QLoRA）+ 自托管推理 + Agent Workspace + RAG + CUA（宿主级计算机使用）**，其能力覆盖广度在标杆产品里独此一家。

**给决策者的三句话**
1. **先止血**：用户本地 `.env` 关闭了认证与限流（项目代码与模板默认开启，但 `.env` 覆盖了默认值）+ shell 命令注入 + CORS 凭据反射，这三项不修，其余优化都是给敞开的门装防盗窗。
2. **再打地基**：把"异步非阻塞"和"可观测性主干（结构化日志 + 应用级 metrics + 分布式追踪）"当成一等公民补齐，否则规模一大就会在凌晨三点以最痛的方式暴露。
3. **最后长生态**：把"静态能力表"演进为真正插件体系、把存储/协调换成可分布式方案（或显式声明单机天花板），是从"能用的内部平台"走向"可对外服务的顶级产品"的最后一跃。

**成熟度快照（10 分制，评审主观打分）**

| 维度 | 评分 | 一句话 |
|---|---:|---|
| 架构设计（分层纪律） | 7 | 新模块分层好，但 `core→api` 反向依赖 + 胖路由遗留 |
| 代码质量 / 测试 | 6 | 测试量大但关键分支薄、覆盖率不进门禁 |
| 性能 / 异步纪律 | 5 | 自研 `run_sync` 很好，却有多处绕过致事件循环阻塞 |
| 安全性 | 5 | 原语强（bcrypt/HS256/fail-closed/prod 硬失败）；`.env` 默认开启认证与限流，但用户本地覆盖会关；`sandbox.py` 注入与 CORS 反射是真实高危 |
| 可扩展性 | 4 | SQLite+文件锁封死水平扩展；"能力表"非插件体系 |
| 可维护性 / 观测 | 6 | 文档/CI 雏形好，但无 OTel/关联 ID、CI 门禁多为可选 |
| 用户体验 / a11y | 6 | 错误处理链完整、a11y 高于平均；轮询蔓延拖累流畅度 |
| Agent 能力 | 6 | 单 agent+CUA+持久化达一线；多 agent 团队、token 追踪、生态落后 |

> 结论：距顶级产品有 **2 个代差（可观测性主干、扩展/插件生态）** 与 **3 个落后（异步纪律、测试门禁、Agent token 追踪）**，但**广度护城河 + CUA/微调一体化**是真实差异化优势。注：原报告"安全默认关闭"为误判（项目代码默认开启认证与限流），已修正。

---

## 1. 评审范围与方法

- **代码探查**：4 条并行 Explore agent，分别覆盖 ① 架构/代码质量 ② 安全 ③ 性能/扩展 ④ UX/可观测性/CI-CD；所有结论附 `file:line` 证据。
- **对标基准**：GitHub API 实时拉取 Star/语言/描述/归档状态（2026-07-10）。分三组：
  - **平台/基础设施标杆**（Dify、Open WebUI、vLLM、LLaMA-Factory、Langfuse、MLflow）——对标"平台成熟度"。
  - **Agent 框架标杆**（n8n、browser-use、OpenHands、MetaGPT、AutoGen、CrewAI、LangGraph、OpenAI Agents SDK）——对标"Agent 编排能力"。
  - **编程 Agent 产品标杆**（OpenClaw、Codex、OpenCode）——对标"宿主级/终端 coding agent 产品形态"。
- **重要说明**：本项目是**广度型平台**，与单一能力的 LLaMA-Factory/vLLM 不是直接竞品；与 Dify/Open WebUI 在"平台成熟度"可直接对标；与 Agent 框架/编程 Agent 产品的对标见 §5.8。

---

## 2. 对标基准全景（GitHub 权威数据，2026-07-10）

### 2.1 平台 / 基础设施标杆

| 标杆项目 | Star | 定位 | 本项目最该借鉴的能力 |
|---|---:|---|---|
| **Dify** (langgenius/dify) | 148,358 | 生产级 LLM 应用平台 | 插件市场、Celery+Redis 任务队列、PostgreSQL、工作流编排、全链路观测 |
| **Open WebUI** (open-webui) | 144,913 | 自托管 AI 交互界面 | 离线 UX、函数/工具扩展、RAG、精细权限 |
| **vLLM** (vllm-project/vllm) | 85,867 | 高吞吐推理引擎 | PagedAttention、连续批处理、OpenAI 兼容服务、吞吐与显存效率 |
| **LLaMA-Factory** (hiyouga/LLaMA-Factory) | 73,122 | 统一高效微调框架 | 100+ 模型零代码微调、DeepSpeed/多卡、训练方法广度（LoRA/QLoRA/DPO/PPO） |
| **Langfuse** (langfuse/langfuse) | 30,844 | LLM 观测/评估平台 | OpenTelemetry 追踪、评估、Prompt 管理 |
| **MLflow** (mlflow/mlflow) | 26,960 | ML 生命周期平台 | 实验追踪、模型注册、血缘 |

### 2.2 Agent 框架标杆

| Agent 标杆 | Star | 定位 | 本项目可借鉴 |
|---|---:|---|---|
| **n8n** (n8n-io/n8n) | 195,564 | 可视化工作流+AI（400+ 集成） | 工作流编排、节点市场、原生 MCP |
| **browser-use** (browser-use) | 69,458 | 浏览器 CUA 代理 | 浏览器内 CUA 沙箱、可观测步骤 |
| **OpenHands** (All-Hands-AI) | 69,204 | AI 软件工程代理（terminal/文件/浏览器） | 容器沙箱代码执行、CUA 安全模型 |
| **MetaGPT** (FoundationAgents) | 69,203 | 多智能体"SOP 流水线" | 多 agent 角色编排、流水线 |
| **AutoGen** (microsoft) | 59,556 | 多 agent 会话编排 | 多 agent 对话、群聊、代码执行 |
| **CrewAI** (crewAIInc) | 54,944 | 角色扮演多 agent 团队 | 团队图、角色委派 |
| **LangGraph** (langchain-ai) | 36,908 | 有状态 agent 图 | 持久化、HITL、LangSmith 追踪（**本项目编排底座**） |
| **OpenAI Agents SDK** (openai/openai-agents-python) | 27,534 | 轻量多 agent 工作流 | handoff、guardrails、traces |

### 2.3 编程 Agent 产品标杆（终端 / 宿主级 Coding Agent）

| 编程 Agent 标杆 | Star | 语言 | 定位 | 与本项目 Agent Workspace 的可借鉴点 |
|---|---:|---|---|---|
| **OpenClaw** (openclaw/openclaw) | **382,089** | TypeScript | 本地优先、模型无关的个人 AI 助手（"own your data"、cron、多 agent） | 宿主级 agent 的"个人助手"产品范式；SOUL.md/MEMORY.md/agents 目录的数据自持模型；模型无关适配层；庞大技能/插件生态 |
| **Codex** (openai/codex) | **27,595** | Rust | OpenAI 官方轻量终端编程 Agent | 终端内安全代码执行沙箱；Rust 单二进制轻量分发；强类型安全；**原生用量/成本（token）采集** |
| **OpenCode** (opencode-ai/opencode) | **13,397** | Go | 终端 TUI 编程 Agent（provider-agnostic） | ⚠️ 仓库已 `archived`（2026-07-10 核验）；TUI/配置驱动、provider 抽象可借鉴，但社区活力已失 |

> 注：OpenClaw 的 382,089 为 GitHub API 实时值（增速极快，发布于 2025-11，建议复核）；其"本地优先 + 模型无关 + 数据自持"范式与本项目 **Agent Workspace + CUA + 记忆** 的愿景最贴近，是战略上最该对齐的标杆。OpenCode 已 archived，仅作"终端 coding agent 形态"参考；Codex 是 OpenAI 官方出品、强于安全沙箱与成本可观测性。**勘误**：原报告 Codex star 数 96,811 有误，GitHub API 实际值 27,595（2026-07-10 核验），已修正。

---

## 3. 战略坐标：本项目的定位（综合判断）

把三组标杆叠在一起看，本项目的战略坐标很清晰：

- **横向（能力广度）**：本项目是唯一把"微调 + 推理服务 + Agent + RAG + CUA"合体的平台。OpenClaw/Codex/OpenCode **都不做微调与自托管推理**——这是差异化护城河。
- **纵向（单点深度）**：在"微调方法广度"上落后 LLaMA-Factory（100+ 模型/DPO/PPO）；在"推理吞吐"上落后 vLLM（自研单锁调度器）；在"Agent 多 agent 团队/编排所有权"上落后 CrewAI/MetaGPT/LangGraph；在"安全默认/可观测性/插件生态"上落后 Dify/Open WebUI/Langfuse。
- **最危险的结构性错位**：本项目拥有 **CUA 宿主级控制**（鼠标/键盘/截屏/终端），而用户本地 `.env` 覆盖关闭了认证（项目代码默认开启，但配置文件覆盖会关）——即"能远程控制宿主"的能力面，在没有门禁的情况下暴露。这是顶级产品不会容忍的配置级安全风险。

> **一句话战略**：扬长（一体化平台 + CUA）必须先补短（安全默认 + 可观测性 + 插件/扩展）。否则"广度"会从优势变成攻击面。

---

## 4. 五大根本性缺陷（root cause）

项目在**分层清晰度、测试治理、认证密码学原语、训练队列持久化**上已达到"超出同体量平均水平"的水准。但存在 5 个**根本性（root-cause）缺陷**，决定了它距离顶级产品仍有代差：

1. **用户本地 `.env` 覆盖关闭了认证与限流（项目代码默认开启）** — `server/.env`（用户本地配置）设 `ENABLE_AUTH=false` / `ENABLE_RATE_LIMIT=false`，覆盖了 `config.py:42-44`（`enable_auth` 默认 `True`）与 `factory.py:127`（限流默认 `"true"`）的代码默认值。整个面（含可控制宿主的 CUA 鼠标/键盘/截屏）在无认证下暴露。认证原语本身写得好（bcrypt/HS256/fail-closed/prod 硬失败），但**用户本地配置覆盖等于没设防**。这是最危险的配置级风险（注：非架构级设计缺陷，项目默认是安全的）。
2. **异步/事件循环正确性缺失** — 在 `async` 路由内直接跑同步 SQLite（`training.py` worker 路由）与阻塞式 `requests`/网络探测，事件循环会被卡死。对一个并发敏感的 AI 服务平台这是结构性问题。
3. **"能力目录"被误当作"扩展体系"** — `capability_registry.py` 只是 tier 标志 + 挂载表，无动态注册、无插件发现、无 hook。Dify/Open WebUI 的真正插件生态在此完全缺位，封死了生态增长天花板。
4. **存储与协调的单机天花板** — SQLite + 文件锁（GPU 租约）+ 进程内队列，按设计只能跑单机。缺少 Postgres/Redis 这道"分水岭"，控制面/状态面无法水平扩展。
5. **没有可观测性主干** — 无分布式追踪（零 OpenTelemetry）、无全应用 `/metrics`、JSON 日志默认关闭、无关联 ID。顶流产品（vLLM/Langfuse/MLflow）把观测当一等公民，本项目把它当可选项。

这 5 条是"为什么还不是顶级产品"的根本答案；其余维度的问题大多是其下游症状。

---

## 5. 八维度逐项对比分析

### 5.1 架构设计（分层 / 解耦 / 依赖方向）

**现状与证据（偏正面）**
- 路由层不直接碰 DB：`grep` 全 `server/api/` 无 `get_db|SessionLocal|session.execute`（0 命中）。分层真实存在：router → service（`services/`、`training_engine/`、`agent_session/service.py`）→ repository（`*_repository.py`）。
- 应用装配优雅：`apps/routers.py` 用 `RouterSpec` + 懒 `import_module`（`routers.py:35-42`），`apps/factory.py:527 create_application` 按 profile 构建 combined/agent/finetune 三个 FastAPI 应用，无 `api→apps` 反向依赖，无顶层循环依赖。
- 治理测试扎实：`test_no_legacy_imports.py`、`test_architecture_cleanup.py`、`test_application_profiles.py`、`test_dependency_profiles.py` 把架构约束写进了 CI。

**缺陷**
- **依赖倒置（upward dependency）**：`server/core/inference_gateway.py:127-218` 直接 `from api.inference.routes import ... / openai_routes / scheduler`——底层 `core/` 反向依赖高层 `api/`，`core/inference_gateway.py` 实质成了第二路由层；`core/memory_monitor.py:179` 同样。正确方向是 `api → core`。
- **胖路由（fat router）**：`api/inference/routes.py` 1644 行、`api/training.py` 1354、`api/evaluation.py` 1345、`datasets.py` 1079、`cloud_chat.py` 1117。业务并未完全下沉——`training.py:95-123 _worker_progress` 在路由内做状态映射与 default-dict 拼装。
- **上帝模块**：`core/storage.py` 2027 行（虽内部分了 `ChatRepository/ShareRepository/MemoryRepository/AuditRepository`，但单体文件仍是维护负担）。
- **导入期副作用**：`factory.py:44 setup_logging`、`factory.py:57 get_rate_limiter` 在 import 时执行；`apps/{combined,agent,finetune}.py:6 app = create_application(...)` 在 import 即完整构建应用（重）；`agent_session/terminal_manager.py:366` 模块加载即 `AgentTerminalManager()` 单例；`core/utils.py:24 _vram_cache` 可变全局缓存有脏读风险。

**根本原因**：分层纪律在"新模块"遵守良好，但历史大模块未做持续重构；`core/inference_gateway` 是为绕开早期依赖问题而生长的"快捷通道"，成了反向依赖的温床。

**对标差距**：Dify 用清晰的后端服务层 + Celery worker 分离，依赖单向且可独立部署；vLLM 把 scheduler/engine 严格隔离。本项目的 `core→api` 反向依赖在顶级项目里会被 lint/架构测试直接拦截。

**改进建议**
- 将 `inference_gateway` 的编排逻辑移出 `core/`，下沉到 `services/` 或新建 `app_services/` 层，使 `core` 仅作底层工具（P1）。
- 用架构测试锁定"禁止 `core` import `api`"（P1，已有 `test_architecture_cleanup.py` 可扩展）。
- 拆分 `storage.py` 与胖路由，把路由内联逻辑抽到 service（P2）。

---

### 5.2 代码质量（可读性 / 重复率 / 测试覆盖）

**现状与证据（偏正面）**
- 集中式错误处理：`factory.py:435-479` 统一注册 `APIError/HTTPException/RequestValidationError/通用` 处理器，并以 `/v1/` OpenAI 风格塑形。
- 测试量可观：**92** 个 server 测试文件 + **39** 个 client 测试文件；48 个用 mock/fixture，17 个真正调用业务类（如 `test_chat_agent_intent.py:30-45` 实例化 `ChatAgentService()` 断言真实输出）。
- 几乎没有 `TODO/FIXME/HACK` 漂移标记（grep 命中均为文档示例误报）——代码整洁度信号好。

**缺陷**
- **测试"虚胖"**：最大的两个文件是**测试** `test_agent_session_deepagents_runtime.py` 2246 行、`test_training.py` 939 行，偏集成/smoke；对最大、最易错的胖路由（`training.py`/`evaluation.py` 的业务分支）单元测试偏薄。
- **耦合测试到路由**：`training.py:52-65` 为满足测试"重新导出 `training_engine.schemas`"，使测试绑定在 router 模块上，反向污染分层。
- **覆盖率未强制**：`ci.yml` 中 `fail_ci_if_error: false`，没有门槛约束，覆盖数字只是装饰。

**对标差距**：vLLM/MLflow 有严格的覆盖率门槛与分层单测（engine 层与 API 层解耦测试）；本项目"测试很多但关键分支覆盖薄"，且覆盖率不进 CI 门禁。

**改进建议**
- 给胖路由补分支单测（特别是 `training.py`/`evaluation.py` 的状态机与异常路径）（P2）。
- 移除 `training.py` 的 schema 重导出 hack，改为测试直接依赖 `training_engine`（P2）。
- CI 设最低覆盖率门禁（如 60% 增量、逐步提升），把 `fail_ci_if_error` 改为 `true`（P2）。

---

### 5.3 性能优化（瓶颈 / 缓存 / 资源加载）

**现状与证据（喜忧参半）**
- 好设计：`db_manager.py` 自带 `run_sync`（anyio 线程池）把同步 SQLite 移出事件循环；SQLite 连接池 + `BEGIN IMMEDIATE` + WAL + 全局上限 100；`distributed_cache.py` Redis 优先 + 内存 LRU 回退（好）。
- 训练队列是**最扎实的可伸缩点**：`training_worker/repository.py` 用 SQLite 持久队列 + 每任务 lease（`claim_next:200-254`） + 心跳（`:280`）+ `recover_expired`（`:394`），多 worker 进程可共享 SQLite 抢占执行。
- `ModelScheduler` 的 LRU 淘汰/引用计数/空闲超时（`scheduler.py`）良好。

**缺陷（瓶颈）**
- **异步内阻塞 SQLite**：`training.py:1210-1249` 的 worker 路由（`get_queue_status/get_task_status/cancel_task/_worker_progress`）直接同步 `sqlite3`，绕过了自家 `run_sync`——并发下卡死事件循环。
- **异步内阻塞 HTTP**：`core/inference/ollama_engine.py:59,88,121,270` 用 `requests.get/post/delete`（非 httpx 异步）；`core/proxy_config.py:227`、`core/mirror_manager.py:297-308` 同样；`backends/swift_backend.py:133,156` 有 `time.sleep`；`core/user_experience.py:195 subprocess.run`。
- **忙等轮询**：`core/training_queue.py:181 time.sleep(0.1)` 占槽循环；`training_worker/worker.py:190` 每 0.25s 轮询取消。
- **每请求重算目录扫描**：`api/datasets.py:553 iterdir` + `:566 rglob("*")` 逐文件算大小；`api/model_center.py` 扫描 modelscope 缓存目录——无缓存。
- **MCP 缓存无 TTL**：`mcp/tool_registry.py:168-195 _tool_cache` 仅 `cache_key in ...` 无过期判断，可能返回陈旧结果。
- **GPU 协调仅单机**：`core/gpu_coordination.py` 仅文件锁（`gpu_lease.json`），跨主机争用无协调。
- 所有训练/推理接口显式 `Cache-Control: no-cache`（`training.py:240,293,812`），无响应缓存。

**对标差距**：vLLM 用连续批处理 + PagedAttention 把单卡吞吐做到极致，且全程异步非阻塞；本项目自研单进程 `asyncio.Lock` 调度器（`api/inference/scheduler.py:88`）在吞吐与并发上代差明显，且不阻塞事件循环的纪律未贯彻。

**改进建议**
- 给 `training.py` worker 路由套 `run_sync`（P0，低风险高收益）。
- 把 `ollama_engine/proxy_config/mirror_manager` 的 `requests` 换成 httpx 异步；移除 async 上下文的 `time.sleep`（P1）。
- 给数据集/模型目录扫描加缓存；给 `mcp` tool_cache 加 TTL（P1）。
- 把忙等改为事件/条件变量或 DB 轮询 + 退避（P1）。
- 评估用 vLLM/sglang 作为可选推理后端，替代自研单锁调度器（P3）。

---

### 5.4 安全性（漏洞防护 / 认证授权）

**现状与证据（原语强，用户本地 `.env` 覆盖会关）**
- 认证原语写得好：`jwt_auth.py` 用 bcrypt（`:232`）、HS256、角色层级 + 黑名单；`require_configured_jwt_secret`（`security/runtime_policy.py:64-85`）**fail-closed**（无 `JWT_SECRET_KEY` 直接 `RuntimeError`）；`config.py:224-233` 在 production 下 `enable_auth=false` 或缺失密钥时**硬失败**。数据集路径用 `validate_path_security`（`datasets.py:142-159`）做了真实校验。
- **项目代码默认开启认证与限流**：`config.py:42-44` `enable_auth` 默认 `True`；`.env.example:56` 模板 `ENABLE_AUTH=true`；`factory.py:127` 限流默认 `"true"`。即**项目出厂默认是安全的**，问题出在用户本地 `server/.env` 覆盖关闭。
- 命令执行业务路径多数为安全写法：`models.py:383 subprocess.run` 用 list、`code_executor.py` 用 `create_subprocess_exec`。

**缺陷（高危）**
- **🚨 用户本地 `.env` 覆盖关闭认证（P0，配置级风险）**：`server/.env:53 ENABLE_AUTH=false`（注：非项目默认，项目代码与模板默认开启）；`factory.py:187-189` 在关闭时直接 `call_next` 跳过全部鉴权——包括 CUA 的鼠标/键盘/截屏路由。CUA 的"ADMIN 必需"（`cua.py:43 require_cua_admin`）在 `auth_middleware.py:322-347` 中 `if not enable_auth: return current_user` —— **匿名用户直接通过**。即该 `.env` 覆盖下，任何人可远程控制宿主。
- **🚨 命令注入（P0）**：`security/sandbox.py:501-502` 只校验命令首词：`cmd_name = command.split()[0] ... in allowed_commands`；随后 `sandbox.py:531` 与 `:892` 用 `asyncio.create_subprocess_shell(command)`（shell=True）。首词白名单 + `$(...)`/`; rm -rf /` 即可逃逸。**可达路径**：`/code/` 端点（`api/code_executor.py:21` 导入 `security/sandbox.py`）；Agent 命令执行走 DeepAgents 官方 sandbox execute，**不走** `security/sandbox.py`（勘误：原报告"Agent 可达此路径"为误导，已修正）。
- **🚨 CORS 凭据反射（P0）**：`factory.py:258-259/274-275` 在错误/限流响应里 `Access-Control-Allow-Origin: request.headers.get("origin","*")` + `Access-Control-Allow-Credentials: "true"`——反射任意攻击者 Origin 并带凭据，等价于任意站点发起带凭证跨域请求（主 `CORSMiddleware` 用了固定源列表，属不一致）。
- **🚨 CUA 路径穿越（P1）**：`cua.py:753-758 /record/load` 直接用用户绝对路径 `Path(request.filepath)` → `recorder.load_from_file` 任意文件读；`/record/play`（`:802-803`）同理，无目录 containment。
- **默认内部密钥（P1）**：`config.py:152-155` `inference_internal_api_key` 硬编码默认 `finetune-local-inference-dev-key`，仅在 prod/staging 拒绝（`runtime_policy.py:88-104`），dev 下即推理控制面（8020）的真实密钥。
- **用户本地 `.env` 覆盖关闭限流（P1）**：`server/.env:20 ENABLE_RATE_LIMIT=false`（注：非项目默认，`factory.py:127` 代码默认 `"true"`；`.env.example` 不设此变量走代码默认）→ 全关，暴力/滥用敞开；`factory.py:83 IP_BLACKLIST` 是占位符 `{"1.2.3.4","5.6.7.8"}`。
- **提交示例凭据（P1）**：`server/data/credentials/test_api_key.json`、`test_key.json` 入库。
- **前端 XSS（待核实，P2）**：`CodeBlock.tsx:464`、`CodePreview.tsx:485/570` 用 `dangerouslySetInnerHTML` 注入高亮结果——需确认 highlighter 输出已转义（多半安全，但应加测试断言）。

**对标差距**：Dify/Open WebUI 默认即带认证与细粒度 RBAC，CORS 用显式源白名单且默认不带通配凭据；LLaMA-Factory/vLLM 即便本地工具也不提供"远程控制宿主"的能力面，因而规避了 CUA 这类高危攻击面。**本项目的"能控制宿主 + 用户本地 `.env` 覆盖关闭认证"组合，是顶级产品不会容忍的配置级安全风险（注：项目代码默认是安全的，问题在配置覆盖）**。

**改进建议（全部 P0/P1，先不动代码，仅排期）**
- 确保 `.env.example` 与文档强调生产必须开启认证 + 限流；审查 `server/.env` 不随发货/镜像带入关闭值；`enable_auth=false` 在 prod 已有 fail-closed 机制，需确保发货配置不被覆盖（P0）。
- `sandbox.py` 改用 `create_subprocess_exec` + 参数列表，或全命令（非首词）白名单 + 参数校验，彻底消除 shell 注入（P0）。
- CORS 统一为固定源白名单，移除反射 + 通配凭据（P0）。
- `/record/load|play` 做 `realpath` 前缀校验，锁定在 recordings 目录内（P1）。
- 移除硬编码默认内部密钥，改为首次启动生成并持久化；清理提交的示例凭据（P1）。
- 确保限流默认开启（代码已默认 `"true"`，需确保 `.env` 不覆盖关闭）；给 `IP_BLACKLIST` 接真实来源（P1）。

---

### 5.5 可扩展性（插件 / 配置 / 水平扩展）

**现状与证据**
- 配置灵活性**好**：`core/config.py:18` Pydantic `BaseSettings` + `env_file=".env"` + `field_validator`（`:261/276`），环境驱动 + schema 校验；`validate_environment_security` 在 prod 缺认证时硬失败。
- 小扩展点：`mcp/tool_registry.py:58 register_tool` + `category="extension"`。
- 水平扩展（worker 模式）**好**：基于 SQLite lease 的训练队列天然支持多 worker。

**缺陷**
- **"能力目录"不是扩展机制**：`apps/capability_registry.py` 的 `CAPABILITY_CATALOG`（`:31-92`）是 `frozen` dataclass 元组，静态罗列 ga/beta/experimental + HTTP 挂载点，供 `/api/info` 展示；`EXPERIMENTAL_ROUTER_SPECS`（`:95-102`）硬编码模块名静态装载。**无动态注册、无插件发现、无 hook、无生命周期事件。** 它本质是"分层标志 + 挂载表"，不是 Dify 那样的插件系统。
- **传统模式不可水平扩展**：`core/training_queue.py` 进程内 `PriorityQueue` + 全局单例 + JSON 状态文件，`max_concurrent=1`，状态全内存。
- **SQLite 即天花板**：WAL + `busy_timeout` 稳健，但跨主机需共享文件系统，无 Postgres 选项。
- **GPU 锁仅同机**：文件锁，多主机争用无协调。
- **API 共享态漂移风险**：`distributed_cache._memory_cache`、`mcp` tool_cache、`gpu_coordinator` 全局——多 API 实例下除非启用 Redis，否则内存态漂移。

**对标差距**：Dify 有**插件市场 + 后端服务插件运行时 + Celery/Redis 任务总线 + PostgreSQL**；Open WebUI 有函数/pip 插件与工具扩展；两者都能水平扩展。本项目的"静态 tier 表"在生态扩展上落后至少一个数量级，控制面水平扩展缺最后一块砖（集中存储）。

**改进建议**
- 明确 `capability_registry` 的边界：要么定位为"分层/挂载元数据"（并在文档讲清），要么演进为真正的插件注册表（动态注册 + hook 点 + 生命周期）（P1/P2）。
- 多主机场景引入 Postgres（状态/队列）+ Redis（缓存/分布式锁）替代文件锁与 SQLite 单文件；或**显式文档声明单机天花板**并给出横向扩展路径（P1）。
- 把 `gpu_coordination` 的文件锁换成 Redis/etcd 分布式锁，支持多机 GPU 池协调（P1）。

---

### 5.6 可维护性（文档 / 日志监控 / CI-CD）

**现状与证据（整体成熟）**
- 文档：**有** `README.md`（335 行，含能力分层/配置表/页面地图）、`README_EN.md`、`docs/adr/` 5 篇真实 ADR（0001–0005）、`docs/DEPLOYMENT_STRATEGY.md` 等运维 runbook。
- 可观测性（部分）：结构化 JSON 日志**可用**（`core/logging.py:9,12,40-43`，pythonjsonlogger）；推理侧 Prometheus（`/inference/metrics`、`/inference/performance/prometheus`、`core/performance.py:312`）；多级健康检查 `/health`、`/experimental/status`、`inference_server/app.py:113`。
- 前端 API 客户端**成熟**：`api.ts` 有指数退避重试、连接池去重/防抖、离线队列、统一错误归一化；`ErrorBoundary`、共享 `LoadingState/EmptyState` 组件齐全。
- CI/CD：**强矩阵**——`ci.yml` 跑 ruff（focused+full）、black、mypy、后端 unit/integration pytest + Codecov、前端 typecheck/lint/vitest/build；`cd.yml` 用 GHA 缓存构建并推 `ghcr.io`，含 staging/prod 环境与部署校验。
- 配置生产安全：prod 缺认证/密钥硬失败，experimental 默认关。

**缺陷**
- **JSON 日志默认关闭**：`log_format` 默认 `"text"`（`config.py:32-34`），仅 `LOG_FORMAT=json` 才 JSON；`log_inference_event`（`logging.py:68-71`）把字段追加成空格分隔字符串而非 JSON。
- **无关联 ID / 无全应用 metrics / 无追踪**：日志无 request/correlation ID；Prometheus 仅推理侧，无 `/metrics` 应用级；零 `opentelemetry|traceparent`；训练指标仅 JSON（`training.py:407`、`agent_sessions.py:373`）。
- **轮询蔓延**：`Evaluation.tsx` ×12、`HeartbeatPage`、`ModelRuntimeCenter` ×2、`useOllamaConnection` ×5 的 `setInterval`，无统一轮询/abort 策略，冗余请求风险。
- **CI 门禁形同虚设**：`ci.yml` 中 ruff-full/black/mypy/前端 lint/安全扫描多为 `continue-on-error: true`，真正阻断的只有 focused ruff；根目录无 pre-commit（仅 `deepagents_reference/.pre-commit-config.yaml`）；Codecov `fail_ci_if_error: false`。
- **缺架构图**：README 无架构图，`docs/design/` 仅 PNG 截图；`AGENTS.md` 57KB 自陈"以代码为准"但声明 "2.0" 而 README 写 "2.1"，漂移风险高。

**对标差距**：Langfuse 把 OpenTelemetry 追踪 + 评估当产品内核；vLLM 暴露细粒度 Prometheus 指标；MLflow 把实验/血缘作为一等公民。本项目的可观测性"有雏形但非主干"，且 CI 把质量门禁设为可选——顶级项目的 CI 是**合并的硬门槛**而非建议。

**改进建议**
- 非 dev 环境默认 `LOG_FORMAT=json`；`log_inference_event` 改为结构化字段；加 request/correlation ID 中间件（P1）。
- 加应用级 `/metrics` + OpenTelemetry 追踪（至少跨 API→inference→training），导出到 OTel Collector（P1）。
- 前端引入 SWR/React Query 类缓存 + 统一轮询/abort，收敛 `setInterval` 蔓延（P2）。
- CI 把 mypy/black/安全扫描设为阻断（或明确记录"为何不阻断"的 ADR）；根目录加 pre-commit；Codecov 设增量门槛（P2）。
- 补 C4 架构图（README 引用）；把 `AGENTS.md` 版本与 README 对齐（P3）。

---

### 5.7 用户体验（响应速度 / 错误处理 / 无障碍）

**现状与证据（整体不错）**
- 错误处理链路完整：响应拦截器结构化记录（`api.ts:394-421`）、`extractApiErrorMessage` 归一化（`api.ts:1823-1838`）、离线队列（`:225-233, 379-390`）、顶层 `ErrorBoundary`。
- 加载/空态组件化：`LoadingState/EmptyState` + AntD `Spin/Empty/Result` 广泛使用。
- 无障碍**高于平均**：`App.tsx:64-66 role="status" aria-live="polite"`、`App.tsx:423 role="main"`、`CUAControl.tsx:267-497` 完整 tablist/tab/tabpanel、`ChatNew.tsx:146 role="log" aria-live`、`ChatInput.tsx:406-418 listbox/option`。
- 训练用 SSE 而非轮询（`subscribeTrainingProgress` `api.ts:1995`）。

**缺陷**
- **响应速度隐患**：大量页面依赖 `setInterval` 轮询（见 5.6），无统一缓存/失效，训练/推理大接口 `no-cache`，高频轮询下易抖动。
- **无障碍缺口**：toast/`message.error`（`utils/notify.ts`）无 `aria-live`；无可见对比度主题 token；焦点管理依赖 AntD 默认，键盘操作复杂面板（CUA）的 trap/focus 顺序未显式保障。
- **错误现场信息**：部分服务端错误经归一化后丢失结构化上下文，用户侧只能看到泛化提示，难自助排查。

**对标差距**：Open WebUI 在离线优先、键盘可达性、细粒度权限 UX 上打磨更深；Dify 用统一状态管理与乐观更新消除轮询抖动。本项目的 a11y 基础好，但"轮询蔓延 + 无 aria-live 通知 + 无对比度 token"使其达不到顶流的无障碍与流畅度。

**改进建议**
- 收敛轮询为统一缓存层（见 5.6），关键通知加 `aria-live`（P2）。
- 引入对比度/主题 token 并做 WCAG AA 走查（P2）。
- 错误归一化保留 `error_code`/可操作提示，前端按 code 给自助建议（P2）。

---

### 5.8 Agent 能力专项对标（框架 + 编程 Agent 产品）

本项目的 agent 编排**不是自研**，而是 **LangGraph + Deep Agents 的"消费方"** —— `deepagents_reference/` 为 vendored 的 Deep Agents harness（MIT），运行时依赖 pinned `deepagents==0.6.10` / `langgraph==1.2.5`（`server/requirements.txt:95,242`）；`agent_session/deepagents_runtime.py:14` `from langgraph.types import Command`。外层是自研 **session/runtime 管理层**（阶段状态机、崩溃恢复、人工审批、轨迹、CUA）。

#### 5.8.1 与顶级 Agent 框架逐轴对比

- **编排模型**：Deep Agents 单会话图循环 + 自研阶段状态机（`running/waiting_approval/completed/failed/interrupted`，`session_state_machine.py:25-103`）。多 agent 仅为 fan-out（`deepagents_runtime.py:64-72` `start_async_task`/`task` 工具）+ 委派策略（`runtime_policy.py:308-314`）。**无原生团队图**（无 CrewAI 角色图、无 MetaGPT SOP 流水线）。→ 与 LangGraph 持平（本就是 LangGraph）；落后 CrewAI/MetaGPT 的原生多 agent 团队。
- **工具/扩展**：真实协议 —— `MCPToolRegistry.register_tool`（`mcp/tool_registry.py:58`）、JSON-schema→参数转换（`:102`）、MCP server 管理器、300s 结果缓存；工具按 agent 声明（`runtime_policy.py:318-325`）。第三方经 MCP server 扩展。→ 与 OpenAI Agents SDK / LangGraph MCP 持平。
- **Computer Use（CUA）**：**成熟且超前多数框架** —— `cua.py` 暴露 screenshot（`:180`）/mouse（`:246`）/keyboard（`:354`）/窗口/OCR/record（`:659`）/play（`:792`）；权限级别 `read_only/interactive/full_control`（`:856-868`）+ 安全控制器 + 审计日志（`:880`）；由 `require_cua_admin` + `can_execute_commands` 守卫。→ 比 LangGraph/CrewAI/AutoGen（无原生 CUA）超前；与 OpenHands/browser-use 可比，但**宿主级控制比容器沙箱风险更高**（叠加 5.4 默认无认证 = 高危）。
- **持久化/HITL/检查点**：LangGraph `AsyncSqliteSaver` 检查点（`deepagents_checkpoint.py:13,33`）+ `recover_active_sessions_after_restart` + 恢复闩（`service.py:167-171`）+ `interrupt`/`waiting_approval` 状态 + `ApprovalService.approve_permission`（`service.py:234`）。→ 与 LangGraph 持平；超前 CrewAI/MetaGPT。
- **Agent 可观测性**：**明显落后** —— 仅步骤级（`trajectory.py:360 record_step` 存最多 200 步、`score_trajectory:220`、事件总线推前端）；**无 token/usage 采集**（grep `prompt_tokens|completion_tokens|usage` 在 `agent_sessions.py`/`events.py` 为零），无 OTel。→ 落后 LangGraph（LangSmith）、OpenAI Agents SDK（traces）。
- **记忆**：`core/memory_monitor.py` 名不副实 —— 是 **GPU/RAM 压力监控**（`check_pressure`、`torch.cuda`），非 agent 记忆。Agent 记忆为 (a) 每会话文件（`service.py:195` `MEMORY.md`）与 (b) 用户级 SQLite `memory_items`（FTS5 + 向量 reconcile，`storage.py:288,974,960`）。无显式短/长程会话作用域记忆。→ 与专用记忆框架持平/偏弱。
- **护栏/安全**：强 —— `sandbox.py` 有 `DANGEROUS_COMMANDS`/`DANGEROUS_PATTERNS` 黑名单（`:38-123`）、6 级能力 + 命令白名单（`:193-253`）、`IsolatedExecutor`（`:459`）、`NetworkIsolation`（`:999`）、`ProcessIsolation`（`:860`）、`require_cua_admin` + `rate_limiter`。**但限流器未实际作用于 agent/CUA 端点**（grep `rate_limit` 在 `agent_sessions.py`/`cua.py` 为空）。→ 持平，限流未落地。

**Agent 框架差距矩阵**

| Agent 能力轴 | 本项目 | AutoGen | LangGraph | CrewAI | MetaGPT | OpenHands | browser-use | 判定 |
|---|---|---|---|---|---|---|---|---|
| 编排模型 | LangGraph 消费方 | 多agent会话 | 状态图(底座) | 团队图 | SOP流水线 | 单agent+工具 | 浏览器CUA | 持平/落后团队 |
| 多agent原生团队 | ❌ fan-out | ✅ | ⚠️ | ✅ | ✅ | ⚠️ | ❌ | 落后 |
| Computer Use | ✅ 宿主级 | ❌ | ❌ | ❌ | ❌ | ✅ 容器沙箱 | ✅ 浏览器 | **超前但风险高** |
| 持久化/HITL | ✅ 检查点 | ⚠️ | ✅ | ⚠️ | ⚠️ | ✅ | ⚠️ | 持平 |
| Agent token/usage追踪 | ❌ | ⚠️ | ✅ LangSmith | ⚠️ | ⚠️ | ⚠️ | ⚠️ | **代差** |
| 工具/MCP生态 | ✅ MCP | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 持平 |
| 记忆 | ⚠️ 文件+SQLite | ✅ | ✅ | ⚠️ | ⚠️ | ✅ | ⚠️ | 偏弱 |
| 护栏/限流落地 | ⚠️ 限流未用 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 落后 |

> ✅ 达标 / ⚠️ 部分或落后 / ❌ 缺失

**根本原因**：agent 编排引擎是**外部 pinned 依赖的消费方而非所有者**——升级 harness 是维护负担；且**零 token/usage/追踪可观测性**，无法度量 agent 成本或诊断运行，除非自己插桩 vendored 层。缺少 CrewAI/MetaGPT 原生的多 agent 团队图。

#### 5.8.2 与编程 Agent 产品（OpenCode / Codex / OpenClaw）逐轴对比

三者均为**运行在终端 / 宿主上的编程（coding）Agent**，与本项目"嵌在微调平台内的 Agent Workspace + CUA"形态不同：它们是**独立的 Agent 产品**，且都具备"在机器上写代码 / 操作环境"的能力——这正好对上本项目的 CUA + 终端/代码执行面。

| 维度 | 本项目（Agent Workspace+CUA） | OpenCode (Go) | Codex (Rust/OpenAI) | OpenClaw (TS) | 判定 |
|---|---|---|---|---|---|
| 产品形态 | 平台内嵌 Agent 模块 | 终端 TUI coding agent | 终端轻量 coding agent | 宿主级个人 AI 助手 | 本项目缺**独立 coding agent 产品面** |
| 语言/分发 | Python（依赖重） | Go 单二进制 | Rust 单二进制（轻量） | TS（跨平台） | 落后：无单二进制轻量分发 |
| 模型无关性 | ✅ 多 provider 推理 | ✅ provider-agnostic | ❌ 强绑定 OpenAI | ✅ 模型无关适配层 | 与 OpenCode/OpenClaw 持平 |
| 宿主级控制 | ✅ CUA 鼠标/键盘/截屏 | 文件/终端 | 终端（沙箱） | ✅ 全宿主 | 持平/超前（但风险高） |
| 代码执行沙箱 | ⚠️ shell 注入（§5.4） | 中（本地执行） | ✅ 强（OpenAI 安全模型） | ⚠️ 本地优先、自担风险 | 落后 Codex |
| 用量/成本(token)追踪 | ❌ 无（§5.8.1） | ⚠️ 弱 | ✅ 原生 | ⚠️ 弱 | **代差（Codex 示范）** |
| 插件/技能生态 | ❌ 静态 tier 表（§5.5） | ⚠️ 有限 | ⚠️ 有限 | ✅ 庞大社区+技能市 | **代差（OpenClaw 示范）** |
| 数据自持 | ⚠️ 记忆散落多存储 | — | ❌ 云端 | ✅ SOUL/MEMORY/agents+cron+git | 落后 OpenClaw |
| 交互（diff/apply） | ⚠️ 偏自主 | ✅ TUI 流式 diff+apply | ✅ 流式+审批 | ✅ CLI/TUI | 落后交互打磨 |

**关键发现**
- **OpenClaw 是战略上最该对齐的标杆**：它的"本地优先 + 模型无关 + 数据自持（SOUL.md/MEMORY.md/agents 目录/cron/git 灾难恢复）"范式，与本项目 **Agent Workspace + CUA + 记忆 + 多 provider 推理 + experimental(cua/heartbeat/mcp/gateway)** 的愿景几乎 1:1 对应。差距不在"能力覆盖"，而在**产品/生态成熟度与统一叙事**——OpenClaw 把这些积木拼成一个有 38 万星的"个人 agent 产品"，本项目则把同类积木分散在 GA/beta/experimental 多层、无统一入口，且用户本地 `.env` 覆盖关闭认证（§5.4）让"宿主级控制"从卖点变成隐患。
- **Codex 示范了本项目最该补的两块**：① 终端内**安全代码执行沙箱**（直接对照 §5.4 的 `create_subprocess_shell` 注入与 CUA 宿主级风险）；② **原生 token/usage 成本追踪**（直接对照 §5.8.1 的"agent 可观测性代差"）。Rust 单二进制也提示"轻量分发"是可取形态。
- **OpenCode 已 archived**（2026-07-10 核验 `archived:true`）——它代表的"终端 TUI coding agent + provider 抽象"形态值得借鉴，但作为活力标杆已失效；其 TUI 流式 diff/apply 交互仍是本项目 Agent 面板可追的交互标杆。
- **本项目独有价值**：没有哪个标杆把"微调 + 推理服务 + CUA + 多 provider Agent"做成同一平台；OpenClaw/Codex/OpenCode 都不做微调与自托管推理。这是差异化的护城河，但前提是把安全默认、可观测性、插件生态这三块补到标杆线。

**改进建议（与路线图合并）**
- 立"个人 Agent 产品"统一叙事：把 Agent Workspace + CUA + 记忆 + experimental 能力收敛为一个 OpenClaw 式的"本地优先、数据自持"入口（P1，呼应 §5.8.1）。
- 补 Codex 式**安全代码执行沙箱**与**token/usage 成本采集**，直接消除 §5.4/§5.8.1 两处代差（P1）。
- 借鉴 OpenClaw 的 **SOUL.md/MEMORY.md/agents 目录** 数据自持模型，将散落的记忆/会话状态收敛为可 git 备份的"workspace 自持包"（P2）。
- 评估 OpenCode 式 TUI/CLI **流式 diff + apply/reject** 交互，提升 Agent 面板的代码编辑体验（P2/P3）。
- 把"轻量分发"（单二进制 / 独立进程入口）纳入规划——当前 Agent 入口仅 `server.apps.agent:app` 藏于 combined 之后，无独立轻量形态（P3）。

**Agent 对标差距（一句话）**：在"单 agent + CUA + 持久化"与"宿主级控制 + 微调/推理一体化平台"上独有优势；在"多 agent 团队协作、运行成本/token 追踪可观测性、原生编排所有权、独立 coding agent 产品面、安全代码沙箱、技能/插件生态、数据自持产品化"上落后。

---

## 6. 优先级排序的改进路线图

| 优先级 | 项 | 维度 | 为什么这个序 |
|---|---|---|---|
| **P0** | 审查 `server/.env` 不随发货带入关闭值；强化文档/校验确保生产开启认证（代码已默认开启）+ 清理示例凭据 | 安全 | 用户本地 `.env` 覆盖关闭认证 + 可控制宿主 = 最高危；代码已有 fail-closed 机制，改动小 |
| **P0** | 修复 shell 命令注入（`create_subprocess_exec` + 参数白名单） | 安全 | 任意命令执行，可达（`/code/` 端点） |
| **P0** | 修复 CORS 凭据反射 | 安全 | 任意站点带凭证跨域 |
| **P0** | `training.py` worker 路由套 `run_sync` | 架构/性能 | 阻塞事件循环，低风险高收益 |
| **P1** | CUA `/record/load\|play` 路径 containment | 安全 | 任意文件读 |
| **P1** | 移除硬编码默认内部密钥；确保限流默认开启（代码已默认 `"true"`） | 安全 | 默认值弱点 |
| **P1** | 异步化阻塞 HTTP（`requests`→httpx）+ 去 `time.sleep` | 性能 | 并发吞吐 |
| **P1** | 目录扫描缓存 + mcp tool_cache TTL | 性能 | 热点重复计算 |
| **P1** | 分布式协调（Postgres/Redis 队列 + Redis GPU 锁）或显式声明单机天花板 | 扩展 | 水平扩展分水岭 |
| **P1** | `core→api` 反向依赖上移 + 架构测试锁定 | 架构 | 依赖卫生 |
| **P1** | 默认 JSON 日志 + correlation ID + 应用级 `/metrics` + OTel 追踪 | 可维护/观测 | 可运维性主干 |
| **P1** | 安全代码执行沙箱 + agent token/usage 成本采集（对齐 Codex） | 安全/Agent | 消除 §5.4/§5.8 代差 |
| **P2** | 拆分胖路由/上帝模块；路由内联逻辑下沉 service | 架构/代码 | 长期可维护性 |
| **P2** | 胖路由分支单测 + 覆盖率门禁 + 移除 schema 重导出 hack | 代码质量 | 覆盖薄 |
| **P2** | CI 门禁阻断化 + 根 pre-commit | 可维护 | 质量纪律 |
| **P2** | 前端统一缓存/轮询收敛 + a11y 补全（aria-live/对比度） | UX | 流畅度与可达性 |
| **P2** | "个人 Agent 产品"统一叙事（对齐 OpenClaw） | Agent/产品 | 收敛分散能力、形成卖点 |
| **P3** | 演进真正插件注册表（动态注册+hook）或文档澄清边界 | 扩展 | 生态天花板 |
| **P3** | 评估以 vLLM/sglang 为可选推理后端 | 性能 | 吞吐代差 |
| **P3** | MLflow/Langfuse 集成或 OTel 导出（实验追踪/评估） | 可维护 | 替代 JSON 历史 |
| **P3** | C4 架构图 + AGENTS.md 版本对齐 | 文档 | 减少漂移 |

---

## 7. 附录：对标能力差距矩阵（速览）

### 7.1 平台 / 基础设施维度

| 能力 | 本项目 | Dify | Open WebUI | vLLM | LLaMA-Factory | Langfuse | 差距判定 |
|---|---|---|---|---|---|---|---|
| 认证/RBAC 默认 | ⚠️ 代码默认开，`.env` 覆盖会关 | ✅ | ✅ | N/A | N/A | ✅ | 配置级风险（注：项目代码默认开启，非架构代差） |
| 命令执行隔离 | ⚠️ shell 注入 | — | — | — | — | — | **高危** |
| 异步非阻塞 | ⚠️ 部分 | ✅ | ✅ | ✅ | ✅ | ✅ | 落后 |
| 插件/扩展生态 | ❌ 静态 tier 表 | ✅ 市场 | ✅ 函数 | N/A | ⚠️ | ✅ | **代差** |
| 水平扩展（控制面） | ⚠️ 单机 | ✅ PG+Celery | ⚠️ | ✅ | ⚠️ | ✅ | 落后 |
| 分布式追踪 | ❌ 无 | ✅ | ⚠️ | ⚠️ | ❌ | ✅ OTel | **代差** |
| 推理吞吐引擎 | ⚠️ 单锁 | — | ⚠️ | ✅ | — | — | 落后 |
| 训练方法广度 | ⚠️ LoRA/QLoRA | — | — | — | ✅ 100+模型/DPO/PPO | — | 落后 |
| 实验追踪/血缘 | ⚠️ JSON | ⚠️ | ❌ | ❌ | ⚠️ | ✅ | 落后 |
| 分层/架构治理测试 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 持平 |
| 前端 API 客户端成熟度 | ✅ | ✅ | ✅ | N/A | N/A | ✅ | 持平 |

> ✅ 达标 / ⚠️ 部分或落后 / ❌ 缺失 / N/A 非对标项 / — 不适用

### 7.2 Agent 框架维度（详见 §5.8.1）

| 能力 | 本项目 | 判定 |
|---|---|---|
| 多agent原生团队 | ❌ fan-out | 落后（详见 §5.8.1） |
| Computer Use(CUA) | ✅ 宿主级 | 超前但风险高（详见 §5.8.1） |
| Agent token/usage追踪 | ❌ | 代差（详见 §5.8.1） |

### 7.3 编程 Agent 产品维度（OpenCode / Codex / OpenClaw，详见 §5.8.2）

| 能力 | 本项目 | OpenCode | Codex | OpenClaw | 差距判定 |
|---|---|---|---|---|---|
| 独立 coding agent 产品面 | ❌ 内嵌 | ✅ TUI | ✅ 终端 | ✅ 宿主助手 | 缺失 |
| 安全代码执行沙箱 | ⚠️ shell 注入 | ⚠️ | ✅ 强 | ⚠️ | 落后 Codex |
| token/usage 成本追踪 | ❌ | ⚠️ | ✅ | ⚠️ | **代差** |
| 技能/插件生态 | ❌ 静态 tier | ⚠️ | ⚠️ | ✅ 庞大 | **代差** |
| 数据自持(记忆/会话) | ⚠️ 散落 | — | ❌ | ✅ 自持包 | 落后 OpenClaw |
| 模型无关性 | ✅ | ✅ | ❌ 绑OpenAI | ✅ | 持平 |
| 宿主级控制(CUA) | ✅ 超前 | 文件/终端 | 终端沙箱 | ✅ 全宿主 | 持平/超前(风险高) |
| 微调+推理一体化平台 | ✅ 独有 | ❌ | ❌ | ❌ | **独有优势** |

---

## 8. 架构决策记录草案（ADR）

> 把本轮最关键的决策写成 ADR，落实"记录决策而非仅记录设计"。状态均为 **Proposed**（未执行，待确认）。

### ADR-001：确保生产部署开启认证与限流（强化配置校验，代码已默认开启）

- **Context**：项目代码默认开启认证（`config.py:42-44` `enable_auth` 默认 `True`；`.env.example:56` `ENABLE_AUTH=true`）与限流（`factory.py:127` 默认 `"true"`），且 production 下 `enable_auth=false` 或缺失密钥会硬失败。但用户本地 `server/.env` 设 `ENABLE_AUTH=false` / `ENABLE_RATE_LIMIT=false` 覆盖了默认值，CUA 路由在该覆盖下无认证暴露，任何人可远程控制宿主（§5.4）。**勘误**：原 ADR 把此问题描述为"默认关闭"，实为"用户本地配置覆盖关闭"，已修正。
- **Decision**：① 强化 `.env.example` 与文档，明确生产必须开启认证 + 限流；② 审查 `server/.env` 不随发货/镜像带入关闭值；③ 可选：在非 development 环境对 `enable_auth=false` / `ENABLE_RATE_LIMIT=false` 加 startup warning 或拒绝启动。
- **Consequences**：部署配置变安全；dev 体验不变。可逆（环境变量控制）。

### ADR-002：消除 `core → api` 反向依赖

- **Context**：`core/inference_gateway.py:127-218` 与 `core/memory_monitor.py:179` 反向 import 高层 `api/`，使 `core` 实质成为第二路由层。
- **Decision**：将编排逻辑移出 `core/`，下沉到 `services/` 或新建 `app_services/`；用架构测试锁定"禁止 `core` import `api`"。
- **Consequences**：依赖方向单向化，可独立部署测试；需重构 `inference_gateway`（中等工作量）。

### ADR-003：建立可观测性主干（日志 + metrics + 追踪）

- **Context**：无 OTel、无全应用 `/metrics`、JSON 日志默认关、无关联 ID（§5.6）。
- **Decision**：非 dev 默认 `LOG_FORMAT=json` + correlation ID 中间件；加应用级 `/metrics`；引入 OpenTelemetry 追踪跨 API→inference→training，导出到 OTel Collector；agent 运行处采集 token/usage（呼应 §5.8.1）。
- **Consequences**：可诊断、可度量（尤其 agent 成本）；引入 OTel 依赖与运维组件。

### ADR-004：存储与协调向分布式演进（或声明单机天花板）

- **Context**：SQLite + 文件锁按设计只能单机（§5.5）。
- **Decision**：多主机场景引入 Postgres（状态/队列）+ Redis（缓存/分布式锁/GPU 锁）；或显式文档声明单机天花板并给出横向扩展路径。
- **Consequences**：水平扩展可行；运维复杂度上升（需 PG/Redis）。可逆（先文档声明、后演进）。

### ADR-005：`capability_registry` 边界澄清或演进为插件注册表

- **Context**：当前仅是"分层标志 + 挂载表"，被误当扩展体系（§5.5）。
- **Decision**：要么定位为"分层/挂载元数据"并在文档讲清；要么演进为真正插件注册表（动态注册 + hook 点 + 生命周期）。
- **Consequences**：若演进，生态天花板打开但需设计插件隔离/沙箱；若仅澄清，成本低但生态受限。

### ADR-006：CUA 沙箱化 + 安全代码执行

- **Context**：CUA 宿主级控制 + `create_subprocess_shell` 注入 + 用户本地 `.env` 覆盖关闭认证 = 高危（§5.4、§5.8.2）。
- **Decision**：首选容器/VM 沙箱承载 CUA 与 agent 命令执行（学 OpenHands/Codex）；`sandbox.py` 改用 `create_subprocess_exec` + 参数白名单；限流器实际挂到 agent/CUA 端点。
- **Consequences**：宿主风险大幅下降；沙箱带来资源开销与配置成本。

### ADR-007："个人 Agent 产品"统一叙事（对齐 OpenClaw）

- **Context**：Agent Workspace + CUA + 记忆 + experimental 能力分散在多层，无统一入口与卖点（§5.8.2）。
- **Decision**：收敛为"本地优先、数据自持"的个人 Agent 产品入口；借鉴 OpenClaw 的 SOUL.md/MEMORY.md/agents 目录数据自持模型，形成可 git 备份的 workspace 自持包。
- **Consequences**：产品叙事清晰、差异化突出；需跨 GA/beta/experimental 的 UI/入口整合。

---

— 评审完 —
