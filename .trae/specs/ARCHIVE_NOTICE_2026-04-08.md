# Archive Notice (2026-04-08)

本目录下的 spec / checklist / tasks 文件主要用于历史规划与方案追踪。
它们不自动等价于当前已落地实现。

当前项目请以以下现实状态为准：

- Chat 只保留 `/chat/sessions...` canonical 会话接口
- `GET /training` 根别名已移除，训练状态统一通过 `GET /training/status`
- `Gateway / Heartbeat / CUA / MCP` 当前为 experimental 能力

如果某份 spec 中仍引用以下路径，请按历史信息处理：

- `/chat/history`
- `/chat/session`
- `/chat`
- `GET /training`

执行实现或评审时，优先参考：

- [项目架构诊断与整改方案.md](C:\Users\JHJ\Desktop\finetune-platform\项目架构诊断与整改方案.md)
- [AGENTS.md](C:\Users\JHJ\Desktop\finetune-platform\AGENTS.md)
- 当前源码中的真实路由与测试
