# AI 对话模块架构重构计划

## 一、当前架构分析

### 1.1 模块清单与职责

| 模块文件                 | 路由前缀              | 主要职责                       | 代码行数    |
| -------------------- | ----------------- | -------------------------- | ------- |
| `inference.py`       | `/inference`      | 核心推理服务（HuggingFace/Ollama） | \~1380行 |
| `chat_history.py`    | `/chat`           | 对话历史持久化存储（SQLite）          | \~200行  |
| `session.py`         | `/sessions`       | 会话元数据管理                    | \~300行  |
| `dialog_context.py`  | `/dialog-context` | 对话上下文窗口管理、压缩               | \~250行  |
| `rag.py`             | `/rag`            | RAG 知识库管理、检索、评估            | \~500行  |
| `knowledge_base.py`  | `/knowledge-base` | 知识库统一接口（与 rag.py 重叠）       | \~400行  |
| `context.py`         | `/context`        | 项目上下文扫描、索引、检索              | \~300行  |
| `memory.py`          | `/memory`         | 基础记忆服务                     | \~350行  |
| `enhanced_memory.py` | `/memory/v2`      | 增强记忆系统（三级架构、知识图谱）          | \~580行  |
| `agent.py`           | `/agent`          | Agent 操作执行、意图识别            | \~400行  |
| `cloud_chat.py`      | `/cloud`          | 云端 AI 集成（Minimax/GLM）      | \~300行  |

### 1.2 数据流向图

```
用户请求
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│                      API 路由层                                  │
│  inference.py (核心) ←→ rag.py / knowledge_base.py (知识检索)   │
│         ↓                    ↓                                   │
│  context.py (项目上下文) ←→ memory.py / enhanced_memory.py      │
│         ↓                    ↓                                   │
│  session.py (会话) ←→ dialog_context.py (上下文压缩)            │
│         ↓                    ↓                                   │
│  agent.py (意图) ←→ cloud_chat.py (云端)                        │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│                      服务层                                      │
│  context/knowledge_integration.py - 知识集成                     │
│  context/service.py - 项目上下文服务                             │
│  memory/memory_service.py - 记忆服务                             │
│  memory/enhanced_memory_service.py - 增强记忆服务                │
│  rag/service.py - RAG 服务                                       │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│                      基础设施层                                  │
│  rag/embedder.py - 文本嵌入                                      │
│  rag/vector_store.py - ChromaDB 向量存储                         │
│  rag/hybrid_retriever.py - 混合检索                              │
│  memory/knowledge_graph.py - 知识图谱                            │
│  memory/short_term_memory.py - 短期记忆                          │
│  core/model_cache.py - 模型 LRU 缓存                             │
└─────────────────────────────────────────────────────────────────┘
```

### 1.3 核心问题识别

#### 问题 1：模块职责重叠严重

| 重叠模块                                                     | 重叠功能          | 影响           |
| -------------------------------------------------------- | ------------- | ------------ |
| `rag.py` vs `knowledge_base.py`                          | 文档上传、检索、统计、监控 | 维护困难、API 不一致 |
| `chat_history.py` vs `session.py` vs `dialog_context.py` | 会话管理、消息存储     | 数据不同步、状态混乱   |
| `memory.py` vs `enhanced_memory.py`                      | 记忆提取、存储、检索    | API 不兼容、功能分散 |

#### 问题 2：状态管理分散

```
全局状态分布：
├── inference.py: _model_cache, lora_adapter_cache, merge_state
├── session.py: SessionStore (内存/文件)
├── dialog_context.py: ContextManager (内存)
├── memory_service.py: MemoryService (单例)
├── knowledge_integration.py: _session_knowledge (内存)
└── short_term_memory.py: STMManager (内存)
```

**问题**：缺乏统一的状态管理器，会话状态在多个模块中重复维护。

#### 问题 3：API 设计不一致

```python
# 命名风格不一致
inference.py: model_id, max_tokens, top_p  # 下划线
inference.py: modelId, maxTokens, topP     # 驼峰（兼容前端）

# 响应格式不一致
rag.py: {"query": ..., "results": [...], "context": ...}
knowledge_base.py: {"query": ..., "method": ..., "results": [...], "total_count": ...}

# 错误处理不一致
方式1: raise HTTPException(status_code=404, detail="会话不存在")
方式2: return {"success": False, "message": "获取失败"}
方式3: return get_friendly_error("model_not_found")
```

#### 问题 4：配置硬编码

```python
# inference.py
PROMPT_INJECTION_PATTERNS = [...]  # 应该在配置文件中
MAX_MESSAGE_LENGTH = 10000
MAX_MESSAGES_COUNT = 100

# knowledge_integration.py
KNOWLEDGE_KEYWORDS = [...]
EXCLUSION_KEYWORDS = [...]
DOMAIN_KEYWORDS = {...}  # 大量硬编码
```

#### 问题 5：循环依赖风险

```
inference.py
    └──► context/knowledge_integration.py (函数内 import)
              └──► rag/service.py
                        └──► rag/embedder.py
                                  └──► rag/vector_store.py
```

当前通过延迟导入规避，但增加了维护难度。

#### 问题 6：性能问题

- **重复初始化**：embedder、vector\_store 在多处重复创建
- **缺少连接池**：cloud\_chat.py 每次请求创建新连接
- **缓存策略不完善**：模型缓存只有 LRU，缺少 TTL

***

## 二、Ollama 架构借鉴

### 2.1 Ollama 项目结构

```
ollama/
├── api/
│   ├── types.go        # 统一类型定义（39KB）
│   ├── client.go       # 客户端实现
│   └── examples/       # 示例代码
├── server/
│   ├── routes.go       # 统一路由（78KB，核心）
│   ├── sched.go        # 模型调度器（33KB）
│   ├── prompt.go       # Prompt 处理
│   ├── chat.go         # 聊天处理
│   ├── images.go       # 图像处理
│   └── auth.go         # 认证
├── llm/
│   └── server.go       # LLM 服务层
├── model/
│   └── *.go            # 模型管理
└── template/
    └── *.go            # 模板处理
```

### 2.2 Ollama 核心设计模式

#### 1. 统一类型定义（api/types.go）

```go
// 所有请求/响应类型集中定义
type GenerateRequest struct {
    Model     string    `json:"model"`
    Prompt    string    `json:"prompt"`
    System    string    `json:"system"`
    Template  string    `json:"template"`
    Context   []int     `json:"context"`
    Stream    bool      `json:"stream"`
    Raw       bool      `json:"raw"`
    Format    string    `json:"format"`
    KeepAlive *Duration `json:"keep_alive,omitempty"`
    Options   Options   `json:"options"`
}

type ChatRequest struct {
    Model     string    `json:"model"`
    Messages  []Message `json:"messages"`
    Stream    bool      `json:"stream"`
    Format    string    `json:"format"`
    KeepAlive *Duration `json:"keep_alive,omitempty"`
    Tools     []Tool    `json:"tools,omitempty"`
    Options   Options   `json:"options"`
}

type Options struct {
    Temperature   float64 `json:"temperature,omitempty"`
    TopP          float64 `json:"top_p,omitempty"`
    TopK          int     `json:"top_k,omitempty"`
    NumPredict    int     `json:"num_predict,omitempty"`
    Stop          []string `json:"stop,omitempty"`
    Seed          int     `json:"seed,omitempty"`
    NumKeep       int     `json:"num_keep,omitempty"`
    // ... 更多选项
}
```

**借鉴点**：统一类型定义文件，避免类型分散。

#### 2. 统一路由处理（server/routes.go）

```go
// 所有路由集中在一个文件，按功能分区
func (s *Server) GenerateHandler(c *gin.Context) {
    // 1. 解析请求
    var req api.GenerateRequest
    if err := c.ShouldBindJSON(&req); err != nil {
        c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
        return
    }
    
    // 2. 获取模型
    model, err := s.sched.GetModel(req.Model)
    if err != nil {
        c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
        return
    }
    
    // 3. 执行推理
    if req.Stream {
        s.streamGenerate(c, model, req)
    } else {
        s.generate(c, model, req)
    }
}
```

**借鉴点**：路由集中管理，处理逻辑清晰分层。

#### 3. 模型调度器（server/sched.go）

```go
type Scheduler struct {
    loaded   map[string]*loadedModel
    requests chan *LlmRequest
    done     chan *LlmRequest
    // ...
}

func (s *Scheduler) GetModel(name string) (*Model, error) {
    // 1. 检查已加载模型
    if m, ok := s.loaded[name]; ok {
        return m, nil
    }
    
    // 2. 加载新模型
    model, err := LoadModel(name)
    if err != nil {
        return nil, err
    }
    
    // 3. 缓存模型
    s.loaded[name] = model
    return model, nil
}
```

**借鉴点**：统一的模型调度器，管理模型生命周期。

#### 4. Prompt 处理（server/prompt.go）

```go
func (m *Model) Prompt(p Prompt, opts api.Options) (string, error) {
    // 1. 构建 template
    t, err := template.New("").Parse(m.Template)
    if err != nil {
        return "", err
    }
    
    // 2. 应用参数
    var buf bytes.Buffer
    if err := t.Execute(&buf, p); err != nil {
        return "", err
    }
    
    // 3. 返回处理后的 prompt
    return buf.String(), nil
}
```

**借鉴点**：统一的 Prompt 处理管道。

### 2.3 Ollama 对话流程

```
用户请求
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  routes.go: ChatHandler                                         │
│  1. 解析 ChatRequest                                            │
│  2. 验证消息格式                                                 │
│  3. 获取/加载模型                                                │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  sched.go: Scheduler                                            │
│  1. 检查模型是否已加载                                           │
│  2. 如果未加载，加载模型                                         │
│  3. 返回模型实例                                                 │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  prompt.go: PromptBuilder                                       │
│  1. 应用 chat template                                          │
│  2. 处理 system prompt                                          │
│  3. 构建最终 prompt                                              │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  llm/server.go: LLM Server                                      │
│  1. 执行推理                                                     │
│  2. 流式/非流式响应                                              │
│  3. 返回结果                                                     │
└─────────────────────────────────────────────────────────────────┘
```

***

## 三、重构方案

### 3.1 新架构设计

```
server/
├── api/
│   ├── __init__.py              # 路由注册
│   ├── types.py                 # 统一类型定义（参考 Ollama）
│   ├── errors.py                # 统一错误处理
│   │
│   ├── chat/                    # 对话模块（合并）
│   │   ├── __init__.py
│   │   ├── routes.py            # 对话路由
│   │   ├── session.py           # 会话管理（统一）
│   │   └── context.py           # 上下文管理（统一）
│   │
│   ├── inference/               # 推理模块
│   │   ├── __init__.py
│   │   ├── routes.py            # 推理路由
│   │   ├── backends/            # 后端实现
│   │   │   ├── __init__.py
│   │   │   ├── base.py          # 后端基类
│   │   │   ├── huggingface.py   # HuggingFace 后端
│   │   │   ├── ollama.py        # Ollama 后端
│   │   │   └── cloud.py         # 云端后端
│   │   └── scheduler.py         # 模型调度器（参考 Ollama）
│   │
│   ├── knowledge/               # 知识模块（合并 rag.py + knowledge_base.py）
│   │   ├── __init__.py
│   │   ├── routes.py            # 知识库路由
│   │   ├── rag.py               # RAG 功能
│   │   └── retrieval.py         # 检索接口
│   │
│   ├── memory/                  # 记忆模块（统一）
│   │   ├── __init__.py
│   │   ├── routes.py            # 记忆路由
│   │   ├── short_term.py        # 短期记忆
│   │   ├── long_term.py         # 长期记忆
│   │   └── knowledge_graph.py   # 知识图谱
│   │
│   └── agent/                   # Agent 模块
│       ├── __init__.py
│       ├── routes.py            # Agent 路由
│       ├── intent.py            # 意图识别
│       └── executor.py          # 操作执行
│
├── core/
│   ├── config.py                # 配置管理（外部化）
│   ├── state.py                 # 统一状态管理器
│   ├── cache.py                 # 统一缓存管理
│   └── errors.py                # 统一错误定义
│
├── services/
│   ├── chat_service.py          # 对话服务
│   ├── knowledge_service.py     # 知识服务
│   ├── memory_service.py        # 记忆服务
│   └── inference_service.py     # 推理服务
│
└── config/
    ├── knowledge.yaml           # 知识库配置
    ├── memory.yaml              # 记忆配置
    └── inference.yaml           # 推理配置
```

### 3.2 统一类型定义（api/types.py）

```python
"""
统一类型定义 - 参考 Ollama api/types.go
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from enum import Enum
from datetime import datetime


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class Message(BaseModel):
    role: MessageRole
    content: str
    timestamp: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None


class InferenceOptions(BaseModel):
    """推理选项 - 统一参数"""
    temperature: float = Field(default=0.7, ge=0, le=2)
    top_p: float = Field(default=0.9, ge=0, le=1)
    top_k: int = Field(default=50, ge=1)
    max_tokens: int = Field(default=1024, ge=1, le=8192)
    repetition_penalty: float = Field(default=1.1, ge=0.1, le=2)
    stop: Optional[List[str]] = None
    seed: Optional[int] = None


class ChatRequest(BaseModel):
    """聊天请求 - 统一格式"""
    model: str = Field(..., description="模型 ID")
    messages: List[Message] = Field(..., description="消息历史")
    options: InferenceOptions = Field(default_factory=InferenceOptions)
    stream: bool = Field(default=False, description="是否流式输出")
    
    # 知识库相关
    use_knowledge: bool = Field(default=False)
    collection_id: Optional[str] = None
    top_k: int = Field(default=5)
    
    # 项目上下文相关
    use_context: bool = Field(default=False)
    project_path: Optional[str] = None
    
    # 会话相关
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    """聊天响应 - 统一格式"""
    message: Message
    model: str
    backend: str
    usage: Dict[str, int]  # prompt_tokens, completion_tokens, total_tokens
    knowledge_sources: Optional[List[Dict[str, Any]]] = None
    done: bool = True


class GenerateRequest(BaseModel):
    """生成请求"""
    model: str
    prompt: str
    options: InferenceOptions = Field(default_factory=InferenceOptions)
    stream: bool = False
    system: Optional[str] = None


class GenerateResponse(BaseModel):
    """生成响应"""
    text: str
    model: str
    backend: str
    usage: Dict[str, int]


class SessionInfo(BaseModel):
    """会话信息"""
    id: str
    title: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    message_count: int
    metadata: Dict[str, Any] = Field(default_factory=dict)


class APIError(BaseModel):
    """API 错误响应"""
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None


class ErrorResponse(BaseModel):
    """统一错误响应"""
    error: APIError
```

### 3.3 统一错误处理（api/errors.py）

```python
"""
统一错误处理
"""
from fastapi import HTTPException
from typing import Optional, Dict, Any


class APIError(Exception):
    """API 错误基类"""
    
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: Optional[Dict[str, Any]] = None
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)
    
    def to_http_exception(self) -> HTTPException:
        return HTTPException(
            status_code=self.status_code,
            detail={
                "error": {
                    "code": self.code,
                    "message": self.message,
                    "details": self.details
                }
            }
        )


# 预定义错误
class ModelNotFoundError(APIError):
    def __init__(self, model_id: str):
        super().__init__(
            code="model_not_found",
            message=f"模型不存在: {model_id}",
            status_code=404,
            details={"model_id": model_id}
        )


class SessionNotFoundError(APIError):
    def __init__(self, session_id: str):
        super().__init__(
            code="session_not_found",
            message=f"会话不存在: {session_id}",
            status_code=404,
            details={"session_id": session_id}
        )


class OllamaNotRunningError(APIError):
    def __init__(self):
        super().__init__(
            code="ollama_not_running",
            message="Ollama 服务未运行，请先启动 Ollama",
            status_code=503
        )


class ContextTooLongError(APIError):
    def __init__(self, current: int, max_length: int):
        super().__init__(
            code="context_too_long",
            message=f"上下文长度超出限制（当前: {current}, 最大: {max_length}）",
            status_code=400,
            details={"current": current, "max_length": max_length}
        )


class MaliciousInputError(APIError):
    def __init__(self, pattern: str):
        super().__init__(
            code="malicious_input",
            message="检测到潜在的恶意输入",
            status_code=400,
            details={"detected_pattern": pattern}
        )
```

### 3.4 统一状态管理器（core/state.py）

```python
"""
统一状态管理器 - 参考 Ollama sched.go
"""
import asyncio
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import threading


@dataclass
class ModelState:
    """模型状态"""
    model_id: str
    model: Any
    tokenizer: Any
    loaded_at: datetime
    last_used: datetime
    use_count: int = 0
    memory_usage: int = 0


@dataclass
class SessionState:
    """会话状态"""
    session_id: str
    messages: list = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


class StateManager:
    """
    统一状态管理器
    
    管理所有运行时状态：
    - 模型缓存
    - 会话状态
    - 记忆状态
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._models: Dict[str, ModelState] = {}
            self._sessions: Dict[str, SessionState] = {}
            self._model_lock = asyncio.Lock()
            self._session_lock = asyncio.Lock()
            self._initialized = True
    
    # 模型管理
    async def get_model(self, model_id: str) -> Optional[ModelState]:
        async with self._model_lock:
            return self._models.get(model_id)
    
    async def set_model(self, model_id: str, model_state: ModelState):
        async with self._model_lock:
            self._models[model_id] = model_state
    
    async def remove_model(self, model_id: str) -> bool:
        async with self._model_lock:
            if model_id in self._models:
                del self._models[model_id]
                return True
            return False
    
    async def list_models(self) -> Dict[str, ModelState]:
        async with self._model_lock:
            return dict(self._models)
    
    # 会话管理
    async def get_session(self, session_id: str) -> Optional[SessionState]:
        async with self._session_lock:
            return self._sessions.get(session_id)
    
    async def create_session(self, session_id: str) -> SessionState:
        async with self._session_lock:
            session = SessionState(session_id=session_id)
            self._sessions[session_id] = session
            return session
    
    async def update_session(self, session_id: str, **kwargs):
        async with self._session_lock:
            if session_id in self._sessions:
                session = self._sessions[session_id]
                for key, value in kwargs.items():
                    if hasattr(session, key):
                        setattr(session, key, value)
                session.updated_at = datetime.now()
    
    async def delete_session(self, session_id: str) -> bool:
        async with self._session_lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False


def get_state_manager() -> StateManager:
    return StateManager()
```

### 3.5 模型调度器（api/inference/scheduler.py）

```python
"""
模型调度器 - 参考 Ollama sched.go
"""
import asyncio
from typing import Dict, Optional, Any
from datetime import datetime
import logging

from core.state import get_state_manager, ModelState
from core.config import get_settings
from api.errors import ModelNotFoundError

logger = logging.getLogger(__name__)


class ModelScheduler:
    """
    模型调度器
    
    职责：
    - 模型加载/卸载
    - LRU 缓存管理
    - 内存管理
    - 并发控制
    """
    
    def __init__(self, max_models: int = 3):
        self.max_models = max_models
        self.state = get_state_manager()
        self.settings = get_settings()
        self._loading: Dict[str, asyncio.Event] = {}
    
    async def get_model(self, model_id: str) -> ModelState:
        """获取模型（自动加载）"""
        # 检查是否正在加载
        if model_id in self._loading:
            await self._loading[model_id].wait()
        
        # 检查缓存
        model_state = await self.state.get_model(model_id)
        if model_state:
            model_state.last_used = datetime.now()
            model_state.use_count += 1
            return model_state
        
        # 加载模型
        return await self._load_model(model_id)
    
    async def _load_model(self, model_id: str) -> ModelState:
        """加载模型"""
        # 设置加载标志
        load_event = asyncio.Event()
        self._loading[model_id] = load_event
        
        try:
            # 检查缓存容量
            await self._ensure_capacity()
            
            # 加载模型
            logger.info(f"加载模型: {model_id}")
            
            import torch
            from transformers import AutoTokenizer, AutoModelForCausalLM
            
            model_path = self.settings.models_dir_resolved / model_id
            if not model_path.exists():
                raise ModelNotFoundError(model_id)
            
            tokenizer = AutoTokenizer.from_pretrained(
                str(model_path), trust_remote_code=True
            )
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token
            
            model = AutoModelForCausalLM.from_pretrained(
                str(model_path),
                device_map="auto",
                torch_dtype=torch.float16,
                trust_remote_code=True,
                low_cpu_mem_usage=True,
            )
            model.eval()
            
            # 创建状态
            model_state = ModelState(
                model_id=model_id,
                model=model,
                tokenizer=tokenizer,
                loaded_at=datetime.now(),
                last_used=datetime.now(),
                use_count=1
            )
            
            # 缓存
            await self.state.set_model(model_id, model_state)
            
            logger.info(f"模型加载完成: {model_id}")
            return model_state
            
        finally:
            # 清除加载标志
            del self._loading[model_id]
            load_event.set()
    
    async def _ensure_capacity(self):
        """确保缓存容量"""
        models = await self.state.list_models()
        
        if len(models) >= self.max_models:
            # LRU 淘汰
            sorted_models = sorted(
                models.items(),
                key=lambda x: x[1].last_used
            )
            
            # 淘汰最久未使用的模型
            for model_id, _ in sorted_models[:len(models) - self.max_models + 1]:
                await self.unload_model(model_id)
    
    async def unload_model(self, model_id: str):
        """卸载模型"""
        model_state = await self.state.get_model(model_id)
        if model_state:
            # 清理 GPU 内存
            import torch
            import gc
            
            del model_state.model
            del model_state.tokenizer
            
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            
            await self.state.remove_model(model_id)
            logger.info(f"模型已卸载: {model_id}")
    
    async def unload_all(self):
        """卸载所有模型"""
        models = await self.state.list_models()
        for model_id in models:
            await self.unload_model(model_id)


# 全局调度器
_scheduler: Optional[ModelScheduler] = None


def get_scheduler() -> ModelScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = ModelScheduler()
    return _scheduler
```

### 3.6 配置外部化（config/inference.yaml）

```yaml
# 推理配置
inference:
  default_backend: "huggingface"
  max_concurrent_requests: 10
  
  model_cache:
    max_size: 3
    ttl_seconds: 3600  # 1小时
  
  prompt_injection:
    enabled: true
    patterns:
      - "ignore\\s+(all\\s+)?previous\\s+instructions?"
      - "ignore\\s+(all\\s+)?(the\\s+)?above"
      - "disregard\\s+(all\\s+)?previous"
      - "forget\\s+(all\\s+)?(previous\\s+)?instructions?"
      - "you\\s+are\\s+now\\s+"
      - "new\\s+instructions?:"
      - "system:\\s*you\\s+are"
      - "<\\|im_start\\|>system"
      - "jailbreak"
      - "dan\\s+mode"
      - "developer\\s+mode"
      - "sudo\\s+mode"
  
  limits:
    max_message_length: 10000
    max_messages_count: 100
    max_tokens: 8192

# 知识库配置
knowledge:
  retrieval:
    default_top_k: 5
    max_top_k: 20
    min_score: 0.3
  
  exclusion_keywords:
    - "写代码"
    - "运行命令"
    - "执行脚本"
    - "创建文件"
    - "修改文件"
    - "删除文件"
    - "帮我写"
    - "生成代码"
  
  domain_keywords:
    law:
      - "法律"
      - "法规"
      - "合同"
      - "诉讼"
      - "判决"
    medical:
      - "医疗"
      - "健康"
      - "疾病"
      - "症状"
      - "治疗"
    financial:
      - "金融"
      - "投资"
      - "股票"
      - "基金"
      - "理财"

# 记忆配置
memory:
  short_term:
    max_messages: 50
    max_tokens: 4000
    summary_threshold: 30
  
  long_term:
    max_memories: 1000
    embedding_model: "shibing624/text2vec-base-chinese"
  
  knowledge_graph:
    enabled: true
    max_entities: 500
    max_relations: 1000
```

***

## 四、实施步骤

### 阶段一：基础重构（预计 3-5 天）

#### 任务 1.1：创建统一类型定义

- [ ] 创建 `api/types.py`，定义所有请求/响应类型
- [ ] 迁移现有 Pydantic 模型到新文件
- [ ] 更新所有 API 端点使用新类型

#### 任务 1.2：创建统一错误处理

- [ ] 创建 `api/errors.py`，定义错误类
- [ ] 创建错误处理中间件
- [ ] 迁移现有错误处理到新系统

#### 任务 1.3：创建统一状态管理器

- [ ] 创建 `core/state.py`
- [ ] 实现模型状态管理
- [ ] 实现会话状态管理
- [ ] 迁移现有状态到新管理器

### 阶段二：模块合并（预计 5-7 天）

#### 任务 2.1：合并会话管理模块

- [ ] 合并 `chat_history.py`、`session.py`、`dialog_context.py`
- [ ] 创建 `api/chat/` 目录结构
- [ ] 统一会话 API

#### 任务 2.2：合并知识库模块

- [ ] 合并 `rag.py`、`knowledge_base.py`
- [ ] 创建 `api/knowledge/` 目录结构
- [ ] 统一知识库 API

#### 任务 2.3：合并记忆模块

- [ ] 合并 `memory.py` 到 `enhanced_memory.py`
- [ ] 创建 `api/memory/` 目录结构
- [ ] 统一记忆 API

### 阶段三：推理模块重构（预计 3-5 天）

#### 任务 3.1：创建模型调度器

- [ ] 创建 `api/inference/scheduler.py`
- [ ] 实现 LRU 缓存
- [ ] 实现并发控制

#### 任务 3.2：重构推理后端

- [ ] 创建后端抽象基类
- [ ] 重构 HuggingFace 后端
- [ ] 重构 Ollama 后端
- [ ] 重构云端后端

### 阶段四：配置外部化（预计 1-2 天）

#### 任务 4.1：创建配置文件

- [ ] 创建 `config/inference.yaml`
- [ ] 创建 `config/knowledge.yaml`
- [ ] 创建 `config/memory.yaml`

#### 任务 4.2：迁移硬编码配置

- [ ] 迁移 Prompt 注入模式
- [ ] 迁移领域关键词
- [ ] 迁移限制参数

### 阶段五：测试与验证（预计 2-3 天）

#### 任务 5.1：单元测试

- [ ] 编写类型定义测试
- [ ] 编写错误处理测试
- [ ] 编写状态管理测试

#### 任务 5.2：集成测试

- [ ] 测试对话流程
- [ ] 测试知识库检索
- [ ] 测试记忆系统

#### 任务 5.3：性能测试

- [ ] 测试模型加载性能
- [ ] 测试并发性能
- [ ] 测试内存使用

***

## 五、预期收益

### 5.1 代码质量提升

| 指标      | 当前          | 目标      |
| ------- | ----------- | ------- |
| 模块数量    | 14 个 API 文件 | 6 个模块目录 |
| 代码重复率   | \~30%       | <10%    |
| 类型定义一致性 | 60%         | 100%    |
| 错误处理一致性 | 50%         | 100%    |

### 5.2 可维护性提升

- **清晰的模块边界**：每个模块职责单一
- **统一的类型定义**：参考 Ollama 的类型系统
- **统一的错误处理**：一致的错误响应格式
- **配置外部化**：便于调整和维护

### 5.3 性能提升

- **模型调度器**：智能缓存管理，减少重复加载
- **统一状态管理**：避免状态分散导致的性能问题
- **连接池**：云端 API 连接复用

### 5.4 扩展性提升

- **后端抽象**：易于添加新的推理后端
- **模块化设计**：易于添加新功能
- **配置驱动**：易于调整行为

***

## 六、风险评估

### 6.1 技术风险

| 风险       | 影响 | 缓解措施          |
| -------- | -- | ------------- |
| 重构导致功能回归 | 高  | 完善测试覆盖，逐步迁移   |
| 性能下降     | 中  | 性能基准测试，优化关键路径 |
| API 不兼容  | 中  | 保持向后兼容层       |

### 6.2 项目风险

| 风险     | 影响 | 缓解措施         |
| ------ | -- | ------------ |
| 开发周期延长 | 中  | 分阶段实施，优先核心功能 |
| 团队适应成本 | 低  | 完善文档，代码注释    |

***

## 七、总结

本计划基于对当前 AI 对话模块的全面分析，参考 Ollama 开源项目的优秀设计模式，提出了一套完整的重构方案。主要改进包括：

1. **模块合并**：合并职责重叠的模块，减少冗余
2. **统一类型**：参考 Ollama 的类型系统，统一请求/响应格式
3. **统一状态管理**：创建中心化状态管理器，解决状态分散问题
4. **模型调度器**：参考 Ollama sched.go，实现智能模型管理
5. **配置外部化**：将硬编码配置迁移到 YAML 文件

通过这些改进，预期可以显著提升代码质量、可维护性和执行效率。
