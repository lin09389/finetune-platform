# AGENTS.md

This file provides guidance to AI coding agents (Codex, Claude Code, Qoder, Gemini 等) when working with code in this repository.

> 本文档于 2026-07-29 重构指令上下文布局：根文档只保留项目概述、命令面、依赖/版本约束、能力分层与安全边界；后端/前端目录树详解、25 条核心设计模式与 API 端点全表见 `docs/architecture-reference.md`；`client/src/` 与 `server/api/` 子树各有聚焦的 `AGENTS.md`。**以代码为准**：若文档与代码冲突，以代码为准并回头修订本文档。后端应用装配与能力边界以 `server/apps/routers.py`、`server/apps/lifespan.py`、`server/apps/capability_registry.py` 和 `/api/info` 为准。

## 项目概述

Finetune Platform 2.0 - 企业级大模型微调平台，专为消费级显卡优化（4GB+ 显存）。支持 LoRA/QLoRA 微调、模型管理、数据集处理、实时监控、推理服务、Agent 会话执行底座及 Ollama 集成。

**技术栈：**
- 后端：FastAPI + Python 3.11（`requires-python = ">=3.11,<3.12"`；PyTorch、Transformers、PEFT 按 profile 安装）
- 前端：React 18 + TypeScript + Ant Design + Vite + Framer Motion
- 桌面端：Electron（Phase 9 正式产品边界；Phase 10 引入版本化受管 Python 3.11 runtime pack，本地服务仍按进程运行）
- 存储：SQLite（应用/会话/训练状态）、ChromaDB（向量存储）、JSON（训练/评估历史）
- 依赖管理：根目录 `pyproject.toml` + `uv`（单一 `uv.lock`）；按进程拆 optional extras（`agent` / `rag` / `cua` / `training` / `inference` 等）；`server/requirements*.txt` 由 `uv export` 生成，**不要手改**
- 部署：Docker + Docker Compose（`docker-compose.yml`；API / training-worker / inference-service 可分镜像）

## 能力分层（ga / beta / experimental）

**后端单一事实源**：`server/apps/capability_registry.py`（能力 id → tier / mounts）。  
`apps/routers.py` 注册与 `GET /api/info` 必须读此注册表。

**前端对齐**：`client/src/capability/tiers.ts`（`ROUTE_CAPABILITY` 路径 → capability id）+ `ExperimentalRouteGuard.tsx` + Sidebar 徽章；**禁止**再手写与后端漂移的静态 tier 字典。前端以 `/api/info` 的 `capability_tiers` / `experimental_enabled` 为运行时权威。

- **GA（正式能力，有完整测试与 UI）**：device、models、datasets、training、inference、chat_sessions、knowledge_base
- **Beta（较稳定，但有变动可能）**：project_context、memory、model_center、workspace、agent_eval、**cloud_chat**（always-on 辅助，不走 experimental 开关）
- **Experimental（实验性，API/UI 可能变动）**：cua、heartbeat、mcp、gateway、ocr_fallbacks、action_recorder

**强制机制（阶段 2）：**
- 开关：`ENABLE_EXPERIMENTAL_CAPABILITIES`（`settings.enable_experimental_capabilities`）
- production/staging：**默认关闭** experimental 路由注册，除非环境变量显式 `true`
- development / pytest：默认开启（conftest 会 setdefault）
- 启用时：规范挂载 `/experimental/*`，并保留 `/cua`、`/mcp`、`/gateway` 等 **legacy 别名**
- 关闭时：不注册 experimental 路由；`/api/info` 中 `experimental_enabled=false`，前端隐藏/守卫实验入口
- 隔离：`experimental_isolation_middleware` 仅包裹 `/experimental/*` 异常 → 503，不影响 GA
- 就绪信号：`GET /experimental/status`（与核心 `/health` 分离）
- CUA 仍强制 ADMIN（阶段 0）；分层关闭不会削弱已开启时的鉴权

改动 GA 能力必须保证向后兼容并补回归测试；改动 Experimental 能力相对自由。分层语义详表见 `docs/capability-truth-table.md`。

## 开发命令

### 后端

```bash
# 本地完整开发（推荐；与 Windows start*.bat 一致）
uv sync --frozen --extra all --extra dev
uv run --extra all python -m server.inference_server          # 推理执行面，默认 127.0.0.1:8020
uv run --extra all python -m server.training_worker           # 训练 GPU worker
uv run --extra all python -m uvicorn server.main:app --host 127.0.0.1 --port 8010
# 开发热重载：在上面 API 命令追加 --reload

# 应用边界独立入口（默认前端仍连 combined :8010）
uv run --extra all python -m uvicorn server.apps.agent:app --host 127.0.0.1 --port 8011
uv run --extra all python -m uvicorn server.apps.finetune:app --host 127.0.0.1 --port 8012

# 单进程精简依赖（Docker/分镜像场景）
uv run --extra inference python -m server.inference_server
uv run --extra training --extra gpu python -m server.training_worker

# 运行测试（仓库根目录；conftest 在 server/tests/；完整跑需 --extra all 环境）
python -m pytest server/tests -q
python -m pytest server/tests -m "not integration and not e2e" -q   # 仅单元
python -m pytest server/tests -m integration -q
python -m pytest server/tests -m e2e -q
python -m pytest server/tests --cov=server --cov-report=html

# 运行单个测试
python -m pytest server/tests/test_training.py -v
```

> 无 `--extra` 的 `uv run` 只装 base 控制面依赖，Agent/RAG/CUA/训练/本地推理相关 import 会缺包。本地联调请始终 `--extra all`（或对应进程 extra）。

> 注意：临时调试/运维脚本已迁至 **`server/scripts/`**（`check_*.py`、`test_*.py`、`clear_*.py` 等），**不是** pytest 套件的一部分，禁止从生产代码 import。正式测试一律在 `server/tests/`。`test_phase1_resilience.py` 含守卫，防止散落脚本回到 `server/` 根目录。

### 依赖管理

```bash
# 依赖事实源是根目录 pyproject.toml（用 uv 管理；单一 uv.lock）
# 在仓库根目录执行：
uv sync --frozen --extra all --extra dev   # 本地完整开发环境
uv lock                                    # 更新 lockfile

# 按进程导出 requirements（供 Docker / 无 uv 环境；全部不要手改）
uv export --extra all --no-dev --no-hashes --format requirements-txt -o server/requirements.txt
uv export --extra agent --extra rag --extra cua --extra modelhub --extra model-ops --no-dev --no-hashes --format requirements-txt -o server/requirements-api.txt
uv export --extra training --extra gpu --no-dev --no-hashes --format requirements-txt -o server/requirements-training.txt
uv export --extra inference --no-dev --no-hashes --format requirements-txt -o server/requirements-inference.txt
```

| 文件 | 用途 |
|------|------|
| `server/requirements.txt` | 全量兼容环境 |
| `server/requirements-api.txt` | 控制面 / API 镜像 |
| `server/requirements-training.txt` | 训练 worker 镜像 |
| `server/requirements-inference.txt` | 本地推理服务镜像 |

完整 profile 说明见 `docs/dependency-profiles.md` 与 ADR `docs/adr/0004-split-runtime-dependency-profiles-and-images.md`。

### 前端

```bash
cd client
npm run dev                # 启动开发服务器（端口 5173，strictPort）
npm run build              # 生产构建（tsc && vite build）
npm run preview            # 预览构建产物
npm run lint               # eslint src --ext .ts,.tsx
npm run typecheck          # tsc --noEmit
npm run format             # prettier --write

# 测试（Vitest）
npm test                   # vitest（watch 模式）
npm run test:ui            # vitest --ui
npm run test:coverage      # vitest --coverage
npm run test:smoke         # 单次跑：Sidebar + beta + experimental + ga 页面 smoke
npm run test:runtime       # 单次跑：RuntimeContext + RuntimeWorkflows
npm run test:perf          # npm run build && lhci autorun

# Storybook
npm run storybook          # dev -p 6006
npm run build-storybook    # 生产构建
```

> 注意：`npm test` 默认是 **watch 模式**。CI 或一次性验证用 `npx vitest run` 或上述 `test:smoke` / `test:runtime`。

**前后端连接**：前端 dev server（5173）**不走 Vite proxy**，直连后端。`API_BASE_URL` 解析顺序：Electron → `import.meta.env.VITE_API_URL` → `http://{hostname}:8010`（本地通常即 `http://127.0.0.1:8010`）。见 `client/src/services/api.ts` 与 `client/vite.config.ts` 注释。

### Docker

```bash
# 仅启动 API
docker compose up -d api

# 启动完整栈（含前端）
docker compose --profile dev up -d

# 启动 Ollama
docker compose --profile ollama up -d

# 查看日志
docker compose logs -f api

# 重新构建
docker compose build --no-cache
```

### Windows 快速启动

仓库根目录存在以下批处理脚本：
- `install.bat` —— 安装依赖
- `start.bat` —— 同时启动推理服务 + 训练 worker + API + 前端（`uv sync --extra all`）
- `start-backend.bat` / `start-frontend.bat` —— 分别启动后端三进程 / 前端
- `start-inference-service.bat` —— 仅推理服务（`--extra inference`）
- `start-training-worker.bat` —— 仅训练 worker（`--extra training --extra gpu`）
- `verify.bat` —— 验证安装

### Electron 桌面端（Phase 9–10）

```bash
npm run test:desktop       # Node 原生测试：监督器、Python 解析、IPC、app://、数据路径
npm run test:runtime-pack  # runtime pack manifest/确定性制品策略
npm run test:package-policy # 安装包内容与用户数据排除策略
npm run build:runtime-pack -- --runtime-dir <dir> --output-dir <dir> --profile base --version <v> --platform win32 --architecture x64 --python-version 3.11.x
npm run build              # 先构建 React renderer
npm run start              # 开发环境启动 Electron（要求可用的 Python 3.11 与依赖）
npm run build:electron     # electron-builder 打包
```

桌面运行时只接受 Python `>=3.11,<3.12`；开发环境可通过 `FINETUNE_PYTHON` 指定。Phase 10 的 runtime pack 必须使用严格 manifest、SHA-256、staging、健康探针和原子激活；可用 `FINETUNE_RUNTIME_MANIFEST` 指定本地 manifest，或让 Electron 从 `FINETUNE_RUNTIME_PACK_DIR` / packaged `resources/runtime-packs` 发现唯一兼容包。可变数据、数据库、模型、输出、日志、工作区和运行时密钥必须位于 Electron `userData/runtime`（或显式的 `FINETUNE_USER_DATA_ROOT`）；受管运行时位于其同级 `managed-runtimes`（或 `FINETUNE_MANAGED_RUNTIME_ROOT`），两者都禁止写入 packaged resources。

## 架构设计（外链）

架构详解已迁至 `docs/`，本节只保留导航：

- **目录树详解 / 25 条核心设计模式 / API 端点全表 / 架构收口现状**：`docs/architecture-reference.md`
- **后端应用装配边界（combined / agent / finetune）**：`docs/backend-application-profiles.md`
- **依赖 profile 拆分**：`docs/dependency-profiles.md`
- **能力分层语义真值表**：`docs/capability-truth-table.md`
- **ADR**：`docs/adr/`（Agent 主运行时、训练 worker 隔离、推理 Provider、依赖 profile、云端模型访问等）

**子树约定（改对应目录前先读）：**

- `client/src/` 前端约定、禁止事项与本地验证命令：`client/src/AGENTS.md`
- `server/api/` 路由层约定、禁止事项与本地验证命令：`server/api/AGENTS.md`
- `server/agent_session/` Agent 会话领域包约定、禁止事项与本地验证命令：`server/agent_session/AGENTS.md`

## 配置说明

环境变量位于 `server/.env`（从 `server/.env.example` 复制）。**变量清单与示例值的单一事实源是 `server/.env.example`**（含每个变量的注释与本地测试矩阵说明），本文档不再复制完整变量块；运行时解析与校验以 `server/core/config.py` 的 `settings` 与 `server/security/runtime_policy.py` 为准。

跨环境语义口径（详细注释见 `server/.env.example`）：
- `PORT`：实际启动用 8010；`.env.example` 默认 8000，按需改
- `ENVIRONMENT`：staging 与 production 同等安全基线（JWT 必填、禁默认推理密钥、禁本地 agent 免登）
- `JWT_SECRET_KEY`：必填，禁止依赖自动生成（缺失则 JWT 初始化 / 启用 auth 时启动失败）
- `ALLOW_LOCAL_AGENT_AUTH`：默认 false；仅非 production/staging 生效，生产即使设 true 也无效
- `INFERENCE_INTERNAL_API_KEY`：production/staging 禁止默认值 `finetune-local-inference-dev-key`
- `GPU_COORDINATION`：默认 on；仅非生产可设 off
- `ENABLE_EXPERIMENTAL_CAPABILITIES`：development 默认 true；production/staging 未显式设 true 时强制 false
- `DEBUG`：生产环境必须 false；DEBUG 不会放行 CUA 鉴权

### 本地 / 生产用法矩阵（阶段 0）

| 场景 | 推荐配置 | 说明 |
|------|----------|------|
| **本地 UI 联调** | `ENVIRONMENT=development` `ENABLE_AUTH=true` `JWT_SECRET_KEY=...` `ALLOW_LOCAL_AGENT_AUTH=true` | Agent 本机可免 token；普通接口仍建议登录 |
| **测 CUA** | 同上 + **ADMIN** 账号登录 | `/cua/*` 在 `ENABLE_AUTH=true` 时强制 ADMIN；USER→403，无 token→401；`DEBUG` **不会**绕过 |
| **pytest** | conftest 已 `setdefault`：`JWT_SECRET_KEY`、`ALLOW_LOCAL_AGENT_AUTH=true`、`INFERENCE_INTERNAL_API_KEY=test-...`、`ENABLE_AUTH=false`、`ENABLE_EXPERIMENTAL_CAPABILITIES=true`、`TRAINING_EXECUTION_MODE=worker`、`INFERENCE_EXECUTION_MODE=service` | 多数单测免登；默认走 worker/service 边界 + Test Double；安全契约在 `tests/test_phase0_security.py` 自行 opt-in auth |
| **生产 / staging** | `ENVIRONMENT=production` `ENABLE_AUTH=true` 强随机 `JWT_SECRET_KEY` + 非默认 `INFERENCE_INTERNAL_API_KEY` | 禁止 `ALLOW_LOCAL_AGENT_AUTH` 生效；缺 JWT 或用默认推理密钥 → 配置/启动失败 |

**常用自测路径：**

```bash
# 1) 复制环境
cp server/.env.example server/.env
# 编辑 JWT_SECRET_KEY（本地可保留 example 中的 dev 值）

# 2) 启动后端三进程（推荐 --extra all）
uv run --extra all python -m server.inference_server
uv run --extra all python -m server.training_worker
uv run --extra all python -m uvicorn server.main:app --host 127.0.0.1 --port 8010

# 3) 登录拿 token
# POST /auth/register 或 /auth/login → access_token
# 请求头：Authorization: Bearer <token>

# 4) CUA：使用 role=admin 的用户；USER 会 403
# 5) Agent 本机免 token：ALLOW_LOCAL_AGENT_AUTH=true 且非 production
# 6) 边训边推：GPU_COORDINATION=on 时一方占卡另一方会受控拒绝；仅开发可 GPU_COORDINATION=off
```

## 安全边界

- 速率限制：内存 + 滑动窗口（可选 Redis）
- 文件上传验证：类型/大小/内容
- 路径遍历防护：严格路径验证
- CORS：可配置允许来源
- **活鉴权链**：仅 `apps/factory.authentication_middleware` 注册为 HTTP 中间件；`JWTAuthMiddleware` 类版为 legacy，勿与 factory 双挂
- **JWT fail-closed**：`JWTAuth` **禁止**静默 `secrets.token_hex` 自动生成密钥；必须设置 `JWT_SECRET_KEY`（见 `security/runtime_policy.require_configured_jwt_secret`）
- **Agent 本地免登**：生产/staging 硬关；非生产需显式 `ALLOW_LOCAL_AGENT_AUTH=true`（`factory._allows_local_agent_auth_fallback` + `get_agent_session_user`）
- **CUA 强鉴权**：`/cua/*` 路由级 `Depends(require_cua_admin)`——`ENABLE_AUTH=true` 时需 ADMIN/SUPER_ADMIN；**DEBUG 不放行 CUA**
- **推理 internal key**：`INFERENCE_INTERNAL_API_KEY` 在 production/staging 禁止默认值 `finetune-local-inference-dev-key`（settings 校验 + `assert_inference_internal_key_safe` + inference_server lifespan）
- **GPU 训练/推理互斥**：`core/gpu_coordination.py` 文件 lease；训练 claim（model_loader）/ 结束 release（pipeline cleanup + worker finally）；推理 load claim / 最后卸载或 shutdown release；`GPU_COORDINATION=off` 仅非生产
- **训练日志 XSS 防护**：前端 `highlightLog` 先 HTML 转义再高亮（`Training/components/highlightLog.ts`）
- **chatStore 不持久化 API key**：`partialize` 剥离 `cloudConfig.config.api_key`
- JWT 认证：可选启用（`ENABLE_AUTH`）；生产/staging 强制 true
- WAF：`apps/factory.py` 内置 SQL 注入 / XSS / 路径遍历正则规则
- 安全响应头：`apps/factory.py` middleware 注入 CSP/X-Frame-Options 等
- Agent 动作隔离：文件操作由 DeepAgents `FilesystemBackend` 路径隔离；命令走 sandbox execute

## 测试

### 后端测试

位于 `server/tests/`。仓库根目录运行：`python -m pytest server/tests -q`

**CI 测试口径（最小依赖覆盖边界）**：CI（`.github/workflows/ci.yml`）以 `uv sync --frozen --extra dev --extra agent` 安装依赖，不装 training/inference/cua 等重型 extras（torch、aiohttp、pynput）。本文档不维护用例计数快照；排除清单以 `ci.yml` 单元测试步骤的 `--ignore` / `--deselect` 参数为单一事实源，当前收集数量在该依赖口径下用 `uv run pytest server/tests/ -m "not integration and not e2e" --collect-only -q`（并附加 `ci.yml` 中相同的 `--ignore` / `--deselect` 参数）实测获取。以下依赖边界用例在 CI 主流水线中被排除，由补充轨道 `.github/workflows/heavy-tests.yml`（workflow_dispatch + 每周定时，`--extra all --extra dev` 全量依赖）执行，本地可用 `--extra all` 环境运行：
- `test_cua.py`、`test_architecture_cleanup.py`（模块级 `from pynput import ...`；heavy-tests 轨道通过 xvfb 虚拟显示运行）
- `test_openai_compatible_api.py`（导入 `aiohttp`，属 inference extra）
- `test_inference_service_boundary.py` 的 native 服务用例与 `test_phase0_capability_fact_source.py` 的 backend-aware 工具事实用例（运行时需 torch；确切 nodeid 见 `ci.yml` 的 `--deselect` 参数）

**CI lint 门控口径（阻断 vs advisory）**：lint job 的**阻断**门控为：encoding 检查、focused ruff 5 规则门控（`--select W291,W293,I001,UP015,UP012`，作用于整个 `server/`）、以及 `server/security/` 的独立 ruff + mypy 全量门控（含 mypy follow-imports 连带的 `server/core/*`、`server/memory/*` 模块，必须保持零错误）。全量 ruff、black、全量 mypy（`server/` 整体）仍是 **advisory**（`continue-on-error: true`，历史 backlog 未清零前不阻断）。门控清单以 `ci.yml` lint job 为单一事实源，修改时须与本节同步。

**Advisory 清偿节奏（下一个待收口子树）**：advisory 门控按子树逐个清零后升级为阻断，**下一个待收口子树是 `server/core/`**——security 门控的 mypy follow-imports 已连带覆盖其被 security 引用的模块（config、db_manager、logging、storage、training_state、utils 等，当前零错误），但 standalone 检查仍有余量（ruff 约 17 处、多为可自动修复的 UP038/SIM105；mypy 除 core 自身错误外还会 follow-imports 连带 `server/agent_session/*`）。**升级为阻断的条件**：`uv run --extra dev --extra agent python -m ruff check server/core/` 与 `uv run --extra dev --extra agent python -m mypy server/core/`（含 follow-imports 连带模块）两条命令本地实跑零错误后，在 `ci.yml` lint job 增加对应阻断步骤并同步本节。

主要测试覆盖（按主题，非穷举）：设备/模型/数据集、安全阶段 0（`test_phase0_security.py`、`test_global_auth_middleware.py`）、韧性阶段 1（`test_phase1_resilience.py`）、能力分层阶段 2（`test_phase2_capability_tiers.py`）、依赖 profile/边界、训练控制面与 worker、推理、Agent Session（`test_agent_session_*`、`test_agent_execution_plan*`、`test_agent_trajectory.py` 等）、云端模型、评估/发布、Gateway/Heartbeat/MCP/CUA、上下文/记忆/工作区、存储/架构守卫、Phase 9 桌面与能力评测（`electron/test/*.test.js`、`test_agent_eval_*.py`）。

Agent 链路重点回归：

```bash
python -m py_compile server/agent_session/repository.py server/agent_session/service.py server/agent_session/async_subagents.py server/agent_session/deepagents_runtime.py server/agent_session/deepagents_checkpoint.py server/tests/test_agent_session_deepagents_runtime.py
python -m pytest server/tests/test_agent_session_deepagents_runtime.py server/tests/test_agent_session_auth_optional.py server/tests/test_agent_frontend_diagnostics.py server/tests/test_agent_execution_plan.py server/tests/test_agent_execution_plan_events.py server/tests/test_agent_execution_plan_recovery.py server/tests/test_agent_trajectory.py -q
```

### 前端测试

位于 `client/src/test/`，Vitest + React Testing Library。运行：`cd client && npm test`（watch）或 `npx vitest run`（单次）。

主要覆盖：动效（`motion.test.tsx`）、能力分层（`capabilityTiers.test.ts`、`ExperimentalRouteGuard.test.tsx`、`Sidebar.test.tsx`）、Agent Session SSE（`agentSessionStream.test.ts`）、Agent Workbench（`AgentWorkbenchRuntime.test.tsx` 等；专用命令 `npm run test:agent-foundation`）、页面 smoke（ga/beta/experimental）、运行时（`RuntimeContext.test.tsx`）、Chat（`useChatStream.test.ts`、`ChatNewVirtualization.test.tsx`）、安全/XSS（`highlightLog.test.ts`）、Agent 业务门控（共享事件夹具对比最终 Store 投影）等。约定与验证命令详见 `client/src/AGENTS.md`。

## 常见问题

**1. CUDA 内存不足**
- 减少 `per_device_train_batch_size`，启用梯度检查点，对大模型用 INT4 量化

**2. 模型下载失败**
- 检查 `HF_MIRROR` 设置，验证代理配置，确保磁盘空间充足

**3. 训练卡住**
- 检查 `logs/` 目录错误，验证 GPU 未被占用，重启后端清除状态

**4. 前端无法连接**
- 后端默认 `8010`，前端 dev `5173` 无 Vite proxy；`API_BASE_URL` 默认 `http://{hostname}:8010`，可用 `VITE_API_URL` 覆盖
- 检查 `ALLOWED_ORIGINS` 是否包含前端来源；后端是否用 `--extra all` 启动（缺包会导致部分路由 500）
- 验证防火墙规则

**5. 启动报 JWT secret is required / 生产配置校验失败**
- 在 `server/.env` 设置 `JWT_SECRET_KEY`（不要依赖自动生成）
- production/staging：必须 `ENABLE_AUTH=true`，且 `INFERENCE_INTERNAL_API_KEY` 不能是 `finetune-local-inference-dev-key`

**6. Agent 接口无 token 变 401**
- 生产/staging：必须带 `Authorization: Bearer ...`
- 本地：设置 `ALLOW_LOCAL_AGENT_AUTH=true` 且 `ENVIRONMENT=development`（仅 development 裸环境不够，还要显式 flag）

**7. CUA 403 / 401**
- `ENABLE_AUTH=true` 时需要 **ADMIN**（或 SUPER_ADMIN）JWT；普通 USER 固定 403
- `DEBUG=true` **不会**关闭 CUA 鉴权

**8. 训练结束后推理仍提示 GPU busy**
- 正常路径会在 pipeline cleanup / unload 时 release lease；若进程被强杀，lease 文件可能残留
- 开发可临时 `GPU_COORDINATION=off`，或删除 `data/gpu_lease.json`（默认路径在 settings.base_dir/data）后重启

## API 文档

完整 API 文档：`http://localhost:8010/docs`（Swagger UI）、`/redoc`、`/openapi.json`
元数据端点：`GET /api/info`（含 capability_tiers 分层）

端点按 `server/apps/routers.py` 的 profile 注册表为准；按能力分层分组的端点全表与架构收口现状见 `docs/architecture-reference.md`。

## 其他目录

- `docs/` —— 架构/迁移/验收文档，**非**运行时行为的单一事实源（以代码与本文档开发约定为准）
  - 架构参考（目录树/设计模式/API 端点全表）：`architecture-reference.md`
  - 依赖与运行时：`dependency-profiles.md`、`backend-application-profiles.md`、`PLATFORM_RUNTIME_FOUNDATION.md`、`local-inference-*.md`、`training-worker.md`
  - ADR：`docs/adr/`（Agent 主运行时、训练 worker 隔离、推理 Provider、依赖 profile、云端模型访问等）
  - 设计/计划：`docs/plans/`、`docs/design/`；阶段完成记录在 `docs/history/`
- `mcps/` —— 本地 MCP 工具定义（如 MiniMax / tasks），非应用运行时核心
- `electron/` —— Electron 桌面运行时、进程监督、安全 IPC、受管 Python runtime pack 与 app:// renderer
- 根 `pyproject.toml` + `uv.lock` —— uv 依赖事实源
- `docker-compose.yml` —— 容器编排（api / training-worker / inference-service 等）

## 项目特性

- **中文支持**：UI 和日志支持中文（zh_CN）
- **Windows 优化**：批处理脚本便于设置
- **低显存支持**：针对 4GB+ GPU 优化，支持 INT4/QLoRA
- **Electron 桌面端**：正式桌面产品边界；单机数据自持并保留后端服务可替换性
- **云端 AI 集成**：支持外部 AI API（OpenAI、Anthropic 等），经 `server/ai/gateway.py` 统一客户端池
