# Finetune Platform 2.0

大模型微调平台 - 消费级显卡专用 · 企业级增强版

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18+-61dafb.svg)](https://reactjs.org)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 🌟 特性亮点

## Capability Tiers

Finetune Platform does not treat every visible page as equally mature. Current product copy, navigation, and API metadata follow three tiers:

- `GA`：训练、推理、模型管理、数据集、Chat Session、基础知识库。这些是当前的核心可交付能力。
- `Beta`：项目上下文、智能记忆、模型中心、工作空间。可试用，但仍依赖环境和持续 UX 收口。
- `Experimental`：CUA、Action Recorder、MCP、Heartbeat、Gateway 扩展链路。仅用于受控验证，页面可打开不代表能力已稳定可用。

Experimental 模块会在页面内显示实时状态、依赖要求和受限原因；如果你要评估平台主能力，请优先以 `GA` 路径为准。

### 核心功能
- 🎯 **低显存优化**：支持 4GB 显存微调（INT4 + QLoRA）
- 🔧 **多种微调方式**：LoRA / QLoRA 主线支持，SWIFT 为实验性后端
- 📦 **模型管理**：HuggingFace 模型下载、ONNX 导出
- 📊 **数据集管理**：上传、验证、统计分析
- 📈 **实时监控**：训练过程可视化、SSE 流式进度
- 🤖 **推理服务**：内置推理、Ollama 集成、流式输出
- ♻️ **断点续训**：支持从检查点恢复训练

### 新增增强（v2.0）
- ✅ **线程安全**：异步状态管理，支持并发任务
- 🔒 **安全加固**：文件上传校验、路径遍历防护、速率限制
- 📝 **结构化日志**：JSON 格式日志，便于分析
- ⚙️ **配置管理**：pydantic-settings 集中配置
- 🧪 **测试覆盖**：pytest + vitest 完整测试套件
- 🐳 **Docker 支持**：一键部署，GPU 加速
- 📖 **完善文档**：API 指南、部署文档

## 🏗️ 技术架构

```
┌─────────────────────────────────────────────────────────────┐
│                      Finetune Platform                       │
├─────────────────────────────────────────────────────────────┤
│  Frontend (React 18 + TypeScript + Ant Design)              │
│  ┌─────────────┬─────────────┬─────────────┬─────────────┐ │
│  │  设备检测   │  模型管理   │  数据集     │  训练监控   │ │
│  └─────────────┴─────────────┴─────────────┴─────────────┘ │
│                          │                                   │
│                    HTTP / SSE                                │
├──────────────────────────┼───────────────────────────────────┤
│  Backend (FastAPI + Python)                                  │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  API Layer (RESTful Endpoints)                          │ │
│  ├─────────────────────────────────────────────────────────┤ │
│  │  Core Module                                             │ │
│  │  ┌─────────────┬─────────────┬─────────────┐            │ │
│  │  │  Config     │  Logging    │  State Mgr  │            │ │
│  │  └─────────────┴─────────────┴─────────────┘            │ │
│  ├─────────────────────────────────────────────────────────┤ │
│  │  ML Backends                                             │ │
│  │  ┌─────────────────┬─────────────────┬─────────────────┐│ │
│  │  │  PyTorch/CUDA   │  Transformers   │  PEFT/LoRA      ││ │
│  │  └─────────────────┴─────────────────┴─────────────────┘│ │
│  └─────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│  Storage                                                     │
│  ┌─────────────┬─────────────┬─────────────┬─────────────┐ │
│  │  models/    │  datasets/  │  outputs/   │  logs/      │ │
│  └─────────────┴─────────────┴─────────────┴─────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

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
git clone https://github.com/your-org/finetune-platform.git
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
PORT=8000

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
python -m uvicorn main:app --host 127.0.0.1 --port 8000

# 终端 2 - 启动前端
cd client
npm run dev
```

#### 4. 访问应用

- 前端：http://localhost:5173
- API 文档：http://localhost:8000/docs

### 方法二：Docker 部署

```bash
# 启动 API 服务
docker compose up -d api

# 启动完整栈（包含前端）
docker compose --profile dev up -d

# 查看日志
docker compose logs -f api
```

详细 Docker 配置见 [DOCKER.md](DOCKER.md)

### 训练监测 V2 联调验收（API 直连）

用于验证训练监测链路（`SSE 主通道 + WS 备通道 + V2 事件协议`）是否可用。

```bash
# 1) 启动后端（若尚未启动）
cd server
python -m uvicorn main:app --host 127.0.0.1 --port 8000

# 2) 在仓库根目录执行联调脚本
cd ..
python scripts/validate_training_v2_flow.py --base-url http://127.0.0.1:8000 --auto-stop-after 45
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
| [API 指南](API_GUIDE.md) | API 端点、使用示例、Python SDK |
| [Docker 部署](DOCKER.md) | 容器化部署、GPU 配置 |
| [启动说明](启动说明.txt) | Windows 快速启动指南 |
| [能力真值表](docs/capability-truth-table.md) | 功能成熟度、依赖、失败模式、回归覆盖 |

## 📁 项目结构

```
finetune-platform/
├── server/                     # 后端服务
│   ├── api/                    # API 路由
│   │   ├── device.py           # 设备管理
│   │   ├── models.py           # 模型管理
│   │   ├── datasets.py         # 数据集管理
│   │   ├── training.py         # 训练管理
│   │   └── inference.py        # 推理服务
│   ├── core/                   # 核心模块
│   │   ├── config.py           # 配置管理
│   │   ├── logging.py          # 日志配置
│   │   ├── training_state.py   # 训练状态（线程安全）
│   │   └── utils.py            # 工具函数
│   ├── tests/                  # 测试套件
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

### 推理服务
- `POST /inference/generate` - 文本生成
- `POST /inference/chat` - 聊天对话
- `POST /inference/stream` - 流式输出
- `GET /inference/backends` - 后端列表
- `POST /inference/merge` - 合并 LoRA

> 说明：`/chat` 旧兼容路由与 `GET /training` 根别名已移除，请使用上面的 canonical 路径。

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
| `PORT` | 服务端口 | `8000` |
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
