# Trusted Local AI Engineer Roadmap（修订版）

**状态：** Active blueprint

**首次制定：** 2026-07-13

**修订日期：** 2026-07-16
**修订原因：** 对齐 Phase 9–10 的实际交付，并吸收 Pi Agent 的薄宿主思想，同时保持 DeepAgents 为唯一执行引擎。

> 实施时一次只推进一个阶段。任何并行轨道必须先冻结共享契约和文件所有权，由主线程负责集成、回归与验收。

## 1. 产品终点

Finetune Platform 的目标是一个可安装、桌面优先、本地优先、数据自持的个人 AI Engineer App，而不是浏览器后台，也不是单纯的微调控制台。产品有两条同等级主线：

1. **Coding Agent：** 理解复杂仓库、计划修改、编辑与验证、审查 diff、安全恢复并协调隔离子任务。
2. **AI 模型训练助手：** 检查数据与硬件、提出训练方案、启动和诊断任务、比较评测并形成可复现实验。

两条主线共享 Workbench、Workspace、Agent Session、执行计划、审批、事件、工件、评测和可观测性。Electron 是正式产品宿主；FastAPI、training worker 与 inference service 仍是本地受监督进程。SQLite、本地文件和本地 GPU 保持默认，PostgreSQL/Redis 只作为未来团队版适配器。

## 2. 核心架构决策

### 2.1 正确组合方式

采用 Pi 的架构思想，不把 Pi 代码作为 DeepAgents 下方的第二个 Runtime：

```text
                    User
                      │
             Electron / Workbench
                      │
       Platform Task Workflow（确定性状态机）
      会话 / 审批 / 恢复 / 训练任务 / 工件
                      │
              AgentSessionService
       上下文 / 生命周期 / 事件 / Steering
                      │
        DeepAgents Execution Harness
       模型循环 / Planner / 子 Agent / 工具决策
                      │
             Tool Gateway + Policy
                      │
    Local / Sandbox / Worktree / GPU Runtime
                      │
            Structured Event Spine
             ├─ Workbench Timeline
             ├─ Diagnostics / Agent Eval
             ├─ Automation / Extensions
             └─ Trace Collector
                      │
       Dataset Curation → Training Pipeline
                      │
        Evaluation → Model Registry → Deploy
```

### 2.2 职责边界

| 层 | 拥有的职责 | 明确不拥有 |
|---|---|---|
| Platform Workflow | 会话状态、审批、暂停/恢复、幂等、训练任务、工件、持久化恢复 | 下一步工具选择、第二套 LLM Planner |
| `AgentSessionService` | 跨 Turn 生命周期、上下文装配、运行时绑定、事件发布、steering/follow-up | DeepAgents 内部工具循环 |
| DeepAgents | 模型调用、工具决策、执行计划、子 Agent、interrupt/resume | 产品数据库、桌面生命周期、训练控制面 |
| Tool Gateway / Runtime | 权限、路径、进程、网络、资源与取消边界 | 会话业务状态 |
| Event Spine | 版本化事实投影、UI、诊断、评测、自动化和轨迹采集 | 反向控制模型循环的隐式副作用 |
| Training Pipeline | 数据筛选、版本、训练、评测、模型注册 | 阻塞当前 Agent Turn |

如果未来评估真实 Pi Runtime，只能作为实验性的 `AgentRuntimeProvider` 与 DeepAgents 二选一，不能在同一 Session 中上下嵌套。

## 3. 不可破坏的约束

- `server/agent_session/` 与 `AgentSessionService` 继续是唯一开发 Agent 生命周期所有者。
- DeepAgents 继续是默认且唯一生产执行循环；不复制 ReAct、Planner、审批或 resume 状态机。
- `execution_plan` 是计划事实源，不能再引入平行 Todo/Workflow 状态源。
- Workbench 的 timeline 来自持久化 Agent parts/events，刷新后必须可重建。
- Agent 事件不得包含密钥、原始环境变量、绝对用户路径或未经选择的项目源码。
- Trace-to-Train 必须异步、可关闭、可审查；采集失败不能让 Coding 任务失败。
- 单机核心流程不得依赖 PostgreSQL、Redis、Docker、Kubernetes 或外部 SaaS。
- 更安全的 Runtime 初始化失败时必须 fail closed，不得静默降级为宿主执行。
- 新前端继续复用现有 Workbench 视觉、交互、无障碍和性能预算。

## 4. 非功能目标

| 维度 | 目标 |
|---|---|
| 安全 | 文件、命令、网络、密钥与 GPU 权限均显式绑定 Workspace/Session/Runtime。 |
| 恢复 | Agent 自有修改可恢复，且不破坏用户已有 dirty changes。 |
| 长任务 | Steering、follow-up、取消、重启恢复和结构化 compaction 有明确语义。 |
| 并发 | 并行任务默认不共享可写 checkout，冲突可见且不自动覆盖。 |
| 证据 | 每个完成声明能关联 diff、验证结果、运行时与评测证据。 |
| 可观测 | 用户能解释运行了什么、改变了什么、为何停止、如何重试。 |
| 本地体验 | 无云基础设施也能完成 Coding、Training 和 Hybrid 主流程。 |
| 团队可演进 | 存储、队列、事件、工件和协调通过接口替换，不改变用户语义。 |

## 5. 已完成基线

| Phase | 状态 | 已形成的基础 |
|---|---|---|
| 0–8 | Completed | 安全与韧性、能力分层、统一 Workbench、训练 Agent 化、复杂 Coding 基线、Workspace 可移植性。 |
| 9 | Completed | Electron 正式宿主、本地服务监督、Agent Eval v1 和本地能力记分卡。 |
| 10 | Implementation complete | 版本化受管 Python 3.11 runtime pack、校验/修复/原子激活、窄 IPC 和打包数据保护；真实 runtime 制品、签名安装器与干净机器矩阵仍属发布验收。 |

旧版路线图曾把“可信执行边界”编号为 Phase 10；实际 Phase 10 已用于可分发桌面运行时。本修订从 Phase 11 重新排序，后续线程必须以本表为准。

## 6. Phase 11 — Thin Session Host and Event Spine

### 目标

在不重写 DeepAgents 的前提下，收敛 AgentSession 宿主职责、运行环境重绑定、用户运行中干预和版本化事件，为后续沙箱、worktree、自动化及 Trace-to-Train 提供单一接入点。

### 范围

- 明确 `AgentSessionService → runtime factory → DeepAgents runner` 的单向依赖与生命周期。
- 定义可替换的 Session runtime binding：Workspace、模型、工具目录、执行环境、上下文来源和初始化诊断。
- 切换 Workspace、分支或执行环境时，先关闭旧 binding、取消其后台工作、发布 shutdown，再创建新 binding；禁止复用旧路径绑定服务。
- 为 `steer` 与 `follow_up` 建立不同的持久化队列语义：steer 在安全边界重新进入当前 Turn，follow-up 在当前 Turn 终止后开始下一 Turn。
- 统一内部事件信封，至少携带 `schema_version`、`event_id`、`session_id`、`turn_id`、`causation_id`、`kind`、时间和安全 payload；继续以现有 Agent parts/repository 为事实源，不建立第二个会话数据库。
- 工具结果保留文本之外的结构化 details：耗时、退出状态、验证、diff/artifact 引用和用户处置；大输出只保存有界摘要与引用。
- 引入结构化 compaction record，保存目标、已完成/待办、决策、触及文件、失败尝试、验证状态、Workspace 基线和遗漏原因。
- 先只提供内部订阅者接口；公开安装式扩展留到 Phase 17。

### 退出门禁

- 同一用户动作不会触发两套 Agent Loop、两份审批或两个完成事件。
- Session 在刷新、API 重启和 runtime 重绑定后保持事件顺序与稳定标识。
- steering 能在工具安全边界改变后续行为，follow-up 不会污染当前 Turn。
- Compaction 前后，复杂任务的目标、修改文件、未完成验证和失败方向不丢失。
- Trace/诊断订阅者故障不会阻断主执行路径。

## 7. Phase 12 — Trusted Execution Boundary

### 目标

建立真正可执行的 `ExecutionEnvironmentProvider`，区分显式 `local_trusted` 与 fail-closed sandbox。

### 范围

- 统一命令执行、文件挂载、网络策略、环境变量、资源预算、取消和能力报告。
- 首个安全 provider 优先评估 WSL2/Linux + 可验证隔离机制；WSL 本身不等同于沙箱。
- Workspace 读写挂载之外默认不可见；网络默认拒绝或显式 allowlist。
- 只注入声明过的临时密钥；限制超时、进程树、输出、CPU/内存和磁盘能力。
- Workbench 在任务开始前显示实际执行模式与网络策略。

### 退出门禁

- 逃逸测试无法读写 Workspace 外 sentinel。
- 未声明网络访问失败，子进程继承限制并能被完整取消。
- 安全 provider 初始化失败产生 blocked 状态，不回退到宿主执行。

## 8. Phase 13 — Isolated Task Workspaces

### 目标

让每个可写任务或子 Agent 拥有独立 Git worktree/branch；非 Git 目录使用有界 snapshot fallback。

### 范围

- 建立 `WorkspaceCheckoutProvider`、所有权记录、基线 revision、生命周期和崩溃恢复。
- 子 Session 继承仓库上下文但不共享可写 checkout。
- 支持 adopt、merge、keep、discard；检测重叠路径并显式进入 conflict。
- 只清理平台确认拥有的 worktree，保护用户主工作区和未知目录。

### 退出门禁

- 两个任务可并行修改同一仓库而看不到彼此未提交内容。
- 非重叠更改可确定性合并；重叠更改绝不静默覆盖。
- 用户原有 dirty files 保持逐字节不变。

## 9. Phase 14 — Review Ledger, Checkpoints and Rewind

### 目标

把现有持久化 diff 证据升级为用户可控制的修改账本、检查点和安全回退。

### 范围

- 关联 Session events、worktree revision、文件快照、diff、验证结果和 commit。
- 在高风险工具批次前、成功验证后建立检查点。
- 支持 Agent 自有变更的文件/块级接受、拒绝与 rewind。
- 原地恢复不安全时，在新 worktree 中恢复检查点。
- 提交准备包括建议消息、文件摘要、验证证据与密钥扫描；push/PR 单独授权。

### 退出门禁

- 回退 Agent 修改不影响无关用户修改。
- 刷新和重启后保留审查决策与检查点历史。
- 二进制、大文件、重命名和删除拥有明确的安全行为。

## 10. Phase 15 — Complex-project Coding Agent

### 目标

让产品成为可信赖的日常复杂 Coding Agent，而不靠增加另一个 Planner。

### 范围

- 仓库级 context manifest：架构、符号、测试、构建命令、所有权提示和来源。
- 显式 context budget、progressive disclosure 和结构化 compaction。
- 依赖有序的多文件重构批次与验证检查点。
- 技术栈验证 profile、失败分类和有界 repair loop。
- 基于隔离 worktree 的任务依赖图；reviewer/verifier 消费已有工件而非重复 builder 工作。
- 通过版本化 Agent Eval 对比变更前后能力、安全动作和干预次数。

### 退出门禁

- 真实模型复杂仓库评测优于 Phase 9 基线，且不以降低安全或验证要求换分。
- 多文件任务可跨刷新、进程重启和 compaction 恢复。
- 每个交付声明都能链接到 durable diff 和验证证据。

## 11. Phase 16 — Integrated Training Copilot and Trace-to-Train

### 目标

把模型训练变成统一 AI Engineer 工作流，并让经过用户与评测门禁的 Agent 轨迹形成可治理的数据飞轮。

### 范围

- 数据质量诊断、硬件感知方案、VRAM/磁盘/时间估算和 GPU 前 dry-run。
- 在同一 Session 中比较、启动、暂停、恢复和诊断训练 run，保持现有审批和 GPU 协调。
- Coding、Training、Hybrid 使用同一事件、attention 和工件模型。
- Trace Collector 只订阅版本化事件，执行脱敏、噪声过滤、结果判定和轨迹完整性检查。
- 从树状 Session/Branch/Turn 生成成功轨迹、失败轨迹和 preference pair；禁止把未经同意的项目源码、prompt、密钥或绝对路径写入数据集。
- 候选集必须经过自动评测与可选人工门禁，再生成版本化训练集；训练结果必须回到固定 Agent Eval，而不是直接替换默认模型。
- 生成实验复现包：配置、数据/模型引用及校验和、环境 profile 与评测摘要，不默认携带大文件和密钥。

### 退出门禁

- Coding、Training、Hybrid golden paths 全部通过。
- Trace 采集关闭或失败时，Agent 主功能不受影响。
- 每条训练样本可追溯到同意范围、版本化轨迹和评分依据，并可删除。
- 微调模型只有通过固定回归评测和安全门禁后才能进入 Model Registry/Deploy。

## 12. Phase 17 — Hooks, Personal Automation and Extensions

### 目标

让重复工作可编程，同时避免把 `capability_registry` 误做成无边界插件市场。

### 范围

- 基于 Phase 11 事件脊柱定义版本化生命周期 hooks。
- 支持声明权限的本地命令、HTTP、MCP、Skill/Agent package provider。
- Hook 默认有超时、取消、隔离、兼容版本、校验和和故障策略。
- Scheduled/when workflow 只消费公开事件并发起正常任务，不直接修改内部状态表。
- 自动任务与交互任务共用沙箱、worktree、审批、账本和评测。

### 退出门禁

- 扩展不能获得未声明的文件、网络、密钥或 GPU 权限。
- Hook 故障可观测且被隔离；阻断型 hook 只有在明确契约下 fail closed。
- 不存在绕开 `AgentSessionService` 的第二条工具执行路径。

## 13. Phase 18 — Desktop Release Hardening

### 目标

完成真实桌面发布验收，使非开发者可安装、升级、诊断和恢复。

### 范围

- 构建真实 Python 3.11 runtime packs，完成签名安装器、更新与回滚策略。
- 干净 Windows 账户/VM 验证首次启动、重启、修复、升级、回滚和卸载数据保留。
- 首次运行硬件、GPU 驱动、Sandbox、存储、网络和模型 provider 诊断。
- 本地脱敏 crash bundle 与显式导出。
- 启动、时间线、大 diff、流式输出和长任务恢复性能预算。
- macOS 只在 Windows 主路径稳定后进入独立适配与签名/notarization 计划。

### 退出门禁

- 支持的干净机器无需仓库命令即可完成安装和 Coding golden path。
- 升级/回滚保留 SQLite、Workspace manifests、设置、模型引用与审查历史。
- 诊断默认不导出密钥或项目内容。

## 14. Phase 19 — Optional Team Edition

### 目标

在不改变个人版默认体验的前提下，用真实适配器验证团队版边界。

### 范围

- PostgreSQL transactional repositories/leases。
- Redis queue wake-up、临时协调和跨进程事件广播。
- 对象存储工件适配器，继续使用引用与校验和契约。
- 团队身份、RBAC、审计保留、配额、Workspace 所有权和管理策略。
- 相同领域契约同时运行在 SQLite/local 与 PostgreSQL/Redis profile。

### 退出门禁

- 个人版仍默认 SQLite/local，并通过相同领域契约测试。
- 核心服务不直接 import PostgreSQL/Redis client；选择只发生在应用装配层。
- 个人版与团队版迁移显式、版本化且尽可能可逆。

## 15. Trace-to-Train 数据流

```text
tool.completed / verification.completed / user.accepted / session.completed
                              │
                              ▼
                       Trace Collector
                   ┌──────────┼──────────┐
                   ▼          ▼          ▼
                 脱敏      轨迹完整性    结果评分
                   └──────────┼──────────┘
                              ▼
                       Candidate Dataset
                              │
                  自动评测 + 可选人工门禁
                              ▼
                    Versioned Training Set
                              │
                       LoRA / QLoRA
                              ▼
                     Fixed Agent Eval Suite
                              │
                    Model Registry / Deploy
```

数据飞轮不是主执行路径的一部分。任何阶段都不得因为“方便采集训练数据”而扩大默认遥测、降低审批要求或保存用户未选择的项目内容。

## 16. 并行执行策略

### 可安全并行

- Phase 11 冻结事件信封与 runtime binding 后，后端生命周期、前端只读投影和隐私 fixtures 可分轨道推进。
- Phase 13 的 checkout backend 与只读 UI 可并行，但 merge/adopt 必须等待共享契约。
- Phase 16 的训练领域工具与 Trace fixtures 可提前开发；真实轨迹接入必须等待 Phase 11 事件契约，Hybrid 写操作等待 Phase 12–14。
- ADR、威胁模型、评测 fixtures 和 UI stories 可提前准备。

### 禁止并行

- 不允许不同分支同时重写 Session 状态、审批语义、DeepAgents runner 或事件 schema。
- 不允许沙箱 runtime 与 worktree runtime 在没有统一 binding 契约时分别接线。
- Mutation rewind 必须等待 checkout 所有权稳定。
- 公开 extensions 必须等待事件、沙箱和权限模型稳定。

每条并行轨道必须交付：owned/forbidden files、版本化契约、测试命令、迁移/回滚说明和干净 commit range。主线程拥有共享契约修改、合并、完整回归与最终验收。

## 17. 公共发布门禁与停止规则

每阶段必须验证：

- 后端/前端聚焦测试与架构守卫；
- 持久化变更的迁移、刷新与重启恢复；
- 文件、命令、网络、密钥、扩展或远程能力的威胁审查；
- loading、empty、degraded、blocked、interrupted、conflict、recovery UI；
- 遥测与 Trace 不含密钥、原始 token、绝对路径和未经选择的源码；
- ADR、`AGENTS.md` 和用户文档与代码同步。

遇到以下情况停止合并：

- 新代码引入第二套 Agent Loop、Planner、审批或 Session 状态源；
- 安全模式失败后静默回退到更弱模式；
- 恢复操作可能破坏用户已有修改；
- 持久化 schema 没有版本或迁移；
- 能力提升只来自放松安全、验证或评测口径；
- 单机功能被迫依赖 PostgreSQL/Redis。

## 18. ADR 序列

| ADR | 决策 |
|---|---|
| 0011 | DeepAgents 保持唯一执行循环；平台采用薄 AgentSession 宿主与统一事件脊柱。 |
| 0012 | ExecutionEnvironmentProvider 与 fail-closed sandbox。 |
| 0013 | Task-scoped Git worktree 与非 Git fallback。 |
| 0014 | Mutation ledger、checkpoint 所有权与 rewind。 |
| 0015 | Lifecycle hooks 与 extension permission manifest。 |
| 0016 | Personal-to-team provider contracts 与兼容测试。 |

## 19. 推荐交付波次

```text
Wave A — Agent 宿主收敛
  Phase 11

Wave B — 安全、隔离与恢复
  Phase 12 → Phase 13 → Phase 14

Wave C — 核心产品能力
  Phase 15 + Phase 16 中互不冲突的轨道

Wave D — 可编程与可发布
  Phase 17 → Phase 18

Wave E — 可选团队版
  Phase 19（仅在真实需求出现后）
```

**大致完成点：** Phase 16 结束时，Coding Agent 与训练助手的核心闭环大致完整；Phase 18 结束时，个人桌面产品达到可对外分发的成熟形态；Phase 19 不属于个人版完成条件。
