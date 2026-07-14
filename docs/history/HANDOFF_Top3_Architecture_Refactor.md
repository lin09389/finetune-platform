# Top3 架构重构交接文档

> 日期：2026-07-04
> 状态：全部完成，857 测试全绿，F401 全部清零，未提交

## 一、重构目标

将平台核心执行面（训练、推理、Agent 会话）从「散落模式判断」重构为「网关集中决策 + 服务层委托」，消除跨模块重复的 `training_execution_mode` / `inference_execution_mode` 分支，拆分过大的 AgentSessionService 门面，并清理应用装配边界。

## 二、变更全景

**统计**：29 个已跟踪文件修改 + 6 个新文件/目录，净减 1,564 行代码

### 新增文件

| 文件 | 行数 | 职责 |
|---|---|---|
| `server/core/training_gateway.py` | ~270 | 训练执行面网关：`InProcessTrainingGateway` / `WorkerTrainingGateway`，按 `training_execution_mode` 自动选择，对外暴露 `get_training_gateway()` |
| `server/core/inference_gateway.py` | ~290 | 推理执行面网关：`LocalInferenceGateway` / `ServiceInferenceGateway`，按 `inference_execution_mode` 自动选择，对外暴露 `get_inference_gateway()` |
| `server/api/inference/facade.py` | ~130 | 推理路由门面：将 `/inference` 路由注册与 `inference_execution_mode` 解耦，无论哪种模式路由都可注册 |
| `server/agent_session/services/` | 8 个文件 | 从 `service.py` 拆分出的子服务包（见下表） |
| `server/tests/fixtures/execution_mode.py` | ~70 | 测试夹具：`inference_in_process` / `training_in_process` 的实现 |
| `server/tests/fixtures/training_worker_stub.py` | ~40 | 测试夹具：Worker 模式下的 repository stub |

### `agent_session/services/` 拆分明细

原 `agent_session/service.py` 从 ~1,800 行瘦身至 ~198 行纯门面，逻辑下沉到：

| 子服务文件 | 职责 |
|---|---|
| `session_lifecycle.py` | 会话创建、状态机驱动、终止 |
| `event_broadcast.py` | SSE 事件广播、part 解析与合并 |
| `approval_service.py` | 动作审批、权限检查 |
| `background_task_manager.py` | 异步子任务注册、取消、恢复 |
| `recovery_service.py` | 会话恢复、崩溃恢复 |
| `model_call_coordinator.py` | 模型调用适配 |
| `utils.py` | 共享工具函数 |

### 修改文件分类

#### 核心架构（P1-P3）

| 文件 | 改动摘要 |
|---|---|
| `server/core/training_gateway.py` | **新建**。训练网关，集中 `training_execution_mode` 决策 |
| `server/core/inference_gateway.py` | **新建**。推理网关，集中 `inference_execution_mode` 决策 |
| `server/api/inference/facade.py` | **新建**。推理路由门面，解耦路由注册与执行模式 |
| `server/api/inference/__init__.py` | 改用 facade 注册路由 |
| `server/api/training.py` | 改用 `get_training_gateway()` 替代直接调用 context/worker；`_worker_mode()` 作为唯一保留的模式判断点 |
| `server/api/runtime.py` | 改用 `get_inference_gateway()` 获取推理运行时 |
| `server/apps/routers.py` | Profile 分域注册清理 |
| `server/apps/lifespan.py` | 生命周期按 profile 组合 |
| `server/inference_server/app.py` | 适配网关接口 |
| `server/agent_session/service.py` | 从 ~1,800 行 → ~198 行门面 |

#### API 层模式判断清除（P3 延伸）

| 文件 | 改动摘要 |
|---|---|
| `server/api/evaluation.py` | `_find_training_record` / `_persist_evaluation_link` 委托 `services.training.records`，去除 `training_execution_mode` 分支 |
| `server/api/deployment.py` | `_find_training_record` / `_sync_training_promotion` 委托 `services.training.records`，删除模块级 `get_training_context` 导入 |
| `server/api/models.py` | `_find_training_history_adapter` 委托 `services.training.records`，删除模块级 `get_training_context` 导入 |

#### 环境修复

| 文件 | 改动摘要 |
|---|---|
| `pyproject.toml` | 新增 `pyarrow>=15.0.0,<20` 约束（24+ 在 Windows 崩溃） |
| `uv.lock` | pyarrow 24.0.0 → 19.0.1 |
| `server/rag/__init__.py` | `rag.structured` 改为 `__getattr__` 懒加载，避免导入 rag 包时触发 pandas/pyarrow |
| `server/rag/structured/table_store.py` | pandas 改为方法级延迟导入 |
| `server/core/storage.py` | 小适配 |

#### 测试适配

| 文件 | 改动摘要 |
|---|---|
| `server/tests/conftest.py` | 新增 `training_in_process` / `inference_in_process` fixtures |
| `server/tests/fixtures/execution_mode.py` | **新建**。fixture 实现 |
| `server/tests/fixtures/training_worker_stub.py` | **新建**。worker stub |
| `server/tests/test_training_v2_events.py` | `pytestmark` 切换 in_process；monkeypatch 目标从 `training_api` 改为 `core.training_context` / `core.training_events_v2` |
| `server/tests/test_training_recovery_analytics.py` | 添加 `training_in_process` fixture |
| `server/tests/test_agent_session_model_adapter.py` | 添加 `inference_in_process` fixture |
| `server/tests/test_evaluation_deployment.py` | 3 处 monkeypatch 从 `deployment.get_training_context` 改为 `services.training.records.find/save_training_record` |
| `server/tests/test_models.py` | monkeypatch 从 `models_api.get_training_context` 改为 `services.training.records.list_training_records` |
| `server/tests/test_agent_session_deepagents_runtime.py` | monkeypatch 目标从 `agent_session.service.secure_storage` 改为 `agent_session.services.session_lifecycle.secure_storage` |
| 其他 7 个测试文件 | 小幅适配（添加 fixture 参数或 import 调整） |

## 三、重构后的架构心智模型

### 模式决策点（仅 2 处）

```
training_execution_mode
  ├── server/api/training.py → _worker_mode()     [训练控制面网关]
  └── server/core/training_gateway.py              [训练记录访问网关]
      └── services/training/records.py             [记录 CRUD 的模式切换]

inference_execution_mode
  ├── server/core/inference_gateway.py              [推理执行面网关]
  ├── server/api/inference/facade.py               [推理路由注册门面]
  └── server/agent_session/model_adapter.py        [Agent 模型路由]
```

### 数据流

```
API 层（evaluation / deployment / models / training）
  │
  ├─ 训练记录访问 ──→ services.training.records.find/list/save_training_record()
  │                      └── 内部按 training_execution_mode 切换数据源
  │
  ├─ 训练控制操作 ──→ get_training_gateway().start/cancel/get_status()
  │                      └── InProcess 或 Worker 实现
  │
  └─ 推理调用     ──→ get_inference_gateway().generate_stream/batch()
                         └── Local 或 Service 实现
```

### Agent Session 调用链

```
api/agent_sessions.py
  └── agent_session/service.py (198行门面)
        ├── services/session_lifecycle.py     → 创建/状态机
        ├── services/event_broadcast.py      → SSE 事件
        ├── services/approval_service.py     → 审批
        ├── services/background_task_manager.py → 异步任务
        ├── services/recovery_service.py     → 恢复
        └── services/model_call_coordinator.py → 模型调用
```

## 四、测试验证

### 最终结果

```
pytest server/tests -q
→ 857 passed, 17 deselected, 1 warning in ~225s
```

### ruff 清理

本轮额外发现并修复 7 个 F401（未使用导入）：

| 文件 | 处理 |
|---|---|
| `agent_session/service.py` | 删除未使用的 `secure_storage` 导入 |
| `agent_session/services/event_broadcast.py` | 删除未使用的 `AgentSessionEventBus` 导入 |
| `agent_session/services/recovery_service.py` | 删除未使用的 `build_initial_execution_plan`、`build_agent_runtime_policy` 导入 |
| `agent_session/services/session_lifecycle.py` | 删除未使用的 `AgentRegistry` 导入 |
| `api/runtime.py` | 删除未使用的 `settings` 导入 |
| `core/inference_gateway.py` | 删除 `chat_completions` 方法内未使用的 `httpx` 导入 |
| `tests/test_agent_session_deepagents_runtime.py` | 同步更新 monkeypatch 目标，避免测试找不到 `agent_session.service.secure_storage` |

清理后：`ruff check server/ --select F401` → 无报错

### 第二轮排查

| 检查项 | 结果 |
|---|---|
| 全模块导入测试 | 31 个关键模块全部导入成功 |
| 三个 profile 实例化 | combined(386 routes) / agent(284 routes) / finetune(106 routes) 均成功 |
| 致命 lint 检查（F401/F811/F821） | 全工程无报错 |
| 全量测试回归 | 857 passed |
| 新增/修改文件 ruff | 无报错 |

### 发现并及时修复的关键问题

1. **`api/training.py` 存在约 83 行不可达死代码**
   - 在 `/progress/stream` 路由中，第一个 `return StreamingResponse(...)` 之后存在第二个 `event_generator()` 实现，使用了未定义的 `time`、`hub`、`state` 等名字
   - 原因：重构为网关委托后，旧实现未被删除
   - 处理：删除死代码，消除 F821 隐患，文件从 ~1,344 行减至 ~1,261 行

2. **`api/training.py` 导入结构问题**
   - 函数定义 `_load_checkpoints_for_task` 放在导入块中间，触发 E402
   - 处理：将函数移到所有 import 之后

3. **`agent_session/services/` 新文件 lint 问题**
   - I001（导入未排序）和 UP037（带引号类型注解）
   - 处理：`ruff check --fix` 自动修复全部 11 处

### 验证覆盖

| 维度 | 验证方法 | 结果 |
|---|---|---|
| 全量回归 | `pytest server/tests` | 857 passed |
| 训练模式切换 | 手动切换 `in_process` / `worker` | 两种 gateway 均正确实例化 |
| 推理模式切换 | 手动切换 `in_process` / `service` | 两种 gateway 均正确实例化 |
| Agent 拆分 | facade 行数检查 | 198 行 < 300 行限制 |
| 静态检查 | `ruff check` 改动文件 | 无新增错误 |
| 依赖一致性 | `uv pip check` | All compatible |
| pyarrow 版本 | `import pyarrow; __version__` | 19.0.1 |
| 懒加载 | `import rag` 不触发 pandas | 通过 |

### 已知限制

1. **pyarrow 约束是 Windows 特有**：Linux/CI 上 pyarrow 24+ 不崩溃，但约束 `<20` 不会造成问题（19.x 功能足够）
2. **17 个 deselected 测试**：标记为 `integration` / `e2e`，需要真实 GPU/Ollama 环境，不在单元测试范围内
3. **`api/training.py` 仍保留 `_worker_mode()`**：这是设计决策——训练控制面需要快速判断模式以选择 API 路径（gateway vs repository），不宜强制走网关

## 五、提交前检查清单

- [ ] `uv sync --frozen` 确认锁文件一致
- [ ] `uv export --no-dev --no-hashes --format requirements-txt -o server/requirements.txt` 更新导出
- [ ] 在 Linux 环境跑一次全量测试（确认无 Windows 特有问题）
- [ ] 提交消息建议：`refactor: Top3 architecture refactor — gateway abstraction, agent service split, mode dispatch consolidation`

## 六、后续可改进项（非本轮范围）

1. **`api/training.py` 的 `_worker_mode()` 也可下沉到网关**：但需要改写 `test_training.py` 中大量直接 mock context 的用例，ROI 较低
2. **`agent_session/model_adapter.py` 的 `inference_execution_mode` 判断**：在 `inference_execution_mode == "service"` 时将 ollama 路由到本地推理服务（provider 改为 "openai"），这一逻辑可考虑移入 `inference_gateway`
3. **`server/requirements.txt` 未更新**：需要 `uv export` 重新生成以包含 pyarrow 版本约束
