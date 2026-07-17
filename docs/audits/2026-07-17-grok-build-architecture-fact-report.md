# Grok Build 全模块架构事实报告

> 日期：2026-07-17
>
> 研究对象：`C:\Users\JHJ\Desktop\grok-build`、`C:\Users\JHJ\Desktop\grok-prompts`
> 目的：在规划 Finetune Platform 的 Native Agent Loop 之前，先建立可核验的 Grok Build 架构事实基线。

## 1. 范围与研究纪律

本报告只回答三个问题：

1. Grok Build 的模块如何分层，各自拥有什么状态和职责？
2. 一次用户请求如何经过 Session、Turn、Sampling、Tool、Persistence 与 UI？
3. 哪些设计原则适合 Finetune Platform，哪些实现不应直接照搬？

本报告**不包含 Native Agent Loop 迁移阶段、文件改造清单或工期规划**。迁移规划必须在本报告被确认后单独完成。

研究方法：

- 静态读取 Rust workspace 根 `Cargo.toml`、75 个内部 crate 的 manifest、公共入口与核心实现。
- 下钻 Session Actor、ChatState Actor、Sampler Actor、Prompt Queue、Tool Runtime、Compaction、Rewind、Goal、Subagent、Hooks、MCP、Workspace、Sandbox、TUI/ACP 与测试模块。
- 单独读取 `grok-prompts` 中的主提示词、Goal 角色提示词、验证提示词与子 Agent 提示词。
- 核对根许可证为 Apache-2.0。

限制：

- `cargo metadata` 在 30 秒内未返回，因此依赖图由各 crate 的 `Cargo.toml` 静态恢复。
- 没有编译整个 Grok Build，没有运行其在线采样、远程 Workspace 或真实模型路径。
- 对未进入核心调用链的辅助 crate，仅按公共接口、依赖关系和模块树说明职责。
- `grok-prompts` 仅用于职责分析；除非其许可证边界另行确认，不应直接复制提示词正文。

## 2. 总体结论

Grok Build 不是一个“更复杂的 `while model -> tool` 循环”。它的核心是四层 Actor/生命周期结构：

```text
ACP / TUI / Headless Host
          │
          ▼
MvpAgent（多 Session 宿主与客户端协议适配）
          │
          ▼
SessionActor（单 Session 调度、队列、Turn 生命周期）
          │
          ├──────────────► ChatStateActor（对话、Token、模型配置）
          │
          ▼
Turn Loop（模型响应 ↔ 工具调用，直至终止）
          │
          ▼
SamplerActor（并发请求、流、重试、取消、HTTP）
```

工具、工作区、沙箱、压缩、回退、Goal、子 Agent、Hook、插件和 UI 都围绕这四层连接，但不共享一个巨型可变状态。

最值得借鉴的不是 Rust 实现本身，而是以下边界：

- **宿主与 Session 分离**：`MvpAgent` 管理多 Session，`SessionActor` 只拥有单 Session 顺序语义。
- **Session 与 Chat State 分离**：调度状态和对话状态由不同 Actor 串行化。
- **Turn 与 Sampling 分离**：Turn 决定业务循环，Sampler 只负责模型 I/O、重试和取消。
- **工具协议与工具实现分离**：纯 wire types、统一 runtime contract、具体工具实现分层。
- **事件先于投影**：持久化、回放、TUI、遥测、Trace 和训练数据可以消费同一事实。
- **回退是显式领域能力**：Rewind Point、文件快照、Rewind Marker、历史截断与跨压缩测试共同构成语义。
- **复杂目标不塞进主提示词**：Goal Planner、Strategist、Verifier、Summarizer 是独立角色与状态机。

同时，Grok Build 也存在明显复杂度成本：`xai-grok-shell` 与 `MvpAgent` 已经非常庞大；大量兼容路径、实验开关、远程能力和客户端差异使边界并非处处理想。它适合作为成熟工程参考，不适合作为逐文件翻译模板。

## 3. 运行时分层

### 3.1 宿主层：ACP、TUI 与 Headless

主要模块：

- `xai-grok-shell`：核心宿主、Session、Agent、模型、认证、上传与远程能力。
- `xai-grok-pager`：完整 TUI 产品，包含输入、滚动区、任务视图、Leader Cluster、设置、搜索与命令。
- `xai-grok-pager-minimal`：较小宿主形态。
- `xai-grok-pager-bin`：进程入口、启动配置、沙箱和崩溃处理装配。
- `xai-acp-lib`：Agent Client Protocol 公共支持。

`MvpAgent` 实现 ACP `Agent` 接口，公开 `new_session`、`load_session`、`prompt`、`cancel`、`set_session_mode`、`set_session_model` 等能力。它是多 Session 目录和客户端协议适配器，不是单次 Turn Loop。

`MvpAgent` 维护按 `SessionId` 索引的：

- `SessionHandle`
- Session 线程/LocalSet
- Prompt 入口串行锁
- 权限事件接收器
- Live State/watch channel
- 模型/CodeNav/索引/插件等宿主级附属状态

这使 ACP/TUI 不需要直接接触 Session Actor 内部字段。

### 3.2 Session Host：SessionActor

证据入口：

- `xai-grok-shell/src/session/acp_session.rs`
- `xai-grok-shell/src/session/commands.rs`
- `xai-grok-shell/src/session/handle.rs`
- `xai-grok-shell/src/session/acp_session_impl/run_loop.rs`

`SessionCommand` 是驱动单 Session 的消息协议。其职责远超简单 Prompt：

- 初始化与系统提示词替换
- Prompt 提交、队列编辑和 send-now
- 模型与 Session 模式切换
- Agent Definition 零 Turn 重建
- 手动/自动 Compaction
- Plugin、Hook、Skill 与 MCP 刷新
- Memory flush
- 权限与计划审批恢复
- Rewind、Fork、状态查询和取消

`SessionActor` 自身保留“调度所必需的状态”，源码注释明确说明大部分聊天状态已迁入 `ChatStateActor`。调度状态主要包括：

- `pending_inputs`
- `current_prompt_id` / running slot
- 当前 Turn 取消句柄
- 后台任务、通知和监控队列
- Pending interaction/approval
- Goal orchestration 与 continuation
- Tool registry、MCP 快照和权限上下文
- Hook、Memory、Compaction 与 Persistence 连接

这是一个重要原则：**Session Actor 决定何时发生什么，但不直接拥有所有数据。**

### 3.3 对话状态层：ChatStateActor

主要模块：`xai-chat-state`。

它以 Actor 串行管理：

- `conversation`
- `sampling_config`
- `prompt_index`
- Token 用量与模型 metadata
- Turn capture 与 harness trace turns
- 图像预算和裁剪
- Compaction 后的对话重置

调用者通过 `ChatStateHandle` 发送命令和 oneshot 查询，不直接锁住一个共享 `Vec<ConversationItem>`。

该拆分解决了三类问题：

1. Prompt/Tool/Compaction 对同一对话的并发写被序列化。
2. Token、prompt index 和持久化 barrier 具有统一顺序。
3. Session Actor 可以继续处理通知、取消和队列，不必长期持有聊天状态锁。

### 3.4 Turn 生命周期层

主要实现：

- `acp_session_impl/turn.rs`
- `acp_session_impl/turn_end.rs`
- `acp_session_impl/sampler_turn.rs`
- `acp_session_impl/tool_dispatch.rs`
- `turn_completion.rs`

一个 Turn 的高层序列是：

```text
取出 InputItem
  → 解析/标准化 Prompt 与图片
  → before-turn lifecycle / hooks
  → 将用户输入写入 ChatState
  → 持久化 barrier（可向调用者 ack）
  → 构建模型请求与工具定义
  → Sampling
  → 处理流式内容和工具调用
  → 工具执行、权限、Hook、结果回写
  → 若模型需要继续则再次 Sampling
  → 完成/取消/错误/最大 Turn
  → finalize bookkeeping
  → 持久化 TurnCompleted
  → after-turn lifecycle / hooks
  → Goal、通知、Memory、Laziness 等外围收尾
```

Turn 的终止不仅是模型 `end_turn`。`PromptCompletionKind` 区分：

- `Completed`
- `Cancelled`
- `MaxTurnsReached`
- `Rewound`
- `RemovedFromQueue`

`RemovedFromQueue` 的专门语义很重要：一个从未开始的排队 Prompt 不能广播普通 `prompt_complete`，否则其他客户端会误以为正在运行的 Turn 已结束。

### 3.5 Sampling 层：SamplerActor

主要模块：

- `xai-grok-sampling-types`：纯数据，不含 I/O。
- `xai-grok-sampler`：HTTP、流、重试、并发请求和取消。

`SamplerActor` 注释直接说明其职责：拥有全局采样状态，并为每个请求启动独立任务。外部只能通过 `SamplerHandle` 交互。

命令包括：

- Submit
- Cancel
- UpdateConfig
- IsActive
- ActiveCount

Sampler 层负责：

- 共享 HTTP/2 client 与 fallback client
- 流式响应
- 认证 header 注入
- Retry policy
- 请求取消
- 采样错误分类

Session/Turn 层负责：

- 何时发起采样
- 对话和工具定义是什么
- 失败是否应触发认证刷新、降级或终止
- 采样结果怎样进入工具循环和持久化事件

因此 Sampler 不是 Agent Loop；它是模型 I/O Actor。

## 4. Prompt Queue、Steering 与取消

主要实现：

- `session/prompt_queue.rs`
- `acp_session_impl/prompt_queue.rs`
- `xai-prompt-queue`
- `xai-interjection-core`

队列的事实源在服务端 Session State，而不是 TUI 本地数组。用户 Prompt 含 `QueueEntryMeta`，系统自动唤醒、通知 drain、Goal nudge 等 synthetic input 不进入用户可见队列。

队列支持：

- 普通 FIFO Prompt
- `send_now`
- 队列项编辑、删除和清空
- 多客户端 owner/last_editor/version 元数据
- 运行项与待运行项区分
- 用户 Prompt 对 synthetic auto-wake 的优先级

`send_now` 不是无条件取消：

- 当前 Turn 在可中断等待中，可自动推导 send-now。
- Goal 模式活动时会避免取消，以保护目标编排的一致性。
- 多个 send-now 仍保持 FIFO，避免后发插话反向越过先发插话。

Grok Build 将三种概念分开：

1. **Queue**：下一 Turn 的输入。
2. **Interjection/Steering**：当前 Turn 的即时干预或等待中的注入。
3. **Cancellation**：终止当前运行任务，并携带结构化触发原因。

这种分离比“用户一发新消息就 cancel 当前请求”更稳定。

## 5. Agent Definition 与提示词装配

主要模块：`xai-grok-agent`。

`Agent` 是可移植的运行定义，聚合：

- 工具集合
- System prompt
- System reminder policy
- Compaction policy
- Model configuration
- Plugin/Skill/Agent Definition 来源

`AgentBuilder` 负责把多种配置源解析为一个 Agent。`AgentDefinition` 支持：

- 内置 Agent
- 项目/用户级定义
- Model override
- Prompt mode
- Permission mode
- Isolation mode
- Memory scope
- MCP inheritance
- Subagent 配置

提示词不是一个不可分割的大字符串。`PromptContext`、模板 override、AGENTS/规则、Skills、Plugin、工具说明和运行时 reminder 在构建阶段组合。

关键设计是：**Agent Definition 描述能力与策略，Session 保存运行时状态，Turn 只消费当次快照。**

## 6. 工具体系

### 6.1 三层契约

Grok Build 把工具拆成三层：

1. `xai-tool-protocol`：JSON-RPC/wire types、ID、capability、handshake、错误码和通知。
2. `xai-tool-runtime`：`Tool` trait、`ToolDispatch`、`ToolCallContext`、流与统一错误。
3. `xai-grok-tools`：具体工具、registry、bridge、normalization、retry 与版本兼容。

`xai-tool-types` 提供纯类型和 canonical subagent/task tool DTO；`xai-grok-tools-api` 提供 protobuf/配置 API。

这使本地工具、MCP 工具、Computer Hub 工具和远程工具可以收敛到同一种 Session 可消费的形状。

### 6.2 Tool Runtime 的上下文

`ToolCallContext` 组合：

- Cancellation
- CWD
- Session context
- Trace context
- Workspace binding metadata
- Typed extensions
- Viewer/behavior version

工具输出不是只有字符串：

- `ToolOutput`
- `ContentBlock`
- progress/partial result
- structured notification
- typed error kind

因此 UI、模型上下文、遥测和持久化可以对同一次工具调用使用不同投影。

### 6.3 Tool Dispatch

Session Tool Dispatch 负责：

- 名称/版本解析
- 参数标准化
- 计划模式编辑门控
- 权限请求
- pre-tool Hook
- 工具执行和取消
- streaming progress
- post-tool success/failure Hook
- Tool result 截断和模型可见输出
- Hunk/文件变更/任务通知

`PreparedToolCall` 在真正执行前固定工具身份和 metadata，避免 Hook、权限 UI 与最终执行引用不同名称。

### 6.4 具体工具家族

`xai-grok-tools` 同时包含多套兼容工具族：

- Grok Build：`read_file`、`list_dir`、`grep`、`search_replace`、`bash`、Goal、Task、Monitor 等。
- Codex compatibility：`read_file`、`list_dir`、`grep_files`、`apply_patch`。
- OpenCode compatibility：`read`、`write`、`edit`、`bash`、`glob`、`grep`、`skill`、`todowrite`。
- LSP、Web search/fetch、image/video、memory、skills、computer 等外围工具。

这说明 Grok Build 的 Tool Runtime 是稳定层，但具体工具面仍承担大量兼容复杂度；Finetune Platform 不应复制所有兼容家族。

## 7. 权限与沙箱

### 7.1 权限

Workspace/Session 权限层负责：

- Tool permission policy
- 用户询问与答案
- plan mode transition
- 文件夹 trust
- MCP 工具命名与来源
- client type/capability

权限是 Tool Dispatch 前的领域决策，不由某个具体 `bash` 工具自行弹窗。

### 7.2 OS 沙箱

`xai-grok-sandbox` 使用 `nono`，在支持的平台提供 Landlock/Seatbelt 级进程沙箱；进程启动时应用，且不可逆。

设计特点：

- 进程文件访问沙箱与子进程网络限制分开。
- 主进程需要模型 API，因此主进程网络保持开放；子进程可通过 seccomp 限制网络。
- Profile、实际 applied 状态、违规日志和 metrics 分开记录。
- 沙箱开启后可以选择自动批准 bash，但该行为依赖真实 `is_active()`，不能只看配置名。

风险与限制：

- 源码明确允许“平台不支持时优雅降级”；如果产品宣称强安全边界，宿主必须额外 fail-closed。
- 主要 enforce 路径面向 Unix；Windows 不能直接照搬 Landlock/Seatbelt。
- 沙箱是进程级不可逆设置，不适合在一个长期进程中为不同 Session 随意切换 Profile。

## 8. Workspace、Worktree 与变更跟踪

### 8.1 Workspace

`xai-grok-workspace` 是独立的大领域层，负责：

- 文件系统与 VCS
- 权限与 folder trust
- Session 生命周期
- Tool/MCP/Hook/Plugin/Skill 装配
- Workspace Hub、RPC 与远程客户端
- 预览服务、恢复、诊断和活动
- Worktree 与 Hunk Tracker

`xai-grok-workspace-types` 是纯数据 wire crate，不依赖 Tokio 或 I/O，并明确固定：

- adjacent tagged enum wire format
- snake_case 字段
- 固定宽度整数
- workspace RPC、chunk、event 与 metadata

这是一条清晰的依赖倒置边界。

### 8.2 Fast Worktree

`xai-fast-worktree` 的目标不仅是调用 `git worktree add`，而是优化大仓库隔离成本：

- `git worktree add --no-checkout`
- 并行 CoW 文件克隆
- dirty file replication
- ignored file copy policy
- Linux BTRFS snapshot/overlay
- worktree pool sync
- SQLite metadata/GC

它还提供 snapshot-to-ref、rehydrate 和迁移能力。Worktree 因而是可管理资源，不只是临时目录。

### 8.3 Hunk Tracker

`xai-hunk-tracker` 是另一个 Actor：

- Agent 写入与外部文件系统变化进入同一 actor mailbox。
- 维护文件状态和 Git dirty cache。
- 对 hunk 标注 Agent/External attribution。
- 支持 accept/reject 等 HunkAction。
- 向客户端发出 HunkAdded/HunkRemoved 事件。

它把“模型说自己改了什么”升级为独立可审计事实。

## 9. 持久化、回放、Fork 与 Rewind

主要实现：

- `session/storage/*`
- `session/persistence.rs`
- `session/replay_events.rs`
- `session/fork.rs`
- `acp_session_impl/rewind.rs`
- `xai-sqlite-journal`

持久化不是保存最终聊天 JSON。Session storage 包含：

- 顺序更新流
- Prompt history
- 对话与系统提示词
- Session metadata 与 summary
- Rewind points
- Compaction request/checkpoint/segment
- Turn completion 与 trace patch
- 搜索索引和远程同步信息

Rewind 同时处理两种状态：

1. **对话历史**：写入 `RewindMarker`，回放时截断死分支 Prompt/response。
2. **Workspace 文件**：使用 `RewindPoint` 中的 FileSnapshot 恢复修改。

源码测试覆盖：

- 多次 rewind 后的新分支
- rewind + reconnect cursor
- 跨 compaction rewind
- synthetic turn 不被错误当作用户 Prompt
- JSONL 回放只保留活分支

因此 Rewind 是“事件历史分支 + 文件状态恢复”，不是简单删除最后一条消息。

## 10. Compaction 与 Memory

### 10.1 Compaction Core

`xai-grok-compaction` 是 transport-agnostic 核心，不依赖具体 conversation crate。它通过 trait seam 接收：

- Compaction item/builder
- Token counter
- Compaction sampler
- Observer
- State commit processor

支持三类压缩：

- Code full-replace：整个会话总结替换。
- Intra compaction：单步 tail-keep。
- Inter compaction：Turn 之间分块压缩。

Host 仍然拥有：

- 触发时机
- 持久化与回放
- Rewind
- 状态 commit
- metrics backend
- Host-specific prompt variant

这避免 Compaction Core 反向拥有 Session 生命周期。

### 10.2 ChatState 中的 Compaction

ChatState Actor 负责原子替换对话、Token 重算和事件发布。Session Actor 负责发起、审批/Hook、checkpoint 文件和失败降级。

### 10.3 Memory

`xai-grok-memory` 是跨 Session 知识层：

- 全局与 workspace-scoped Markdown memory
- Session logs
- Chunking/index/search
- Embedding 与 MMR
- Query expansion
- Dream/flush/watcher

Memory 由 Session 生命周期 Hook 触发，但不进入主 Tool Loop 的状态所有权。Session idle、session end、compaction recovery 都可以独立触发 Memory 工作。

## 11. Goal 与子 Agent

### 11.1 Goal Orchestration

Goal 不是主模型 Prompt 中的一组模糊规则。源码将其拆成：

- classifier
- planner
- strategist
- verifier/skeptic
- summarizer
- stop detector
- next-step resolver
- orchestration state
- continuation directive
- token/time budget

Goal 计划写入磁盘，作为完成标准的事实源；实现者、验证者和策略角色读取同一计划。

完成门不是“模型说完成”：

- 实现者请求完成。
- Verifier 尝试 refute。
- 失败多轮后 Strategist 分析不收敛原因。
- Goal 状态决定继续、完成、预算停止或阻塞。

这是一个位于 Session Host 外围的确定性 Workflow。它不会替代 Turn 内的工具决策。

### 11.2 Subagent

子 Agent 支持：

- 内置与用户定义角色
- forked conversation/context
- 前台阻塞与后台执行
- task output/wait/kill
- 取消、完成和超时语义
- worktree isolation mode
- 模型/权限/工具集继承规则
- Roster 与父 Session 通知

子 Agent 生命周期由宿主协调，具体子 Agent 内仍运行同一种 Session/Turn 架构。

## 12. Hooks、Plugins、Skills 与 MCP

### 12.1 Lifecycle Contributor

`xai-agent-lifecycle` 定义 host-agnostic contributor：

- Session lifecycle
- Turn input contributor
- Turn lifecycle
- Command contributor

源码文档明确：Contributor 收到纯数据输入，通过安装时注入的 capability 行动，**永远不拥有 Loop 控制权**。

### 12.2 Hooks

`xai-grok-hooks` 提供文件发现、匹配、信任、命令执行和结果。事件覆盖：

- Session start/end/stop
- User prompt submit
- Pre/post tool use 与 failure
- Permission denied
- Subagent start/stop
- Pre/post compact
- Notification

初始设计偏 fail-open；pre-tool hook 可阻断，其他通常非阻断。项目级 Hook 受 folder trust 约束。

### 12.3 Plugins

Plugin 模块分成：

- `xai-grok-agent/plugins`：manifest、discovery、trust、git install、install registry。
- `xai-hooks-plugins-types`：无领域依赖的 ACP DTO。
- `xai-grok-plugin-marketplace`：来源、索引、扫描、安装与官方 marketplace。

Plugin 可以贡献 Agent、Prompt、Hook、MCP、Skill 等，但 trust/status 被显式投影给客户端。

### 12.4 Skills

Skills 在 Agent prompt assembly 与工具发现中接入。主 Prompt 只描述使用规则；具体 Skill 内容按需加载，避免全部常驻上下文。

### 12.5 MCP

`xai-grok-mcp` 隔离 `rmcp` 与不同 reqwest 主版本，拥有：

- stdio/streamable HTTP transport
- credentials store
- OAuth 与跨进程去重
- reconnect/backoff
- server lifecycle
- tool invocation/error classification
- managed MCP refresh

MCP 最终适配统一 Tool Runtime，而不是让 Session Actor直接理解 rmcp 类型。

## 13. 模型、认证、HTTP 与遥测

### 13.1 模型

`xai-grok-models` 嵌入默认模型清单；运行时优先级为：CLI > ENV > config > remote settings > defaults。

模型切换由宿主与 Session 协作：

- 更新 Sampler config。
- 更新 Context window/auto compact threshold。
- 必要时零 Turn 重建 Agent Definition。
- 保持已有会话不被错误重写。

### 13.2 认证

`xai-grok-auth` 是依赖倒置 seam，提供可刷新 credential provider 与可选 retry middleware。Shell 拥有具体认证流程，但文件工具、HTTP 或 telemetry 不需要反向依赖 Shell 类型。

### 13.3 HTTP

`xai-grok-http` 缓存非采样 client；采样 HTTP 归 `xai-grok-sampler`。它还区分通用、上传、blocking 和逃离 poisoned pool 的 fresh HTTP/1 client。

### 13.4 Telemetry

`xai-grok-telemetry` 独立拥有：

- 产品事件
- Session/Prompt/Memory/Sampling metrics
- OpenTelemetry
- Sentry
- Mixpanel
- unified structured log
- 外部 span/metric donation

重要的是 telemetry 有自己的 ownership boundary，而不是散落在工具和 UI 中。

## 14. TUI、ACP 与展示投影

`xai-grok-pager` 并非直接读取 Session 内存。它消费 ACP SessionUpdate、Prompt Queue wire、Tool Call/Update、Hunk、Roster、Task、Permission 与状态快照。

TUI 分层包含：

- App state/effects/dispatch
- Agent view 与 leader cluster
- Prompt widget、输入、slash commands
- Scrollback block（assistant、tool、status）
- Settings、project picker、search、dashboard
- Fullscreen/inline/minimal/headless
- ACP handler 与 reconnect/replay

`xai-grok-pager-render` 单独拥有 Markdown、terminal、appearance、clipboard 和渲染；`xai-grok-pager-pty-harness` 用 PTY 场景验证真实终端行为。

ACP 在这里是宿主协议，也是多前端边界：同一个 Session runtime 可被 TUI、minimal、headless 或其他客户端驱动。

## 15. 测试策略

Grok Build 的测试不是只有 crate 单元测试，至少包含以下层次：

1. **纯类型/算法测试**：wire、token、compaction、normalization。
2. **Actor 测试**：ChatState、Sampler、HunkTracker、Prompt Queue。
3. **Session 集成测试**：Turn、权限、interjection、cancel、replay、rewind、goal、memory、MCP。
4. **工具 E2E**：真实工具分派、stream、错误与输出限制。
5. **PTY E2E**：真实 TUI/终端行为与滚动矩阵。
6. **Goal adversarial verification**：实现证据与 verifier 分离。
7. **测试支撑 crate**：`xai-grok-test-support`、`xai-test-utils`、`ptyctl`。

值得注意的测试主题：

- Prompt Queue 多客户端语义
- Send-now/Cancel/Interjection
- Turn end guard
- Tool failure 与 auth retry
- Rewind 跨 compaction
- Hook trust 与 lifecycle
- Subagent cancel/worktree cleanup
- 环境变量测试全局锁和 RAII 恢复
- PTY 场景而非只测试渲染函数

## 16. Crate 全景清单

下面覆盖研究目录中的全部内部 crate。每个 crate 只列主职责；更细的内部模块已在前文按调用链展开。

### 16.1 核心 Agent 与 Session

| Crate | 主要职责 |
|---|---|
| `xai-grok-shell` | 多 Session 宿主、Session Actor、Turn、Goal、Subagent、模型、认证与产品装配 |
| `xai-grok-agent` | Agent Definition、Builder、Prompt Assembly、Plugin/Skill/Reminder 策略 |
| `xai-chat-state` | Actor 化对话、模型配置、Token、Turn capture 与 Compaction commit |
| `xai-agent-lifecycle` | Host-agnostic Session/Turn/Command contributor 接口 |
| `xai-prompt-queue` | 前后端共享 Prompt Queue wire types |
| `xai-interjection-core` | 当前 Turn 插话/干预的核心类型 |
| `xai-grok-subagent-resolution` | 子 Agent 类型与能力解析 |

### 16.2 Sampling、模型与网络

| Crate | 主要职责 |
|---|---|
| `xai-grok-sampling-types` | 无 I/O 的采样、对话、流和错误类型 |
| `xai-grok-sampler` | Sampler Actor、HTTP、流、重试、取消、共享 client |
| `xai-grok-models` | 内置模型清单与默认模型角色 |
| `xai-grok-auth` | Credential provider 和认证 retry seam |
| `xai-grok-http` | 非采样 HTTP client、UA 与连接池策略 |
| `xai-circuit-breaker` | 通用断路器 |

### 16.3 工具与 Computer Hub

| Crate | 主要职责 |
|---|---|
| `xai-tool-protocol` | JSON-RPC/wire、capability、ID、错误、通知与握手 |
| `xai-tool-runtime` | 统一 Tool trait、dispatch、context、stream、error |
| `xai-tool-types` | 工具 schema 与 task/subagent canonical DTO |
| `xai-grok-tools-api` | 工具 protobuf 与配置 API |
| `xai-grok-tools` | 具体工具、registry、bridge、版本与兼容工具族 |
| `xai-computer-hub-core` | Computer Hub 核心注册与路由 |
| `xai-computer-hub-sdk` | Hub 客户端 SDK |
| `xai-computer-hub-mcp-adapter` | MCP 与 Hub/Tool Runtime 适配 |

### 16.4 Workspace、隔离与变更

| Crate | 主要职责 |
|---|---|
| `xai-grok-workspace` | Workspace 领域、FS/VCS、权限、Session、Hub 与恢复 |
| `xai-grok-workspace-types` | 纯数据 RPC/chunk/event/wire types |
| `xai-grok-workspace-client` | Workspace 客户端 |
| `xai-fast-worktree` | 高性能 Worktree、CoW、Pool、GC 与快照 |
| `xai-grok-sandbox` | Landlock/Seatbelt、子进程网络限制、profile 与审计 |
| `xai-hunk-tracker` | Actor 化 Hunk、来源归因与 accept/reject |
| `xai-gix-status` | Git 状态辅助 |
| `xai-codebase-graph` | 代码库图、语言解析、scope graph 与索引管理 |
| `xai-fsnotify` | 文件系统通知 |
| `xai-file-utils` | 文件、上传/采集与通用文件支持 |
| `xai-grok-paths` | Grok 路径约定 |
| `xai-sqlite-journal` | SQLite 日志/持久化基础 |

### 16.5 Compaction、Memory 与 Token

| Crate | 主要职责 |
|---|---|
| `xai-grok-compaction` | Transport-agnostic 压缩核心与多种策略 |
| `xai-grok-memory` | 跨 Session Markdown memory、索引、embedding、dream |
| `xai-token-estimation` | Token 估算 |

### 16.6 Hook、Plugin、MCP 与配置

| Crate | 主要职责 |
|---|---|
| `xai-grok-hooks` | Hook discovery、trust、matcher、runner、dispatcher |
| `xai-hooks-plugins-types` | Hook/Plugin ACP DTO |
| `xai-grok-plugin-marketplace` | Marketplace、索引、扫描、安装 |
| `xai-grok-mcp` | MCP transport、OAuth、credential、server lifecycle |
| `xai-grok-config` | 配置加载、合并与基础类型 |
| `xai-grok-config-types` | 跨 crate 配置 DTO |
| `xai-grok-env` | 环境解析 |
| `xai-grok-secrets` | Secret 存储/读取边界 |
| `xai-grok-shared` | Shell/Pager 共享配置和模型辅助 |

### 16.7 UI、ACP 与终端

| Crate | 主要职责 |
|---|---|
| `xai-acp-lib` | ACP 公共实现支持 |
| `xai-grok-pager` | 完整 TUI 产品 |
| `xai-grok-pager-bin` | TUI 可执行入口 |
| `xai-grok-pager-minimal` | 精简宿主 |
| `xai-grok-pager-render` | Markdown、终端、主题与展示 |
| `xai-grok-pager-pty-harness` | PTY E2E 场景 |
| `xai-ratatui-inline` | Inline Ratatui 支撑 |
| `xai-ratatui-textarea` | 文本输入与渲染 |
| `xai-grok-markdown` | Markdown 上层渲染 |
| `xai-grok-markdown-core` | Markdown 核心 |
| `xai-grok-markdown-fuzz` | Markdown fuzz target |
| `xai-grok-mermaid` | Mermaid 支持 |
| `xai-grok-voice` | 语音/音频/STT |
| `xai-tty-utils` | TTY 通用支持 |
| `ptyctl` | PTY 控制库 |
| `ptyctl-cli` | PTY 调试 CLI |

### 16.8 运行、发布与观测

| Crate | 主要职责 |
|---|---|
| `xai-grok-telemetry` | 产品事件、OTel、Sentry、统一日志与指标 |
| `xai-tracing` | 通用 tracing 支撑 |
| `xai-tracing-macros` | tracing 宏 |
| `xai-mixpanel` | Mixpanel 适配 |
| `xai-crash-handler` | 崩溃处理 |
| `xai-system-power` | 电源/休眠相关集成 |
| `xai-grok-update` | 更新机制 |
| `xai-grok-version` | 版本事实源 |
| `xai-grok-announcements` | 公告 |
| `xai-grok-shell-base` | Shell 基础启动与共享配置 |
| `xai-grok-shell-session-support` | Session 相关 Shell 支撑 |

### 16.9 构建、测试与辅助

| Crate | 主要职责 |
|---|---|
| `xai-proto-build` | Protobuf 构建辅助 |
| `xai-grok-test-support` | Grok 集成测试支撑 |
| `xai-test-utils` | 通用测试工具 |
| `xai-grok-pager-pty-harness` | 终端级场景测试（亦属于 UI） |

## 17. `grok-prompts` 职责分析

### 17.1 主提示词

`prompt.md` 主要定义：

- 产品身份与交互风格
- 行动安全
- 工具调用纪律
- 计划工具使用条件
- 项目指令文件规则
- 输出格式与沟通约束

它没有承载 Goal 的完整状态机、Verifier 逻辑或持久化算法。

### 17.2 Goal 提示词集合

Goal 被拆成专用角色：

- `goal_planner_prompt.md`：一次性生成可验证计划。
- `goal_rules.md`：实现者持续执行纪律。
- `goal_continuation_directive.md`：每 Turn 的剩余目标和下一步提醒。
- `goal_verifier_prompt.md`：对证据进行对抗式 refute。
- `goal_strategist_prompt.md`：多轮不收敛时分析原因。
- `goal_summarizer_prompt.md`：最终短摘要。
- `goal_plan_block.md`：计划文件与验证证据约定。
- `goal_task_discipline.md`：防止只叙述不执行、中途无故停下和测试作秀。

这些 Prompt 的效力依赖运行时：Goal 状态、预算、计划文件、scratch、verifier 输出和 continuation 由 Session/Goal Orchestrator 注入。单独复制 Prompt 不会得到同等能力。

### 17.3 子 Agent 提示词

`subagent_prompt.md` 强调：

- 任务边界
- 工具优先
- 不扩 scope
- 项目指令层级
- 输出契约
- 后台任务与行号/anchor 协议

它是专用执行角色，不是主 Agent 的缩短版。

### 17.4 结论

Grok Build 的可靠性主要来自“运行时提供真实状态 + Prompt 规定如何消费状态”。不能把成功归因于一份超长 system prompt。

## 18. 架构优点与代价

### 18.1 优点

- Actor 边界清晰，关键状态有明确所有者。
- Tool/Workspace/Wire types 有较好的依赖倒置。
- Prompt Queue、Interjection、Cancel 语义分离。
- Rewind 同时覆盖对话分支和文件状态。
- Compaction Core 与 Host 生命周期解耦。
- Goal/Verifier 将“完成”变成可验证状态，而非模型自报。
- TUI/ACP、远程和 Headless 共用同一核心。
- 测试覆盖 Actor、Session、PTY 与 adversarial verification 多层。

### 18.2 代价

- `xai-grok-shell` 仍然是巨型集成 crate，编译与理解成本高。
- `MvpAgent` 持有大量客户端、模型、插件、索引和 Session 附属 map。
- 配置优先级、兼容工具族与远程能力产生显著组合复杂度。
- 事件/通知类型多，若缺少版本和投影规范会快速膨胀。
- Actor message + oneshot 提高一致性，但调试跨 channel 因果链更难。
- OS 沙箱平台能力不对称；“优雅降级”与强安全承诺存在张力。
- Goal 多角色验证提高可靠性，也显著增加 token、延迟和实现复杂度。

## 19. 对 Finetune Platform 的适配判断

本节只给适配判断，不给实施阶段。

### 19.1 高度适合吸收

- `AgentRuntimeProvider` 下的独立 Native Runtime，而不是把 Loop 继续塞进 `AgentSessionService`。
- Session mailbox 与服务端权威 Prompt Queue。
- Session 调度状态与 Chat/Conversation 状态分离。
- Sampling client/actor 与 Turn loop 分离。
- 统一 Tool Runtime contract 和 structured notification。
- 持久化 lifecycle event 与 UI projection 分离。
- Prompt Queue、Steering/Follow-up、Cancel 三种语义。
- Compaction core 与 host commit/persistence seam。
- Rewind Marker + Workspace mutation ledger 的双重回退。
- Goal/Verifier 作为可选上层 Workflow，而不是主 Loop。
- Harness、Runtime、Tool、Workspace、Telemetry 的多层测试门。

### 19.2 需要按当前项目重写

- Rust Actor 要映射到 Python asyncio task/mailbox，而不是机械模拟 Rust 类型。
- ACP/TUI 投影要映射到现有 FastAPI/SSE/Electron 协议。
- Workspace/Tool 权限必须复用现有用户、Workspace owner 和 HITL 语义。
- Sampling 要适配本地模型、云模型、Ollama 与 OpenAI-compatible provider。
- Tool Runtime 要包含训练/GPU/评测工件，而不只 Coding 工具。
- Sandbox 要面向 Windows-first Electron，不能依赖 Landlock/Seatbelt。
- Persistence 应继续使用现有 SQLite Repository 与事件表，而非复制 JSONL 布局。

### 19.3 不建议照搬

- 不复制整个 `xai-grok-shell` 巨型宿主。
- 不同时保留多套 Codex/OpenCode/Grok 工具兼容家族。
- 不把远程同步、Marketplace、Voice、Computer Hub 全部纳入 Native Loop 首版。
- 不把 Hook 默认 fail-open 直接用于高风险训练、命令或外部副作用。
- 不把 Goal 多模型验证设为所有普通任务的默认路径。
- 不逐字复制 `grok-prompts`。

## 20. 在规划前仍需确认的架构问题

以下问题应在迁移规划前明确，但不影响本报告的事实结论：

1. Native Loop 首个生产宿主是否只服务 Build，还是同时覆盖 Train/Hybrid？
2. 迁移期 DeepAgents 与 Native Runtime 的 Session 选择是否允许用户可见，还是只用于 feature flag/benchmark？
3. 现有 Agent Session event/part 是否作为兼容事实源，还是允许引入新的底层 lifecycle event 后再投影？
4. Prompt Queue 的 steering、follow-up、send-now 需要哪些明确用户交互？
5. Windows可信执行环境在 Native Tool Runtime 中采用何种 fail-closed provider？
6. Rewind 的第一版是否恢复文件，还是先只实现对话/计划分支？
7. Goal/Verifier 是否作为普通 Session 的可选 workflow，还是独立的长期任务产品模式？
8. Trace-to-Train 收集哪些事件，哪些内容必须在写入前脱敏或征得同意？

## 21. 最终判断

Grok Build 适合作为 Native Agent Loop 重构的主要工程参考，尤其适合参考其：

- Session Actor
- ChatState Actor
- Turn/Sampler 分层
- Prompt Queue 与 Interjection
- Tool Runtime contract
- Compaction seam
- Rewind 语义
- Goal/Verifier workflow
- Worktree/Hunk/Sandbox 边界
- ACP/TUI 多宿主投影

但正确目标不是“在 Python 中复刻 Grok Build”，而是：

> 用 Grok Build 已验证的状态所有权和生命周期边界，重新组织 Finetune Platform 自有的 Session、Native Loop、工具、训练、评测与 Electron 宿主。

在这一事实基线上，下一步才适合制定“DeepAgents → NativeAgentLoop”的渐进迁移规划。
