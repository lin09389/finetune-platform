# 第二十七阶段开发文档：真实云端 Agent 提速与 Prompt/Observation 压缩

## 1. 背景

当前项目已经完成 Chat Agent 主链路迁移：

```text
/chat
→ /agent-sessions
→ AgentSessionProcessor
→ AgentToolRegistry
→ AgentPart transcript
```

旧 `/chat-agent` 已降级为兼容层，只用于历史消息、旧 workflow run 和旧动作恢复。

第二十六阶段已经完成：

- `collect_context` 可根据用户目标推断相关文件和搜索词。
- 新增 `detect_project_commands` 工具。
- Processor 可纠偏 patch / command 跳步。
- 新 Agent 输出已按 `AgentPart` transcript 渲染。

第二十七阶段目标是：**让真实云端模型执行更快、更稳、更少废话**。

## 2. 阶段目标

- 减少真实云端模型调用轮次。
- 减少喂给模型的 observation token。
- 让模型更稳定输出 JSON tool request。
- 避免模型长篇解释但不调用工具。
- 保持 Codex 风格 transcript 输出。
- 不新增页面、不扩大执行权限、不恢复旧 workflow 主链路。

## 3. 后端实现

### 3.1 压缩 System Prompt

修改 `AgentSessionProcessor._initial_messages(...)`。

推荐协议：

```text
你是开发 Agent。只输出 JSON 工具请求。
格式：{"tool":"工具名","arguments":{...}}
每次只调用一个工具。
默认流程：collect_context → patch 或 bash_command → finalize。
写文件用 patch。验证用 bash_command。完成用 finalize。
不要解释，不要 Markdown，不要输出多段文本。
```

补充规则：

- 不知道文件路径时先 `collect_context` 或 `search`。
- patch 后必须验证。
- 验证成功后必须 `finalize`。
- 验证失败最多 repair 一次。
- 只读分析任务允许 `collect_context → finalize`。

### 3.2 压缩 Observation

新增 helper：

```python
def _compact_observation(tool_name, result, guidance=None) -> dict:
    ...
```

压缩规则：

- `collect_context`
  - 不回传完整 file content。
  - 只回传文件路径、匹配摘要、commands、guidance。
- `read`
  - content 超过 2000 字符时截断。
- `search`
  - matches 最多 8 条。
- `patch`
  - 只回传 changed_files、policy_decision、risk_level、policy_reason。
- `bash_command`
  - stdout/stderr 最多各 2000 字符。
  - failure_summary 必须保留。
- 完整 payload 仍保存到 `AgentPart.payload`，只压缩喂给模型的内容。

### 3.3 模型输出纠偏

增强 `parse_tool_request` 或 Processor 解析逻辑：

支持：

```json
{"tool_name":"collect_context","args":{}}
```

```json
{"name":"patch","parameters":{}}
```

新增行为：

- 普通文本 + 已有执行记录：自动转 `finalize`。
- 普通文本 + 无执行记录：先返回一次协议提示，要求只输出 JSON。
- 连续 2 次协议失败：进入 `needs_manual_review`，并生成 summary。

### 3.4 Fast Path

在 session metadata 中记录：

```python
task_intent = "analyze" | "develop" | "verify"
```

判断规则：

- 包含“分析 / 看看 / 排查 / 不写文件 / 只读 / 解释”：`analyze`
- 包含“修改 / 新增 / 修复 / typecheck / 跑测试”：`develop`
- 包含“验证 / 测试 / 检查”：`verify`

行为：

- `analyze`：允许 `collect_context → finalize`
- `develop`：prompt 强调需要 patch 或 command
- `verify`：优先 `detect_project_commands → bash_command → finalize`

### 3.5 协议诊断

保存到 metadata 或 part payload：

- `last_raw_model_output`
- `last_parse_error`
- `protocol_repair_count`
- `compact_observation_used`

普通聊天 UI 默认不展示，只用于调试和测试。

## 4. 前端要求

不新增页面。

保持当前 transcript：

- `AgentPartMessage` 继续渲染 text/tool/diff/command/summary。
- 不恢复大卡片。
- 不展示 workflow / artifact / observability 等内部词。
- summary 仍固定可见。
- diff / command 仍可展开。

前端只需同步类型字段，如后端新增 metadata 字段。

## 5. 测试计划

新增：

```text
server/tests/test_agent_session_prompt_compaction.py
```

覆盖：

- system prompt 包含严格 JSON 协议。
- `collect_context` observation 不包含完整大文件内容。
- `read` 超长内容会截断。
- `search` matches 数量受限。
- `bash_command` 保留 failure_summary，并截断 stdout/stderr。
- 普通文本 + 已有执行记录会自动 finalize。
- 普通文本 + 无执行记录会先生成协议纠偏提示。
- 连续协议失败进入 `needs_manual_review`。
- 分析类任务允许 `collect_context → finalize`。
- 开发类任务 patch 后会引导 command。

回归命令：

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$env:SystemRoot='C:\Windows'
$env:WINDIR='C:\Windows'
$env:SystemDrive='C:'
.\.venv\Scripts\python.exe -m pytest `
  server\tests\test_agent_session_prompt_compaction.py `
  server\tests\test_agent_session_processor.py `
  server\tests\test_agent_session_dev_loop.py `
  server\tests\test_agent_session_state.py `
  server\tests\test_agent_tool_registry.py `
  server\tests\test_chat_agent.py -q
```

前端验证：

```powershell
cd client
npm run typecheck
```

## 6. 手动验收 Prompt

### 只读分析

```text
分析当前 Chat Agent Session 的执行链路，不要写文件。
```

期望：

- 只执行只读工具。
- 不生成 patch。
- 最终输出分析 summary。

### 小开发任务

```text
给 AgentPartMessage 增加一个更清晰的命令失败摘要展示，并运行 typecheck。
```

期望：

- 先 collect_context/read。
- 再 patch。
- 低风险自动执行，中风险请求确认。
- 运行或建议 `npm run typecheck`。
- 最终输出修改文件、验证结果和下一步。

### 协议兜底

让 mock 模型输出普通文本而不是 JSON。

期望：

- 第一次提示模型只输出 JSON。
- 已有执行记录时自动 finalize。
- 不出现卡死或无输出。

## 7. 明确约束

- 不新增页面。
- 不扩大自动执行权限。
- 不开放任意 shell。
- 不自动 git commit / push。
- 不删除旧 `/chat-agent`。
- 不恢复旧 workflow 主链路。
- 优先改 `server/agent_session/*`。
- 不扩旧 `agent_runtime`。
