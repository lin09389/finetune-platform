# Changelog 2026-04-08

## Summary

本次更新完成了 Finetune Platform 2.0 的一轮架构收口，目标是减少伪实现、统一 canonical 路径、降低状态源割裂，并将 experimental 能力与核心主链路明确分层。

当前核心结论：

- Chat 已统一到 session-based canonical API
- Training 状态入口已统一到 `/training/status`
- Workspace、Action Recorder、Gateway、Heartbeat 的关键闭环已补齐或收紧
- `Gateway / Heartbeat / CUA / MCP` 已明确降级为 experimental

## Implemented

### Chat / Session

- `Chat Branch` 改为挂到主 session storage，不再维护独立 `data/chat/...` 分支文件
- chat 消息发送与清空操作现在会显式落盘
- 前端通用 chat helper 已统一迁移到 `/chat/sessions...`
- 历史测试脚本也已迁移到 canonical chat session 路径

### Workspace / Knowledge / Recorder

- `Workspace` 元数据已持久化到本地存储
- `Action Recorder` 已补齐 `save/load/clear` 接口
- `knowledge` stub 已删除，只保留正式实现入口

### Gateway / Heartbeat / Experimental

- `Gateway / Heartbeat / CUA / MCP` 页面均已加 experimental 提示
- Gateway 与 Heartbeat 的乐观 success 语义已收紧
- Gateway 设备与 Heartbeat 任务接口已补齐更稳定的 canonical 字段
- Gateway 注册参数已与后端契约对齐

### Config / State

- 后端默认端口已统一为 `8000`
- 前端默认 backend URL 已统一走共享配置
- chat 领域状态已从 `appStore` 收敛到 `chatStore`

## Removed

以下旧入口已不再保留：

- `POST /chat`
- `GET /chat`
- `GET /chat/{session_id}`
- `DELETE /chat/{session_id}`
- `POST /chat/{session_id}/messages`
- `GET /training`

请统一改用：

- `GET /chat/sessions`
- `POST /chat/sessions`
- `GET /chat/sessions/{session_id}`
- `DELETE /chat/sessions/{session_id}`
- `POST /chat/sessions/{session_id}/messages`
- `GET /training/status`

## Docs Updated

- `README.md`
- `AGENTS.md`
- `项目架构诊断与整改方案.md`
- `.trae/documents/ARCHIVE_NOTICE_2026-04-08.md`
- `.trae/specs/ARCHIVE_NOTICE_2026-04-08.md`

这些文档现在都已反映新的 canonical 路径和 experimental 分级。

## Verification

本轮修改已通过以下验证：

- `pytest server/tests/test_architecture_cleanup.py -q`
- `npm run typecheck`
- 关键 Python 文件 `py_compile`

## Remaining

以下事项仍属于后续阶段任务：

- `Branch Merge` 真实合并语义尚未实现
- `Training WebSocket` 生命周期治理仍可继续优化
- `.trae/documents/` 历史设计稿本体仍保留旧表述，目前通过归档说明做风险提示
