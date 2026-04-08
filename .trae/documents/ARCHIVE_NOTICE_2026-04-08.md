# Archive Notice (2026-04-08)

本目录下的大量文档属于历史设计稿、评审稿、重构草案或阶段性分析材料。
它们保留用于追溯，但不再代表当前项目的 canonical 架构状态。

在阅读本目录材料前，请先以以下文档为准：

- 仓库根目录 [项目架构诊断与整改方案.md](C:\Users\JHJ\Desktop\finetune-platform\项目架构诊断与整改方案.md)
- 仓库根目录 [AGENTS.md](C:\Users\JHJ\Desktop\finetune-platform\AGENTS.md)
- 仓库根目录 [README.md](C:\Users\JHJ\Desktop\finetune-platform\README.md)

当前已生效的关键 canonical 约束：

- Chat 会话接口统一为 `/chat/sessions`、`/chat/sessions/{session_id}`、`/chat/sessions/{session_id}/messages`
- 旧 Chat compat 路由已移除：
  - `POST /chat`
  - `GET /chat`
  - `GET /chat/{session_id}`
  - `DELETE /chat/{session_id}`
  - `POST /chat/{session_id}/messages`
- Training 状态接口统一为 `GET /training/status`
- 旧 Training 根别名 `GET /training` 已移除
- `Gateway / Heartbeat / CUA / MCP` 当前视为 experimental，不属于稳定主承诺

阅读本目录时请特别注意：

- 若文档中仍出现 `/chat/history`、`/chat/session`、`/chat` 兼容入口，请视为历史信息
- 若文档中仍出现 `GET /training` 根状态入口，请视为历史信息
- 若文档默认将 `Gateway / Heartbeat / CUA / MCP` 作为核心主线，请以最新整改文档中的 experimental 分级为准

建议：

- 需要做当前实现判断时，优先读代码和根目录正式文档
- 需要追溯设计演进时，再回看本目录历史材料
