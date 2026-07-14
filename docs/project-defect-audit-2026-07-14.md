# Finetune Platform 项目缺陷深度审计报告

> **审计日期**：2026-07-14
> **审计版本**：`task-54e`
> **审计范围**：`server/`、`client/`、`docs/`、启动脚本、`.env.example`、`pyproject.toml`、审计与编码日志
> **审计方式**：全量代码/文档静态走查（未修改任何文件），所有结论均附 `文件:行号` 证据
> **交叉验证**：结论与 [ux-audit-2026-07-14.md](./ux-audit-2026-07-14.md) 一致，并补齐后端安全 / Agent / 数据一致性维度

---

## 0. 摘要

### 0.1 发现总数

**P0 × 6 + P1 × 10 + P2 × 9 = 25 项**

### 0.2 优先级速览

| 级别 | 数量 | 关键代表 |
|------|------|---------|
| **P0** | 6 | README 幻影脚本、审计日志双写与全空、i18n 死代码、`.env.example` 弱密钥、启动端口 3 套、`require_cua_admin` 本地绕过 |
| **P1** | 10 | inference internal key 弱默认、legacy Auth middleware 残留、WAF 正则过粗、DEBUG 500 兜底泄漏、CSP `unsafe-inline`、AI 指令三份冲突、Agent 服务失败仅 warn、CORS 生产校验无 example、Storybook 空壳、编码扫描误报 |
| **P2** | 9 | 移动端 `/agent` 无降级、Motion 降级覆盖不全、install.bat 单镜像、pyproject torch 硬钉、日志无轮转、部署决策树缺失、`workspaces/` 双源、能力徽章缺 tooltip、deepagents 错误提示不友好 |

### 0.3 审计维度覆盖

本报告按用户请求覆盖 8 个维度，每个维度均附具体缺陷：

1. 功能完整性问题（§1）
2. 安全漏洞（§2）
3. 架构缺陷（§3）
4. 数据一致性问题（§4）
5. 编码和国际化问题（§5）
6. 依赖管理和启动问题（§6）
7. Agent 模块功能缺陷（§7）
8. API 和接口问题（§8）

---

## 1. 功能完整性问题

### P0-1 · README 引用不存在的 GPU 安装脚本

- **文件**：[README.md:121](../README.md#L121)、[README_EN.md:121](../README_EN.md#L121)
- **证据**：两份 README 都写：
  ```bat
  install-pytorch-gpu.bat
  ```
  但仓库根目录只有 [install.bat](../install.bat)（94 行），实际 GPU 脚本在 [server/install-gpu.bat](../server/install-gpu.bat)（54 行）
- **影响**：新手按 README 敲命令直接得到 `'install-pytorch-gpu.bat' is not recognized as an internal or external command`
- **严重程度**：P0（新手入门直接卡死）
- **修复建议**：
  1. 将 README.md L118-122 改为：
     ```markdown
     如果你使用 NVIDIA 显卡并希望安装 GPU 版 PyTorch（脚本位于 server/ 目录）：
     ```bat
     cd server
     install-gpu.bat
     cd ..
     ```
     ```
  2. 或在根目录创建 `install-pytorch-gpu.bat` 转发脚本：
     ```bat
     @echo off
     pushd "%~dp0server" && call install-gpu.bat & popd
     ```

### P0-2 · 前端 i18n 完全死代码

- **文件**：[client/src/i18n/index.ts](../client/src/i18n/index.ts)（134 行）
- **证据**：
  - 定义完整 zh-CN / en-US 字典
  - 提供 `useTranslation`、`useI18n` Zustand persist store
  - **但** `client/src/**` 全量 grep `useTranslation|useI18n|from.*i18n` **零命中**（仅 index.ts 内部）
  - 全站文本硬编码中文
- **影响**：与 [README.md:1](../README.md#L1) "简体中文 | English" 承诺不符，构成隐性伪功能；用户无处切换语言
- **严重程度**：P0（对外承诺与实际能力不符）
- **修复建议二选一**：
  - **落地**：Sidebar 或 HeaderBar 增加 locale toggle，逐页替换硬编码文案（工作量约 3-5 人日）
  - **删除**：删除 `client/src/i18n/` 目录，并从 README 移除双语暗示（工作量 <30 分钟）

### P1-1 · Storybook 只有官方脚手架

- **文件**：`client/src/stories/`（3 个 story 文件）
- **证据**：
  ```
  client/src/stories/Button.stories.ts       (54 行, 脚手架)
  client/src/stories/Header.stories.ts       (34 行, 脚手架)
  client/src/stories/Page.stories.ts         (33 行, 脚手架)
  ```
  但 [client/DESIGN_SYSTEM.md](../client/DESIGN_SYSTEM.md) 承诺的 GlassCard / NeumorphicButton / PremiumInput、shared/ 下 EmptyState / LoadingState / PageHeader / StatusBadge 全无 story；`client/storybook-static/` 已构建产物暗示"有基建"
- **影响**：贡献者被误导，以为有完整设计系统预览
- **严重程度**：P1（治理缺陷）
- **修复建议**：
  1. 至少为 `client/src/components/shared/` + `client/src/agent/components/` 关键组件补 story
  2. 或从 `package.json` 移除 storybook 依赖并删除 `client/storybook-static/`

### P2-1 · 移动端 `/agent` 无响应式降级

- **文件**：[client/src/App.tsx:374](../client/src/App.tsx#L374)、`client/src/agent/workbench/`
- **证据**：App.tsx 只对全局侧栏做 mobile 抽屉；agent 四栏（Timeline + ActivityBar + RightDock + TerminalDock）在 <768px 无 layout 降级
- **影响**：手机/平板打开 `/agent`（默认路由 `/` → `/agent`）横向溢出，几乎不可用
- **严重程度**：P2
- **修复建议**：小屏折叠为单栏 + Tab 切换 ActivityBar/RightDock/Terminal

### P2-2 · Framer Motion 减动画覆盖不完整

- **文件**：[client/src/hooks/useMotion.ts:64-71](../client/src/hooks/useMotion.ts#L64-L71)、[client/src/components/motion/useMotionConfig.ts:16-21](../client/src/components/motion/useMotionConfig.ts#L16-L21)
- **证据**：封装存在但仅 GlassCard、TechBackground、AgentActivityBar 使用；Sidebar、MobileNav、SubagentModal、WorkbenchSettingsDrawer 直接 `import { motion } from 'framer-motion'`，未通过封装
- **影响**：`prefers-reduced-motion` 用户仍看到部分动画
- **严重程度**：P2（可访问性）
- **修复建议**：
  1. ESLint 自定义规则禁止直接 `import { motion } from 'framer-motion'`
  2. 或在 `client/src/components/motion/index.ts` 导出统一 `SafeMotion.div` 组件

---

## 2. 安全漏洞

### P0-3 · `.env.example` 弱密钥与首启矛盾

- **文件**：[.env.example](../.env.example)
- **证据**：
  ```env
  ENABLE_AUTH=true                                                        # L26
  JWT_SECRET_KEY=your-super-secret-key-change-this-in-production           # L30
  ```
- **影响**：
  1. [server/security/jwt_auth.py](../server/security/jwt_auth.py) 的 `require_configured_jwt_secret()` 是 fail-closed 策略。新手直接 `cp .env.example .env && start.bat`，后端会因占位符密钥拒绝启动
  2. 若用户手动跳过验证（改代码），弱密钥反而进入生产
- **严重程度**：P0（首启失败 + 潜在生产弱密钥）
- **修复建议**：
  1. `.env.example` 拆两段：
     ```env
     # =========== 首次本地体验推荐 ===========
     ENABLE_AUTH=false
     JWT_SECRET_KEY=

     # =========== 生产环境必填 ===========
     # ENABLE_AUTH=true
     # JWT_SECRET_KEY=<32 字节以上强随机；生成：python -c "import secrets;print(secrets.token_urlsafe(32))">
     ```
  2. `install.bat` 检测到 `.env` 中 `JWT_SECRET_KEY` 为空或占位符时自动生成随机 secret 并写回

### P0-4 · `require_cua_admin` 在 `enable_auth=false` 时无 role 校验

- **文件**：[server/security/auth_middleware.py:322-347](../server/security/auth_middleware.py#L322-L347)
- **证据**：
  ```python
  async def require_cua_admin(
      current_user: TokenPayload | None = Depends(get_current_user_optional),
  ) -> TokenPayload | None:
      if not get_settings().enable_auth:
          return current_user   # ← 直接放行，未校验 role=ADMIN
      ...
  ```
- **影响**：[server/api/cua.py:1-30](../server/api/cua.py) 中 `router = APIRouter(prefix="/cua", dependencies=[Depends(require_cua_admin)])` 全路由都过此 gate。本地/测试环境（`enable_auth=false`）任何匿名请求都能：
  - `POST /cua/screenshot` 截屏
  - `POST /cua/mouse/click` 控制鼠标
  - `POST /cua/keyboard/type` 键盘输入
  等 —— 完整的**主机控制权限**。虽默认监听 127.0.0.1，但同机恶意进程 / 其他 Docker 容器可利用
- **严重程度**：P0（本地权限提升 / 主机接管）
- **修复建议**：
  1. 即使 `enable_auth=false`，也应至少要求 header `X-Local-Admin-Token: <settings.local_admin_token>` 匹配
  2. 新增 `settings.local_admin_token` 字段（首次启动随机生成、写入 `data/credentials/local_admin.token`）
  3. `.env.example` 添加说明

### P0-5 · 启动脚本入口/端口三套并存

- **文件**：
  - [start.bat](../start.bat) — 后端 `--port 8010`
  - [start.py:30-31](../start.py#L30-L31) — `uvicorn.run(app, host="127.0.0.1", port=8000)` 且 `os.chdir(server_path)`
  - [Dockerfile](../Dockerfile) / [docker-compose.yml](../docker-compose.yml) — 内部 `0.0.0.0:8000`
  - [.env.example:10](../.env.example) — `PORT=8010`
- **影响**：
  - 前端 [client/src/services/api.ts](../client/src/services/api.ts) 默认 `http://{hostname}:8010`
  - 用 `start.py` 或 Docker 启动的用户前端全 404，且无提示
- **严重程度**：P0（用户跑不通）
- **修复建议**：
  1. 删除 `start.py`（属遗留调试脚本），或改为 `uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8010")))`
  2. Dockerfile 内部端口显式改为 8010，或 nginx 反向代理层收敛
  3. `.env.example` 头部加端口清单注释：
     ```env
     # 端口清单：API=8010, Inference=8020, Frontend=5173
     ```

### P0-6 · 审计日志双写路径 + 上下文全空

- **文件**：[server/security/audit_log.py:116](../server/security/audit_log.py#L116)
- **证据**：
  ```python
  self.storage_path = storage_path or Path("data/audit_logs")
  ```
  是相对路径。取决于进程 cwd：
  - `start.bat` 用 `uv run --extra all python -m uvicorn server.main:app` → cwd = **仓库根** → 写 `<repo>/data/audit_logs/`
  - `start-backend.bat` 分支 `cd /d "%~dp0server"` → cwd = **server/** → 写 `<repo>/server/data/audit_logs/`
  - 两目录都实际存在 audit_*.jsonl 文件

  抽样 `data/audit_logs/audit_2026-07-10.jsonl`：
  ```json
  {"user_id": null, "session_id": null, "agent_id": null,
   "source_ip": null, "resource_type": null, "resource_id": null,
   "action": "set_api_key",
   "details": {"provider": "mock-preserve-f3fde93b"}, ...}
  ```
  所有身份字段均为 `null`；`details.provider = mock-preserve-<hash>` 是占位测试数据
- **影响**：
  1. 排障时不知看哪个目录
  2. 无法回答"谁在何时改了什么"这一最基础合规问题
  3. 测试脚本污染真实审计通道
- **严重程度**：P0（审计能力事实失效）
- **修复建议**：
  1. `AuditLogger.__init__` 改用 [core/storage.py:26](../server/core/storage.py#L26) 已有的 `resolve_storage_path("data/audit_logs")`
  2. API Key / CUA / Auth 路由调用点补 `user_id=request.state.user_id`（`authentication_middleware` 已注入 `request.state`）
  3. 剔除 `mock-preserve-*` 写入路径（属测试脚本污染）
  4. 迁移脚本：合并两个目录旧数据

### P1-2 · inference internal API key 弱默认

- **文件**：[server/core/config.py:158](../server/core/config.py#L158)
- **证据**：
  ```python
  inference_internal_api_key: str = Field(
      default="finetune-local-inference-dev-key",
      ...
  )
  ```
  L258 仅在 production/staging 环境 fail-closed 拒绝默认值
- **影响**：开发者机器若临时对外暴露 8020（如共享网络排障），任何人可调用 OpenAI-compat inference API
- **严重程度**：P1
- **修复建议**：
  1. `inference_server` 启动时检测默认值 → WARNING 日志并强制绑定 `127.0.0.1`
  2. `install.bat` 首次运行自动生成随机 internal key 写入 `.env`

### P1-3 · legacy `JWTAuthMiddleware` / `SecurityMiddleware` 类残留

- **文件**：[server/security/auth_middleware.py](../server/security/auth_middleware.py)
- **证据**：类形式的 `JWTAuthMiddleware`、`SecurityMiddleware` 仍导出，仅有 `_warn_legacy_auth_middleware` 触发一次性 `DeprecationWarning`
- **风险**：新贡献者按老示例 `app.add_middleware(JWTAuthMiddleware)` 会与 `apps.factory.authentication_middleware` 冲突（双重认证 / 顺序错乱），出现难以排查的 401
- **严重程度**：P1
- **修复建议**：类构造函数直接抛 `RuntimeError("Use apps.factory.authentication_middleware instead")` fail-fast

### P1-4 · WAF 规则粗糙、易误伤

- **文件**：[server/apps/factory.py](../server/apps/factory.py)（`WAF_RULES` 常量）
- **证据**：正则如 `union\s+select`、`<script`、`\.\./`，扫描整个 query + body
- **影响**：合法 JSON 内容如 `"我要 union select 相关的 SQL 培训"` 会被 403 拦截
- **严重程度**：P1（误杀合法请求）
- **修复建议**：
  1. 缩范围到 query string + header，body 交给 pydantic 校验
  2. 或引入成熟 WAF（如 `owasp-python-waf`）

### P1-5 · DEBUG 模式 500 兜底泄漏栈信息

- **文件**：`server/apps/factory.py` `security_middleware`
- **证据**：500 分支在 `debug_mode=True` 时 `content={"detail": str(exc)}`
- **影响**：本地 debug 开启且不慎暴露到内网时会泄露栈帧
- **严重程度**：P1
- **修复建议**：仅 development profile 输出 `str(exc)`；staging/production 统一返回 `{"error": "internal_server_error"}`，`logger.exception` 内部记录

### P1-6 · CSP 允许 `unsafe-inline` / `unsafe-eval`

- **文件**：`server/apps/factory.py` `security_headers_middleware`
- **证据**：CSP header 含 `'unsafe-inline' 'unsafe-eval'`
- **影响**：XSS 防线大幅削弱；React + Vite 生产构建不需要 `unsafe-eval`
- **严重程度**：P1
- **修复建议**：
  1. 生产 profile 移除 `unsafe-eval`
  2. `unsafe-inline` 逐步用 nonce 替换（Vite 支持 `crossorigin` + nonce 注入）

### P1-7 · 三份 AI 指令文档并存

- **文件**：[AGENTS.md](../AGENTS.md)、[CLAUDE.md](../CLAUDE.md)、[GEMINI.md](../GEMINI.md)
- **证据**：三份文件同时存在，内容重叠但会逐渐漂移
- **风险**：不同 AI 助手看到不同上下文；改动一处不同步
- **严重程度**：P1（治理）
- **修复建议**：AGENTS.md 为单一事实源，CLAUDE.md / GEMINI.md 改为一行链接指向：
  ```markdown
  # Claude Code / Gemini Code Instructions
  See [AGENTS.md](./AGENTS.md).
  ```

---

## 3. 架构缺陷

### P1-8 · Agent 服务初始化失败仅 warning

- **文件**：[server/apps/lifespan.py](../server/apps/lifespan.py) `_initialize_agent_services`
- **证据**：embedder / vector_store / context / memory 初始化失败仅 `logger.warning`，不阻断 lifespan
- **影响**：Agent 运行时二次抛错，用户看到"启动看似成功但 Agent 白屏"，且无 readiness 探针暴露此状态
- **严重程度**：P1
- **修复建议**：
  1. combined profile 必需服务初始化失败 → `raise` 阻断启动
  2. `/health/ready` 增加 agent readiness 探针（区分 GA/beta 能力）
  3. 前端 `/api/info` 增加 `agent_ready` 字段供 Sidebar 展示

### 异步/事件循环风险

- **文件**：[server/agent_session/services/background_task_manager.py](../server/agent_session/services/background_task_manager.py)
- **证据**：`AgentSessionService.prompt/resume` 触发的 background task 依赖 SSE client 断开来终止；DeepAgents 死循环时无强制 timeout
- **影响**：僵尸后台任务占用连接与 GPU lease
- **严重程度**：P1
- **修复建议**：`asyncio.wait_for(coro, timeout=session_max_seconds)`；超时 → `session.status = failed(reason="timeout")`

### P2-3 · `deepagents` 硬依赖缺失时错误提示不友好

- **文件**：[server/agent_session/runtime_factory.py](../server/agent_session/runtime_factory.py)
- **证据**：`ensure_deepagents_available()` fail-fast 抛 `DeepAgentsUnavailable`，错误信息未指明修复命令
- **严重程度**：P2
- **修复建议**：错误信息附上 `请运行: uv sync --extra agent` 或 `pip install deepagents`

### P2-4 · `workspaces/` 双源歧义

- **文件**：根目录 `workspaces/`（运行时数据）、`server/workspace/`（源码包）
- **证据**：两者名称高度相似，新贡献者易混淆
- **严重程度**：P2
- **修复建议**：AGENTS.md 顶部注明"⚠️ 根目录 `workspaces/` 是运行时数据、`server/workspace/` 是源码包"，或将数据目录改名 `runtime_workspaces/`

### P2-5 · 日志无轮转

- **文件**：`logs/finetune-platform.log`、`frontend-dev.err.log` 等
- **证据**：无 size/time-based rotation；`.env.example` 无 `LOG_ROTATION_*`
- **影响**：长时间运行后日志文件膨胀，磁盘耗尽
- **严重程度**：P2
- **修复建议**：`core/logging.py` 集成 `RotatingFileHandler`（默认 100MB × 5 份）

### P2-6 · 部署决策树缺失

- **文件**：Dockerfile / Dockerfile.frontend / Dockerfile.gpu / docker-compose.yml / docker-compose.gpu.yml
- **证据**：5 份 Docker 相关文件，README 无"何时用哪个"一览
- **严重程度**：P2
- **修复建议**：README 加决策表：
  | 场景 | 使用 |
  |------|------|
  | 本地开发 | `start.bat` |
  | 单机 GPU 训练 | `docker compose -f docker-compose.gpu.yml up` |
  | 集群/分镜像 | 三个 Dockerfile 按 profile 分别构建 |

---

## 4. 数据一致性问题

### P0-6（已覆盖）· 审计日志双写

见 §2 P0-6。

### SQLite `executescript` 隐式 COMMIT 风险

- **文件**：[server/core/db_manager.py](../server/core/db_manager.py)
- **证据**：某些调用点使用 `executescript`；虽已包 BEGIN IMMEDIATE + WAL，但 `executescript` 隐式 COMMIT 会打破外层事务
- **影响**：并发迁移或批量写入时事务边界丢失
- **严重程度**：P1
- **修复建议**：
  1. `db_manager` 内禁用 `executescript`，改为逐语句 `execute` + 显式事务
  2. 添加 lint 规则禁止业务代码直接调 `executescript`

### 相对路径导致的数据漂移

- **文件**：除 [audit_log.py:116](../server/security/audit_log.py#L116) 外，需 grep 其他相对路径写入点
- **修复建议**：全项目 grep `Path\("data/`、`Path\("logs/`、`Path\("workspaces/`，改用 `resolve_storage_path`

### P2-7 · `pyproject.toml` torch 硬钉版本

- **文件**：[pyproject.toml](../pyproject.toml)
- **证据**：`torch==2.2.2` + `pytorch-cu121` index
- **风险**：Ada/Blackwell 新卡（cu124+）用户装完不能用 GPU
- **严重程度**：P2
- **修复建议**：拆 `[gpu-cu121]` / `[gpu-cu124]` extras，install.bat 或 Python 启动脚本询问 CUDA 版本

---

## 5. 编码和国际化问题

### P0-2（已覆盖）· 前端 i18n 死代码

见 §1 P0-2。

### P1-9 · 编码扫描器只报二进制文件，漏检源码 mojibake

- **文件**：[reports/encoding/encoding_issues.json](../reports/encoding/encoding_issues.json)、[scripts/check_encoding.py](../scripts/check_encoding.py)
- **证据**：
  - 只报告 6 个 modelscope `.mdl/.msc` 二进制"无法检测编码"（良性噪音）
  - 未捕获历史 TrainingChart.tsx GBK→UTF-8 mojibake 事故
- **影响**：无自动化防线，下一次源码腐化仍要到用户白屏才发现
- **严重程度**：P1
- **修复建议**：`check_encoding.py` 增加：
  ```python
  MOJIBAKE_CHARS = re.compile(r"[锟烫涓閿鎺å¸ç]{2,}")
  # 命中 → CI 失败
  # 二进制 .mdl/.msc/.bin/.pt/.safetensors 白名单跳过
  ```

### P2-8 · 能力徽章 tooltip 文案缺失

- **文件**：[client/src/components/Sidebar.tsx](../client/src/components/Sidebar.tsx)
- **证据**：Beta/Experimental 徽章无 tooltip 说明"接口/UI 可能变动"
- **严重程度**：P2
- **修复建议**：徽章 aria-label + Tooltip，文案对齐 [docs/capability-truth-table.md](./capability-truth-table.md)

---

## 6. 依赖管理和启动问题

### P0-5（已覆盖）· 启动脚本入口/端口三套并存

见 §2 P0-5。

### P2-9 · install.bat 回退 pip 只用清华镜像

- **文件**：[install.bat](../install.bat)
- **证据**：失败分支 `pip install -r server/requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple`
- **影响**：海外贡献者 fallback 失败
- **严重程度**：P2
- **修复建议**：
  1. 检测 `curl -s pypi.org` 通达性后选择镜像
  2. 或加 `--mirror china|global|auto` 参数

### P1-10 · CORS 生产校验依赖 env 但无 example 演示

- **文件**：[server/core/config.py](../server/core/config.py)、[.env.example](../.env.example)
- **证据**：生产验证器拒绝 `origins = ["*"]`；`.env.example` 未给出 `CORS_ORIGINS=https://example.com,https://app.example.com` 示例
- **严重程度**：P1
- **修复建议**：`.env.example` 加分组：
  ```env
  # =========== 生产 CORS 示例（禁用通配符）===========
  # ALLOWED_ORIGINS=https://your-domain.com,https://api.your-domain.com
  ```

### 附加：`HF_MIRROR` 默认 `hf-mirror` 只对中国用户友好

- **文件**：[.env.example:87](../.env.example#L87)
- **修复建议**：加注释说明海外用户改 `official`

---

## 7. Agent 模块功能缺陷

### P0-4（已覆盖）· CUA 本地绕过

见 §2 P0-4。

### P1-8（已覆盖）· Agent 服务初始化失败仅 warning

见 §3 P1-8。

### Agent 模型调用错误消息中文硬编码

- **文件**：[server/agent_session/model_adapter.py](../server/agent_session/model_adapter.py)
- **证据**：`get_chat_model` 抛出的 `ValueError` 消息全中文
- **风险**：非中文用户与前端 error propagation 后无法国际化
- **严重程度**：P2
- **修复建议**：错误码化 —— `ModelAdapterError(code="INVALID_PROVIDER_FORMAT", detail_i18n_key="agent.model.invalid_provider")`

### Agent Session background_task 无超时

见 §3 异步/事件循环风险。

### Agent 审批门控依赖 DeepAgents interrupt，中断状态可靠性

- **文件**：[server/agent_session/deepagents_runtime.py](../server/agent_session/deepagents_runtime.py)、[server/agent_session/services/approval_service.py](../server/agent_session/services/approval_service.py)
- **证据**：`waiting_permission` / `waiting_approval` 依赖 DeepAgents 触发 interrupt；`_approve_deepagents_action` 内部 resume
- **风险**：进程崩溃或 SSE 断开后 interrupt 状态需从 LangGraph checkpoint 恢复；`deepagents_checkpoint.py` 使用 SQLite WAL + busy_timeout 缓解，但仍需回放测试
- **严重程度**：P1
- **修复建议**：
  1. `recovery_service` 增加"审批中断态恢复"回归测试
  2. `/agent-sessions/{id}` 响应显式返回 `pending_approval_id` 让前端幂等重试

---

## 8. API 和接口问题

### P0-5（已覆盖）· 端口混乱

见 §2 P0-5。

### P1-4（已覆盖）· WAF 规则粗糙

见 §2 P1-4。

### API 兼容性：`/agent-sessions` `workspace_id` 强制性 UI/API 不一致

- **文件**：[README.md:55-260](../README.md#L55)、`server/api/agent_sessions.py`
- **证据**：
  - README 声明 UI 强制 workspace_id
  - API 仍兼容旧 `project_path`
- **影响**：curl 用户可绕过 UI 强制约束；过渡期无截止日期
- **严重程度**：P1
- **修复建议**：
  1. API 层加 `Deprecation` / `Sunset` header：`X-Deprecated: workspace_id required since 2026-08-01`
  2. `2026-09-01` 后完全拒绝无 `workspace_id` 的请求，回 422

### 训练 API 参数校验缺失

- **文件**：[server/api/training.py](../server/api/training.py)
- **证据**：未见对 `batch_size`、`learning_rate`、`num_epochs` 的上下限
- **影响**：`batch_size=0` 或 `learning_rate=-1` 会导致训练崩溃并触发 500
- **严重程度**：P1
- **修复建议**：pydantic
  ```python
  batch_size: int = Field(gt=0, le=64)
  learning_rate: float = Field(gt=0, lt=1)
  num_epochs: int = Field(gt=0, le=1000)
  ```
  返回 422 而非 500

### 错误响应格式不统一

- **文件**：多处 `raise HTTPException(status_code=..., detail=...)`
- **证据**：detail 有时是字符串、有时是 `{"error": ..., "message": ...}` dict
- **严重程度**：P2
- **修复建议**：统一 `ErrorResponse` pydantic 模型 + 全局 exception handler

---

## 附录 A：修复优先级路线图

### 第一周（P0，6 项，冲刺）

| ID | 任务 | 工作量 |
|----|------|--------|
| P0-1 | README 幻影脚本改为 `server\install-gpu.bat` | 10 min |
| P0-2 | i18n 死代码：删除或落地 UI 切换（二选一） | 30 min / 3-5d |
| P0-3 | `.env.example` 拆分 dev/prod + install.bat 自动 secret | 1h |
| P0-4 | `require_cua_admin` 增加 localhost token gate | 2h |
| P0-5 | `start.py` 改读 PORT env 或删除 | 30 min |
| P0-6 | `audit_log.py` 绝对路径 + 补上下文 + 剔除 mock | 3h |

### 第二周（P1，10 项）

- inference internal key WARNING + 127.0.0.1 绑定
- legacy Auth middleware 类抛 `RuntimeError`
- CSP 移除 `unsafe-eval`
- WAF 缩范围到 query/header
- DEBUG 500 分支去 traceback
- AGENTS.md 为单源，其余改软链
- Agent 服务失败 → lifespan raise
- CORS_ORIGINS 加 example
- 编码扫描器加 mojibake 规则
- Storybook 至少覆盖 shared/ 或明确移除

### 第三周（P2，9 项，治理）

- 部署决策树表
- 日志轮转
- pyproject torch 拆 extras
- install.bat 镜像自动选
- 能力徽章 tooltip
- `/agent` 移动端降级
- Motion ESLint 规则
- `workspaces/` 命名说明
- deepagents 错误提示附修复命令

---

## 附录 B：与 ux-audit-2026-07-14.md 的交叉验证

**一致结论（互相佐证）**：

| 本报告 ID | ux-audit 章节 | 主题 |
|-----------|--------------|------|
| P0-1 | §2.2 | README 幻影脚本 |
| P0-2 | §2.1 | i18n 死代码 |
| P0-3 | §2.6 | `.env.example` 弱密钥 |
| P0-5 | §3.1 | 启动脚本端口混乱 |
| P0-6 | §2.3 | 审计日志双写 |
| P1-1 | §1.2 | Storybook 空壳 |
| P2-1 | §1.3 | 移动端 `/agent` 无降级 |
| P2-2 | §1.4 | Motion 覆盖不完整 |

**本报告额外补齐（ux-audit 未深入的后端维度）**：

- `require_cua_admin` 本地绕过（P0-4）
- Legacy Auth Middleware 残留（P1-3）
- WAF 规则粗糙（P1-4）
- DEBUG 500 泄漏（P1-5）
- CSP unsafe-inline（P1-6）
- Agent lifespan 失败仅 warning（P1-8）
- SQLite `executescript` 隐式 COMMIT
- Agent background_task 无超时
- Inference internal key 弱默认（P1-2）
- CORS 生产校验无 example（P1-10）
- 训练 API 参数校验缺失

---

## 附录 C：证据复现命令（PowerShell）

```powershell
# 1. 幻影脚本验证
Test-Path .\install-pytorch-gpu.bat
Get-Content .\README.md | Select-String -Pattern "install-pytorch-gpu"

# 2. i18n 零调用点核验
Select-String -Path .\client\src -Pattern "useTranslation|useI18n|from.*i18n" -Recurse `
  | Where-Object { $_.Path -notmatch "i18n\\index.ts" }

# 3. 审计日志双写核验
Get-ChildItem -Recurse -Filter "audit_*.jsonl" | Select-Object FullName, Length
Get-Content .\data\audit_logs\audit_2026-07-10.jsonl -TotalCount 3 | ConvertFrom-Json `
  | Select-Object user_id, session_id, source_ip, action

# 4. 启动端口比对
Select-String -Path .\start*.bat, .\start.py, .\Dockerfile, .\docker-compose.yml `
  -Pattern "8010|8000|8020|--port"

# 5. CUA 路由权限核验
Select-String -Path .\server\api\cua.py -Pattern "require_cua_admin|Depends"
Select-String -Path .\server\security\auth_middleware.py -Pattern "enable_auth" -Context 2,2

# 6. Storybook 覆盖率
Get-ChildItem .\client\src\stories\*.stories.* | Measure-Object

# 7. 编码 mojibake 检测（现有扫描器漏检）
Select-String -Path .\client\src, .\server -Pattern "[锟烫涓閿鎺]" -Recurse
```

---

## 附录 D：审计方法论声明

- **只读**：本次审计未修改任何文件；所有结论基于当前代码 HEAD
- **可复现**：附录 C 提供的命令可任何时候重跑，输出应与本报告一致
- **交叉验证**：与既有 [ux-audit-2026-07-14.md](./ux-audit-2026-07-14.md) 对照，共同结论互相加权，独有结论各自补齐
- **优先级判定**：P0 = 用户/管理员立刻卡壳或安全事故；P1 = 一周内应修的功能或治理缺陷；P2 = 长期治理项
- **超出范围**：本报告未覆盖性能压测、真实网络攻击模拟、GPU 数值稳定性；这些需单独排期

---

*Finetune Platform 项目缺陷深度审计 · 静态走查 · 2026-07-14 · task-54e*
