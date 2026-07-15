# Phase 9 执行契约：桌面运行时基础与真实能力评测

状态：基础范围已完成
日期：2026-07-15
主线程：负责共享契约、集成、回归与验收

## 目标

Phase 9 同时建立两个互不替代的基础：

1. Electron 成为正式桌面产品边界，负责本地服务的启动、就绪、故障、重启和退出。
2. Coding Agent 获得版本化、可复现、隐私安全的能力评测基线。

本阶段不重写 FastAPI，不引入第二套 Agent 执行循环，不把真实付费模型评测放入普通 CI，也不打包完整 GPU Python 运行时。

## 冻结契约

### 桌面协议

- 协议版本：`1`。
- Electron 向 renderer 暴露只读的运行时描述与服务状态；renderer 不持有内部服务密钥。
- 控制面默认监听 `127.0.0.1:8010`，推理服务默认监听 `127.0.0.1:8020`。
- 服务状态统一为 `stopped | starting | ready | degraded | failed | stopping`。
- Electron 只管理自己启动的进程；退出时必须按训练 worker、推理服务、控制面的顺序结束进程树。
- Python 解析顺序必须明确并可诊断：显式配置、项目虚拟环境、受管运行时、兼容的系统 Python。Python 必须满足 `>=3.11,<3.12`，不允许静默接受其他版本。
- 开发与生产数据均通过显式环境变量指向用户数据根目录，不写入安装资源目录。
- IPC 文件读取只允许用户通过系统选择器选中的文件；打开目录只允许已登记工作区或用户刚选择的目录。

### 评测协议

- 场景 schema 版本：`1`。
- 任务模式：`coding | training | hybrid`。
- 结果：`passed | partial | failed | blocked`。
- 失败归因：`platform | model | environment | ambiguous`。
- 报告只保存相对 fixture 标识、聚合指标和脱敏错误摘要；禁止保存绝对路径、密钥、Authorization、完整 prompt 或项目源码。
- 确定性 runner 是 CI 门禁；真实模型 runner 必须显式 opt-in，并支持 dry-run。
- Phase 9 至少提供 30 个版本化场景定义，覆盖 Python、React/TypeScript、跨栈、调试、重构、训练和混合任务。

## 文件所有权

### Track A：桌面运行时

允许修改：

- `electron/**`
- 根 `package.json` / `package-lock.json`
- `server/tests/test_desktop_*.py` 之外的桌面 Node 测试目录

禁止修改：

- `server/agent_eval/**`
- `server/agent_session/**`
- `client/src/**`

### Track B：能力评测

允许修改：

- `server/agent_eval/**`
- `server/tests/test_agent_eval*.py`
- `server/tests/fixtures/agent_eval/**`

禁止修改：

- `electron/**`
- 根 `package.json`
- `client/src/**`
- 现有 Agent 会话状态机与 DeepAgents 执行循环

### 主线程

主线程独占以下共享区域：

- `client/src/**`
- `server/apps/capability_registry.py`
- `server/apps/routers.py`
- `AGENTS.md`
- ADR、Phase 9 文档与最终集成测试

## 批次与验收

### Batch 1：基础契约

- Track A：服务描述、Python 解析、用户数据路径、安全 IPC、进程监督器单元测试。
- Track B：schema、fixture loader、确定性评分、脱敏报告、至少 30 个场景。
- 主线程：审查协议没有引入第二套 runtime 或绕过现有权限模型。

### Batch 2：产品集成

- Electron main/preload 接入服务监督器。
- 评测 API 只暴露本地报告与显式 opt-in 运行入口。
- Workbench 展示桌面服务状态和本地能力记分卡，保持现有视觉体系。

### Batch 3：验收

- Node 桌面单元测试。
- `python -m pytest server/tests/test_agent_eval*.py -q`。
- 现有 Coding Agent deterministic E2E。
- 前端 typecheck、focused Vitest、生产构建。
- `git diff --check` 与架构回归。

## 停止条件

- 更安全的桌面模式初始化失败后退回不受管 host 执行。
- Electron 能读取任意 renderer 指定路径。
- 真实评测默认发起付费调用或把敏感内容写入报告。
- 新评测代码复制 Agent 循环、审批状态机或训练队列。
- 打包或升级会覆盖用户数据库、模型、数据集、输出或工作区。

## 验收结果

- Electron 桌面运行时测试：14 项通过。
- Agent 评测 loader、评分、真实模型双门禁与 API：24 项通过；默认测试零外呼。
- 应用 profile、能力分层和桌面路径：20 项通过。
- 既有 Coding Agent 离线确定性 E2E：7 项通过。
- 前端桌面状态与能力记分卡：8 项通过；TypeScript 类型检查、生产构建与 bundle budget 通过。
- 生产评测基线包含 32 个独立场景：coding 22、training 6、hybrid 4；22 个场景是多文件工作区，case 文件覆盖 `.py`、`.ts`、`.tsx`、`.json`。
- `git diff --check` 与 Phase 9 Python 模块语法编译通过。

## 已知边界

- 本阶段未执行真实或付费模型评测；真实运行仍需服务端环境变量与请求显式 opt-in 双门禁。
- Python 3.11 运行时未内置进安装包，桌面端按显式配置、项目虚拟环境、受管运行时和系统 Python 的顺序解析。
- Windows unpacked 产物已验证未包含用户可变数据；最终 electron-builder smoke 因 GitHub `winCodeSign-2.6.0` 下载连续 EOF 未完成，网络恢复后需重跑。
