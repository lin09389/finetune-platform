# 阶段 1–3 架构验收记录

日期：2026-07-03

## 结论

阶段 1（应用装配边界）、阶段 2（训练 Worker 隔离）和阶段 3（本地推理服务隔离）已经完成。默认部署仍保持单仓库、单一对外 API；GPU 训练和本地推理由独立进程承担。

## 阶段 1：控制面应用边界

- `combined`、`agent`、`finetune` 三个 profile 由应用工厂装配。
- Router 所有权集中在 `server/apps/routers.py`，生命周期集中在 `server/apps/lifespan.py`。
- `server.main:app` 继续导出 combined 应用，前端 API 地址不变。
- Agent profile 不初始化训练上下文；Finetune profile 不初始化 Agent、Memory、RAG 生命周期。
- 服务模式下，控制面不会导入本地推理 scheduler、pipeline 或 `server.core.inference`。

验收证据：`server/tests/test_application_profiles.py` 和 `server/tests/test_inference_service_boundary.py::test_control_profile_does_not_import_native_inference_runtime`。

## 阶段 2：训练执行面隔离

- API 仅把训练任务写入 SQLite；`python -m server.training_worker` 独立领取并执行任务。
- job、event、log、lease 和 worker 注册表均持久化。
- 领取任务使用原子 lease；支持续租、取消、过期回收、进程硬退出后的恢复，以及达到重试上限后标记 interrupted。
- SSE 和日志流从持久化记录重放，API 重启不会丢失事件游标。
- 训练终态和 artifact/history 仍写回现有训练记录，保持前端契约兼容。

验收证据：`server/tests/test_training_worker_api.py`、`server/tests/test_training_worker_repository.py` 和 `server/tests/test_training_worker_runtime.py`。

## 阶段 3：本地推理执行面隔离

- `python -m server.inference_server` 提供独立、OpenAI-compatible 的本地推理服务。
- 控制面公开 `/v1/models`、`/v1/chat/completions` 及兼容路由，但只通过 HTTP Provider 转发。
- Agent 的本地/Ollama 模型和评估调用通过 Provider HTTP 访问推理服务，不再导入推理引擎实现。
- 推理服务具有内部 Bearer 认证、能力描述、OpenAI 错误信封、连接/读取超时、有限重试和流式响应契约。
- 公共代理不会转发用户 Authorization 或内部模型路径/LoRA header。
- 云端降级默认关闭；只有显式启用并配置 provider 时，才在本地服务不可用、超时或 503 时触发。客户端 4xx 不降级。
- 推理服务只绑定回环地址或 Docker 私网，不发布公网端口。
- 推理进程退出后，控制面健康端点继续可用；推理请求返回稳定的 503/504 错误。

验收证据：`server/tests/test_inference_service_boundary.py`，以及双进程 smoke test（代理模型列表 200、杀死推理进程后控制面 200、推理请求 504）。

## 2026-07-03 回归结果

- 后端普通测试：857 passed。
- 后端 integration：17 passed。
- 前端：`npm run typecheck` 通过，`npm run build` 通过。
- Python：`compileall` 通过；阶段新增 Python 文件 Ruff 检查通过。
- 部署：`docker compose config --quiet` 通过。

唯一测试警告来自 Starlette 对旧 `multipart` import 的上游 PendingDeprecationWarning，不影响本次边界。

## 不属于本次验收的后续阶段

- 阶段 4：按 agent/training/inference 拆依赖组和镜像；若 Agent 镜像要完全移除 Torch，还需将 embedding 改为远程 Provider 或独立服务。
- 阶段 5：仅在运行单元需要跨机器部署时，再拆数据库和 migration 所有权。
- 独立 Evaluation Worker 仍可作为后续增强；当前评估编排留在控制面，但模型执行已通过阶段 3 的远程推理 Provider 隔离。
