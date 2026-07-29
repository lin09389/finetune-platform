# server/api AGENTS.md

本文件只覆盖 `server/api/` 子树（FastAPI 路由层）的约定、禁止事项与本地验证命令。项目级概述、命令面与安全边界见根 [`AGENTS.md`](../../AGENTS.md)；目录树详解、设计模式与 API 端点全表见 [`docs/architecture-reference.md`](../../docs/architecture-reference.md)。

## 子树约定

- **注册所有权**：本目录只定义 Router；实际挂载由 `server/apps/routers.py` 按 profile（combined / agent / finetune）注册，能力分层以 `server/apps/capability_registry.py` 为单一事实源。新增/改名路由必须同步注册表，`GET /api/info` 是运行时权威。
- **薄路由层**：路由函数只做参数校验、鉴权依赖和服务调用；业务逻辑放对应领域包（`agent_session/`、`training_engine/`、`rag/`、`cloud_models/` 等）。
- **experimental 双挂载**：experimental 能力（cua/heartbeat/mcp/gateway/ocr 等）启用时挂 `/experimental/*` 并保留 legacy 别名；关闭时不注册。不要在路由内自行判断开关。
- **鉴权依赖**：使用 `security/auth_middleware.py` 的 `get_current_user` / `require_roles` / `require_cua_admin`；`/cua/*` 路由级强制 `Depends(require_cua_admin)`，`DEBUG` 不放行。
- **降级语义**：下游服务（inference gateway / facade 等）不可用时返回 503/504 + `Retry-After`，不得返回占位成功。
- **SSE 端点**：（如 `/training/progress/stream`、`/agent-sessions/{id}/events/stream`）必须关闭代理缓冲并维持心跳。
- **长任务解耦**：HTTP 处理器只提交请求或决策；prompt/resume/评估等长耗时执行走后台任务（`BackgroundTaskManagerService`、评估后台 run），禁止在请求内 `await` 长耗时模型调用。
- **阻塞 I/O**：经 `asyncio.to_thread` 卸下事件循环，不得阻塞主 loop。
- **路径安全**：涉及用户提供路径的接口（如 `/context/scan`）必须走 `workspace/path_policy.py` 校验：越界 403、非法 400。
- **已迁出模块**：`inference_engine/` 引擎选择已迁独立 `inference_server`，主 app 不再注册；`chat_agent.py` 仅保留兼容意图分类。

## 禁止事项

- 禁止绕过 `apps/routers.py` 在别处直接 `include_router` 挂载本目录 Router。
- 禁止在路由层内联业务逻辑或直接操作数据库/模型（走领域服务）。
- 禁止新增未在 `capability_registry.py` 登记的能力挂载点。
- 禁止改动 GA 能力端点造成破坏性变更（须向后兼容 + 回归测试；见根 AGENTS.md 能力分层）。
- 禁止从 `server/scripts/` import 任何内容。
- 禁止在响应/日志中泄露 JWT、`INFERENCE_INTERNAL_API_KEY` 或其他密钥。

## 本地验证命令

```bash
# 仓库根目录执行（完整跑需 uv sync --frozen --extra all --extra dev 环境）
python -m pytest server/tests -m "not integration and not e2e" -q   # 单元口径

# 路由层高频回归（按改动域选择）
python -m pytest server/tests/test_phase0_security.py server/tests/test_global_auth_middleware.py -q   # 鉴权/安全契约
python -m pytest server/tests/test_phase2_capability_tiers.py server/tests/test_application_profiles.py -q   # 能力分层/挂载
python -m pytest server/tests/test_training.py server/tests/test_training_worker_api.py -q   # 训练路由
python -m pytest server/tests/test_inference_facade_gateway.py -q   # 推理降级
python -m pytest server/tests/test_agent_session_auth_optional.py server/tests/test_phase9_agent_eval_api.py -q   # Agent/评测 API

# 语法快速检查
python -m py_compile server/api/<changed_file>.py
```
