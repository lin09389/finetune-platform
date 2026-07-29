# Finetune Platform 能力成熟度表

Last updated: `2026-06-25`

本文档用于对齐产品文案、导航标签、发布说明、测试深度和 README。后端 `GET /api/info` 是能力分层的权威来源；如果本文档与代码冲突，以代码为准并回头修订本文档。

相关文档：

- [AGENTS.md](../AGENTS.md)
- [PLATFORM_RUNTIME_FOUNDATION.md](PLATFORM_RUNTIME_FOUNDATION.md)
- [agent_system_design.md](agent_system_design.md)

## 分层定义

| 分层 | 含义 | 维护要求 |
| --- | --- | --- |
| `GA` | 已形成前后端闭环的核心用户能力 | 保持向后兼容，补充回归测试，失败状态必须清晰 |
| `Beta` | 已可用但仍可能调整的能力 | 明确限制和依赖，避免承诺稳定 API |
| `Experimental` | 实验性能力，主要用于验证和二次开发 | UI 和文档必须标注实验状态，依赖缺失时显式失败 |

## `/api/info` 权威分层

| 分层 | Capability key |
| --- | --- |
| `GA` | `device`、`models`、`datasets`、`training`、`inference`、`chat_sessions`、`knowledge_base` |
| `Beta` | `project_context`、`memory`、`model_center`、`workspace` |
| `Experimental` | `cua`、`heartbeat`、`mcp`、`gateway`、`ocr_fallbacks`、`action_recorder` |

## 能力矩阵

| 能力 | API / 页面 | 分层 | 主要依赖 | 失败模式 | 建议验证 |
| --- | --- | --- | --- | --- | --- |
| 设备监控 | `/device`、`/device` 页面 | `GA` | 本机 CPU/GPU/内存探测 | 返回明确 API 错误或降级信息 | 后端集成测试、前端 smoke |
| 模型管理 | `/models`、`/models` 页面 | `GA` | 本地文件系统、HuggingFace、ModelScope | 下载/删除/导出失败必须带错误信息 | 后端集成测试 |
| 数据集管理 | `/datasets`、`/datasets` 页面 | `GA` | 本地文件系统、上传解析 | 文件类型、大小、格式校验失败显式返回 | 后端集成测试、前端 smoke |
| 训练 | `/training`、`/training` 页面 | `GA` | PyTorch、Transformers、PEFT、本地 GPU/CPU | 预检、启动、停止、恢复和 SSE 中断都应有状态 | 后端集成测试、训练事件测试 |
| 推理 | `/inference`、`/inference` 页面 | `GA` | HuggingFace/Ollama/llama.cpp/vLLM | 后端不可用、模型加载失败、熔断状态显式返回 | 后端契约测试、前端 smoke |
| 聊天会话 | `/chat/sessions`、`/chat` 页面 | `GA` | SQLite、本地或云端模型配置 | 会话读写失败、流式中断清晰提示 | 后端集成测试 |
| 知识库 | `/knowledge`、`/knowledge` 页面 | `GA` | ChromaDB、sentence-transformers、文档解析器 | 嵌入模型缺失、索引失败、解析失败显式返回 | 后端集成测试 |
| 项目上下文 | `/context`、`/project-context` 页面 | `Beta` | 本地项目扫描、符号提取、索引 | 质量受项目结构影响，错误需可追踪；`project_path` 必须位于允许的工作区根内：越界路径返回 `403`，非法路径返回 `400`（防 LFI/路径遍历，见 `workspace/path_policy.py`） | 服务层测试（`test_phase3_context_safety.py::test_context_scan_rejects_out_of_scope_path`）、前端 smoke |
| 记忆系统 | `/memory`、`/memory` 页面 | `Beta` | SQLite/向量检索/抽取逻辑 | 读写失败和检索失败显式返回 | 服务层测试 |
| 模型中心 | `/model-center`、`/modelhub` 页面 | `Beta` | 外部模型源和网络 | 网络失败、镜像源不可用、鉴权失败清晰提示 | 后端局部测试 |
| 工作区 | `/workspace`、`/workspace` 页面 | `Beta` | 本地文件系统、工作区状态 | 路径、权限、文件读写错误显式返回 | 后端集成测试 |
| CUA | `/cua`、`/cua-control` 页面 | `Experimental` | OS 自动化、屏幕、键盘、鼠标、OCR | 环境不可用时展示限制，不返回假成功 | 后端局部测试、前端 smoke |
| Action Recorder | `/cua-recorder` 页面 | `Experimental` | 本地交互钩子、文件系统 | 录制权限或保存失败需明确 | 前端 smoke、保存/加载测试 |
| OCR fallback | `/ocr` | `Experimental` | Tesseract、RapidOCR、图像依赖 | 依赖缺失返回 unavailable，不静默占位 | 定向后端测试 |
| MCP | `/mcp`、`/mcp` 页面 | `Experimental` | 已配置 MCP servers | 连接、发现、调用失败显式返回 | 后端集成测试 |
| Gateway | `/gateway`、`/gateway` 页面 | `Experimental` | WebSocket、设备配对、认证 | 配对/鉴权/路由失败显式返回 | 后端集成测试 |
| Heartbeat | `/heartbeat`、`/heartbeat` 页面 | `Experimental` | 本地调度器、任务处理器 | 调度启动/停止失败显式返回 | 后端集成测试 |

## Agent Workbench 说明

`/agent` 是当前默认应用入口，也是平台的重要产品表面。它依赖 Agent Session、DeepAgents、workspace、project context、审批和 SSE 事件流等模块。由于 `/api/info` 当前没有把 `agent_workbench` 单独列为 capability key，文档和 README 应将它描述为“工作台/产品入口”，而不是额外声明一个未在 `/api/info` 中出现的稳定分层。

如果未来要把 Agent Workbench 纳入正式能力分层，应先更新后端 `/api/info`，再同步 README、本文档、导航标签和测试计划。

## 当前守则

- README、导航文案、测试说明和发布说明必须与 `/api/info` 的分层保持一致。
- GA 能力必须避免破坏性 API 变更；确需变更时需要迁移说明或兼容层。
- Beta 能力可以迭代，但要在 UI 或文档里说明限制。
- Experimental 页面不得暗示生产稳定性；依赖缺失时必须显式显示状态。
- 后端不得用“占位成功”掩盖依赖缺失、模型不可用、权限不足或执行失败。
- 前端 smoke 测试应覆盖断连、未加载、不可用、空状态等真实用户会遇到的状态。

## 近期文档维护优先级

1. 每次修改 `/api/info` 的 capability key 后，同步更新 README 和本文档。
2. 每次把能力从 Experimental 提升到 Beta/GA 前，补齐前后端验证说明。
3. 每次修改启动端口、环境变量或 Docker profile 后，同步更新 `.env.example`、README 和部署文档。
