# Finetune Platform 2.0 全仓库深度审查报告

> **报告编号**：AUDIT-2026-07-14-FULL
> **检测日期**：2026-07-14
> **检测范围**：全仓库（后端 Python / 前端 TypeScript / C++ 桥接 / CI-CD / 依赖 / 测试 / 文档）
> **检测方法**：静态扫描（AST / Ruff / TSC / ESLint / 编码守卫）+ 结构度量 + 配置审阅 + 依赖拓扑分析
> **仓库版本**：`pyproject.toml` version `2.1.0` · Python 3.11 · React 18 · FastAPI 0.109
> **执行环境**：Windows 25H2 · PowerShell 8 · Python 3.11 · Node 18+

---

## 目录

1. [执行摘要](#一执行摘要)
2. [检测方法论](#二检测方法论)
3. [代码质量与规范](#三代码质量与规范)
4. [项目结构与架构](#四项目结构与架构)
5. [技术栈合规性](#五技术栈合规性)
6. [数据一致性与完整性](#六数据一致性与完整性)
7. [测试覆盖率评估](#七测试覆盖率评估)
8. [工程实践（CI/CD、审查、安全）](#八工程实践cicd审查安全)
9. [按严重度分类的问题清单](#九按严重度分类的问题清单)
10. [改进建议路线图](#十改进建议路线图)
11. [附录：关键度量与命令](#十一附录关键度量与命令)

---

## 一、执行摘要

### 1.1 总体健康度：🟢 良好偏上（8.2 / 10）

Finetune Platform 呈现**成熟且工程化程度高**的状态：编码零缺陷、语法零错误、能力分层与依赖 profile 拆分执行到位，CI/CD 五段流水线齐备。主要债务集中在**样式规范收敛**（Ruff / TypeScript `any`）与**若干 God Module 拆分**，无深层架构或安全隐患。

### 1.2 关键指标概览

| 维度 | 指标 | 状态 |
|---|---|---|
| Python 语法 / 编码 | 495 个源文件全部 AST 可解析；683 文件通过编码守卫 | 🟢 |
| Python Ruff（门禁项） | 189 处（W291/W293/I001/UP015/UP012） | 🟡 |
| Python Ruff（全量） | 444 处（284 可 `--fix`、95 可 `--unsafe-fixes`） | 🟡 |
| TypeScript 类型 | `tsc --noEmit` **0 错误** | 🟢 |
| ESLint | **0 错误 / 72 警告**（全部 `@typescript-eslint/no-explicit-any`） | 🟡 |
| 后端测试 | 1215 用例中 **1198 收集成功**，1 个文件因 Windows 环境失败 | 🟡 |
| 前端测试 | 36 个 `*.test.tsx` | 🟢 |
| SQL 迁移 | 16 个（001–016 连续无缺号） | 🟢 |
| 生产源码硬编码密钥 | **零命中** | 🟢 |
| CI 流水线 | Lint / 后端单元 / 后端集成 / 前端 / 安全扫描 五段齐备 | 🟢 |
| 依赖 profile | 单 `pyproject.toml` 拆 8 个 extras + 4 份 requirements 分镜像 | 🟢 |
| 大文件（>800 行 后端 / >600 行 前端） | 17 + 21 = 38 处 | 🟡 |

### 1.3 三大即时行动项

1. **修 Windows 测试收集失败**：`cua/keyboard.py` 顶层 `import pyautogui` 在 Python 3.11 + 现代 `cv2` 环境下崩溃，导致 `test_architecture_cleanup.py` 无法 collect。改为函数体内惰性 import。
2. **一键 Ruff 自动修复**：`uv run ruff check server --fix` 消除 284 项安全修复项（含 121 unsorted-imports、65 whitespace），单次 PR 即可结清。
3. **Pydantic v2 字段名冲突**：`WorkspaceManifestV1.schema` 遮蔽父类属性，需改名。

---

## 二、检测方法论

### 2.1 静态分析工具矩阵

| 工具 | 目标 | 命令 |
|---|---|---|
| Python `ast.parse` | 语法 / Unicode 解码 | 遍历 `server/**/*.py` |
| `scripts/check_encoding.py` | mojibake / BOM / 私有区字符 | 683 个文本文件全量 |
| Ruff | 焦点规则 + 全量 | `ruff check server` |
| MyPy | 类型（配置项） | `mypy server`（CI 目前 advisory） |
| Black | 格式（配置项） | `black --check`（CI 目前 advisory） |
| TSC | 前端类型 | `tsc --noEmit` |
| ESLint | 前端规范 | `eslint src --ext .ts,.tsx` |
| Pytest collect-only | 测试可用性 | `pytest server/tests --collect-only -q` |
| 自研度量 | 大文件 / print / fetch / 硬编码路径 / 密钥 | Python 脚本遍历 |

### 2.2 检测覆盖率

- 后端 495 个 `.py`（排除 `__pycache__` / `.venv`）
- 前端 `client/src/**` 全量 `.ts / .tsx`
- 16 个 SQL 迁移
- 2 个 CI/CD workflow (`ci.yml` / `cd.yml`)
- 3 个 Dockerfile（`Dockerfile` / `Dockerfile.frontend` / `Dockerfile.gpu`）
- `pyproject.toml`, `client/package.json`, `.env.example`, `.gitignore`

### 2.3 参考基线

- [`AGENTS.md`](../../AGENTS.md)：能力分层、依赖 profile、Agent Session 生命周期等约定
- [`server/scripts/batch_fix_encoding.py`](../../server/scripts/batch_fix_encoding.py)：历史 mojibake 修复模式
- [`server/scripts/test_deep_integration.py`](../../server/scripts/test_deep_integration.py)：数据一致性 / E2E 测试参考
- [`server/context/models.py`](../../server/context/models.py)：Pydantic v2 模型规范样板

---

## 三、代码质量与规范

### 3.1 编码卫生 🟢 完美通过

[`scripts/check_encoding.py`](../../scripts/check_encoding.py) 已建立多重防线：

- BOM 检测（`codecs.BOM_UTF8`）
- Unicode 替换字符 `\ufffd`
- 私有使用区 U+E000–U+F8FF
- 历史事故 token（`宸茶繛鎺` = "已连接" 的 GBK 二次解码残留，来自 `TrainingChart.tsx` 过往事故）
- GBK/CP936→UTF-8 双重解码稀有区字符密度启发式（`_MOJIBAKE_HOT_CHARS`）

**结果**：**683 个文件全部通过**，零 mojibake。CI `lint` job 已强制执行（`ci.yml:41-42`）。

### 3.2 Python 语法 🟢

495 个 `.py` 文件全部 `ast.parse` 通过：**0 SyntaxError / 0 UnicodeDecodeError**。历史修复模式（参见 [`server/scripts/batch_fix_encoding.py`](../../server/scripts/batch_fix_encoding.py)）已不再命中新代码。

### 3.3 Ruff 问题分布 🟡

**焦点门禁**（CI `--select W291,W293,I001,UP015,UP012`）：**189 处**
**全量顾问**：**444 处**（284 可自动 fix，另 95 unsafe fix）

Top 规则命中：

| 规则 | 计数 | 严重度 | 修复方式 |
|---|---:|---|---|
| `I001` unsorted-imports | 121 | 低 | `--fix` |
| `W293` blank-line-with-whitespace | 65 | 低 | `--fix` |
| `UP042` replace-str-enum | 54 | 低 | 手工替换 `Enum` → `StrEnum` |
| `E402` module-import-not-at-top | 30 | 中 | 部分为有意延迟 import，需 `# noqa: E402` |
| `SIM105` suppressible-exception | 27 | 低 | 用 `contextlib.suppress` |
| `UP045` non-pep604-optional | 25 | 低 | `Optional[X]` → `X \| None` |
| `UP041` timeout-error-alias | 22 | 低 | 用内置 `TimeoutError` |
| `ARG005` unused-lambda-argument | 16 | 低 | |
| `F401` unused-import | 15 | 中 | 真实冗余导入 |
| `UP035` deprecated-import | 7 | 中 | 库 API 迁移 |
| `F541` f-string-missing-placeholders | 5 | 低 | 去掉 `f` 前缀 |
| `F841` unused-variable | 2 | 中 | 实际未用变量 |

**修复策略**：
```powershell
# 第一批（安全）
uv run ruff check server --fix

# 第二批（评估后）
uv run ruff check server --fix --unsafe-fixes
```

### 3.4 前端 Lint 🟡

- **TypeScript 类型**：`tsc --noEmit` **0 错误** ✅
- **ESLint**：**0 错误 / 72 警告**

72 个警告**全部**为 `@typescript-eslint/no-explicit-any`，集中在：

| 文件 | 大致数量 |
|---|---:|
| [`client/src/services/api.ts`](../../client/src/services/api.ts)（3523 行的巨型 API client） | 60+ |
| 其他分散 | 10+ |

**建议**：
- 短期：为 `api.ts` 中的 `any` 引入 `unknown` + zod 校验或类型守卫。
- 中期：引入 `openapi-typescript` 由后端 OpenAPI 自动生成契约类型，消除手写 `any` 的根源。

### 3.5 大文件（可维护性风险）🟡

**后端 >800 行（17 个）**：

| 行数 | 文件 | 建议 |
|---:|---|---|
| 2027 | [`server/core/storage.py`](../../server/core/storage.py) | 按领域拆：会话 / 事件 / parts / 训练 / 推理 |
| 1644 | [`server/api/inference/routes.py`](../../server/api/inference/routes.py) | 按引擎（HF / Ollama / llama.cpp / cloud）拆 |
| 1354 | [`server/api/training.py`](../../server/api/training.py) | 生命周期 / 进度 / 恢复 分离 |
| 1347 | [`server/api/evaluation.py`](../../server/api/evaluation.py) | 后台执行 / 人工评分 分离 |
| 1216 | [`server/security/sandbox.py`](../../server/security/sandbox.py) | 保留（安全内聚） |
| 1157 | [`server/api/cloud_chat.py`](../../server/api/cloud_chat.py) | 按 provider 拆 |
| 1106 | [`server/core/conversation_manager.py`](../../server/core/conversation_manager.py) | |
| 1080 | [`server/agent_session/trajectory.py`](../../server/agent_session/trajectory.py) | 门控器 / 评分器 分离 |
| 1079 | [`server/api/datasets.py`](../../server/api/datasets.py) | |
| 977 | [`server/rag/structured/db_connector.py`](../../server/rag/structured/db_connector.py) | |
| 924 | [`server/workspace/file_api.py`](../../server/workspace/file_api.py) | |
| 919 | [`server/ai/gateway.py`](../../server/ai/gateway.py) | |
| 912 | [`server/training_engine/pipeline.py`](../../server/training_engine/pipeline.py) | |
| 903 | [`server/api/cua.py`](../../server/api/cua.py) | |
| 859 | [`server/api/model_center.py`](../../server/api/model_center.py) | |
| 848 | [`server/api/workspace.py`](../../server/api/workspace.py) | |
| 818 | [`server/agent_session/deepagents_runtime.py`](../../server/agent_session/deepagents_runtime.py) | |

**前端 >600 行（21 个）**，最大：

| 行数 | 文件 |
|---:|---|
| **3523** | [`client/src/services/api.ts`](../../client/src/services/api.ts) |
| 1525 | [`client/src/pages/History.tsx`](../../client/src/pages/History.tsx) |
| 1260 | `client/src/test/AgentWorkbenchRuntime.test.tsx`（测试文件可放宽） |
| 1132 | [`client/src/pages/Evaluation.tsx`](../../client/src/pages/Evaluation.tsx) |
| 1025 | [`client/src/agent/components/AgentRunTimeline.tsx`](../../client/src/agent/components/AgentRunTimeline.tsx) |
| 919 | [`client/src/pages/Training/components/TrainingDashboard.tsx`](../../client/src/pages/Training/components/TrainingDashboard.tsx) |
| 887 | [`client/src/pages/Training/index.tsx`](../../client/src/pages/Training/index.tsx) |
| 881 | [`client/src/pages/Dashboard.tsx`](../../client/src/pages/Dashboard.tsx) |
| 835 | [`client/src/hooks/chat/useChatStream.ts`](../../client/src/hooks/chat/useChatStream.ts) |

### 3.6 命名与注释

- **Pydantic v2 规范样板**：[`server/context/models.py`](../../server/context/models.py) 中 `ProjectInfo` 及其子模型使用 `Field(..., description="...")` 完整描述字段，可作为其他模型的参考基线。
- **StrEnum 使用**：`TechStackType`、`SymbolType` 已用 Python 3.11 `StrEnum`，但仓库中仍有 54 处 `UP042` 命中，说明部分模块未跟进。
- **`print()` 残留**：27 处生产 print()：
  - 25 处在 [`server/scratch/`](../../server/scratch)（`.gitignore` 已排除，但磁盘残留）
  - 2 处在 [`server/api/inference/routes.py`](../../server/api/inference/routes.py)
  - 1 处在 [`server/api/model_center.py`](../../server/api/model_center.py)

  API 层的 3 处应替换为 `logger.*`。

---

## 四、项目结构与架构

### 4.1 后端模块分布

```
server/  (495 个 .py)
├── tests/            (122)  # 正式测试套件
├── api/              ( 70)  # FastAPI 路由层
├── core/             ( 56)  # 存储 / 训练队列 / GPU 协调 / 迁移
├── agent_session/    ( 48)  # 唯一 Agent 执行底座
├── scripts/          ( 24)  # 临时调试脚本（非 pytest）
├── context/          ( 18)  # 项目上下文
├── workspace/        ( 16)  # 工作区
├── training_engine/  ( 15)  # 训练引擎
├── cua/              ( 15)  # 计算机使用 Agent
├── security/         ( 15)  # 安全策略
├── rag/              ( 13)  # RAG 系统
├── gateway/          (  9)  # WebSocket 入口
├── apps/             (  9)  # 应用装配边界
└── ...
```

### 4.2 能力分层执行度 🟢

[`server/apps/capability_registry.py`](../../server/apps/capability_registry.py) 作为 GA/Beta/Experimental 单一事实源：

- **GA (7)**：device / models / datasets / training / inference / chat_sessions / knowledge_base
- **Beta (5)**：project_context / memory / model_center / workspace / cloud_chat
- **Experimental (6)**：cua / heartbeat / mcp / gateway / ocr_fallbacks / action_recorder

**验证点**：
- ✅ `/api/info` 通过 `build_info_capability_payload()` 读取此注册表
- ✅ 前端 `client/src/capability/tiers.ts` 与后端对齐
- ✅ `EXPERIMENTAL_ROUTER_SPECS` 定义 legacy 别名与 `/experimental/*` 双挂载
- ✅ `ENABLE_EXPERIMENTAL_CAPABILITIES` 环境变量控制生产默认关闭

### 4.3 应用装配三档 profile 🟢

| profile | 独立入口 | 端口 | 依赖 extras |
|---|---|---|---|
| `combined` | `server.main:app` / `server.apps.combined:app` | 8010 | `all` |
| `agent` | `server.apps.agent:app` | 8011 | `agent`+`rag`+`cua`+`modelhub` |
| `finetune` | `server.apps.finetune:app` | 8012 | `training`+`gpu` or `inference` |
| `inference_server` | `server.inference_server` | 8020 | `inference` |
| `training_worker` | `server.training_worker` | — | `training`+`gpu` |

### 4.4 前端结构 🟢

`client/src/agent/` 独立域内含 `attention` / `config` / `diagnostics` / `protocol` / `runtime` / `transport` / `commands` / `selectors` / `components` / `workbench` / `testing` 十一个子域，职责划分符合 AGENTS.md。

**约定合规检查**：
- ✅ 页面禁止散落 `fetch()`：仅 1 处例外 [`client/src/hooks/chat/useChatStream.ts`](../../client/src/hooks/chat/useChatStream.ts)（SSE 流，AGENTS.md 明确允许）
- ✅ API 集中在 `services/`
- ✅ Runtime 显式映射，避免类型漂移

### 4.5 结构隐患 🟡

| # | 问题 | 位置 | 建议 |
|---|---|---|---|
| S-1 | Pydantic v2 保留字段名冲突 | [`server/workspace/portability/schemas.py:219`](../../server/workspace/portability/schemas.py) `WorkspaceManifestV1.schema` 遮蔽父类 | 改名 `manifest_schema` |
| S-2 | `server/scratch/archive/*.py` 磁盘残留（含 `__pycache__/`） | `server/scratch/` | 直接 `rm -rf` 或归档至 `docs/_archive/scripts/` |
| S-3 | 硬编码 Windows 路径 | [`server/api/model_center.py:724-730`](../../server/api/model_center.py) 4 处 `C:\Users\{username}\.cache\modelscope\...` | 用 `Path.home() / ".cache" / "modelscope" / "hub"` |
| S-4 | 15 份根目录 `.md`（`AGENT_MODULE_DIAGNOSIS.md`、`Chat页面重构计划.md`、`COMMIT_PLAN_2026-04-08.md`、`CODE_WIKI.md`、`design-qa.md`、`git-workflow-audit-2026-07-09.md` 等） | 根目录 | 迁 `docs/` 或 `docs/_archive/` |
| S-5 | C++ 桥接孤立 | [`cpp/src/finetune_inference.cpp`](../../cpp/src/finetune_inference.cpp) + `cpp/include/finetune_inference.h` 无构建脚本、无测试、无被 Python 侧引用 | 决策：保留则补 CMake+单测；否则归档 |
| S-6 | 平铺测试目录 | `server/tests/` 122 文件平铺 | 按模块分子目录 |

---

## 五、技术栈合规性

### 5.1 版本锁定 🟢

**后端**（`pyproject.toml`）：

- Python `>=3.11,<3.12`
- FastAPI `0.109.0` / Starlette `0.35.1` / Uvicorn `>=0.30,<0.31`
- Pydantic `>=2.10,<2.11` / pydantic-settings `>=2.1,<2.2`
- Torch `2.2.2` 显式绑 CUDA 12.1 index（`[tool.uv.sources]`）
- Transformers `4.46.3` / PEFT `0.18.1` / accelerate `1.13.0`
- deepagents `>=0.6.3,<0.7` / langgraph `>=1.2,<1.3`
- llama-cpp-python `>=0.2.79,<0.3`

**前端**（`client/package.json`）：

- React `^18.2` / react-dom `^18.2`
- Vite `^5.0.8` / TS `^5.3.3`
- Antd `^5.12` / framer-motion `^12.36`（较新）
- Vitest `^1.1` / Playwright `^1.59`
- Storybook `^10.3.5`

### 5.2 依赖 profile 拆分 🟢

`pyproject.toml` 定义 10 个 extras：`agent / rag / cua / modelhub / model-ops / training / inference / all / dev / gpu`；4 份 requirements 由 `uv export` 生成，**禁止手改**：

| 文件 | 用途 |
|---|---|
| `server/requirements.txt` | 全量兼容环境 |
| `server/requirements-api.txt` | API/控制面镜像 |
| `server/requirements-training.txt` | 训练 worker 镜像 |
| `server/requirements-inference.txt` | 推理服务镜像 |

### 5.3 已知兼容性风险 🟡

| # | 问题 | 影响 | 建议 |
|---|---|---|---|
| T-1 | `pyautogui/pyscreeze` 顶层触发 `cv2.__version__` 访问，现代 `cv2` 已移除该属性 → `AttributeError` | Windows 本地 pytest 无法 collect `test_architecture_cleanup.py`；Linux CI 未复现（CUA 依赖不装） | `server/cua/keyboard.py` 惰性 import |
| T-2 | `python-json-logger` API 迁移警告 | DeprecationWarning | 规划升级至 `pythonjsonlogger.json` |
| T-3 | `pynput==1.7.6` 与新版 Python 3.12 潜在冲突 | 目前锁 3.11 无影响 | 迁移 3.12 时评估 |
| T-4 | `bitsandbytes==0.41.3` 版本较老（当前 0.43+） | 训练量化功能新特性缺失 | Sprint 3 评估升级 |

---

## 六、数据一致性与完整性

### 6.1 数据库迁移 🟢

16 个 SQL 迁移递增连续编号：

```
001_*.sql
002_*.sql
...
014_release_registry.sql       # 乐观锁 + 跨进程租约
015_training_worker.sql        # 训练队列持久化
016_training_logs.sql          # 训练日志
```

**验证**：无缺号、无回退脚本命名冲突。

### 6.2 配置管理 🟢

- [`server/core/config.py`](../../server/core/config.py) 使用 Pydantic Settings + `env_file=".env"`
- 3 处生产校验：
  - `@model_validator(mode="after")` — 生产强制 auth
  - `@field_validator('allowed_origins', mode='before')` — CORS 白名单校验
  - `@field_validator('allowed_file_types', mode='before')`
- [`.env.example`](../../.env.example) 分组齐全（服务/安全/CORS/Ollama/训练/推理/性能/日志），含生产 vs 本地差异说明

### 6.3 数据访问层

- [`server/core/storage.py`](../../server/core/storage.py)（2027 行）承担多域存储职责，是**主要拆分候选**
- SQLite WAL 模式（`deepagents_checkpoint.py` 中 `busy_timeout + WAL`）
- checkpoint metadata 原子写（tmp + fsync + replace）✅ 符合 AGENTS.md 阶段 1 韧性要求

### 6.4 日志与审计 🟢

- [`server/security/audit_log.py`](../../server/security/audit_log.py) 提供审计能力
- `data/audit_logs/` 有 20 份历史落盘
- 日志支持 `LOG_FORMAT=text|json`、`LOG_MAX_BYTES=10MB`、`LOG_BACKUP_COUNT=5` 轮转
- 参考 [`server/scripts/test_deep_integration.py`](../../server/scripts/test_deep_integration.py) 定义了 audit_logger / secure_storage / file_sandbox 三层集成断言

### 6.5 运行时数据隔离 🟢

`.gitignore` 显式排除：

```
data/            # SQLite / vectors / sessions / memories
logs/            # 应用日志
outputs/         # 训练输出
.uploads/        # 上传缓存
workspaces/      # 运行时 workspace
server/scratch/  # 临时脚本沙盒
server/modelscope_cache/
*.h5 / *.ckpt / *.safetensors / *.bin
```

同时排除所有 `*_HANDOVER.md` / `*计划*.md` / `COMMIT_PLAN_*.md` / `CLAUDE.md` / `GEMINI.md` 等 AI 协作临时文档 —— 规范齐备。

### 6.6 敏感信息扫描 🟢

生产源码硬编码密钥扫描（正则 `(password|secret|api_?key|token)\s*=\s*["'][A-Za-z0-9_\-]{8,}`）：

- **命中 22 处，全部在 `server/tests/`**（合法测试 fixture）
- 1 处 `DEFAULT_INFERENCE_INTERNAL_API_KEY = "finetune-local-inference-dev-key"` 在 [`server/security/runtime_policy.py:16`](../../server/security/runtime_policy.py)，字面即知为**开发默认值**，且生产由 `settings.inference_internal_api_key` 覆盖

**结论**：生产代码零硬编码密钥。

---

## 七、测试覆盖率评估

### 7.1 规模 🟢

| 层 | 数量 |
|---|---:|
| 后端测试文件 `server/tests/test_*.py` | 122 |
| 后端 collect 用例数 | 1215（1198 成功 / 17 deselect） |
| 前端测试文件 `client/src/test/*.test.tsx` | 36 |
| 迁移脚本 | 16 |

**测试/源文件比例**：122 / 495 ≈ **24.6%**（包含 API 路由 70+、core 56 等胖模块），处于健康区间。

### 7.2 pytest 配置 🟢

`pyproject.toml`：

```toml
[tool.pytest.ini_options]
testpaths = ["server/tests", "tests"]
markers = [
    "unit", "slow", "integration", "e2e",
]
asyncio_mode = "auto"

[tool.coverage.report]
fail_under = 60
```

CI 分单元 (`-m "not integration and not e2e"`) 与集成 (`-m integration`) 两个 job 并行。

### 7.3 Smoke 集覆盖

CI `backend-test` 与 CD `test-before-deploy` 使用同一 smoke 集：

- `test_training.py`
- `test_gateway_api_signature_contract.py`
- `test_device.py`
- `test_datasets.py`
- `test_models.py`

### 7.4 覆盖分布问题 🟡

- 所有 122 个测试文件**平铺**在 `server/tests/`，未按被测模块分子目录
- 对于 `agent_session/` (48 源文件) / `api/` (70 路由) 这样的大域，难以直观定位覆盖缺口

**建议目录结构**：

```
server/tests/
├── unit/
│   ├── agent_session/
│   ├── api/
│   ├── core/
│   └── security/
├── integration/
│   ├── training/
│   ├── inference/
│   └── agent_session/
└── e2e/
```

### 7.5 测试收集失败 🔴

**关键问题**：

```
ERROR server/tests/test_architecture_cleanup.py
  AttributeError: module 'cv2' has no attribute '__version__'
  at pyscreeze/__init__.py:788
  triggered by: server/cua/keyboard.py:7 -> import pyautogui
```

**根因链**：`api.cua` → `cua.keyboard` → 顶层 `import pyautogui` → `pyscreeze` 顶层做 `cv2.__version__ < '3'` 判断，而现代 `cv2 >= 4` 无此属性。

**影响**：
- Windows 本地 dev pytest 减 1 个用例文件
- Linux CI 因不装 `cua` extras 不受影响
- 但 Docker `combined` 镜像装 `--extra all` 时也可能受影响

**修复**：`server/cua/keyboard.py` 采用惰性 import：

```python
# BEFORE (顶层)
import pyautogui

# AFTER (函数体内 / try-except)
def _get_pyautogui():
    try:
        import pyautogui
        return pyautogui
    except (ImportError, AttributeError) as e:
        raise RuntimeError(f"pyautogui unavailable: {e}") from e
```

### 7.6 前端测试

36 个 `.test.tsx`，专项脚本齐全：

```json
"test:runtime":          "vitest run RuntimeContext + RuntimeWorkflows",
"test:agent-foundation": "vitest run Agent 5 个基础用例",
"test:agent-e2e":        "node scripts/verify-agent-workbench.mjs",
"test:smoke":            "vitest run Sidebar + beta + experimental + ga",
"test:perf":             "npm run build && lhci autorun"
```

---

## 八、工程实践（CI/CD、审查、安全）

### 8.1 CI Pipeline 🟢

[`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) 五段：

| Job | 内容 | 门禁 |
|---|---|---|
| `lint` | encoding 守卫 + Ruff 焦点 | ✅ 硬门禁 |
| `lint` (advisory) | Ruff full + Black + MyPy | ⚠️ `continue-on-error` |
| `backend-test` | 单元 + smoke + codecov | ✅ |
| `backend-integration` | `-m integration` + codecov | ✅ |
| `frontend` | typecheck + lint (advisory) + vitest + build | ⚠️ lint advisory |
| `security` | `safety scan` | ⚠️ advisory |

**优化建议**：
- Ruff `--fix` 拉平后升级 `black --check` 与 `mypy` 为硬门禁
- Frontend lint 升级为硬门禁（当前 0 error）

### 8.2 CD Pipeline 🟢

[`.github/workflows/cd.yml`](../../.github/workflows/cd.yml)：

1. `test-before-deploy` — 后端 smoke + 前端 typecheck+build
2. `build-and-push` — GHCR 构建推送（gha cache）
3. `deploy-staging` — main/master 分支
4. `deploy-production` — `v*` tag
5. `post-deploy-verify` — `scripts/verify_docker_release.py`

**缺失**：**无自动 rollback workflow**。生产 tag 部署失败仅报错，无回滚。

**建议**：新增 `.github/workflows/rollback.yml`，接收上一个 tag 参数触发 GHCR 部署。

### 8.3 提交规范

- 无 `commitlint` / `husky` / `pre-commit`
- 团队通过 `AGENTS.md` / `CLAUDE.md` / `GEMINI.md`（gitignored）做多 AI 协作规范

**建议**引入 `.pre-commit-config.yaml`：

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    hooks:
      - id: ruff
      - id: ruff-format
  - repo: local
    hooks:
      - id: encoding-check
        entry: python scripts/check_encoding.py
        language: system
        pass_filenames: false
  - repo: https://github.com/pre-commit/mirrors-prettier
    hooks:
      - id: prettier
        files: ^client/.*\.(ts|tsx|css|json)$
```

### 8.4 安全配置 🟢

| 项 | 状态 | 依据 |
|---|---|---|
| JWT 密钥 fail-closed | ✅ | [`server/security/jwt_auth.py`](../../server/security/jwt_auth.py) 禁止静默生成 |
| CUA 强制 ADMIN | ✅ | `security/auth_middleware.py:require_cua_admin` |
| Experimental 生产默认关闭 | ✅ | `ENABLE_EXPERIMENTAL_CAPABILITIES` |
| 加密存储 | ✅ | Fernet + `data/credentials/`（gitignored） |
| CORS 白名单 | ✅ | `ALLOWED_ORIGINS` 环境变量 |
| 速率限制 | ✅ | `RATE_LIMIT` + Redis 后端 |
| 文件沙箱 | ✅ | [`server/security/file_sandbox.py`](../../server/security/file_sandbox.py) |
| 数据脱敏 | ✅ | [`server/security/data_masking.py`](../../server/security/data_masking.py) |
| 审计日志 | ✅ | [`server/security/audit_log.py`](../../server/security/audit_log.py) |
| 生产源码硬编码密钥 | ✅ | 零命中 |

**建议**：
- `safety` → `pip-audit`（更精确的 CVE 覆盖）
- 启用 GitHub Dependabot 或 Renovate
- 补充 `SECURITY.md` 描述漏洞报告渠道

---

## 九、按严重度分类的问题清单

### 🔴 高（阻塞或近似阻塞）

| # | 问题 | 位置 | 修复难度 |
|---|---|---|---|
| H-1 | Windows 环境测试收集单点失败：`pyautogui`/`pyscreeze` 顶层 import 触发 `cv2.__version__` AttributeError | [`server/cua/keyboard.py`](../../server/cua/keyboard.py) `import pyautogui` | 小（5 分钟） |

### 🟡 中（应尽快修）

| # | 问题 | 位置 | 修复难度 |
|---|---|---|---|
| M-1 | Ruff 189 个门禁项、444 个总计 | `server/**` | 小（`--fix` 一键） |
| M-2 | Pydantic v2 字段名 shadowing | [`server/workspace/portability/schemas.py:219`](../../server/workspace/portability/schemas.py) `WorkspaceManifestV1.schema` | 小 |
| M-3 | 前端 72 处 `any` | 主要在 [`client/src/services/api.ts`](../../client/src/services/api.ts) | 中（渐进式） |
| M-4 | API 层残留 `print()` | `api/inference/routes.py`、`api/model_center.py` | 小 |
| M-5 | 硬编码 Windows 路径 | [`server/api/model_center.py:724-730`](../../server/api/model_center.py) 4 处 | 小 |
| M-6 | CD 无自动回滚 | `.github/workflows/cd.yml` | 中 |
| M-7 | Ruff `F401` 15 处冗余 import | `server/**` | 小（`--fix`） |
| M-8 | Ruff `F841` 2 处真正无用变量 | | 小 |
| M-9 | `python-json-logger` API 迁移警告 | 全局 logger 配置 | 小 |

### 🟢 低（技术债 / 清理）

| # | 问题 | 位置 |
|---|---|---|
| L-1 | God Module：`storage.py` (2027) / `api/inference/routes.py` (1644) / `services/api.ts` (3523) | 三处需拆 |
| L-2 | `server/scratch/archive/` 磁盘残留（含 `__pycache__/`） | `server/scratch/` |
| L-3 | 15 份根目录 `.md` 文档，迁 `docs/` 或 `docs/_archive/` | 根目录 |
| L-4 | C++ 桥接孤立无构建脚本 | [`cpp/`](../../cpp) |
| L-5 | 测试文件平铺无分层 | `server/tests/` |
| L-6 | `safety` → `pip-audit` / Dependabot | CI security job |
| L-7 | 缺 `pre-commit` 钩子 | 仓库根 |
| L-8 | 前端超大页面文件（`History.tsx` 1525 / `Evaluation.tsx` 1132） | `client/src/pages/` |
| L-9 | `UP042` 54 处未跟进 Python 3.11 StrEnum | `server/**` |
| L-10 | `bitsandbytes==0.41.3` 版本过老 | `pyproject.toml` |

---

## 十、改进建议路线图

### Sprint 1（低成本高收益 · 1–2 天）

- **[H-1] 修 Windows 测试收集失败**：`server/cua/keyboard.py` 采用函数体内惰性 import。
- **[M-1] Ruff 自动修复**：
  ```powershell
  uv run ruff check server --fix
  # 评估 diff 后
  uv run ruff check server --fix --unsafe-fixes
  ```
- **[M-2] 修 `WorkspaceManifestV1.schema` 字段名**。
- **[M-4] 清理 API 层 `print()`** → 替换为 logger。
- **[M-5] 修硬编码 Windows 路径**：用 `Path.home()`。
- **[L-2] 清理 `server/scratch/archive/`**。
- **[L-3] 迁移 15 份根目录 `.md` 到 `docs/_archive/`**（保留 `README.md` / `LICENSE`）。
- **[L-7] 引入 `.pre-commit-config.yaml`**。

**产出**：单个 PR 消除 300+ 项 Ruff 警告 + Windows 测试可全量 collect + 项目根目录整洁。

### Sprint 2（结构性 · 1–2 周）

- **[M-3 / L-8] 前端 API 层重构**：
  - `services/api.ts` 按域拆 6–8 个 client 文件（`training / inference / models / datasets / evaluation / agent / knowledge / cloud`）
  - 引入 `openapi-typescript` 由后端 OpenAPI schema 生成契约类型
  - 消除大部分 `any` 警告
- **[L-1] 后端 God Module 拆分**：
  - `storage.py` 按域拆：`storage/sessions.py` / `storage/training.py` / `storage/agent.py` / `storage/inference.py`
  - `api/inference/routes.py` 按引擎拆：`routes_hf.py` / `routes_ollama.py` / `routes_llama_cpp.py` / `routes_cloud.py`
- **[L-5] 测试目录分层**：迁 `server/tests/` → `server/tests/unit/<module>/` + `integration/<flow>/` + `e2e/`
- **[M-6] CD Rollback workflow**。

### Sprint 3（长期 · 1 个月+）

- **Ruff full / Black / MyPy 从 advisory 升级为硬门禁**（在 Sprint 1 拉平后）
- **[L-6] `safety` → `pip-audit`** + 启用 Dependabot / Renovate
- **[L-4] C++ 桥接决策**：保留则补 CMake + GoogleTest；否则归档到 `docs/_archive/cpp-experiment/`
- **[L-10] 评估 `bitsandbytes` 升级**（4-bit / 8-bit 量化新特性）
- **补充 `SECURITY.md`** 与漏洞报告渠道
- **测试覆盖率报告长期跟踪**（当前 `fail_under=60`，逐步提升到 70）

---

## 十一、附录：关键度量与命令

### 11.1 复现本报告的命令

```powershell
# 编码守卫
python scripts/check_encoding.py

# Python 语法批检
python -c "import ast,os;errs=[]
for r,_,fs in os.walk('server'):
  if any(s in r for s in ('__pycache__','.venv')): continue
  for f in fs:
    if f.endswith('.py'):
      p=os.path.join(r,f)
      try:
        with open(p,encoding='utf-8') as h: ast.parse(h.read())
      except Exception as e: errs.append((p,e))
print('errors:',len(errs))"

# Ruff 全量统计
python -m ruff check server --statistics

# Ruff 门禁项（CI 一致）
python -m ruff check server --select W291,W293,I001,UP015,UP012 --output-format=concise

# 前端 typecheck + lint
cd client; npm run typecheck; npm run lint

# 测试收集（不运行）
python -m pytest server/tests --collect-only -q

# 大文件排查
python -c "import os
big=[]
for r,_,fs in os.walk('server'):
  if any(s in r for s in ('__pycache__','tests','scripts')): continue
  for f in fs:
    if f.endswith('.py'):
      p=os.path.join(r,f)
      with open(p,encoding='utf-8') as h: n=sum(1 for _ in h)
      if n>800: big.append((n,p))
for n,p in sorted(big,reverse=True): print(f'{n:5d} {p}')"
```

### 11.2 一键 Ruff 修复步骤

```powershell
# 1. 查看待修
uv run ruff check server --statistics

# 2. 安全修复
uv run ruff check server --fix

# 3. 差异检查
git diff --stat

# 4. 跑测试验证无破坏
uv run pytest server/tests -m "not integration and not e2e" -q

# 5. 评估后应用 unsafe 修复
uv run ruff check server --fix --unsafe-fixes

# 6. 重新验证
uv run pytest server/tests -m "not integration and not e2e" -q
```

### 11.3 关键文件索引

| 用途 | 文件 |
|---|---|
| 能力分层单一事实源 | [`server/apps/capability_registry.py`](../../server/apps/capability_registry.py) |
| 应用装配与路由注册 | [`server/apps/routers.py`](../../server/apps/routers.py) / [`server/apps/lifespan.py`](../../server/apps/lifespan.py) |
| 配置管理 | [`server/core/config.py`](../../server/core/config.py) |
| 编码守卫 | [`scripts/check_encoding.py`](../../scripts/check_encoding.py) |
| 编码历史修复模式 | [`server/scripts/batch_fix_encoding.py`](../../server/scripts/batch_fix_encoding.py) |
| 数据一致性 E2E 参考 | [`server/scripts/test_deep_integration.py`](../../server/scripts/test_deep_integration.py) |
| Pydantic v2 样板 | [`server/context/models.py`](../../server/context/models.py) |
| CI | [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) |
| CD | [`.github/workflows/cd.yml`](../../.github/workflows/cd.yml) |
| 项目约定 | [`AGENTS.md`](../../AGENTS.md) |

### 11.4 检测数据摘要

```
后端源文件（.py）                  495
后端测试文件                       122
后端 pytest 用例                   1215 (1198 collect 成功 / 17 deselect)
后端 collect 失败文件              1 (test_architecture_cleanup.py，Windows)
前端测试文件                       36
SQL 迁移                           16 (001-016)
API 路由文件                       70+
Ruff 焦点门禁命中                  189
Ruff 全量命中                      444 (可 fix 284 + unsafe fix 95)
TypeScript 类型错误                0
ESLint error / warning             0 / 72 (全部 no-explicit-any)
编码守卫覆盖 / 命中                683 / 0
生产源码硬编码密钥                 0
生产源码 print()                   3 (2 in inference/routes.py, 1 in model_center.py)
后端 > 800 行文件                  17
前端 > 600 行文件                  21
根目录 .md 待归档                  15
```

---

## 十二、结论

Finetune Platform 2.0 是一个**工程化程度显著高于同类**的消费级 GPU 微调平台：

**核心优势**：
1. **编码卫生**：`check_encoding.py` 建立多重防线并纳入 CI 硬门禁，历史 mojibake 事故完全治愈。
2. **能力分层清晰**：GA/Beta/Experimental 三档单一事实源、前后端对齐、生产默认关实验能力。
3. **依赖分层**：单 `pyproject.toml` 拆 10 个 extras，4 份 requirements 分镜像，避免 CUA/训练/推理依赖污染 API 镜像。
4. **测试规模**：122 测试文件、1215 用例，五段 CI 流水线覆盖单元 / 集成 / smoke。
5. **安全底盘**：JWT fail-closed、CUA 强制 ADMIN、生产源码零硬编码密钥、审计日志与文件沙箱齐备。

**核心债务**：
1. **样式规范未拉平**：Ruff 189 门禁项、前端 72 `any` 警告，均可通过一次机械修复消除大部分。
2. **God Module**：`storage.py` (2027) / `services/api.ts` (3523) 需领域拆分。
3. **Windows 环境测试单点脆弱**：`pyautogui` 顶层 import 阻塞 collect。

按 Sprint 1（1–2 天工作量）执行后即可将该项目推入**生产可交付**状态。

---

**报告作者**：Codex Deep Audit
**下次建议审查周期**：3 个月，或在 Sprint 2 结束后
**联系方式**：见 `AGENTS.md` / 项目 issue tracker
