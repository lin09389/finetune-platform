# Agent Session 真实云端 Smoke 验收清单

目标：验证 `/chat` 的新 Agent Session 主链路在真实云端模型下能稳定完成“小开发任务”，并且刷新后能恢复同一条运行记录。该清单不要求新增页面，也不扩大自动执行权限。

## 验收前准备

- 后端运行在 `http://127.0.0.1:8010`。
- 前端运行在 Vite 开发服务。
- 云端 API 页面已保存可用 provider、API Key 和默认模型。
- `/chat` 使用 `安全自动` 模式；需要对照时再切换 `确认模式` 或 `只读`。

## 固定 Smoke 任务

1. `新增一个 tmp smoke 文件并运行 typecheck。`
2. `给当前项目做一个很小的前端文案调整并运行 typecheck。`
3. `修改一个小 CSS 样式并运行 typecheck。`
4. `只分析当前项目结构，不写文件。`
5. `故意触发一次验证失败，确认最多 repair 一次并清楚停住。`

## 每次验收记录

| 项目 | 结果 | 备注 |
| --- | --- | --- |
| 是否进入 Agent Session |  |  |
| 是否先读取或搜索项目上下文 |  |  |
| 是否生成 patch/diff |  |  |
| patch 是否按策略自动执行或明确要求确认 |  |  |
| 是否运行白名单验证命令 |  |  |
| 验证失败时是否读取失败并最多 repair 一次 |  |  |
| 是否输出最终总结或阻断原因 |  |  |
| 刷新后状态是否恢复 |  |  |
| 是否没有重复执行已执行动作 |  |  |

## 后端恢复诊断字段

`GET /agent-sessions/{session_id}` 的 `metadata.diagnostics` 应能辅助排查：

- `latest_event`：最近事件。
- `latest_tool_call`：最近工具调用。
- `latest_tool_result`：最近工具结果。
- `latest_action`：最近 diff / command / permission。
- `latest_command`：最近验证命令。
- `latest_summary`：最终总结。
- `stop_reason`：当前停止或等待原因。
- `next_action`：用户下一步应该做什么。
- `refresh_safe`：刷新状态是否不会重复执行动作，固定为 `true`。

## 通过标准

- 成功或停住时，聊天 transcript 都必须给出可读结果，不能无输出。
- 自动执行只能发生在安全策略允许的低风险 patch / 白名单命令上。
- 等待确认、只读阻断、验证失败都必须说明原因和下一步。
- 刷新页面或点击“刷新运行状态”只拉取状态，不重复写文件、不重复执行命令。

