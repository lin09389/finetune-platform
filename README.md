# Finetune Platform 2.1

[English](README_EN.md) | 简体中文

面向独立开发者和小团队的本地大模型微调工作台：在消费级显卡上完成数据集管理、LoRA/QLoRA 微调、评估、推理、部署打包，并把 Agent 工作台、项目上下文、记忆和知识库放在同一个产品里。

![Python](https://img.shields.io/badge/Python-3.11-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109-009688)
![React](https://img.shields.io/badge/React-18-61DAFB)
![Vite](https://img.shields.io/badge/Vite-5-646CFF)
![DeepAgents](https://img.shields.io/badge/DeepAgents-0.6-orange)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

## 项目定位

Finetune Platform 不是一个只跑 demo 的训练脚本集合，而是一套可落地的本地 AI 工作台。它围绕“拿到数据、训练小模型、评估效果、部署使用、让 Agent 辅助项目开发”这条链路组织功能，尽量降低个人设备上的微调和实验成本。

适合你在这些场景里使用：

- 用 4GB+ 显存的消费级 NVIDIA 显卡做 LoRA/QLoRA 实验。
- 管理本地模型、数据集、训练历史、评估记录和部署产物。
- 在一个 Web UI 里完成推理测试、知识库问答、模型中心下载和工作区管理。
- 使用 Agent 工作台读取项目上下文、执行任务、查看计划、审批敏感操作。
- 研究本地 AI 平台、RAG、Agent Session、MCP、CUA 等工程集成方式。

## 能力分层

后端 `/api/info` 会暴露当前能力分层，README 以该接口为准。

| 分层 | 能力 | 稳定性 |
| --- | --- | --- |
| GA | device、models、datasets、training、inference、chat_sessions、knowledge_base | 主流程能力，适合日常使用和回归测试 |
| Beta | project_context、memory、model_center、workspace | 已可用，但接口和 UI 仍可能调整 |
| Experimental | cua、heartbeat、mcp、gateway、ocr_fallbacks、action_recorder | 实验能力，适合探索和二次开发 |

## 核心功能

### 微调与推理

- 模型管理：本地模型列表、下载、删除、导出和 ModelScope/HuggingFace 集成。
- 数据集管理：上传、解析、预处理和训练数据准备。
- LoRA/QLoRA 训练：面向低显存设备优化，支持任务状态、训练历史和检查点恢复。
- 实时训练进度：基于 SSE 的训练事件流，前端可实时展示 loss、step、状态和日志。
- 评估与对比：支持模型评估、人工评分、历史对比和部署前检查。
- 多后端推理：HuggingFace、Ollama、llama.cpp、vLLM 等后端可按环境切换。
- 部署打包：导出适配器、推理样例、Ollama Modelfile、环境模板等部署材料。

### Agent 与工作台

- `/agent` 是默认入口，提供沉浸式 Agent Workbench。
- Agent Session 通过 FastAPI + SSE 管理会话生命周期、事件、状态和输出 parts。
- DeepAgents 作为执行引擎，项目目录以虚拟 `/workspace/` 挂载。
- 支持人类审批门控：文件写入、工具调用或敏感动作可进入等待审批状态，再从后台恢复执行。
- 内置 Build、Explore、Review Agent manifest，可扩展自己的 Agent 定义。
- 工作区视图、终端事件、执行计划、Diff、子 Agent 状态和产物预览统一展示。

### 知识、上下文与记忆

- RAG 知识库：ChromaDB + sentence-transformers，支持文档解析、切片、检索和问答。
- 项目上下文：扫描本地项目结构，提取代码符号，构建上下文包。
- 记忆系统：短期、中期、长期记忆分层，为聊天和 Agent 任务提供背景。
- 文件解析：支持 PDF、DOCX、XLSX、OCR 等常见输入。

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | FastAPI、Python 3.11、Pydantic、SQLite、PyTorch、Transformers、PEFT |
| 前端 | React 18、TypeScript、Vite、Ant Design、Zustand、Framer Motion |
| Agent | DeepAgents、LangGraph、SSE、虚拟 workspace、HITL 审批 |
| RAG | ChromaDB、sentence-transformers、pdfplumber、python-docx、openpyxl |
| 部署 | Docker Compose、可选 Electron 桌面端、Ollama profile、GPU compose 覆盖 |

## 快速开始

### 环境要求

- Python 3.11.x
- Node.js 18+
- Git
- NVIDIA GPU + CUDA 环境，推荐用于训练和本地推理
- Docker Desktop，可选

显存参考：

| 显存 | 适合模型 | 建议方式 |
| --- | --- | --- |
| 4GB | 0.5B-1.5B INT4 | QLoRA，小 batch，短序列 |
| 6GB | 1.5B-3B INT4 | QLoRA |
| 8GB | 3B-7B INT4 | QLoRA 或轻量 LoRA |
| 12GB+ | 7B/13B | LoRA/QLoRA 更从容 |

### Windows 一键启动

在仓库根目录执行：

```bat
start.bat
```

脚本会检查 Python/Node 环境，安装必要依赖，并分别启动：

- 前端：http://127.0.0.1:5173
- 后端：http://127.0.0.1:8010
- Swagger：http://127.0.0.1:8010/docs
- 健康检查：http://127.0.0.1:8010/health

如果你需要先验证环境：

```bat
verify.bat
```

如果你使用 NVIDIA 显卡并希望安装 GPU 版 PyTorch：

```bat
install-pytorch-gpu.bat
```

### 手动启动

推荐使用 `uv` 管理后端依赖：

```bash
git clone https://github.com/lin09389/finetune-platform.git
cd finetune-platform
cp .env.example .env

uv sync
```

启动后端：

```bash
cd server
python -m uvicorn main:app --host 127.0.0.1 --port 8010 --reload
```

启动前端：

```bash
cd client
npm install
npm run dev
```

前端开发服务器默认固定在 `5173`，并直接访问 `http://127.0.0.1:8010`，不依赖 Vite proxy。

### Docker 启动

仅启动 API：

```bash
docker compose up -d api
```

启动开发栈：

```bash
docker compose --profile dev up -d
```

启动 Ollama：

```bash
docker compose --profile ollama up -d
```

使用 GPU 覆盖配置：

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

查看日志：

```bash
docker compose logs -f api
```

## 常用命令

### 后端

```bash
cd server
python -m uvicorn main:app --host 127.0.0.1 --port 8010 --reload
python -m pytest
python -m pytest -m "not integration and not e2e"
python -m pytest -m integration
python -m pytest --cov=server --cov-report=html
```

### 前端

```bash
cd client
npm run dev
npm run build
npm run typecheck
npm run lint
npm run test:smoke
npm run test:runtime
```

注意：`npm test` 是 Vitest watch 模式；CI 或一次性验证建议使用 `npx vitest run` 或上面的专项脚本。

### 依赖管理

```bash
uv sync --extra all --extra dev
uv lock
uv export --extra all --no-dev --no-hashes --format requirements-txt -o server/requirements.txt
uv export --extra agent --extra rag --extra cua --extra modelhub --extra model-ops --no-dev --no-hashes --format requirements-txt -o server/requirements-api.txt
uv export --extra training --extra gpu --no-dev --no-hashes --format requirements-txt -o server/requirements-training.txt
uv export --extra inference --no-dev --no-hashes --format requirements-txt -o server/requirements-inference.txt
```

`server/requirements*.txt` 由 `uv export` 生成，不建议手工编辑。依赖分组与镜像拆分见
`docs/dependency-profiles.md`。

## 主要页面

| 路由 | 页面 |
| --- | --- |
| `/agent` | Agent 工作台，默认入口 |
| `/dashboard` | 平台概览 |
| `/device` | 设备与显存监控 |
| `/models` | 本地模型管理 |
| `/datasets` | 数据集管理 |
| `/training` | 训练任务 |
| `/chat` | 纯聊天界面 |
| `/knowledge` | 知识库 |
| `/inference` | 推理测试 |
| `/evaluation` | 模型评估 |
| `/deployment` | 部署包 |
| `/workspace` | 工作区管理 |
| `/memory` | 记忆系统 |
| `/modelhub` | 模型中心 |
| `/project-context` | 项目上下文 |
| `/mcp`、`/gateway`、`/heartbeat`、`/cua-control` | 实验能力 |

## 关键 API

| API | 说明 |
| --- | --- |
| `GET /health` | 服务健康检查 |
| `GET /api/info` | API 元信息和能力分层 |
| `GET /device` | 设备信息 |
| `GET /models` | 模型管理 |
| `GET /datasets` | 数据集管理 |
| `POST /training/start` | 启动训练 |
| `GET /training/progress/stream` | 训练进度 SSE |
| `POST /inference/*` | 推理服务 |
| `GET /chat/sessions` | 聊天会话 |
| `POST /agent-sessions` | 创建 Agent Session |
| `POST /agent-sessions/{id}/prompt` | 向 Agent Session 发送任务 |
| `GET /agent-sessions/{id}/events/stream` | Agent 事件 SSE |
| `POST /agent-permissions/{permission_id}/approve` | 审批 Agent 权限请求 |
| `POST /agent-permissions/{permission_id}/reject` | 拒绝 Agent 权限请求 |

## 项目结构

```text
finetune-platform/
├── server/                 # FastAPI 后端
│   ├── api/                # 路由层
│   ├── agent_session/      # Agent Session 与 DeepAgents 运行时
│   ├── core/               # 配置、存储、训练状态、事件总线
│   ├── training_engine/    # 微调管线
│   ├── inference_service/  # 推理服务层
│   ├── rag/                # RAG 知识库
│   ├── memory/             # 记忆系统
│   ├── context/            # 项目上下文
│   ├── workspace/          # 文件和任务 API
│   └── tests/              # 后端正式测试
├── client/                 # React 前端
│   └── src/
│       ├── agent/          # Agent Workbench
│       ├── pages/          # 页面
│       ├── components/     # 通用组件
│       ├── services/       # API 客户端
│       └── test/           # Vitest 测试
├── electron/               # 可选桌面端封装
├── docs/                   # 设计、迁移、部署和能力文档
├── scripts/                # 工具脚本
├── models/                 # 本地模型目录
├── datasets/               # 数据集目录
├── outputs/                # 训练输出
└── workspaces/             # 运行时工作区数据
```

## 配置说明

复制 `.env.example` 到 `.env` 后按需修改。常见配置包括：

| 变量 | 用途 |
| --- | --- |
| `HOST`、`PORT` | 后端监听地址和端口 |
| `ALLOWED_ORIGINS` | CORS 白名单 |
| `INFERENCE_ENGINE` | 推理后端选择 |
| `OLLAMA_BASE_URL` | Ollama 服务地址 |
| `HF_MIRROR` | HuggingFace 镜像源 |
| `MAX_CONCURRENT_TRAINING` | 最大并发训练数 |
| `MAX_UPLOAD_SIZE` | 上传文件大小限制 |
| `ENABLE_AUTH`、`JWT_SECRET_KEY` | 可选认证配置 |
| `LOG_LEVEL`、`LOG_FORMAT` | 日志级别和格式 |

## 文档入口

- [AGENTS.md](AGENTS.md)：当前项目结构、开发命令和能力边界。
- [docs/agent_system_design.md](docs/agent_system_design.md)：Agent 系统设计。
- [docs/agent_session_migration.md](docs/agent_session_migration.md)：Agent Session 迁移记录。
- [docs/capability-truth-table.md](docs/capability-truth-table.md)：能力成熟度和依赖说明。
- [docs/local-inference-deployment.md](docs/local-inference-deployment.md)：本地推理部署说明。
- [docs/MCP_INTEGRATION.md](docs/MCP_INTEGRATION.md)：MCP 集成说明。
- [docs/CUA_USAGE.md](docs/CUA_USAGE.md)：CUA 使用说明。

## 开发约定

- 后端依赖事实源是根目录 `pyproject.toml` 和 `uv.lock`。
- 前端 API 地址默认是 `http://127.0.0.1:8010`。
- 正式后端测试主要位于 `server/tests/`，根目录零散脚本多为调试用途。
- 改动 GA 能力时应补充或更新回归测试。
- Experimental 能力可以快速迭代，但 README 和 `/api/info` 应保持诚实一致。

## 当前状态

项目处于活跃开发阶段。训练、推理、模型/数据集管理、知识库、聊天和 Agent Session 已形成主流程；CUA、MCP、Gateway、Heartbeat 等模块仍是实验区，更适合研究、扩展和二次开发。

## 致谢

本项目建立在 FastAPI、React、Ant Design、PyTorch、Transformers、PEFT、DeepAgents、LangGraph、ChromaDB、Ollama 等开源生态之上。
