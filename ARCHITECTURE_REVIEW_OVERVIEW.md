# 架构深度评审 — 概览

**日期**：2026-07-10 ｜ **评审对象**：Finetune Platform 2.x ｜ **状态**：纯评审，未改代码 ｜ **修订**：2026-07-10 勘误（修正"默认关认证/限流"误判、GitHub star 数据失真、`.env` 行号、`sandbox.py` 可达路径）

## 做了什么
从架构师视角对全仓库做了**八维度深度审查**（架构/代码质量/性能/安全/可扩展/可维护/UX/Agent 专项），并以 **GitHub 三组顶级开源项目**为对标基准，逐一对比。本轮按用户要求**总体重写了报告**，整合此前所有调查（平台标杆、Agent 框架标杆、编程 Agent 产品标杆）为一个连贯文档。

## 三组对标基准（Star 经 GitHub API 实时核验，2026-07-10）
- **平台/基础设施**：Dify 148,358 / Open WebUI 144,913 / vLLM 85,867 / LLaMA-Factory 73,122 / Langfuse 30,844 / MLflow 26,960。
- **Agent 框架**：n8n 195,564 / browser-use 69,458 / OpenHands 69,204 / MetaGPT 69,203 / AutoGen 59,556 / CrewAI 54,944 / LangGraph 36,908 / OpenAI Agents SDK 27,534。（**勘误**：原报告 browser-use 104,024、OpenHands 80,287 有误，已按 GitHub API 修正）
- **编程 Agent 产品**：OpenClaw 382,089（TS，本地优先·模型无关个人助手）/ Codex 27,595（Rust，OpenAI 官方终端 Agent；**勘误**：原报告 96,811 有误，已修正）/ OpenCode 13,397（Go，⚠️ 已 archived）。

## 五大根本性缺陷（root cause）
1. **用户本地 `.env` 覆盖关闭了认证与限流（项目代码默认开启）** — `server/.env` 设 `ENABLE_AUTH=false` / `ENABLE_RATE_LIMIT=false`，覆盖了 `config.py`（`enable_auth` 默认 `True`）与 `factory.py:127`（限流默认 `"true"`）的代码默认值；含可控制宿主的 CUA 在无认证下暴露。（**注**：非架构级设计缺陷，项目出厂默认是安全的；问题在配置覆盖）
2. **异步/事件循环正确性缺失** — `training.py` worker 路由内同步 SQLite + 阻塞式 `requests` 卡死事件循环。
3. **"能力目录"被当扩展体系** — `capability_registry` 只是 tier 表，无插件发现/hook，封死生态。
4. **存储/协调单机天花板** — SQLite + 文件锁，无 PG/Redis 分水岭，控制面无法水平扩展。
5. **无可观测性主干** — 无 OTel 追踪、无全应用 `/metrics`、JSON 日志默认关、无关联 ID。

## 战略坐标（综合判断）
- **广度护城河**：唯一把"微调 + 推理 + Agent + RAG + CUA"合体的平台；标杆均不具此广度。
- **最危险错位**：拥有 CUA 宿主级控制，而用户本地 `.env` 覆盖关闭认证 —— "能远程控制宿主"在无门禁下暴露（注：项目代码默认开启认证，问题在配置覆盖）。
- **Agent 现状**：单 agent + CUA + 持久化达一线；多 agent 团队、token/usage 追踪、原生编排所有权、独立 coding agent 产品面、安全沙箱、插件生态、数据自持产品化落后。
- **最该对齐**：OpenClaw（战略）/ Codex（补齐安全沙箱+tokens 追踪两块）。

## 高危安全项（P0，建议先修）
- 用户本地 `.env` 覆盖关闭认证 + CUA 可控制宿主（审查 `.env` 不随发货带入关闭值；代码已默认开启）
- `sandbox.py` shell 命令注入（首词白名单 + `create_subprocess_shell`；可达路径为 `/code/` 端点，Agent 走 DeepAgents sandbox 不走此路径）
- `factory.py` CORS 凭据反射（任意 Origin + 凭据）

## 报告结构（总体重写版，勘误修订）
- §0 执行摘要（三句话 + 成熟度快照）｜ §1 范围与方法 ｜ §2 对标基准全景（三组）｜ §3 战略坐标
- §4 五大根本性缺陷 ｜ §5 八维度逐项对比（5.1–5.8，含 Agent 专项）｜ §6 优先级路线图 P0–P3
- §7 附录差距矩阵（平台/Agent/编程 Agent 三表）｜ §8 ADR 草案（ADR-001~007）

## 交付物
- 完整报告：`ARCHITECTURE_REVIEW_2026-07-10.md`（含 file:line 证据、三组对标、P0–P3 路线图、三张差距矩阵、7 篇 ADR 草案）
- 本概览：`ARCHITECTURE_REVIEW_OVERVIEW.md`

## 下一步
按 P0→P3 排期改进；本轮未改动任何代码，待用户确认后进入修复阶段。
