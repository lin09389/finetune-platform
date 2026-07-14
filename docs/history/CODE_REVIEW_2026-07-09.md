# 代码审查报告 — 工作区全部改动

> **对应改动**：master 分支未推送的 4 个提交（9e6e4fa / 72e396a / 6653319 / e0e4e66）+ 当时的未提交工作区改动（Phase-0 安全 / Phase-1 韧性 / Phase-2 能力分层）。本报告为该快照的审查记录，代码演进后行号与状态可能过时。
> 审查范围：4 个已提交未推送的 commit + 117 个未提交文件改动 + 新增未跟踪文件
> 审查时间：2026-07-09
> 审查重点：正确性、安全性、可维护性、性能、测试覆盖

## 一、总体评价

这是一组**高质量的系统性加固**，覆盖安全（Phase-0）、韧性（Phase-1）、能力分层（Phase-2）三个维度。

**没有发现 🔴 Blocker 级问题。** 整体设计扎实、测试覆盖全面（新增 phase0/1/2 共 1138 行测试），错误处理链完整，安全 posture 明显提升（fail-closed、production 不可绕过）。

主要发现集中在 🟡 一致性与边界场景，以及少量 💭 nit。建议合入前处理标红的 🟡 项。

---

## 二、已推送的 4 个提交

### `9e6e4fa` chore: split runtime dependency profiles
拆分 api/inference/training 三套依赖 profile，新增 `requirements-*.txt`，配套 `test_dependency_profiles.py`。
- 评价：构建/部署改进，方向正确，无安全问题。

### `72e396a` fix: degrade inference service status endpoints
推理状态端点改为优雅降级：`list_backends` / `get_performance_stats` / `get_performance_recommendations` 在推理服务不可用时返回降级 payload 而非 500。统一用 `_json_response`（`json.loads(response.content)`）替代 `response.json()`。

- ✅ 状态端点不应因底层服务挂掉而 500，降级设计合理；测试覆盖完整。
- 🟡 **一致性**：`list_models`、`openai_list_models`、`ollama_status` 同属状态类端点，但未加降级 try/except，服务不可用时仍会抛异常。建议补齐或在注释中明确"这些端点不降级"的理由。

### `6653319` fix: harden agent session background recovery
Agent 会话后台恢复加固，11 个文件。

- ✅ **事件总线跨线程修复（重要）**：原 `notify` 在持有 `_lock` 时直接 `queue.put_nowait`，而 `asyncio.Queue` 非线程安全，从后台任务线程调用存在竞态。新代码用 `subscriber.loop.call_soon_threadsafe(...)` 把 put 调度到订阅者所在事件循环，并新增终端事件优先投递（队列满时丢旧事件腾位给 completed/failed/interrupted），避免 SSE 永久挂起。这是真正的并发 bug 修复。
- ✅ per-session 启动锁防止同一 session 并发启动 prompt。
- ✅ checkpointer 改为每次 run_prompt/resume 用 `_open_checkpointer` async context manager 自管生命周期，避免跨事件循环复用。
- ✅ `AgentConfigurationError` 异常链完整：detached 路由捕获并转 400，`start_prompt_background` 仅在 detached 内部被调用，传播路径正确。
- 🟡 **锁字典只增不减**：`_session_start_locks` 字典在 session 销毁后不清理 Lock 对象。长期运行 + 大量 session 会有缓慢内存增长。建议在 session 终止/回收时移除对应锁。
- 🟡 **兼容 checkpointer 泄漏**：`_get_checkpointer`（兼容测试直接调 `_build_graph`）把 context 压入 `_compat_checkpointer_contexts` 列表但只在 `_close_checkpointer` 时关闭。注释说明是测试用，但若测试不调 close 会泄漏 sqlite 连接。建议测试 fixture 的 teardown 统一调用。

### `e0e4e66` fix: refine agent workbench runtime state
前端 workbench runtime 状态优化。

- ✅ **stale session 事件过滤（重要）**：`stream_event` reducer 检查事件 `session_id` 是否匹配当前 session，不匹配则记录诊断但不应用，避免切换 session 后旧事件污染当前状态。
- ✅ 根据 `failure_kind` / `next_action` 显示友好状态文案；从 axios 错误响应提取后端 `detail.message`。
- 评价：小而精的修复，测试覆盖 stale event 与 failure metadata 两个场景。

---

## 三、未提交改动

### 后端安全核心（Phase-0）— 高质量

**`security/runtime_policy.py`（新增）**：集中式策略模块，单一事实源。
- ✅ `require_configured_jwt_secret`：**fail-closed**，密钥缺失一律抛 RuntimeError（含 dev/test），杜绝多 worker 各自随机密钥的不一致问题。
- ✅ `allow_local_agent_auth`：production/staging 永远 False，非 production 需显式 `ALLOW_LOCAL_AGENT_AUTH=true`。
- ✅ `assert_inference_internal_key_safe`：production 拒绝默认 dev key。
- ✅ `gpu_coordination_enabled`：production 永远 True。

**`security/auth_middleware.py`**：
- ✅ 新增 `require_cua_admin`：auth 开启时强制 ADMIN+，auth 关闭（本地/测试）放行。注释明确"DEBUG never bypasses role checks while auth is on"。
- ✅ legacy `JWTAuthMiddleware`/`SecurityMiddleware` 标记 deprecation，生产路径统一走 `apps.factory.authentication_middleware`。

**`security/jwt_auth.py`**：
- ✅ JWTAuth 初始化改用 `require_configured_jwt_secret`，不再静默生成随机密钥；新增 `reset_jwt_auth` 支持测试/密钥轮换。

**`apps/factory.py`**：
- ✅ `_allows_local_agent_auth_fallback` 改用 `allow_local_agent_auth(settings)`，production 不放行。
- ✅ `api_info` 改为 registry 驱动（从 `capability_registry` 取），消除手写 tier 字典漂移。
- ✅ 新增 `experimental_isolation_middleware`：只包裹 `/experimental/*`，异常 → 503，不影响 GA。中间件顺序正确（isolation 在 auth 外层，路由异常能被捕获）。
- ✅ 新增 `/experimental/status` 就绪端点（加入 `_PUBLIC_PATHS`，不泄露敏感信息）。

**`apps/lifespan.py`**：
- ✅ production 禁止 `ENABLE_AUTH=false`（直接 RuntimeError 阻止启动）；JWT secret fail-closed；inference key 检查。
- ✅ shutdown 新增 chat session / context / rag embedder / vector store / memory 五个服务的 close，资源清理更完整。

**`apps/routers.py`**：
- ✅ experimental 路由按 `enable_experimental_capabilities` 开关注册；开启时双挂载（`/experimental/*` + legacy 别名），`dependencies=[require_cua_admin]` 是 router 级别，双挂载不会绕过安全守卫；broken module 不 abort 启动。

**`apps/capability_registry.py`（新增）**：GA/beta/experimental 单一事实源，设计清晰。

**`core/config.py`**：
- ✅ `field_validator` → `model_validator(mode="after")`，所有字段就绪后验证更可靠；production 新增默认 inference key 拒绝、experimental 默认关闭。
- 🟡 **experimental 默认关闭判断读的是 `os.environ.get` 而非字段值**：若用户通过配置文件（非 env）设 `enable_experimental_capabilities=True`，validator 仍会强制设为 False。偏向关闭是安全的，但行为不直观。建议改读 `self.enable_experimental_capabilities` 的来源或文档说明"production 仅认 env 变量"。
- 💭 `lifespan.py` 中 `__import__("os")` 写法不优雅，应顶部 `import os`。

### 后端推理/训练（Phase-1）

**`core/gpu_coordination.py`（新增）**：跨进程 GPU 租约协调（train vs infer）。
- ✅ tmp + `os.replace` 原子写；lease 过期机制（默认 3600s）覆盖进程崩溃未释放；release 检查 holder 匹配避免误释放。
- 🟡 **TOCTOU 竞态**：`claim` 的 read-check-write 非原子，两进程可能同时读到空闲后都写入。模块注释已明确承认"best-effort, not a perfect distributed lock"，单机场景窗口小，可接受。如要更稳可加文件锁（`fcntl`/`msvcrt`）。

**`api/inference/scheduler.py`**：
- ✅ 模型加载前 `assert_inference_gpu_available` + `claim_inference_gpu`；卸载最后一个模型 / shutdown 时 release；`except Exception` 分支降级为 no-op 协调（有意设计）。
- ✅ `shutdown` 新增 `unload_all()` + release lease 双保险。

**`api/inference/routes.py`**：
- ✅ `_resolve_deployment_target` 是同步 SQLite，新增 `_resolve_deployment_target_async`（`asyncio.to_thread`）卸载到线程，避免阻塞事件循环；cache key 构造接受已解析的 `deployment_target` 避免重复查询。性能改进。

**`api/inference/facade.py`**：
- ✅ `_map_service_degrade_response` 把 service gateway 降级 dict 转成 503/504 + `Retry-After`。

**`training_engine/checkpoint_manager.py`**：
- ✅ checkpoint metadata 改为 tmp + `os.fsync` + `os.replace` 原子写，防止崩溃留下截断 JSON。重要的数据完整性改进；失败时清理 tmp。

**`training_engine/model_loader.py` + `pipeline.py` + `training_worker/worker.py`**：
- ✅ 训练侧 GPU 协调集成完整：claim 在 `_check_vram_before_load`，release 在 pipeline `_run_cleanup`（owner=None 无条件清 training holder）+ worker `finally` safety net。双重释放保证 hard failure 也能释放租约。

### 前端核心（由子代理审查）
- ✅ 删除 `client/src/index.css` 安全：`main.tsx` 引用的是 `./styles/index.css`（未删），样式链完整。
- ✅ `vite.config.ts` chunk 拆分、`ErrorBoundary` 错误上报、`.eslintrc.json` yml→json 迁移 + `no-console: error` 均为正向改进。
- 🟡 `RuntimeContext.tsx:341` 双重类型断言 `as unknown as`，建议让 API 返回正确类型或运行时校验。
- 🟡 `useStreamResponse.ts:212` cleanup 依赖 `[streamManager]`，需确认其为 ref 稳定，否则每次渲染触发 `stop()`。
- 🟡 `Sidebar.tsx:223` 后端断开 early return 时未 `setApiInfo(null)`，旧 `apiInfo` 残留可能让实验性菜单短暂可见。
- 💭 `chatStore.ts:762` 剥离 `api_key` 用 `undefined` 不如解构剔除干净。

### 新增测试与删除脚本
- ✅ `test_phase0_security.py`（462 行）覆盖 JWT fail-closed、production 强制 auth、CUA admin、inference key、GPU lease 全链路、scheduler 拒绝/释放、pipeline cleanup。
- ✅ `test_phase1_resilience.py`（463 行）覆盖 async resolve、知识库 offload、service 降级、facade 状态映射、shutdown 资源关闭、checkpoint 原子写、**`test_server_root_no_longer_hosts_scatter_test_scripts` 防护测试防止临时脚本回退**。
- ✅ `test_phase2_capability_tiers.py`（213 行）覆盖能力分层。
- ✅ 删除 26 个散落临时脚本（`check_*.py`/`test_*.py`/`clear_*.py`/`verify_install.py`/`pip.conf`/`.condarc`/`create`，共 2527 行），均为 AGENTS.md 所述临时调试脚本，清理合理且有防护测试。

---

## 四、需关注的 🟡 项汇总（建议合入前处理）

| # | 位置 | 问题 | 建议 |
|---|------|------|------|
| 1 | `events.py` `_session_start_locks` | 锁字典只增不减，长期运行内存增长 | session 终止时移除对应锁 |
| 2 | `inference_gateway.py` 状态端点 | `list_models`/`ollama_status` 未降级，与 `list_backends` 不一致 | 补齐降级或注释说明不降级原因 |
| 3 | `config.py` experimental 默认关闭 | 读 `os.environ` 而非字段值，配置文件设置不生效 | 改读字段来源或文档说明 |
| 4 | `deepagents_runtime.py` `_get_checkpointer` | 兼容测试用的 context 不关闭 | 测试 fixture teardown 统一 close |
| 5 | `RuntimeContext.tsx:341` | 双重类型断言 | API 返回正确类型或运行时校验 |
| 6 | `Sidebar.tsx:223` | 后端断开未重置 apiInfo | early return 前 `setApiInfo(null)` |

---

## 五、值得表扬的设计

1. **集中式 `runtime_policy.py`**：所有 prod/dev 取舍集中一处，middleware、JWT、agent auth、inference key、GPU 协调共享同一"production hard-closed + explicit local opt-in"定义，避免策略散落漂移。
2. **事件总线跨线程修复**：`call_soon_threadsafe` + 终端事件优先投递，既修了竞态又防了 SSE 挂起，是教科书式的并发修复。
3. **checkpoint 原子写 + GPU 双重释放**：数据完整性与资源释放都有 belt-and-suspenders 设计。
4. **防护测试**：`test_server_root_no_longer_hosts_scatter_test_scripts` 这类"防止回退"的测试体现了工程纪律。
5. **stale session 事件过滤**：小改动解决了一个真实的状态污染 bug。
