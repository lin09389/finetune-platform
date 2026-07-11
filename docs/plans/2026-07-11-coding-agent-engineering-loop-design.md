# Coding Agent 真实工程闭环设计

日期：2026-07-11
状态：Accepted for implementation

## 目标

第 7 阶段把现有“能够调用工具修改代码”的 Build/Hybrid Agent，推进为可以被个人开发者日常使用、可以刷新恢复、可以明确审阅结果的工程闭环：

`任务输入 → 读取/修改 → 持久化 diff → 验证 → 完成摘要 → 刷新后继续审阅`

本阶段不增加训练功能，不更换 DeepAgents，也不引入第二套工具循环或审批系统。

## 已有基础与缺口

已有能力包括：真实工作区文件工具、路径隔离、写前读取门控、失败后重读、静态校验回滚、最终验证、会话/part/SSE 持久化和 Workbench 时间线。

当前关键缺口是：

1. 成功写入不会必然产生一等的 diff part，前端无法保证看到“改了什么”。
2. 完成门能检查验证，却不能证明每次成功写入都有持久化审阅材料。
3. 现有测试偏协议和夹具，缺少离线、确定性、贯穿真实会话边界的 Coding Agent 验收链路。

## 方案选择

### 采用：基于写前快照的不可变逐次 diff

`TrajectoryGuardMiddleware` 已在写入前取得文件快照，并在写入后执行静态验证。只有写入与静态验证成功后，平台才以写前/写后内容生成 unified diff，并追加不可变 `diff` part。

每个 diff part 至少包含：

- `contract_version`
- 工作区相对路径，禁止绝对本机路径
- `added | modified | deleted` 状态
- bounded unified diff
- additions/deletions、binary、truncated
- 单调的 write sequence
- `review_status: ready`

同一文件的多次修正保留为时间顺序记录。这样无需把原始基线内容长期存入 metadata，重启后也不会丢失修改历史。前端按文件分组并默认展示最新记录，同时允许展开历史。

二进制或超大文件仍产生 metadata-only diff part，以保持“成功写入必有审阅记录”的契约，但明确标记不可内联或已截断。

### 不采用：仅运行 `git diff`

它无法可靠覆盖非 Git 项目、未跟踪文件、已有脏工作区和缺失 Git 的环境，也会混入任务开始前的用户修改。

### 不采用：前端临时计算 diff

刷新后无法恢复，无法成为完成门的证据，也会让 SSE 与 REST 投影出现不同事实源。

## 完成门

完成条件在现有轨迹完成门上追加两项证据：

1. 每一个成功写入序列都存在对应的持久化 diff part。
2. 最后一次影响源码/测试/配置的写入之后存在成功验证。

`review_status: ready` 表示审阅材料已准备好，不要求用户点击确认后 Agent 才能完成。显式批准、命令许可仍只走现有 DeepAgents interrupt 包装；本阶段不创建新的 HITL 状态机。

## 前端交互

Workbench 时间线新增一等 Diff Review Card：

- 显示文件、状态、增删行数、截断/二进制提示。
- 默认折叠长 diff，可按文件展开；多次写入可查看历史。
- 刷新后通过服务端持久化 parts 恢复，不能依赖仅存在于浏览器内存的状态。
- 本阶段只做审阅，不直接提供 commit、push、revert 等高影响 Git 操作。

## 离线验收

增加不依赖网络、真实模型或 CUDA 的确定性 Coding Agent runner。它使用临时项目和可注入的假 tool-calling model，尽可能穿过生产 `AgentSessionService`、DeepAgents runtime adapter、repository、part/event 和恢复边界。

固定场景覆盖：

- Python 单文件缺陷修复。
- React/TypeScript 修改。
- 跨前后端多文件修改。
- 工具失败后重新读取再修复。
- 刷新/重载后的 diff 与状态恢复。
- 越界路径写入被拒绝。

验收证明的是平台工程契约，不把假模型场景误称为真实模型质量评测。

## 并行边界

- Track A：后端 diff 生成、持久化契约与完成门。
- Track B：前端 diff 审阅卡、协议守卫与刷新投影。
- Track C：离线确定性 runner、跨层验收场景与使用文档。

三条轨道优先新增文件；共同协议以本文和 ADR 0008 为准。主线程负责最终集成、补齐跨轨断言并运行全量验收。

## 非目标

- 不新增训练助手能力。
- 不自研替代 DeepAgents 的工具循环。
- 不要求 PostgreSQL、Redis 或远程 GPU。
- 不自动提交或推送用户代码。
- 不把线上真实模型表现纳入确定性 CI。
