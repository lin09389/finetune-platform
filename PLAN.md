# 第十阶段计划：Agent 执行内核增强与开发闭环

## Summary

下一阶段不要继续堆页面和模板，而是把执行层做厚：让 `/chat` 里的 Agent 能稳定完成“理解项目 → 提补丁 → 审批/策略执行 → 跑验证 → 读失败 → 修复一次 → 给最终结果”的闭环。

主入口仍是 `/chat`，`/workflows` 继续做观测和审批台。安全边界不变：只读工具可自动执行；写文件和命令必须经过策略门禁或人工审批；不开放任意 shell，不自动 git commit/push。

## Key Changes

### 1. 执行状态机

新增统一执行状态，贯穿 Chat Agent、Workflow、前端卡片：

- 状态包括：`created`、`planning`、`inspecting`、`proposing_patch`、`waiting_permission`、`waiting_approval`、`applying_patch`、`verifying`、`repairing`、`completed`、`needs_manual_review`、`failed`。
- Runtime 每次状态变化写入 timeline / step log，并发出 `agent_state_changed` 事件。
- Chat Agent run metadata 保存当前状态、当前阶段说明、阻断原因、修复次数。
- 前端不再只显示“运行中/失败”，而是显示 Agent 当前到底在做什么。

### 2. 补丁执行引擎

新增 `patch_engine`，让 patch 不只是“写文件内容”，而是支持更接近真实开发的 diff 补丁。

- `patch` action payload 支持两种格式：
  - 兼容旧格式：`files: [{ path, content }]`
  - 新格式：`format: "unified_diff"` + `diff`
- 第一版只支持文本文件的新增/修改，不支持删除、重命名、二进制文件。
- 执行前校验：
  - 路径必须在 workspace 或 workflow `project_path` 内。
  - 禁止路径穿越。
  - 限制单次文件数、单文件大小、总 diff 大小。
  - 检测明显冲突，冲突时进入 `needs_manual_review`。
- 执行结果记录 changed files、before/after 摘要、失败原因，并同步到聊天卡片和 workflow actions。

### 3. 命令策略与项目命令发现

新增命令策略层，让 Agent 能知道“这个项目该怎么验证”，但仍不能乱跑命令。

新增只读工具：

- `detect_project_commands`：读取 `package.json`、`pyproject.toml`、`pytest.ini` 等，识别可用测试/类型检查命令。
- `get_git_status`：读取当前变更概览。
- `get_git_diff`：读取已变更文件 diff 摘要。
- `list_changed_files`：列出本轮 action 影响文件。
- `read_test_failures`：读取最近一次命令执行失败摘要。

命令执行规则：

- 只接受 argv 数组，不接受 shell 字符串。
- 继续限制白名单：`npm run typecheck`、`npm test`、`python -m pytest`、`python -m py_compile`。
- 禁止重定向、管道、删除、移动、提交、推送等危险行为。
- 默认超时 120 秒。
- 执行结果统一生成 `stdout`、`stderr`、`exit_code`、`failure_summary`。

### 4. Developer Loop

升级 `build` Agent 的默认工作流程：

1. `inspect_project`
2. `detect_project_commands`
3. `search_code` / `read_file`
4. 生成实现 checklist
5. `propose_patch`
6. 等待策略执行或用户审批
7. `propose_command`
8. 执行验证
9. 如果失败，读取失败结果并最多 repair 一次
10. `finalize`

最终输出必须包含：

- 做了什么
- 改了哪些文件
- 执行了哪些命令
- 验证是否通过
- 剩余风险
- 下一步建议

如果没有 final summary，后端根据 actions、executions、tool calls 自动生成兜底总结，避免“模型执行完但用户看不到结果”。

### 5. 前端体验打磨

`AgentRunCard` 拆成更清晰的运行面板：

- `AgentExecutionTimeline`：显示当前状态和最近工具调用。
- `AgentActionPanel`：显示 patch / command、审批、执行、输出。
- `AgentFinalSummary`：显示最终交付结果。
- Patch action 展示 diff 预览。
- Command action 展示命令、状态、stdout/stderr、失败摘要。
- Repair loop 显示“正在尝试修复 / 已生成修复建议 / 需要人工处理”。

`/workflows` 不重做，只消费同一套 enhanced observability。

## Public Interfaces / Types

- 不新增主页面，不新增顶层产品入口。
- 现有 `/chat-agent`、`/workflows` API 保持兼容。
- `WorkflowActionResponse` 扩展可选字段：
  - `execution_state`
  - `changed_files`
  - `failure_summary`
  - `policy_reason`
- `patch` action payload 新增支持：
  - `format: "unified_diff"`
  - `diff: string`
- `WorkflowToolCall.tool_name` 新增：
  - `detect_project_commands`
  - `get_git_status`
  - `get_git_diff`
  - `list_changed_files`
  - `read_test_failures`

## Test Plan

后端新增测试：

- `test_patch_engine.py`
  - simple unified diff 可应用。
  - workspace 外路径被拒绝。
  - delete / rename / binary patch 被拒绝。
  - 冲突 patch 进入 `needs_manual_review`。
- `test_command_policy.py`
  - 能识别 npm / pytest 验证命令。
  - 白名单命令可执行。
  - shell 字符串、管道、重定向、危险命令被拒绝。
- `test_agent_developer_loop.py`
  - mock Agent 完成 inspect → patch → command → finalize。
  - actions、executions、final summary 都能返回给聊天页。
- `test_agent_repair_loop.py`
  - command 失败后触发一次 repair。
  - 第二次失败后进入 `needs_manual_review`。
  - repair 生成的新 patch/command 仍需门禁。

回归测试：

- `test_chat_agent.py`
- `test_chat_agent_intent.py`
- `test_agent_permission_replay.py`
- `test_workflow_observability_actions.py`
- `test_agent_tool_runtime.py`
- `npm run typecheck`

手动验收：

1. 打开 `/chat`。
2. 输入“新增一个 tmp smoke 文件并运行 typecheck”。
3. 确认 Agent 自动 inspect/search/read。
4. 确认生成 patch diff。
5. 审批或策略执行 patch。
6. 执行 `npm run typecheck`。
7. 如果失败，确认 Agent 自动 repair 一次。
8. 最后聊天卡片显示明确最终结果。

## Assumptions

- 本阶段不做任意 shell、不做 git commit/push、不做后台长任务队列。
- 第一版 unified diff 只支持文本新增/修改。
- 业务源码修改默认仍走审批；小型安全文件可走自动策略。
- 尽量复用现有 workflow action、tool call、event 表；只有现有 JSON 字段无法承载时才新增迁移。
