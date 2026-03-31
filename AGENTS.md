# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## 项目概述

Finetune Platform 2.0 - 企业级大模型微调平台，专为消费级显卡优化（4GB+ 显存）。支持 LoRA/QLoRA 微调、模型管理、数据集处理、实时监控、推理服务及 Ollama 集成。

**技术栈：**
- 后端：FastAPI + Python 3.10+（PyTorch、Transformers、PEFT）
- 前端：React 18 + TypeScript + Ant Design + Vite
- 桌面端：Electron（可选）
- 存储：ChromaDB（向量存储）、JSON（训练历史）
- 部署：Docker + Docker Compose

## 开发命令

### 后端

```bash
# 启动后端服务
cd server
python -m uvicorn main:app --host 127.0.0.1 --port 8000

# 开发模式（自动重载）
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload

# 运行测试
pytest
pytest --cov=server --cov-report=html

# 运行单个测试
pytest server/tests/test_training.py -v
pytest server/tests/test_training.py::test_start_training -v
```

### 前端

```bash
# 启动开发服务器
cd client
npm run dev

# 生产构建
npm run build

# 运行测试
npm test
npm run test:ui
npm run test:coverage

# 类型检查
npm run typecheck

# 代码检查
npm run lint

# 代码格式化
npm run format
```

### Docker

```bash
# 仅启动 API
docker compose up -d api

# 启动完整栈（含前端）
docker compose --profile dev up -d

# 启动 Ollama
docker compose --profile ollama up -d

# 查看日志
docker compose logs -f api

# 重新构建
docker compose build --no-cache
```

### Windows 快速启动

```bash
# 安装依赖
install.bat

# 同时启动前后端
start.bat

# 或分别启动
start-backend.bat
start-frontend.bat

# 验证安装
verify.bat
```

## 架构设计

### 后端结构

```
server/
├── api/                    # API 端点（RESTful 路由）
│   ├── device.py          # 设备信息（GPU/CPU/内存）
│   ├── models.py          # 模型管理（下载/删除/导出）
│   ├── datasets.py        # 数据集管理（上传/验证/统计）
│   ├── training.py        # 训练控制（启动/停止/恢复）
│   ├── inference.py       # 推理服务（生成/对话/流式）
│   ├── chat_history.py    # 对话历史管理
│   ├── rag.py             # RAG 知识库
│   ├── context.py         # 项目上下文理解
│   ├── memory.py          # 智能记忆
│   ├── agent.py           # Agent 操作
│   ├── cloud_chat.py      # 云端 AI 集成
│   └── gateway/           # Gateway API 路由
│       └── routes.py      # 设备认证、消息路由端点
├── gateway/               # Gateway 统一入口（借鉴 OpenClaw）
│   ├── server.py          # WebSocket 服务器
│   ├── router.py          # 消息路由器
│   ├── session.py         # 会话管理
│   ├── binding.py         # Binding Router（最具体匹配优先）
│   ├── agent_isolation.py # Agent 隔离管理
│   ├── device_auth.py     # 设备认证管理
│   ├── cross_agent.py     # 跨 Agent 通信
│   └── models.py          # Gateway 数据模型
├── heartbeat/             # Heartbeat 主动唤醒（借鉴 OpenClaw）
│   ├── __init__.py        # Heartbeat 调度器
│   └── task_executor.py   # 主动任务执行器
├── core/                   # 核心模块
│   ├── config.py          # Pydantic 配置（环境变量、路径）
│   ├── logging.py         # 结构化日志（JSON/文本）
│   ├── training_state.py  # 线程安全训练状态管理器
│   ├── training_queue.py  # 训练任务队列（最大并发数）
│   ├── model_cache.py     # 模型缓存（减少重复加载）
│   ├── db_manager.py      # 数据库管理
│   ├── utils.py           # 工具函数（显存、清理、验证）
│   ├── quantization.py    # 量化模型支持（GPTQ/AWQ/GGUF）
│   ├── batching.py        # 动态批处理
│   ├── kv_cache.py        # KV Cache 优化
│   └── user_experience.py # 用户体验优化
├── memory/                # 三层记忆系统
│   ├── operation_memory.py # 操作记忆管理
│   └── preference_learner.py # 用户偏好学习
├── skills/                # Skills 系统
│   ├── memory_aware_skill.py # 记忆感知技能基类
│   └── skill_learner.py   # 技能学习与优化
├── context/               # 项目上下文理解
│   ├── project_scanner.py # 技术栈检测
│   ├── symbol_extractor.py# 代码符号提取
│   ├── code_indexer.py    # 向量索引
│   └── context_retriever.py# 语义搜索
├── rag/                   # RAG 系统
│   ├── embedder.py        # 文本嵌入（sentence-transformers）
│   ├── vector_store.py    # ChromaDB 集成
│   ├── document_parser.py # 文档解析
│   └── text_chunker.py    # 文本分块
├── security/              # 安全功能
│   ├── rate_limiter.py    # 速率限制
│   ├── file_sandbox.py    # 文件上传验证
│   ├── middleware.py      # 安全中间件
│   ├── sandbox.py         # 沙箱隔离
│   ├── prompt_security.py # Prompt 安全
│   └── audit_log.py       # 审计日志
└── main.py                # 应用入口
```

### 前端结构

```
client/src/
├── pages/                 # 页面组件
│   ├── Dashboard.tsx      # 概览仪表板
│   ├── DeviceInfo.tsx     # 设备监控
│   ├── ModelManager.tsx   # 模型管理
│   ├── DatasetManager.tsx # 数据集管理
│   ├── Training.tsx       # 训练界面
│   ├── Chat.tsx           # 对话界面
│   ├── Inference.tsx      # 推理测试
│   ├── KnowledgeBase.tsx  # RAG 知识库
│   ├── ProjectContext.tsx # 项目上下文
│   └── History.tsx        # 训练历史
├── components/            # 可复用组件
│   ├── Sidebar.tsx        # 导航侧边栏
│   ├── HeaderBar.tsx      # 顶部导航栏
│   ├── ChatMessage.tsx    # 聊天消息显示
│   ├── CodePreview.tsx    # 代码高亮
│   └── TrainingChart.tsx  # 训练指标图表
├── services/
│   └── api.ts             # Axios API 客户端
├── store/
│   └── appStore.ts        # Zustand 状态管理
└── types/                 # TypeScript 类型定义
```

### 核心设计模式

**1. 线程安全训练状态**
- `TrainingState` 使用 `asyncio.Lock` + 后台工作线程
- 基于队列的状态更新，避免 `asyncio.new_event_loop()` 开销
- 所有训练操作均为非阻塞

**2. 训练队列系统**
- `TrainingQueue` 管理并发训练任务
- 基于优先级的调度（HIGH/NORMAL/LOW）
- 完成/失败时自动清理资源

**3. 模型缓存**
- `ModelCache` 减少重复加载模型
- LRU 淘汰策略
- 自动 GPU 内存管理

**4. SSE 进度流式传输**
- 训练进度使用 Server-Sent Events（SSE）
- 实时更新，无 WebSocket 开销
- 端点：`GET /training/progress/stream`

**5. 检查点恢复**
- 训练支持从检查点恢复
- 端点：`POST /training/resume/{task_id}/{checkpoint}`
- 每 N 步保存检查点（可配置）

**6. Gateway 统一入口（借鉴 OpenClaw）**
- WebSocket 控制平面
- 消息路由和分发
- 设备配对与认证
- 事件广播机制

**7. Binding Router（最具体匹配优先）**
- 支持 peer/guild/channel/team/account 多维度绑定
- 绑定优先级排序算法
- 动态规则管理

**8. Agent 隔离管理**
- 独立 workspace/session/skills 管理
- 能力权限检查
- 路径访问控制

**9. Heartbeat 主动唤醒**
- 定期唤醒 Agent
- 检查/汇报/提醒任务执行
- 避免 CPU 空转轮询

**10. 三层记忆系统**
- 短期记忆（Attention Context）
- 中期记忆（Episodic Memory）
- 长期记忆（Semantic Memory）

## 配置说明

环境变量（`.env` 文件）：

```bash
# 服务器配置
HOST=127.0.0.1
PORT=8000

# CORS 配置
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# Ollama 配置
OLLAMA_BASE_URL=http://localhost:11434
INFERENCE_BACKEND=huggingface  # 或 "ollama"

# HuggingFace 镜像源
HF_MIRROR=hf-mirror  # official/hf-mirror/aliyun/modelscope

# 代理配置（可选）
HTTP_PROXY=http://127.0.0.1:7890
HTTPS_PROXY=http://127.0.0.1:7890

# 训练配置
MAX_CONCURRENT_TRAINING=1
ENABLE_CHECKPOINT=true
CHECKPOINT_INTERVAL=500

# 安全配置
RATE_LIMIT=100
RATE_WINDOW=60
MAX_UPLOAD_SIZE=104857600

# 日志配置
LOG_LEVEL=INFO
LOG_FORMAT=text  # 或 "json"
```

## 重要实现细节

### 训练流程

1. **启动训练**（`POST /training/start`）
   - 验证模型/数据集是否存在
   - 检查 GPU 内存可用性
   - 将任务加入 `TrainingQueue`
   - 立即返回 `task_id`

2. **监控进度**（`GET /training/progress/stream`）
   - SSE 端点流式传输进度更新
   - 更新包括：epoch、step、loss、lr、VRAM、ETA
   - 前端使用 `EventSource` 消费

3. **停止训练**（`POST /training/stop`）
   - 优雅停止训练线程
   - 如启用则保存检查点
   - 清理 GPU 内存

4. **恢复训练**（`POST /training/resume/{task_id}/{checkpoint}`）
   - 加载检查点状态
   - 从保存的步骤继续
   - 保留优化器状态

### RAG 系统

- **嵌入器**：使用 `sentence-transformers`（text2vec-base-chinese）
- **向量存储**：ChromaDB 持久化存储
- **分块**：递归字符分割器（chunk_size=500，overlap=50）
- **检索**：语义搜索，返回 top-k 结果

### 项目上下文理解

- **扫描器**：检测技术栈（Python/JS 框架、UI 库）
- **索引器**：提取代码符号（类、函数、组件）
- **检索器**：代码库语义搜索
- **集成**：自动注入上下文到聊天提示词

### 安全特性

- **速率限制**：内存存储 + 滑动窗口
- **文件上传验证**：类型检查、大小限制、内容验证
- **路径遍历防护**：严格路径验证
- **CORS**：可配置允许来源

## 测试

### 后端测试

位于 `server/tests/`：
- `test_device.py` - 设备信息端点
- `test_models.py` - 模型管理
- `test_datasets.py` - 数据集操作
- `test_training.py` - 训练生命周期
- `test_inference.py` - 推理端点

运行：`pytest -v`

### 前端测试

位于 `client/src/test/`：
- 使用 Vitest + React Testing Library
- 运行：`npm test`

## 常见问题

**1. CUDA 内存不足**
- 减少 `per_device_train_batch_size`
- 启用梯度检查点
- 对大模型使用 INT4 量化

**2. 模型下载失败**
- 检查 `HF_MIRROR` 设置
- 验证代理配置
- 确保磁盘空间充足

**3. 训练卡住**
- 检查 `logs/` 目录中的错误
- 验证 GPU 未被其他进程占用
- 重启后端清除状态

**4. 前端无法连接**
- 确保后端在正确端口运行
- 检查 `.env` 中的 CORS 设置
- 验证防火墙规则

## API 文档

完整 API 文档：`http://localhost:8000/docs`（Swagger UI）

主要端点：
- 设备：`/device/info`、`/device/vram`
- 模型：`/models`、`/models/download`、`/models/{id}`
- 数据集：`/datasets`、`/datasets/upload`、`/datasets/{id}/statistics`
- 训练：`/training/start`、`/training/stop`、`/training/progress/stream`
- 推理：`/inference/chat`、`/inference/stream`、`/inference/merge`
- RAG：`/rag/upload`、`/rag/query`
- 上下文：`/context/scan`、`/context/index`、`/context/retrieve`
- Gateway：`/gateway/status`、`/gateway/devices`、`/gateway/messages`、`/gateway/bindings`、`/gateway/ws`
- 性能监控：`/inference/performance`、`/inference/optimize`

## 项目特性

- **中文支持**：UI 和日志支持中文（zh_CN）
- **Windows 优化**：批处理脚本便于设置
- **低显存支持**：针对 4GB+ GPU 优化，支持 INT4/QLoRA
- **Electron 桌面端**：可选桌面应用封装
- **云端 AI 集成**：支持外部 AI API（OpenAI、Anthropic 等）
