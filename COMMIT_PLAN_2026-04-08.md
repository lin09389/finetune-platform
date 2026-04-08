# Commit Plan 2026-04-08

## Goal

将本轮架构收口改动拆成 3 个高内聚提交，避免把“后端收口、前端对齐、文档归档”混成一个大提交。

## Commit 1

**Title**

`refactor(api): unify canonical chat and training endpoints`

**Scope**

- `server/api/chat/routes.py`
- `server/api/chat/session.py`
- `server/api/chat_branch.py`
- `server/api/training.py`
- `server/core/config.py`
- `server/api/knowledge.py`
- `server/tests/test_architecture_cleanup.py`
- `server/test_comprehensive_api.py`
- `server/test_functional.py`

**Why**

- 收口 chat session canonical 路径
- 移除 chat compat 路由
- 移除 training 根 alias
- 清理 knowledge stub
- 让测试和后端契约同步到当前实现

## Commit 2

**Title**

`feat(ui): align frontend with canonical session and experimental modules`

**Scope**

- `client/src/App.tsx`
- `client/src/components/ChatBranchManager.tsx`
- `client/src/components/ContextPanel.tsx`
- `client/src/pages/ActionRecorder.tsx`
- `client/src/pages/CUAControl.tsx`
- `client/src/pages/GatewayPage.tsx`
- `client/src/pages/HeartbeatPage.tsx`
- `client/src/pages/MCPTools.tsx`
- `client/src/services/api.ts`
- `client/src/store/appStore.ts`

**Why**

- 前端切换到 canonical chat session API
- 页面和后端字段/错误语义对齐
- experimental 模块完成显式降级
- 收敛 chat 状态中心

## Commit 3

**Title**

`docs: document architecture cleanup and archive legacy plans`

**Scope**

- `README.md`
- `AGENTS.md`
- `项目架构诊断与整改方案.md`
- `CHANGELOG_2026-04-08.md`
- `.trae/documents/ARCHIVE_NOTICE_2026-04-08.md`
- `.trae/specs/ARCHIVE_NOTICE_2026-04-08.md`

**Why**

- 把 canonical 路径、experimental 分级、实施状态同步到正式文档
- 给历史设计稿目录补统一归档说明
- 为团队提供一份可转发的整改变更记录

## Optional Split

如果你希望更细，还可以把 `Workspace / CUA / Gateway / Heartbeat` 那组后端能力单独拆成一个中间提交：

**Title**

`feat(platform): persist workspace metadata and tighten gateway heartbeat semantics`

**Files**

- `server/api/workspace.py`
- `server/api/cua.py`
- `server/api/gateway_api/routes.py`
- `server/api/heartbeat.py`

这个拆法更适合需要逐个 review 的场景，但会让提交数从 3 个变成 4 个。

## Recommended Order

1. `refactor(api): unify canonical chat and training endpoints`
2. `feat(ui): align frontend with canonical session and experimental modules`
3. `docs: document architecture cleanup and archive legacy plans`
