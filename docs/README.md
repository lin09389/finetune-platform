# 文档索引

> 本文件是 `docs/` 目录的导航入口。运行时行为以代码与 `AGENTS.md` 开发约定为准。

## 架构与运行时

| 文档 | 说明 |
|------|------|
| [PLATFORM_RUNTIME_FOUNDATION.md](PLATFORM_RUNTIME_FOUNDATION.md) | 平台运行时基础 |
| [backend-application-profiles.md](backend-application-profiles.md) | 后端应用装配边界（combined / agent / finetune） |
| [dependency-profiles.md](dependency-profiles.md) | 依赖 profile 拆分与 `uv` extras 说明 |
| [local-inference-service.md](local-inference-service.md) | 独立本地推理服务 |
| [local-inference-deployment.md](local-inference-deployment.md) | 本地推理部署 |
| [training-worker.md](training-worker.md) | 训练 worker 隔离 |
| [release-lifecycle-design.md](release-lifecycle-design.md) | 评估/部署发布注册表设计 |
| [local-first-observability.md](local-first-observability.md) | 本地优先可观测性 |

## 能力分层

| 文档 | 说明 |
|------|------|
| [capability-truth-table.md](capability-truth-table.md) | GA / Beta / Experimental 分层语义真值表 |

## 前端

| 文档 | 说明 |
|------|------|
| [frontend-review-2026-07-08.md](frontend-review-2026-07-08.md) | 前端评审（性能 / UX / 代码质量 / 视觉一致性 / 可访问性） |
| [frontend-review-2026-07-08-supplement.md](frontend-review-2026-07-08-supplement.md) | 前端评审补充 |
| [frontend-capability-parity-2026-07-12.md](frontend-capability-parity-2026-07-12.md) | 前端能力对齐 |
| [chat-virtualization-2026-07-09.md](chat-virtualization-2026-07-09.md) | 聊天虚拟化 |

## Agent

| 文档 | 说明 |
|------|------|
| [agent-training-foundation.md](agent-training-foundation.md) | Agent 训练基础 |
| [coding-agent-capability-audit-2026-07-11.md](coding-agent-capability-audit-2026-07-11.md) | 编码 Agent 能力审计 |
| [coding-agent-engineering-loop.md](coding-agent-engineering-loop.md) | 编码 Agent 工程循环 |
| [agent_session_migration.md](agent_session_migration.md) | Agent Session 迁移 |

## 审计

| 文档 | 说明 |
|------|------|
| [ux-audit-2026-07-14.md](ux-audit-2026-07-14.md) | UX 全维度审查报告（P0/P1/P2 优先级矩阵） |
| [project-defect-audit-2026-07-14.md](project-defect-audit-2026-07-14.md) | 项目缺陷审计 |

## 集成与运维

| 文档 | 说明 |
|------|------|
| [DEPLOYMENT_STRATEGY.md](DEPLOYMENT_STRATEGY.md) | 部署策略 |
| [INTEGRATION_SPEC.md](INTEGRATION_SPEC.md) | 集成规范 |
| [MCP_INTEGRATION.md](MCP_INTEGRATION.md) | MCP 工具集成 |
| [CUA_USAGE.md](CUA_USAGE.md) | CUA 使用说明 |
| [OLLAMA_CONNECTION_STABILITY.md](OLLAMA_CONNECTION_STABILITY.md) | Ollama 连接稳定性 |
| [QUICK_START_OLLAMA_FIX.md](QUICK_START_OLLAMA_FIX.md) | Ollama 修复快速开始 |

## ADR（架构决策记录）

位于 [`adr/`](adr/) 目录，编号 0001–0009。

## 设计计划

位于 [`plans/`](plans/) 目录，按日期命名。

## 审计报告

位于 [`audits/`](audits/) 目录。

## 运维笔记

位于 [`notes/`](notes/) 目录（Docker / Ollama / Qwen / 数据库修复等）。

## 历史归档

位于 [`history/`](history/) 目录：阶段完成报告（phase0–phase4）、架构重构 handoff、代码评审等历史文档。
