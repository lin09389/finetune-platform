# Finetune Platform 2.0 - Code Wiki

> 企业级大模型微调平台代码百科
> 版本: 2.1.0 | 快照日期: 2026-05-10（**本文为代码导航快照，非运行时事实源**）

> ⚠️ **与 AGENTS.md 同步提示**：架构、开发命令、能力分层、技术栈的**权威描述以 `AGENTS.md`（2026-07-10 更新）为准**。本文档是代码导航地图，部分章节（架构图、运行方式）可能滞后于当前代码，请以 `AGENTS.md` 与代码为准。后端应用装配与能力边界以 `server/apps/routers.py`、`server/apps/capability_registry.py` 和 `GET /api/info` 为准。

---

## 目录

1. [项目概述](#1-项目概述)
2. [整体架构](#2-整体架构)
3. [技术栈](#3-技术栈)
4. [项目结构](#4-项目结构)
5. [后端模块详解](#5-后端模块详解)
6. [前端模块详解](#6-前端模块详解)
7. [关键类与函数](#7-关键类与函数)
8. [API 路由总览](#8-api-路由总览)
9. [依赖关系](#9-依赖关系)
10. [项目运行方式](#10-项目运行方式)
11. [配置说明](#11-配置说明)
12. [测试体系](#12-测试体系)
13. [部署方式](#13-部署方式)

---

## 1. 项目概述

Finetune Platform 2.0 是一款面向消费级显卡（4GB+ 显存）优化的企业级大模型微调平台。支持 LoRA/QLoRA 微调、模型管理、数据集处理、实时监控、推理服务及 Ollama 集成。

### 核心特性

- **低显存支持**: 针对 4GB+ GPU 优化，支持 INT4/QLoRA 量化
- **多推理引擎**: 支持 HuggingFace、vLLM、LlamaCPP、Ollama
- **Agent 工作流**: 多 Agent 编排、观测、审批门控动作执行
- **RAG 知识库**: 基于 ChromaDB 的向量检索
- **项目上下文理解**: 自动检测技术栈、索引代码符号
- **三层记忆系统**: 短期/中期/长期记忆
- **Gateway 统一入口**: WebSocket 控制平面、设备认证

---

## 2. 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端层 (Frontend)                         │
│  React 18 + TypeScript + Ant Design + Vite + Framer Motion     │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐  │
│  │ Dashboard│ │ Training│ │  Chat   │ │ ModelHub│ │Workflows│  │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │ HTTP / SSE / WS
┌─────────────────────────────────────────────────────────────────┐
│                        API 层 (FastAPI)                          │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐  │
│  │  Device │ │ Models  │ │Datasets │ │ Training│ │Inference│  │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘  │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐  │
│  │  Chat   │ │Workflows│ │  RAG    │ │ Context │ │ Gateway │  │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│                      核心服务层 (Core Services)                   │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌──────────┐ │
│  │TrainingState│ │TrainingQueue│ │ ModelCache  │ │DB Manager│ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └──────────┘ │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌──────────┐ │
│  │Agent Runtime│ │ Chat Agent  │ │   Memory    │ │  Skills  │ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └──────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│                      基础设施层 (Infrastructure)                  │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐  │
│  │ SQLite  │ │ChromaDB │ │  JSON   │ │  PyTorch│ │Transform│  │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 技术栈

### 后端

| 技术 | 版本 | 用途 |
|------|------|------|
| Python | >=3.10 | 运行时 |
| FastAPI | - | Web 框架 |
| PyTorch | - | 深度学习框架 |
| Transformers | - | 预训练模型 |
| PEFT | - | LoRA/QLoRA 微调 |
| Pydantic | v2 | 数据验证/配置 |
| SQLite | - | 应用状态持久化 |
| ChromaDB | - | 向量存储 |
| sentence-transformers | - | 文本嵌入 |

### 前端

| 技术 | 版本 | 用途 |
|------|------|------|
| React | 18 | UI 框架 |
| TypeScript | 5.3+ | 类型系统 |
| Vite | 5 | 构建工具 |
| Ant Design | 5.12+ | UI 组件库 |
| Framer Motion | 12.36+ | 动画库 |
| Zustand | 4.4+ | 状态管理 |
| Axios | 1.6+ | HTTP 客户端 |
| Recharts | 3.7+ | 图表库 |

---

## 4. 项目结构

```
finetune-platform/
├── server/                          # 后端服务
│   ├── main.py                      # FastAPI 应用入口
│   ├── api/                         # API 路由层
│   │   ├── training.py              # 训练控制 API
│   │   ├── inference.py             # 推理服务 API
│   │   ├── models.py                # 模型管理 API
│   │   ├── datasets.py              # 数据集管理 API
│   │   ├── device.py                # 设备信息 API
│   │   ├── chat/                    # 聊天会话 API
│   │   ├── workflows.py             # 工作流 API
│   │   ├── evaluation.py            # 评估任务 API
│   │   ├── deployment.py            # 部署包 API
│   │   ├── knowledge.py             # 知识库 API
│   │   ├── context.py               # 项目上下文 API
│   │   ├── memory_new.py            # 记忆系统 API
│   │   ├── gateway_api/             # Gateway API
│   │   └── ...                      # 其他路由
│   ├── core/                        # 核心模块
│   │   ├── config.py                # 配置管理 (Pydantic)
│   │   ├── training_state.py        # 线程安全训练状态
│   │   ├── training_queue.py        # 训练任务队列
│   │   ├── model_cache.py           # 模型缓存 (LRU)
│   │   ├── db_manager.py            # SQLite 连接池
│   │   ├── logging.py               # 结构化日志
│   │   └── ...                      # 其他核心模块
│   ├── agent_runtime/               # Agent 工作流运行时
│   │   ├── engine.py                # 工作流执行引擎
│   │   ├── runner.py                # Agent 执行适配
│   │   ├── service.py               # 工作流应用服务
│   │   ├── repository.py            # 工作流持久化
│   │   ├── actions.py               # 审批门控动作执行
│   │   ├── templates.py             # 内置工作流模板
│   │   ├── langgraph/               # LangGraph 工作流
│   │   └── ...                      # 其他运行时模块
│   ├── chat_agent/                  # Chat Agent 编排
│   │   ├── intent.py                # 意图分类
│   │   ├── service.py               # 编排服务
│   │   ├── models.py                # 数据模型
│   │   └── repository.py            # 运行持久化
│   ├── agent_session/               # Agent Session 管理
│   │   ├── langgraph/               # LangGraph 主路径
│   │   ├── service.py               # Session 服务
│   │   └── processor.py             # 请求处理器
│   ├── gateway/                     # Gateway 统一入口
│   │   ├── server.py                # WebSocket 服务器
│   │   ├── router.py                # 消息路由器
│   │   ├── session.py               # 会话管理
│   │   ├── binding.py               # Binding Router
│   │   └── device_auth.py           # 设备认证
│   ├── heartbeat/                   # 主动唤醒机制
│   │   └── task_executor.py         # 主动任务执行
│   ├── rag/                         # RAG 系统
│   │   ├── embedder.py              # 文本嵌入
│   │   ├── vector_store.py          # ChromaDB 集成
│   │   └── text_chunker.py          # 文本分块
│   ├── context/                     # 项目上下文理解
│   │   ├── project_scanner.py       # 技术栈检测
│   │   ├── code_indexer.py          # 向量索引
│   │   └── context_retriever.py     # 语义搜索
│   ├── memory/                      # 记忆系统
│   │   ├── operation_memory.py      # 操作记忆
│   │   └── preference_learner.py    # 偏好学习
│   ├── skills/                      # Skills 系统
│   │   ├── base.py                  # 技能基类
│   │   └── registry.py              # 技能注册表
│   ├── security/                    # 安全功能
│   │   ├── rate_limiter.py          # 速率限制
│   │   ├── jwt_auth.py              # JWT 认证
│   │   ├── sandbox.py               # 沙箱隔离
│   │   └── prompt_security.py       # Prompt 安全
│   └── tests/                       # 测试套件
│       ├── test_training.py
│       ├── test_workflow_observability_actions.py
│       ├── test_chat_agent.py
│       └── ...
│
├── client/                          # 前端应用
│   ├── src/
│   │   ├── App.tsx                  # 应用根组件
│   │   ├── main.tsx                 # 应用入口
│   │   ├── pages/                   # 页面组件
│   │   │   ├── Dashboard.tsx        # 概览仪表板
│   │   │   ├── Training/            # 训练界面
│   │   │   ├── ChatNew.tsx          # 新版对话界面
│   │   │   ├── Workflows.tsx        # 工作流观测
│   │   │   ├── ModelHub.tsx         # 模型中心
│   │   │   ├── Inference.tsx        # 推理测试
│   │   │   ├── Evaluation.tsx       # 模型评估
│   │   │   ├── KnowledgeBase.tsx    # 知识库
│   │   │   ├── WorkspaceManager.tsx # 工作区管理
│   │   │   └── ...                  # 其他页面
│   │   ├── components/              # 可复用组件
│   │   │   ├── Sidebar.tsx          # 导航侧边栏
│   │   │   ├── HeaderBar.tsx        # 顶部导航栏
│   │   │   ├── ChatMessage.tsx      # 聊天消息
│   │   │   ├── chat/                # Chat 相关组件
│   │   │   │   ├── AgentRunCard.tsx # Agent 运行卡片
│   │   │   │   ├── ChatInput.tsx    # 聊天输入
│   │   │   │   └── ...
│   │   │   ├── motion/              # 动效组件
│   │   │   └── shared/              # 共享组件
│   │   ├── services/                # API 服务层
│   │   │   ├── api.ts               # 核心 API 客户端
│   │   │   ├── trainingApi.ts       # 训练 API
│   │   │   └── chatSessionApi.ts    # 聊天会话 API
│   │   ├── store/                   # 状态管理
│   │   │   ├── appStore.ts          # Zustand 全局状态
│   │   │   └── chatStore.ts         # 聊天状态
│   │   ├── types/                   # TypeScript 类型
│   │   ├── hooks/                   # 自定义 Hooks
│   │   ├── theme/                   # 主题配置
│   │   └── test/                    # 前端测试
│   ├── package.json
│   └── vite.config.ts
│
├── docker-compose.yml               # Docker 编排
├── pyproject.toml                   # Python 项目配置
├── package.json                     # 根 package.json
└── README.md                        # 项目说明
```

---

## 5. 后端模块详解

### 5.1 应用入口 (main.py)

FastAPI 应用的主入口文件，负责：

- **应用生命周期管理**: 使用 `@asynccontextmanager` 管理启动/关闭
- **中间件链**: CORS、Trace、Security、Logging、Security Headers
- **路由注册**: 注册所有 API 路由模块
- **异常处理**: 自定义 APIError、HTTPException、通用异常处理
- **健康检查**: `/health` 端点返回服务状态

```python
app = FastAPI(
    title="Finetune Platform API",
    version="2.0.0",
    lifespan=lifespan,
    default_response_class=UnicodeJSONResponse,
)
```

### 5.2 配置管理 (core/config.py)

基于 Pydantic v2 的配置中心：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `host` / `port` | 服务绑定地址 | 127.0.0.1:8000 |
| `environment` | 运行环境 | development |
| `enable_auth` | JWT 认证开关 | True |
| `inference_engine` | 推理引擎 | huggingface |
| `max_concurrent_training` | 最大并发训练数 | 1 |
| `hf_mirror` | HuggingFace 镜像源 | hf-mirror |
| `ollama_base_url` | Ollama 服务地址 | http://localhost:11434 |

### 5.3 训练状态管理 (core/training_state.py)

**TrainingState** - 线程安全的训练状态管理器：

```python
class TrainingState:
    """训练状态管理器 - 线程安全版本"""
    
    # 核心特性
    - threading.Lock 保证线程安全
    - Queue + 后台工作线程处理状态更新
    - 原子写入历史记录文件
    - 定期清理已完成任务引用（防内存泄漏）
    
    # 关键方法
    - is_training() -> bool: 检查是否正在训练
    - request_stop(): 请求停止训练
    - get_progress() -> TrainingProgress: 获取当前进度
    - add_to_history(record): 添加历史记录
```

**TrainingProgress** - 训练进度数据模型：

| 字段 | 类型 | 说明 |
|------|------|------|
| epoch | int | 当前轮次 |
| step | int | 当前步数 |
| loss | float | 当前损失 |
| lr | float | 学习率 |
| vram_used | float | 显存使用 (GB) |
| eta | float | 预计剩余时间 |
| speed | float | 训练速度 (steps/sec) |

### 5.4 训练队列 (core/training_queue.py)

**TrainingQueue** - 优先级任务队列：

```python
class TrainingQueue:
    """训练任务队列管理器"""
    
    # 特性
    - PriorityQueue 优先级调度 (URGENT > HIGH > NORMAL > LOW)
    - 线程池实现真正的并发控制
    - 支持任务取消（队列中 + 运行中）
    - 状态文件原子写入
    
    # 关键方法
    - submit(task_id, config, callback, priority): 提交任务
    - cancel(task_id): 取消任务
    - get_queue_status(): 获取队列状态
```

### 5.5 Agent 工作流运行时 (agent_runtime/)

**核心组件**:

| 文件 | 职责 |
|------|------|
| `engine.py` | 工作流执行引擎，管理执行状态 |
| `runner.py` | Agent 执行适配器，调度任务 |
| `service.py` | 工作流应用服务，业务逻辑 |
| `repository.py` | 工作流持久化（SQLite） |
| `actions.py` | 审批门控动作执行（patch/command） |
| `templates.py` | 内置工作流模板 |
| `langgraph/` | LangGraph 工作流实现 |

**动作审批机制**:
- Agent 只能提出 `patch` / `command` action
- 必须先 `approve` 再 `execute`
- `patch` 写入校验目标路径必须位于工作区根内
- `command` 只允许白名单命令前缀

### 5.6 Chat Agent (chat_agent/)

| 文件 | 职责 |
|------|------|
| `intent.py` | 意图分类与触发判断 |
| `service.py` | Chat Agent 编排服务 |
| `models.py` | API 数据模型 |
| `repository.py` | 运行记录持久化 |

### 5.7 Gateway (gateway/)

借鉴 OpenClaw 的统一入口：

| 文件 | 职责 |
|------|------|
| `server.py` | WebSocket 控制平面服务器 |
| `router.py` | 消息路由和分发 |
| `session.py` | 会话管理 |
| `binding.py` | Binding Router（最具体匹配优先） |
| `device_auth.py` | 设备配对与认证 |
| `agent_isolation.py` | Agent 隔离管理 |

---

## 6. 前端模块详解

### 6.1 应用入口 (App.tsx)

React 应用根组件：

- **路由管理**: React Router v6，支持 20+ 页面路由
- **懒加载**: 所有页面使用 `React.lazy` 按需加载
- **主题系统**: 支持 Light/Dark 模式，基于 Ant Design ConfigProvider
- **健康检查**: 自动检测后端连接状态
- **响应式**: 适配桌面端和移动端

```typescript
// 核心路由
const routes = [
  { path: '/dashboard', element: <Dashboard /> },
  { path: '/training', element: <Training /> },
  { path: '/chat', element: <Chat /> },
  { path: '/workflows', element: <Workflows /> },
  { path: '/modelhub', element: <ModelHub /> },
  { path: '/inference', element: <Inference /> },
  { path: '/evaluation', element: <Evaluation /> },
  // ... 更多路由
];
```

### 6.2 API 服务层 (services/api.ts)

Axios 封装的 API 客户端：

- **连接池管理**: `ConnectionPool` 管理请求生命周期
- **自动重试**: 指数退避 + 抖动重试策略
- **请求取消**: 支持按 key 或 type 批量取消
- **健康检查**: WebSocket 优先，降级 HTTP 轮询

```typescript
class ConnectionPool {
  acquire(key: string, requestType: string): AbortController
  abortByType(requestType: string): void
  abortAll(): void
}
```

### 6.3 状态管理 (store/appStore.ts)

Zustand 全局状态：

```typescript
interface AppState {
  backendUrl: string;
  backendStatus: 'connected' | 'disconnected';
  sidebarCollapsed: boolean;
  theme: 'light' | 'dark';
  // ...
}
```

### 6.4 页面组件

| 页面 | 文件 | 说明 |
|------|------|------|
| 仪表板 | `pages/Dashboard.tsx` | 系统概览、GPU 监控 |
| 训练 | `pages/Training/index.tsx` | LoRA/QLoRA 微调 |
| 对话 | `pages/ChatNew.tsx` | 流式对话、Agent 卡片 |
| 工作流 | `pages/Workflows.tsx` | 多 Agent 观测与审批 |
| 模型中心 | `pages/ModelHub.tsx` | ModelScope/HF 模型下载 |
| 推理 | `pages/Inference.tsx` | 推理测试 |
| 评估 | `pages/Evaluation.tsx` | 模型评估与人工评分 |
| 知识库 | `pages/KnowledgeBase.tsx` | RAG 知识库管理 |
| 工作区 | `pages/WorkspaceManager.tsx` | 文件管理 |

---

## 7. 关键类与函数

### 7.1 后端核心类

#### TrainingState

```python
class TrainingState:
    """线程安全训练状态管理器"""
    
    def __init__(self, history_file: Path)
    def is_training(self) -> bool
    def request_stop(self) -> None
    def should_stop(self) -> bool
    def get_progress(self) -> TrainingProgress
    def get_current_record(self) -> TrainingRecord | None
    def add_to_history(self, record: TrainingRecord) -> None
    def get_history(self) -> list[TrainingRecord]
    def get_status(self) -> dict[str, Any]
    def cleanup(self) -> None
```

#### TrainingQueue

```python
class TrainingQueue:
    """优先级训练任务队列"""
    
    def __init__(self, max_concurrent: int, max_queue_size: int)
    def start(self) -> None
    def stop(self) -> None
    def submit(self, task_id, config, callback, priority) -> bool
    def cancel(self, task_id: str) -> bool
    def get_queue_status(self) -> dict[str, Any]
    def get_task_status(self, task_id: str) -> dict | None
```

#### Settings (Pydantic)

```python
class Settings(BaseSettings):
    """应用配置"""
    
    host: str = "127.0.0.1"
    port: int = 8000
    environment: Literal["development", "staging", "production"]
    enable_auth: bool = True
    jwt_secret_key: str | None = None
    inference_engine: Literal["huggingface", "vllm", "llamacpp", "ollama"]
    max_concurrent_training: int = 1
    enable_checkpoint: bool = True
    checkpoint_interval: int = 500
    
    @property
    def models_dir_resolved(self) -> Path
    @property
    def hf_endpoint(self) -> str
```

### 7.2 前端核心函数

#### API 客户端

```typescript
// services/api.ts
export const API_BASE_URL: string;

export async function fetchWithRetry<T>(
  fetchFn: () => Promise<T>,
  config?: Partial<RetryConfig>
): Promise<T>;

export function checkBackendHealth(): Promise<boolean>;
export function startHealthCheck(callback: (isHealthy: boolean) => void): () => void;
```

---

## 8. API 路由总览

### 8.1 核心 API (GA)

| 路由 | 前缀 | 说明 |
|------|------|------|
| Device | `/device` | GPU/CPU/内存信息 |
| Models | `/models` | 模型下载/删除/导出 |
| Datasets | `/datasets` | 数据集上传/验证/统计 |
| Training | `/training` | 训练启动/停止/进度/恢复 |
| Inference | `/inference` | 推理生成/对话/流式 |
| Chat | `/chat/sessions` | 会话管理/消息 |
| Knowledge | `/knowledge` | 知识库上传/查询 |

### 8.2 Beta API

| 路由 | 前缀 | 说明 |
|------|------|------|
| Workflows | `/workflows` | 多 Agent 工作流 |
| Context | `/context` | 项目上下文扫描/检索 |
| Memory | `/memory` | 记忆系统 |
| Model Center | `/model-center` | 模型中心 |
| Workspace | `/workspace` | 工作区管理 |

### 8.3 Experimental API

| 路由 | 前缀 | 说明 |
|------|------|------|
| CUA | `/cua` | Computer User Agent |
| Gateway | `/gateway` | Gateway 统一入口 |
| Heartbeat | `/heartbeat` | 主动唤醒 |
| MCP | `/mcp` | Model Control Protocol |

### 8.4 关键端点详情

```
# 训练
POST   /training/start              # 启动训练
POST   /training/stop               # 停止训练
GET    /training/progress/stream    # SSE 进度流
POST   /training/resume/{id}/{ckpt} # 恢复训练
GET    /training/history            # 训练历史

# 推理
POST   /inference/chat              # 对话推理
POST   /inference/stream            # 流式推理
POST   /inference/merge             # 模型合并

# 工作流
GET    /workflows                   # 工作流列表
POST   /workflows                   # 创建工作流
GET    /workflows/{id}/observability # 工作流观测
GET    /workflows/{id}/events/stream # SSE 事件流
POST   /workflow-actions/{id}/approve # 审批动作

# Chat Agent
POST   /chat-agent/runs             # 创建 Agent Run
GET    /chat-agent/runs/{id}/events/stream # 事件流

# 评估
POST   /evaluation/runs             # 创建评估任务
GET    /evaluation/runs/{id}        # 获取评估状态
POST   /evaluation/runs/{id}/score  # 人工评分
```

---

## 9. 依赖关系

### 9.1 后端依赖

```python
# pyproject.toml
[project]
dependencies = [
    "ast-grep-cli>=0.42.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-cov>=4.0.0",
    "pytest-asyncio>=0.21.0",
    "ruff>=0.1.0",
    "mypy>=1.0.0",
    "black>=23.0.0",
    "playwright>=1.40.0",
    "safety>=2.0.0",
]
```

**运行时依赖** (通过 requirements 或 pip 安装):
- fastapi, uvicorn
- torch, transformers, peft, accelerate
- chromadb, sentence-transformers
- pydantic, pydantic-settings
- aiohttp, websockets
- numpy, pandas, matplotlib

### 9.2 前端依赖

```json
// client/package.json
"dependencies": {
  "react": "^18.2.0",
  "react-dom": "^18.2.0",
  "react-router-dom": "^6.21.0",
  "antd": "^5.12.0",
  "axios": "^1.6.2",
  "framer-motion": "^12.36.0",
  "zustand": "^4.4.7",
  "recharts": "^3.7.0",
  "react-markdown": "^10.1.0",
  "@monaco-editor/react": "^4.7.0"
}
```

---

## 10. 项目运行方式

### 10.1 开发模式

```bash
# 后端
cd server
python -m uvicorn main:app --host 127.0.0.1 --port 8010 --reload

# 前端
cd client
npm install
npm run dev
```

### 10.2 生产构建

```bash
# 前端构建
cd client
npm run build

# 后端运行
cd server
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

### 10.3 Docker 部署

```bash
# 仅启动 API
docker compose up -d api

# 启动完整栈（含前端）
docker compose --profile dev up -d

# 启动 Ollama
docker compose --profile ollama up -d
```

### 10.4 Windows 快速启动

```bash
# 安装依赖
install.bat

# 同时启动前后端
start.bat

# 或分别启动
start-backend.bat
start-frontend.bat
```

---

## 11. 配置说明

### 11.1 环境变量 (.env)

```bash
# 服务器配置
HOST=127.0.0.1
PORT=8010

# CORS 配置
ALLOWED_ORIGINS=*

# Ollama 配置
OLLAMA_BASE_URL=http://localhost:11434
INFERENCE_BACKEND=huggingface

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
ALLOWED_FILE_TYPES=.json,.jsonl

# 日志配置
LOG_LEVEL=INFO
LOG_FORMAT=text  # 或 json
```

### 11.2 前端环境变量

```bash
# client/.env
VITE_API_URL=http://localhost:8010
```

---

## 12. 测试体系

### 12.1 后端测试

```bash
# 运行所有测试
pytest -v

# 覆盖率报告
pytest --cov=server --cov-report=html

# 单个测试文件
pytest server/tests/test_training.py -v
pytest server/tests/test_workflow_observability_actions.py -v
pytest server/tests/test_chat_agent.py -v
```

**测试文件列表**:
- `test_device.py` - 设备信息端点
- `test_models.py` - 模型管理
- `test_datasets.py` - 数据集操作
- `test_training.py` - 训练生命周期
- `test_workflow_observability_actions.py` - 工作流观测与动作审批
- `test_chat_agent.py` - Chat Agent 触发与事件流
- `test_evaluation_deployment.py` - 评估与部署

### 12.2 前端测试

```bash
cd client

# 运行测试
npm test

# UI 模式
npm run test:ui

# 覆盖率
npm run test:coverage

# Smoke 测试
npm run test:smoke

# 类型检查
npm run typecheck

# 代码检查
npm run lint
```

---

## 13. 部署方式

### 13.1 Docker Compose 服务

| 服务 | 说明 | 端口 |
|------|------|------|
| `api` | FastAPI 后端 | 8000 |
| `frontend` | Nginx 前端 | 5173 |
| `frontend-dev` | Vite 开发服务器 | 5173 |
| `ollama` | Ollama 推理服务 | 11434 |

### 13.2 Dockerfile 要点

- 后端基于 Python 3.10+ 镜像
- 前端基于 Node 20 构建，Nginx 托管
- 支持多阶段构建优化镜像大小
- 健康检查配置

---

## 附录: 核心设计模式

### 1. 线程安全训练状态
- `TrainingState` 使用 `threading.Lock` + 后台工作线程
- 基于队列的状态更新，避免 `asyncio.new_event_loop()` 开销

### 2. 训练队列系统
- `TrainingQueue` 管理并发训练任务
- 基于优先级的调度（URGENT/HIGH/NORMAL/LOW）
- 完成/失败时自动清理资源

### 3. 模型缓存
- `ModelCache` 减少重复加载模型
- LRU 淘汰策略
- 自动 GPU 内存管理

### 4. SSE 进度流式传输
- 训练进度使用 Server-Sent Events
- 实时更新，无 WebSocket 开销
- 端点: `GET /training/progress/stream`

### 5. 检查点恢复
- 训练支持从检查点恢复
- 端点: `POST /training/resume/{task_id}/{checkpoint}`
- 每 N 步保存检查点（可配置）

### 6. 审批门控动作执行
- Agent 只能提出 `patch` / `command` action
- 必须先 `approve` 再 `execute`
- patch 校验目标路径在工作区内
- command 只允许白名单前缀

### 7. 异步评估任务
- `POST /evaluation/runs` 立即返回 pending run
- 后台执行真实推理/指标计算
- 前端轮询状态
- 人工评分通过 `POST /evaluation/runs/{run_id}/score`

---

> 本文档基于代码分析自动生成，如有更新请以实际代码为准。
