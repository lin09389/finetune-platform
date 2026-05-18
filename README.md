# Finetune Platform 2.0

大模型微调平台 - 消费级显卡专用 · 本地 AI 工作台

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18+-61dafb.svg)](https://reactjs.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.3+-orange.svg)](https://github.com/langchain-ai/langgraph)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 产品化试用路径

Finetune Platform 当前主线是面向 AI 应用开发者的本地模型适配工作台，核心闭环：

1. 在 `Datasets` 上传业务数据，运行数据集分析，确认格式、字段完整率和可训练样本数。
2. 在 `Training` 选择应用目标（客服/知识问答助手，或结构化输出/信息抽取），启动训练并通过 SSE 事件流监测进度。
3. 训练完成后进入 `Evaluation`，对比 base model 与 fine-tuned model 的输出质量并人工评分。
4. 在 `Deployment` 生成 LoRA adapter、Ollama Modelfile、OpenAI-compatible API 示例和 `.env` 模板。

推荐第一次试用时先使用小模型和 5-20 条样例数据，确认数据准备、评估和部署接入流程跑通后，再扩大训练规模。

## 能力分级 (Capability Tiers)

| 级别 | 包含能力 |
|------|----------|
| **GA** | 训练、推理、模型管理、数据集、Chat Session、基础知识库 |
| **Beta** | 项目上下文、智能记忆、模型中心、工作空间、Agent Session |
| **Experimental** | CUA、Action Recorder、MCP、Heartbeat、Gateway 扩展链路 |

Experimental 模块仅用于受控验证，页面可打开不代表能力已稳定可用。评估平台主能力请优先以 `GA` 路径为准。

## 🌟 当前能力

### 主线能力
- 🎯 **低显存微调**：LoRA / QLoRA 主线支持，针对 4GB+ 显存设备优化
- 📦 **模型与数据集管理**：HuggingFace / ModelScope 双源下载、本地管理、数据集上传与统计分析
- 📈 **训练监测 V2**：SSE 事件流、断点续训、Checkpoint 校验、训练历史、异步清理
- 🤖 **多后端推理**：HuggingFace / vLLM / LlamaCPP / Ollama 可切换，gRPC 推理服务，流式输出
- 🧩 **Chat + Agent**：Chat Session、`auto / chat / agent` 路由模式、Agent Session、审批门控动作执行
- 🛠️ **LangGraph Agent Runtime**：Graph-first 执行、多工具链（文件/命令/符号索引/浏览器/HTTP）、审批恢复、事件诊断
- 🗂️ **Workspace / Context / Memory**：项目上下文扫描与检索（ChromaDB + sentence-transformers）、工作区文件管理、记忆系统
- 📄 **文件解析**：PDF / DOCX / XLSX / OCR（Tesseract + RapidOCR）

### 工程化增强
- ✅ **SQLite 持久化存储**：自动迁移、定时备份（默认每 6 小时）、连接池管理
- 🔒 **多层安全**：WAF（SQL 注入 / XSS / 路径遍历拦截）、IP 黑名单、JWT 认证、速率限制、安全响应头
- 📝 **结构化日志与 Trace ID**：每个请求唯一 Trace ID，便于链路定位
- 🧪 **测试覆盖**：80+ pytest 测试文件，覆盖 agent-session、training、inference、gateway 等关键链路；前端 vitest + Storybook
- 🐳 **Docker / Electron**：Docker Compose（含 GPU、Ollama profile）及 Electron 桌面端两种发布形态
- 🌐 **云模型网关**：统一 `ai.gateway` 接入多云 LLM Provider，支持 OpenAI 兼容接口
- 🔗 **代码执行器**：受控沙箱代码执行（`/code`）
- 📡 **实体识别**：`/entity` 路由，从文本中提取结构化实体

## 🏗️ 架构概览

当前仓库包含四条并行主链：

| 主链 | 说明 |
|------|------|
| **Finetune Runtime** | 模型、数据集、训练引擎、推理、评估、部署 |
| **Chat Surface** | Chat Session、ChatNew UI、流式消息、上下文面板、分支与共享 |
| **Agent Surface** | Chat Agent 意图路由、Agent Session、LangGraph 执行、审批门控 |
| **Workspace Surface** | 工作区文件、项目上下文检索、本地开发协作 |

### 后端目录结构

```text
server/
├── api/                       # FastAPI 路由层（所有 HTTP 端点）
│   ├── chat/                  # Chat Session 路由
│   ├── inference/             # 推理路由（含 gRPC）
│   ├── inference_engine/      # 推理引擎抽象
│   ├── memory_new/            # 记忆 API
│   ├── knowledge/             # 知识库 API
│   └── gateway_api/           # Gateway 路由
├── agent_session/             # Agent Session 核心
│   ├── langgraph/             # LangGraph 图构建、节点、状态、checkpoint
│   ├── file_tools.py          # 文件读写工具
│   ├── browser_tools.py       # 浏览器工具
│   ├── symbol_index_tools.py  # 符号索引工具
│   ├── command_policy.py      # 命令安全策略
│   ├── patch_engine.py        # 代码 patch 引擎
│   ├── processor.py           # 事件处理器
│   └── service.py             # Agent Session 服务
├── ai/                        # 云模型网关
│   └── gateway.py             # 多 Provider 统一接入
├── chat_agent/                # Chat -> Agent 意图路由
├── context/                   # 项目上下文扫描与检索
├── memory/                    # 记忆系统
├── rag/                       # ChromaDB 向量检索 + Embedder
├── training_engine/           # 训练引擎（pipeline、loader、callback）
├── inference_service/         # 推理服务后端
├── backends/                  # 推理后端适配（HF/vLLM/LlamaCPP/Ollama）
├── security/                  # 速率限制、JWT、沙箱
├── workspace/                 # 工作区文件 API、任务 API
├── core/                      # 配置、存储、日志、训练上下文
├── cua/                       # Computer Use Agent（Experimental）
├── gateway/                   # Gateway 扩展链路（Experimental）
├── heartbeat/                 # Heartbeat 主动唤醒（Experimental）
├── mcp/                       # MCP 工具（Experimental）
├── tests/                     # pytest 测试套件（80+ 文件）
└── main.py                    # 应用入口
```

### 前端目录结构

```text
client/src/
├── pages/                     # 页面组件
├── components/                # 通用组件
├── hooks/                     # 自定义 Hooks
├── services/                  # API 服务层
├── store/                     # Zustand 状态管理
├── types/                     # TypeScript 类型定义
├── styles/                    # 全局样式 / 主题
└── test/                      # vitest 测试
```

## 🌈 项目愿景

Finetune Platform 2.0 的核心使命是构建一个**数据驱动、具备自我进化能力的本地 AI 协同生态系统**，致力于实现以下三大愿景：

- 🚀 **智能混合路由**：在本地轻量化模型与云端超大规模模型之间进行毫秒级动态分发，平衡响应速度与成本。
- 🧠 **工作流数字孪生与数据集工厂**：将人机协作轨迹自动转化为高纯度专业指令数据集。
- 🔄 **闭环进化微调**：依托自动生成的数据集持续微调本地模型，实现 AI 能力的私有化深度沉淀。

> [!IMPORTANT]
> 上述愿景代表项目技术演进方向。目前混合路由原型、工作流捕获等底层模块已进入 Experimental/Beta 测试阶段，全自动化"采样-训练-部署"闭环仍在高频迭代中。

> [!CAUTION]
> Finetune Platform 2.0 仍处于**早期迭代阶段**。核心微调与推理链路已跑通，但许多高级特性仍处于快速原型验证期。代码结构与 API 可能随迭代发生较大变动，暂不建议在生产关键业务中使用。

## 📋 系统要求

### 硬件要求

| 显存 | 可用模型规模 | 训练方式 | 场景 |
|------|------------|----------|------|
| 4GB | 0.5B-1.5B (INT4) | QLoRA | 最低要求 |
| 6GB | 3B-7B (INT4) | QLoRA | 入门 |
| 8GB | 7B (INT4) | LoRA | 推荐 |
| 12GB | 7B/13B | LoRA/QLoRA | 理想 |
| 24GB | 13B/30B | LoRA | 专业 |

### 软件依赖

| 依赖 | 版本要求 |
|------|----------|
| Python | 3.10+ |
| Node.js | 18+ |
| CUDA | 11.8+（NVIDIA GPU） |
| Docker | 20.10+（可选） |
| OS | Windows 10/11、Linux、macOS |

### 关键 Python 依赖

| 包 | 版本 | 用途 |
|----|------|------|
| `fastapi` | ≥0.115.0 | Web 框架 |
| `torch` | 2.1.2 | 深度学习框架 |
| `transformers` | 4.57.1 | 模型加载与推理 |
| `peft` | 0.18.1 | LoRA/QLoRA 微调 |
| `accelerate` | 1.13.0 | 训练加速 |
| `bitsandbytes` | 0.41.3 | INT4/INT8 量化 |
| `langgraph` | ≥0.3 | Agent 编排框架 |
| `langchain-core` | ≥0.3 | LangChain 核心 |
| `chromadb` | ≥0.4.22 | 向量数据库 |
| `sentence-transformers` | 5.2.3 | 文本向量化 |
| `llama-cpp-python` | ≥0.2.79 | GGUF 推理后端 |

## 🚀 快速开始

### 方法一：Windows 一键启动（推荐）

直接双击根目录的 `start.bat`，脚本会自动：
1. 检查 Python / Node.js 环境
2. 安装缺失的后端 / 前端依赖
3. 在独立窗口中分别启动后端（`:8010`）和前端（`:5173`）

访问：
- 前端：http://localhost:5173
- API 文档：http://localhost:8010/docs
- 健康检查：http://localhost:8010/health

### 方法二：手动启动（跨平台）

```bash
# 1. 克隆项目
git clone https://github.com/lin09389/finetune-platform.git
cd finetune-platform

# 2. 配置环境（按需修改 .env）
# Linux / macOS
cp .env.example .env
# Windows
# copy .env.example .env

# 3. 安装后端依赖
cd server
pip install -r requirements.txt
cd ..

# 4. 安装前端依赖
cd client
npm install
cd ..
```

然后**分别打开两个终端**，均从项目根目录执行：

```bash
# 终端 1 - 启动后端
cd server
python -m uvicorn main:app --host 127.0.0.1 --port 8010
```

```bash
# 终端 2 - 启动前端
cd client
npm run dev
```

### 方法三：Docker 体验版

```bash
# 启动后端 API + 生产版前端
docker compose up -d --build

# （可选）启动 Ollama 模式
docker compose --profile ollama up -d --build

# （可选）启动 GPU 模式（需要 NVIDIA Docker 环境）
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build

# 查看日志
docker compose logs -f api frontend
```

默认 Docker 体验版不强制要求 GPU，适合先验证平台能否打开、后端是否连接。详细说明见 [DOCKER.md](docs/notes/DOCKER.md)。

### 训练监测 V2 联调验收

```bash
# 启动后端后，在仓库根目录执行
python scripts/validate_training_v2_flow.py --base-url http://127.0.0.1:8010 --auto-stop-after 45
```

验收通过标准：`overall_passed = true`，且 `received_events`、`sequence_monotonic`、`sequence_no_gaps`、`saw_terminal` 均为 `true`。

## 📚 文档

| 文档 | 说明 |
|------|------|
| [AGENTS.md](AGENTS.md) | 当前项目结构、开发命令、能力边界 |
| [CLAUDE.md](CLAUDE.md) | 开发规范与架构约束 |
| [Docker 部署](docs/notes/DOCKER.md) | 容器化部署、GPU 配置 |
| [能力真值表](docs/capability-truth-table.md) | 功能成熟度、依赖、失败模式 |
| [Agent Session 设计](docs/agent_session_migration.md) | LangGraph 设计与迁移说明 |
| [Chat Agent 验收](docs/chat_agent_real_acceptance.md) | Chat Agent 真实验收记录 |

## 📁 项目结构

```
finetune-platform/
├── server/                     # 后端服务（FastAPI + Python）
│   ├── api/                    # HTTP 路由层
│   ├── agent_session/          # Agent Session + LangGraph 执行链
│   ├── ai/                     # 云模型网关（多 Provider）
│   ├── chat_agent/             # Chat -> Agent 意图路由
│   ├── context/                # 项目上下文检索
│   ├── memory/                 # 记忆系统
│   ├── rag/                    # 知识库 / 向量检索
│   ├── training_engine/        # 训练引擎
│   ├── inference_service/      # 推理服务
│   ├── backends/               # 推理后端适配
│   ├── security/               # WAF、JWT、速率限制
│   ├── workspace/              # 工作区文件与任务 API
│   ├── core/                   # 配置、存储、日志
│   ├── cua/                    # CUA（Experimental）
│   ├── gateway/                # Gateway（Experimental）
│   ├── heartbeat/              # Heartbeat（Experimental）
│   ├── mcp/                    # MCP（Experimental）
│   ├── tests/                  # pytest 测试套件
│   ├── main.py                 # 应用入口
│   └── requirements.txt        # Python 依赖
├── client/                     # 前端应用（React 18 + TypeScript）
│   ├── src/
│   │   ├── pages/              # 页面
│   │   ├── components/         # 组件
│   │   ├── services/           # API 服务
│   │   ├── store/              # Zustand 状态
│   │   └── types/              # TypeScript 类型
│   └── package.json
├── electron/                   # Electron 桌面端
├── models/                     # 模型存储
├── datasets/                   # 数据集存储
├── outputs/                    # 训练输出
├── logs/                       # 日志文件
├── scripts/                    # 运维与验收脚本
├── docs/                       # 文档
├── docker-compose.yml
├── Dockerfile
└── README.md
```

## 🖥️ 前端页面列表

### GA / Beta 页面

| 页面 | 说明 |
|------|------|
| `Dashboard` | 平台概览与能力入口 |
| `DeviceInfo` | 设备、显存、系统资源 |
| `ModelManager` | 本地模型管理 |
| `ModelHub` | 模型中心 / HuggingFace + ModelScope 下载 |
| `DatasetManager` | 数据集上传、分析、校验 |
| `Training` | 训练配置、监测、事件流 V2 |
| `Inference` | 推理测试与对话 |
| `Evaluation` | 评估 run、样例输出、人工评分 |
| `Deployment` | 部署包与导出物 |
| `History` | 训练与运行历史 |
| `KnowledgeBase` | 知识库 / RAG |
| `ProjectContext` | 项目上下文扫描与检索 |
| `MemoryPage` | 记忆与上下文存储 |
| `WorkspaceManager` | 工作区、文件与本地开发协作 |
| `ChatNew` | 聊天主界面（Chat Session + Agent Run Cards + Context Panel） |
| `APIKeyManager` | 云模型 API Key 管理 |

### Experimental 页面

| 页面 | 说明 |
|------|------|
| `GatewayPage` | Gateway 扩展链路 |
| `HeartbeatPage` | Heartbeat 主动唤醒 |
| `CUAControl` | Computer Use Agent 控制面板 |
| `MCPTools` | MCP 工具面板 |
| `ActionRecorder` | Action Recorder |
| `SharedChat` | 共享聊天视图 |
| `DesignSystem` | 设计系统展示 |
| `DigitalTeam` | 数字团队（过渡中） |

## 💬 ChatNew 主能力

`ChatNew` 是当前最重要的统一入口，同时承担：

- **Chat Session**：多会话历史、消息列表、会话切换、消息删除
- **路由模式**：`auto / chat / agent` 三种模式，自动或手动判断是否启动 Agent Task
- **云模型支持**：Provider / Model 选择、API Key 管理
- **Workspace 绑定**：绑定工作区与项目路径，让 Agent Task 落在正确上下文
- **Context Panel**：查看路由模式、主 Agent、Autonomy Mode、上下文信息
- **Agent Run Cards**：在聊天流里展示 Agent Session 阶段、动作审批、执行结果
- **会话分支与共享**：支持消息分支和共享聊天链接

使用路径：`ChatNew 发起需求 → 路由判断 → chat（直接回复）或 agent（创建 Agent Session + 审批执行）`

> Agent 模块适合小范围、可观察、可审批的本地任务；跨模块大规模重构仍需人工密切介入。

## 🧭 第一次上手 Chat / Agent

1. 启动后端和前端，确认 `http://localhost:5173` 与 `http://localhost:8010/docs` 都能打开。
2. 进入 `ChatNew`，查看 `Context Panel`，确认路由模式、主 Agent、Workspace 符合预期。
3. 发一条普通问题（如"解释 LoRA 和 QLoRA 的区别"），确认走 `chat` 路由而不是 agent。
4. 发一条开发型目标（如"读取 package.json 和 main.py，总结项目结构"），确认创建 Agent Session 并在卡片里展示执行过程。
5. 发一个小改动目标（如"修改某测试文件中的一个字符串"），观察 Agent 卡片进入 `waiting_approval`，再执行 `approve / execute`。
6. 确认事件与动作状态变化：`pending → approved → executed`。

## 🔌 API 端点

### 核心路由

| 分类 | 前缀 | 说明 |
|------|------|------|
| 设备 | `/device` | 设备信息、显存、磁盘 |
| 模型 | `/models` | 模型列表、下载、ONNX 导出 |
| 数据集 | `/datasets` | 上传、分析、统计 |
| 训练 | `/training` | 启动、停止、进度 SSE、历史、V2 事件 |
| 推理 | `/inference` | 聊天、流式输出、LoRA 合并 |
| 评估 | `/evaluation` | 评估 run、人工评分 |
| 部署 | `/deployment` | 部署包创建与列表 |
| Chat | `/chat` | 会话 CRUD、消息管理 |
| Chat Agent | `/chat-agent` | 意图判断、run 创建、事件流 |
| Agent Session | `/agent-sessions` | 创建、提交目标、事件流 |
| Agent Actions | `/agent-actions` | 审批、拒绝、执行动作 |
| 知识库 | `/knowledge` | RAG 知识库管理 |
| 记忆 | `/memory` | 记忆存取 |
| 上下文 | `/context` | 项目上下文扫描检索 |
| 工作区 | `/workspace` | 工作区管理 |
| 文件 | `/files` | 文件读写 API |
| 任务 | `/tasks` | 任务调度 API |
| 云模型 | `/cloud` | 云模型聊天与流式 |
| 模型中心 | `/model-center` | 模型发现与下载建议 |
| 代码执行 | `/code` | 受控代码执行 |
| 运行时 | `/runtime` | Bootstrap 与运行时能力 |
| 实体 | `/entity` | 实体识别 |
| OCR | `/ocr` | 图像文字识别 |
| CUA | `/cua` | Computer Use Agent（Experimental） |
| MCP | `/mcp` | MCP 工具（Experimental） |
| Gateway | `/gateway` | 扩展网关（Experimental） |
| Heartbeat | `/heartbeat` | 主动唤醒（Experimental） |

### 常用端点参考

```
GET  /health                              # 健康检查（含 CUDA 状态）
GET  /api/info                            # 平台能力元信息
GET  /device/info                         # 设备信息
POST /training/start                      # 启动训练
GET  /training/v2/events/stream           # SSE 训练事件流 V2
POST /inference/stream                    # 流式推理
POST /chat-agent/runs                     # 创建 Chat Agent Run
GET  /chat-agent/runs/{run_id}/events/stream  # Chat Agent 事件流
POST /agent-sessions                      # 创建 Agent Session
POST /agent-sessions/{id}/prompt          # 提交 Agent 目标
POST /agent-actions/{action_id}/approve   # 批准动作
POST /agent-actions/{action_id}/execute   # 执行动作
```

## 🧪 测试

```bash
# 后端测试
cd server
pytest

# 带覆盖率
pytest --cov=. --cov-report=html

# 指定测试文件
pytest tests/test_agent_session_processor.py -v

# 前端测试
cd client
npm test

# 前端冒烟测试
npm run test:smoke

# 前端测试（UI 模式）
npm run test:ui
```

后端当前有 **80+ 个测试文件**，覆盖 agent-session、training、inference、gateway、security、storage 等关键链路。守护测试 `test_no_legacy_imports.py` 会阻止旧包引用回归。

## 🛡️ 安全特性

| 特性 | 说明 |
|------|------|
| WAF | SQL 注入、XSS、路径遍历自动拦截 |
| IP 黑名单 | 可配置阻断来源 |
| JWT 认证 | Bearer token，生产环境可启用 |
| 速率限制 | 每 IP 每窗口最大请求数，Redis 可选持久化 |
| 安全响应头 | `X-Content-Type-Options`、`X-Frame-Options`、`HSTS` 等 |
| 文件上传校验 | 类型、大小、内容多重验证 |
| 路径遍历防护 | 工作区路径严格白名单 |
| 命令策略 | Agent 执行命令的 allowlist + 沙箱约束 |

## 🔧 环境变量配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `HOST` | 服务地址 | `127.0.0.1` |
| `PORT` | 服务端口 | `8010` |
| `ENVIRONMENT` | 运行环境（development/production） | `development` |
| `ENABLE_AUTH` | 启用 JWT 认证 | `false` |
| `JWT_SECRET_KEY` | JWT 密钥（生产环境必须设置） | — |
| `ALLOWED_ORIGINS` | CORS 来源 | `http://localhost:5173` |
| `OLLAMA_BASE_URL` | Ollama 地址 | `http://localhost:11434` |
| `INFERENCE_ENGINE` | 推理引擎（huggingface/vllm/llamacpp/ollama） | `huggingface` |
| `RATE_LIMIT` | 每窗口最大请求数 | `100` |
| `RATE_WINDOW` | 速率限制窗口（秒） | `60` |
| `MAX_UPLOAD_SIZE` | 最大上传大小（字节） | `104857600` |
| `LOG_LEVEL` | 日志级别 | `INFO` |
| `LOG_FORMAT` | 日志格式（text/json） | `text` |
| `HF_MIRROR` | HuggingFace 镜像源 | `hf-mirror` |
| `MODEL_SOURCE` | 模型下载源（modelscope/huggingface） | `modelscope` |
| `MAX_CONCURRENT_TRAINING` | 最大并发训练数 | `1` |
| `BACKUP_INTERVAL_HOURS` | 自动备份间隔（小时） | `6` |
| `BACKUP_RETENTION_DAYS` | 备份保留天数 | `7` |

完整配置示例见 `.env.example`。

## 📊 性能特性

- **模型缓存**：减少重复加载，显存自动清理
- **异步处理**：全异步非阻塞 I/O（asyncio + FastAPI）
- **量化支持**：INT4/INT8（bitsandbytes），GGUF（llama-cpp）
- **gRPC 推理**：可选高性能 gRPC 推理服务端
- **动态批处理**：可配置（`ENABLE_BATCHING`）
- **SQLite 连接池**：多连接池并发管理

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

## 🙏 致谢

- [HuggingFace Transformers](https://github.com/huggingface/transformers)
- [PEFT](https://github.com/huggingface/peft)
- [LangGraph](https://github.com/langchain-ai/langgraph)
- [FastAPI](https://github.com/tiangolo/fastapi)
- [React](https://github.com/facebook/react)
- [Ant Design](https://github.com/ant-design/ant-design)
- [ChromaDB](https://github.com/chroma-core/chroma)

---

**注意**：训练过程中请勿关闭应用，确保数据完整保存。生产环境部署前务必设置 `JWT_SECRET_KEY` 并启用 `ENABLE_AUTH=true`。
