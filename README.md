# Finetune Platform 2.0

大模型微调平台 - 消费级显卡专用 · 企业级增强版

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18+-61dafb.svg)](https://reactjs.org)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 产品化试用路径

Finetune Platform 当前主线正在收口为面向 AI 应用开发者的本地模型适配工作台，核心闭环是：

1. 在 `Datasets` 上传业务数据，运行数据集分析，确认格式、字段完整率和可训练样本数。
2. 在 `Training` 选择应用目标：客服/知识问答助手，或结构化输出/信息抽取。
3. 训练完成后进入 `Evaluation`，对比 base model 与 fine-tuned model 的输出质量。
4. 在 `Deployment` 生成 LoRA adapter、Ollama Modelfile、OpenAI-compatible API 示例和 `.env` 模板。

推荐第一次试用时先使用小模型和 5-20 条样例数据，确认数据准备、评估和部署接入流程跑通后，再扩大训练规模。

## 🌟 特性亮点

## Capability Tiers

Finetune Platform does not treat every visible page as equally mature. Current product copy, navigation, and API metadata follow three tiers:

- `GA`：训练、推理、模型管理、数据集、Chat Session、基础知识库。这些是当前的核心可交付能力。
- `Beta`：项目上下文、智能记忆、模型中心、工作空间。可试用，但仍依赖环境和持续 UX 收口。
- `Experimental`：CUA、Action Recorder、MCP、Heartbeat、Gateway 扩展链路。仅用于受控验证，页面可打开不代表能力已稳定可用。

Experimental 模块会在页面内显示实时状态、依赖要求和受限原因；如果你要评估平台主能力，请优先以 `GA` 路径为准。

### 当前主线能力
- 🎯 **低显存微调**：LoRA / QLoRA 主线支持，针对 4GB+ 显存设备优化
- 📦 **模型与数据集管理**：模型下载、本地管理、数据集上传、验证和统计分析
- 📈 **训练监测**：训练状态、SSE 进度流、断点续训、训练历史
- 🤖 **推理与评估**：本地推理、Ollama 集成、流式输出、评估 run 与人工评分
- 🧩 **Chat + Agent**：Chat Session、Chat Agent 意图路由、Agent Session、审批门控动作执行
- 🛠️ **Workflow Runtime**：多 Agent 工作流、观测、事件流、动作审批与执行
- 🗂️ **Workspace / Context / Memory**：项目上下文检索、工作区管理、记忆与知识库能力

### 工程化增强
- ✅ **LangGraph Agent Session**：Graph-first 执行、审批恢复、事件诊断
- 🔒 **安全约束**：路径白名单、命令 allowlist、上传校验、速率限制
- 📝 **结构化日志与状态诊断**：便于定位训练、推理、Agent、Workflow 链路问题
- 🧪 **测试覆盖**：pytest + vitest，覆盖 chat-agent、agent-session、workflow、evaluation 等关键链路
- 🐳 **Docker / Ollama**：本地 API、前端、Ollama 模式的快速启动路径

## 🏗️ 当前架构

当前仓库已经不是单纯的“训练 + 推理”面板，而是四条主链并存：

1. `Finetune Runtime`
   包含模型、数据集、训练、推理、评估、部署。
2. `Chat Surface`
   包含 Chat Session、ChatNew UI、流式消息、上下文面板。
3. `Agent Surface`
   包含 Chat Agent 意图路由、Agent Session、LangGraph 执行、审批门控动作。
4. `Workflow / Workspace Surface`
   包含多 Agent Workflow Runtime、观测页、工作区文件与上下文能力。

核心后端目录现在以这些模块为主：

```text
server/
├── api/                       # FastAPI 路由
├── agent_session/             # Agent Session、LangGraph、工具、审批恢复
├── agent_runtime/             # 多 Agent workflow runtime
├── chat_agent/                # 聊天意图 -> agent/workflow 路由
├── context/                   # 项目上下文扫描与检索
├── memory/                    # 记忆系统
├── rag/                       # 知识库 / 向量检索
├── security/                  # 速率限制、沙箱、安全中间件
├── workspace/                 # 工作区相关路径与文件能力
└── main.py                    # 应用入口
```

## 🌈 项目愿景 (Project Vision)

Finetune Platform 2.0 的核心使命是构建一个**数据驱动、具备自我进化能力的本地 AI 协同生态系统**。我们不仅仅在打造一款微调工具，更是在探索 AI 开发的新范式，致力于实现以下三大愿景：

- 🚀 **智能混合路由 (Intelligent Hybrid Routing)**
  通过多维度语义感知，系统能根据任务的复杂度、实时算力负载及模型领域专长，在**本地轻量化模型**与**云端超大规模模型**之间进行毫秒级的动态分发。这不仅确保了响应的即时性，更实现了处理性能与运行成本的极致平衡。

- 🧠 **工作流数字孪生与数据集工厂**
  平台能够深度感知并结构化捕获用户与 Agent 的每一次协同交互、代码演进及复杂任务的闭环链路。通过自动化抽象技术，将这些珍贵的人机协作轨迹转化为高纯度的**专业指令数据集**，变“碎片化对话”为“结构化知识”。

- 🔄 **闭环进化微调 (Self-Evolving Fine-tuning)**
  依托自动生成的数据集，用户可对本地模型进行持续的、针对性的微调训练。通过不断吸收特定领域知识与业务逻辑，使本地模型在垂直场景下实现能力跃迁，逐步对标甚至在特定维度超越云端通用模型，最终实现 **AI 能力的私有化深度沉淀**。

> [!IMPORTANT]
> **开发状态说明**：上述愿景代表了项目的技术演进方向。目前，混合路由原型、工作流捕获等底层模块已进入 **Experimental/Beta** 测试阶段，而全自动化的“采样-训练-部署”闭环仍在持续高频迭代中。

> [!CAUTION]
> **项目阶段声明**：Finetune Platform 2.0 目前仍处于**极早期的迭代阶段 (Early Incubation)**。虽然核心微调与推理链路已跑通，但许多高级特性（如自动化 Agent 工作流、多模型混合路由等）仍处于快速原型验证期。代码结构与 API 可能会随迭代发生较大变动，暂不建议在生产环境的关键业务中使用。

## 📋 系统要求

### 硬件要求

| 显存 | 可用模型 | 训练方式 | 推荐配置 |
|------|----------|----------|----------|
| 4GB | 0.5B-1.5B (INT4) | QLoRA | 最低要求 |
| 6GB | 3B-7B (INT4) | QLoRA | 入门 |
| 8GB | 7B (INT4) | LoRA | 推荐 |
| 12GB | 7B/13B | LoRA/QLoRA | 理想 |
| 24GB | 13B/30B | LoRA | 专业 |

### 软件要求

- **操作系统**: Windows 10/11, Linux, macOS
- **Python**: 3.10+
- **Node.js**: 18+
- **CUDA**: 11.8+ (NVIDIA GPU)
- **Docker**: 20.10+ (可选)

## 🚀 快速开始

### 方法一：本地部署

#### 1. 安装依赖

```bash
# 克隆项目
git clone https://github.com/lin09389/finetune-platform.git
cd finetune-platform

# 安装后端依赖
cd server
pip install -r requirements.txt

# 安装前端依赖
cd ../client
npm install
```

#### 2. 配置环境

创建 `.env` 文件（可选）：

```bash
# 服务配置
HOST=127.0.0.1
PORT=8010

# CORS 配置
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# Ollama 配置
OLLAMA_BASE_URL=http://localhost:11434
INFERENCE_BACKEND=huggingface

# 速率限制
RATE_LIMIT=100
RATE_WINDOW=60

# 日志配置
LOG_LEVEL=INFO
LOG_FORMAT=text
```

#### 3. 启动服务

```bash
# 终端 1 - 启动后端
cd server
python -m uvicorn main:app --host 127.0.0.1 --port 8010

# 终端 2 - 启动前端
cd client
npm run dev
```

#### 4. 访问应用

- 前端：http://localhost:5173
- API 文档：http://localhost:8010/docs

### 方法二：Docker 体验版（推荐预览路径）

```bash
# 启动后端 API + 生产版前端
docker compose up -d --build

# 验证核心入口和 GA API
python scripts/verify_docker_release.py

# 查看日志
docker compose logs -f api frontend
```

默认 Docker 体验版不强制要求 GPU，适合先验证平台是否能打开、后端是否连接、核心 GA 页面是否能显示明确状态。

可选能力：

```bash
# 启动 Ollama 模式
docker compose --profile ollama up -d --build

# 启动 GPU 模式（需要 NVIDIA Docker 环境）
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

详细 Docker 启动、清理、GPU/Ollama 和验收说明见 [DOCKER.md](docs/notes/DOCKER.md)。

### 训练监测 V2 联调验收（API 直连）

用于验证训练监测链路（`SSE 主通道 + WS 备通道 + V2 事件协议`）是否可用。

```bash
# 1) 启动后端（若尚未启动）
cd server
python -m uvicorn main:app --host 127.0.0.1 --port 8010

# 2) 在仓库根目录执行联调脚本
cd ..
python scripts/validate_training_v2_flow.py --base-url http://127.0.0.1:8010 --auto-stop-after 45
```

脚本行为：
- 自动解析或发现模型/数据集，调用 `/training/start` 启动训练
- 订阅 `/training/v2/events/stream` 收集事件序列
- 可选自动停止训练（`--auto-stop-after`）
- 拉取 `/training/v2/overview` 与 `/training/v2/tasks/{task_id}/metrics`
- 生成验收报告到 `outputs/validation/training_v2_report_<task8>.json`

通过标准：
- `overall_passed = true`
- 且关键验收项为 true：`received_events`、`sequence_monotonic`、`sequence_no_gaps`、`saw_terminal`

## 📚 文档

| 文档 | 说明 |
|------|------|
| [AGENTS.md](AGENTS.md) | 当前项目结构、开发命令、能力边界 |
| [Docker 部署](docs/notes/DOCKER.md) | 容器化部署、GPU 配置 |
| [能力真值表](docs/capability-truth-table.md) | 功能成熟度、依赖、失败模式、回归覆盖 |
| [Agent Session 迁移说明](docs/agent_session_migration.md) | Agent Session / LangGraph 设计与收口 |
| [Chat Agent 验收](docs/chat_agent_real_acceptance.md) | Chat Agent 真实验收记录 |

## 📁 项目结构

```
finetune-platform/
├── server/                     # 后端服务
│   ├── api/                    # 设备 / 模型 / 数据集 / 训练 / 推理 / chat-agent / workflows
│   ├── agent_session/          # Agent Session 与 LangGraph 执行链
│   ├── agent_runtime/          # Workflow Runtime
│   ├── chat_agent/             # chat -> agent/workflow 编排
│   ├── context/                # 项目上下文
│   ├── memory/                 # 记忆系统
│   ├── rag/                    # 知识库
│   ├── workspace/              # 工作区能力
│   ├── tests/                  # pytest 测试套件
│   ├── main.py                 # 应用入口
│   └── requirements.txt        # Python 依赖
├── client/                     # 前端应用
│   ├── src/
│   │   ├── components/         # 组件
│   │   ├── pages/              # 页面
│   │   ├── services/           # API 服务
│   │   ├── store/              # 状态管理
│   │   ├── test/               # 测试
│   │   └── types/              # TypeScript 类型
│   ├── package.json
│   └── vite.config.ts
├── electron/                   # Electron 桌面端
│   ├── main.js
│   └── preload.js
├── models/                     # 模型存储
├── datasets/                   # 数据集存储
├── outputs/                    # 训练输出
├── logs/                       # 日志文件
├── docker-compose.yml          # Docker 配置
├── Dockerfile                  # Docker 镜像
└── README.md                   # 本文件
```

## 🖥️ 当前前端页面

当前前端页面已经不只是训练面板，实际页面可以按下面理解：

- `Dashboard`：平台概览与能力入口
- `DeviceInfo`：设备、显存、系统资源
- `ModelManager`：本地模型管理
- `ModelHub`：模型中心 / 下载建议
- `DatasetManager`：数据集上传、分析、校验
- `Training`：训练配置、训练监测、训练事件流 V2
- `Inference`：推理测试与对话
- `Evaluation`：评估 run、样例输出、人工评分
- `Deployment`：部署包与导出物
- `History`：训练与运行历史
- `KnowledgeBase`：知识库 / RAG
- `ProjectContext`：项目上下文扫描与检索
- `MemoryPage`：记忆与上下文存储能力
- `WorkspaceManager`：工作区、文件与本地开发协作能力
- `ChatNew`：新版聊天主界面，包含会话、路由、上下文面板、Agent / Workflow 运行卡片
- `Workflows`：多 Agent workflow 观测、审批与事件流
- `APIKeyManager`：云模型 API Key 管理

下面这些页面目前更适合按实验性能力理解：

- `GatewayPage`：Gateway 扩展链路
- `HeartbeatPage`：Heartbeat 主动唤醒
- `CUAControl`：CUA 控制面板
- `MCPTools`：MCP 工具面板
- `ActionRecorder`：Action Recorder
- `SharedChat`：共享聊天视图
- `DesignSystem`：设计系统展示
- `DigitalTeam`：历史页面，当前不应视为主线能力

## 💬 Chat 页面主能力

`ChatNew` 现在是最重要的统一入口，不只是一个“发消息的页面”。它同时承担了：

- `Chat Session`：多会话历史、消息列表、会话切换、消息删除与清空
- `Routing`：支持 `auto / chat / agent` 路由模式，自动判断当前请求应该走普通聊天、Agent Task 还是 Workflow Run
- `Cloud Model`：支持云模型开关、Provider / Model 选择、API Key 管理入口
- `Workspace Binding`：可绑定工作区与项目路径，让聊天、agent、workflow 都落在同一项目上下文里
- `Context Panel`：查看和调整路由模式、主 Agent、Workflow Template、Autonomy Mode、工作区与上下文信息
- `Agent Run Cards`：在同一个聊天流里展示 agent session、动作审批、执行结果、阶段状态
- `Workflow Timeline`：在聊天页直接展示 workflow steps、tool events、当前状态与活跃节点
- `Memory / Context`：从聊天页侧边能力进入记忆管理、上下文信息与 API Key 配置

所以更准确地说，当前项目的使用路径不是“先聊天，再单独去 agent 页面”，而是：
`先在 ChatNew 发起需求 -> 再根据路由结果进入 chat / agent / workflow 三种执行形态`。

同时也需要明确一点：
当前 `agent` 模块已经能完成只读任务、单文件小补丁、动作审批与基础 workflow 观测，但整体仍然比较粗糙，还不应该被理解成“稳定成熟的通用开发代理”。
更合适的预期是：

- 它适合做小范围、可观察、可审批的本地任务
- 它适合做受控验证，而不是一上来就承担大规模重构
- 当任务跨模块、跨多轮修复、强依赖云模型稳定性时，仍然需要人工密切介入

如果你在评估当前项目，请把 `agent` 理解为“正在快速收口中的核心 Beta 能力”，而不是已经完全产品化的终态。

## 🧭 第一次上手 Chat / Agent / Workflow

如果你第一次想体验现在项目里的主链路，推荐把 `ChatNew` 当成第一入口，按这个顺序：

1. 先启动后端和前端，确认 `http://localhost:5173` 与 `http://localhost:8010/docs` 都能打开。
2. 进入 `ChatNew`，先看右侧或抽屉式的 `Context Panel`，确认当前 `routing mode`、主 Agent、Workflow Template、Autonomy Mode、Workspace 都符合你的预期。
3. 先发送一条普通问题，比如“帮我解释一下 LoRA 和 QLoRA 的区别”，确认它会走普通 `chat` 路由，而不是误判成 agent。
4. 再发送一条明确的开发型目标，比如“读取当前项目的 package.json 和 server/main.py，然后总结项目结构”，确认它会从聊天流中创建 `Agent Session`，并在卡片里展示执行过程。
5. 如果要体验动作审批，再发送一个明确的小改动目标，例如“只修改某个测试文件中的一个字符串”，观察聊天流里的 Agent 卡片进入 `waiting_approval`，然后执行 `approve / execute`。
6. 最后进入 `Workflows` 页面看 observability，确认能看到 steps、tool events、actions、recent events，以及动作从 `pending -> approved -> executed` 的状态变化。
7. 如果你只是想验证当前链路是否健康，优先做“只读任务”与“单文件小补丁任务”，不要一开始就让 agent 做跨模块重构。

一个比较稳妥的第一次体验路径是：

- 在 `ChatNew` 里先完成普通聊天验证
- 再用同一个页面发起只读 Agent 任务
- 观察 `AgentRunCard / AgentPartMessage / WorkflowStepCard`
- 再发起一个单文件 patch 任务并审批执行
- 最后到 `Workflows` 页面看观测与事件流

## 🔌 API 端点

### 设备管理
- `GET /device/info` - 设备信息
- `GET /device/vram` - VRAM 信息
- `GET /device/memory` - 系统内存
- `GET /device/disk` - 磁盘信息

### 模型管理
- `GET /models` - 模型列表
- `POST /models/download` - 下载模型
- `GET /models/{id}` - 模型详情
- `DELETE /models/{id}` - 删除模型
- `POST /models/{id}/export/onnx` - 导出 ONNX

### 数据集管理
- `GET /datasets` - 数据集列表
- `POST /datasets/upload` - 上传数据集
- `GET /datasets/{id}` - 数据集详情
- `GET /datasets/{id}/statistics` - 统计信息

### 训练管理
- `GET /training/status` - 当前训练状态
- `POST /training/start` - 开始训练
- `POST /training/stop` - 停止训练
- `GET /training/progress` - 训练进度
- `GET /training/progress/stream` - SSE 进度流
- `GET /training/history` - 训练历史
- `POST /training/resume/{id}/{checkpoint}` - 恢复训练

### Chat Session
- `GET /chat/sessions` - 会话列表
- `POST /chat/sessions` - 创建会话
- `GET /chat/sessions/{id}` - 会话详情
- `DELETE /chat/sessions/{id}` - 删除会话
- `POST /chat/sessions/{id}/messages` - 添加消息
- `GET /chat/sessions/{id}/messages` - 获取消息列表

### Chat Agent / Agent Session
- `POST /chat-agent/intent` - 判断消息应走 `chat / agent / workflow`
- `POST /chat-agent/runs` - 创建 Chat Agent run
- `GET /chat-agent/runs/{run_id}/events/stream` - Chat Agent 事件流
- `POST /agent-sessions` - 创建 Agent Session
- `GET /agent-sessions/{id}` - 获取 Agent Session
- `POST /agent-sessions/{id}/prompt` - 提交 Agent 目标
- `POST /agent-actions/{action_id}/approve` - 批准动作
- `POST /agent-actions/{action_id}/reject` - 拒绝动作
- `POST /agent-actions/{action_id}/execute` - 执行动作

### Workflows
- `GET /workflows` - 工作流列表
- `GET /workflows/{workflow_id}/observability` - 工作流观测
- `GET /workflows/{workflow_id}/events/stream` - 工作流事件流
- `POST /workflow-actions/{action_id}/approve` - 批准 workflow 动作
- `POST /workflow-actions/{action_id}/execute` - 执行 workflow 动作

### Evaluation / Deployment
- `POST /evaluation/runs` - 创建评估 run
- `GET /evaluation/runs/{run_id}` - 查询评估状态
- `POST /evaluation/runs/{run_id}/score` - 人工评分
- `GET /deployment/packages` - 部署包列表
- `POST /deployment/packages` - 创建部署包

### 推理服务
- `POST /inference/chat` - 聊天对话
- `POST /inference/stream` - 流式输出
- `POST /inference/merge` - 合并 LoRA

> 说明：
> `Chat` 旧兼容路由与 `GET /training` 根别名已移除。
> 当前前端和文档默认后端端口为 `8010`。
> `digital_team` 已不再作为独立主线能力存在，相关兼容层仅用于过渡。

## 🧪 测试

```bash
# 后端测试
cd server
pytest

# 带覆盖率
pytest --cov=server --cov-report=html

# 前端测试
cd client
npm test

# 前端测试（带 UI）
npm run test:ui
```

## 🛡️ 安全特性

- **文件上传校验**: 类型验证、大小限制、内容检查
- **路径遍历防护**: 严格的路径验证机制
- **速率限制**: 防止 API 滥用
- **CORS 配置**: 可配置跨域策略
- **输入验证**: Pydantic 严格模式

## 📊 性能优化

- **模型缓存**: 减少重复加载
- **显存管理**: 自动清理、智能分配
- **异步处理**: 非阻塞 I/O
- **量化支持**: INT4/INT8 量化

## 🔧 配置选项

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| `HOST` | 服务地址 | `127.0.0.1` |
| `PORT` | 服务端口 | `8010` |
| `LOG_LEVEL` | 日志级别 | `INFO` |
| `ALLOWED_ORIGINS` | CORS 来源 | `http://localhost:5173` |
| `OLLAMA_BASE_URL` | Ollama 地址 | `http://localhost:11434` |
| `RATE_LIMIT` | 速率限制 | `100` |
| `MAX_UPLOAD_SIZE` | 最大上传 | `104857600` |

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

## 🙏 致谢

- [HuggingFace Transformers](https://github.com/huggingface/transformers)
- [PEFT](https://github.com/huggingface/peft)
- [FastAPI](https://github.com/tiangolo/fastapi)
- [React](https://github.com/facebook/react)
- [Ant Design](https://github.com/ant-design/ant-design)

---

**注意**: 训练过程中请勿关闭应用，确保数据完整保存。
