# Agent Session 主链路迁移记录

## 当前结论

`/chat` 的新开发 Agent 主链路已经切到 `/agent-sessions`：

- 新任务创建：`POST /agent-sessions`
- 新任务推进：`POST /agent-sessions/{session_id}/prompt`
- 新输出协议：`AgentPart` transcript
- 新安全边界：Agent Session policy + patch/command 工具门禁

旧 `/chat-agent` 仍保留，但只作为兼容层：

- 恢复旧历史消息。
- 审批或执行旧 workflow-backed action。
- 维持已有 `/workflows` 观测后台和回归测试。

## 保留原因

暂不直接删除旧 `/chat-agent` 和 workflow-backed run，原因是：

- 旧聊天消息可能仍保存 `agent_run_id`。
- 旧 `AgentRunCard` 仍能展示 historical workflow run。
- `/workflows` 仍是旧观测与审批后台。
- 旧测试覆盖了兼容行为，删除前需要迁移测试和历史数据展示。

## 后续可删除清单

等新 Agent Session 稳定后，可以逐步删除或降级：

- `server/chat_agent/service.py` 中创建 workflow run 的路径。
- `client/src/services/api.ts` 里的 `createChatAgentRun` / `runChatAgentRun`，保留 get/approve/execute 直到历史消息迁移完成。
- `client/src/components/chat/AgentRunCard.tsx` 中新 Agent Session 兼容逻辑，目前新链路已经由 `AgentPartMessage` 承担。
- `/workflows` 对 Chat Agent 主执行的依赖，最终只保留独立 workflow 产品或调试入口。

## 不删除的能力

这些能力仍被新链路复用，不能随旧 workflow 一起删：

- patch engine
- command allowlist / command policy
- 云端 provider 与 API Key 安全存储
- Agent 权限与 autonomy policy
- Agent Session repository / processor / tool registry
