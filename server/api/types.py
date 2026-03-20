"""
统一类型定义 - 参�?Ollama api/types.go
所�?API 请求/响应类型集中定义
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal, Union
from enum import Enum
from datetime import datetime


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    FUNCTION = "function"
    TOOL = "tool"


class Message(BaseModel):
    role: MessageRole
    content: str
    name: Optional[str] = None
    timestamp: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None

    class Config:
        use_enum_values = True


class InferenceOptions(BaseModel):
    temperature: float = Field(default=0.7, ge=0, le=2, description="温度参数")
    top_p: float = Field(default=0.9, ge=0, le=1, description="Top-p 采样")
    top_k: int = Field(default=50, ge=1, description="Top-k 采样")
    max_tokens: int = Field(default=1024, ge=1, le=8192, description="最大生�?token �?)
    repetition_penalty: float = Field(default=1.1, ge=0.1, le=2, description="重复惩罚")
    stop: Optional[List[str]] = Field(default=None, description="停止�?)
    seed: Optional[int] = Field(default=None, description="随机种子")
    num_ctx: int = Field(default=4096, description="上下文窗口大�?)
    num_batch: int = Field(default=512, description="批处理大�?)
    num_keep: int = Field(default=0, description="保留 token �?)
    backend: Optional[str] = Field(default=None, description="推理后端类型")


class KnowledgeRetrievalOptions(BaseModel):
    use_knowledge: bool = Field(default=False, description="是否使用知识库检�?)
    collection_id: Optional[str] = Field(default=None, description="知识库集�?ID")
    top_k: int = Field(default=5, ge=1, le=20, description="检索返回数�?)
    min_score: float = Field(default=0.3, ge=0, le=1, description="最小相似度分数")
    auto_retrieve: bool = Field(default=True, description="是否自动触发检�?)
    include_sources: bool = Field(default=True, description="是否包含知识来源")


class ProjectContextOptions(BaseModel):
    use_context: bool = Field(default=False, description="是否使用项目上下�?)
    project_path: Optional[str] = Field(default=None, description="项目路径")
    max_context_length: int = Field(default=1500, description="最大上下文长度")


class SessionOptions(BaseModel):
    session_id: Optional[str] = Field(default=None, description="会话 ID")
    use_memory: bool = Field(default=True, description="是否使用记忆系统")
    memory_types: Optional[List[str]] = Field(default=None, description="记忆类型过滤")


class ChatRequest(BaseModel):
    model: str = Field(..., description="模型 ID")
    messages: List[Message] = Field(..., description="消息历史")
    options: InferenceOptions = Field(default_factory=InferenceOptions, description="推理选项")
    stream: bool = Field(default=False, description="是否流式输出")
    format: Optional[str] = Field(default=None, description="输出格式: json/text")
    keep_alive: Optional[str] = Field(default=None, description="模型保活时间")
    
    knowledge: KnowledgeRetrievalOptions = Field(default_factory=KnowledgeRetrievalOptions, description="知识检索选项")
    context: ProjectContextOptions = Field(default_factory=ProjectContextOptions, description="项目上下文选项")
    session: SessionOptions = Field(default_factory=SessionOptions, description="会话选项")
    
    tools: Optional[List[Dict[str, Any]]] = Field(default=None, description="工具列表")
    
    def get_last_user_message(self) -> Optional[str]:
        for msg in reversed(self.messages):
            if msg.role == MessageRole.USER or msg.role == "user":
                return msg.content
        return None


class KnowledgeSource(BaseModel):
    id: str = Field(..., description="来源 ID")
    source: str = Field(..., description="来源名称")
    score: float = Field(..., description="相似度分�?)
    content_preview: str = Field(default="", description="内容预览")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="元数�?)


class TokenUsage(BaseModel):
    prompt_tokens: int = Field(default=0, description="提示 token �?)
    completion_tokens: int = Field(default=0, description="完成 token �?)
    total_tokens: int = Field(default=0, description="�?token �?)


class ChatResponse(BaseModel):
    message: Message = Field(..., description="响应消息")
    model: str = Field(..., description="模型 ID")
    backend: str = Field(..., description="推理后端")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    done: bool = Field(default=True, description="是否完成")
    
    usage: TokenUsage = Field(default_factory=TokenUsage, description="Token 使用统计")
    knowledge_sources: Optional[List[KnowledgeSource]] = Field(default=None, description="知识来源")
    retrieval_info: Optional[Dict[str, Any]] = Field(default=None, description="检索信�?)
    
    total_duration: Optional[float] = Field(default=None, description="总耗时(�?")
    load_duration: Optional[float] = Field(default=None, description="模型加载耗时")
    eval_duration: Optional[float] = Field(default=None, description="推理耗时")


class GenerateRequest(BaseModel):
    model: str = Field(..., description="模型 ID")
    prompt: str = Field(..., description="提示文本")
    system: Optional[str] = Field(default=None, description="系统提示")
    template: Optional[str] = Field(default=None, description="模板")
    context: Optional[List[int]] = Field(default=None, description="上下�?token")
    options: InferenceOptions = Field(default_factory=InferenceOptions, description="推理选项")
    stream: bool = Field(default=False, description="是否流式输出")
    format: Optional[str] = Field(default=None, description="输出格式")
    keep_alive: Optional[str] = Field(default=None, description="模型保活时间")
    raw: bool = Field(default=False, description="是否原始模式")
    
    lora_adapter: Optional[str] = Field(default=None, description="LoRA 适配器路�?)


class GenerateResponse(BaseModel):
    model: str = Field(..., description="模型 ID")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    response: str = Field(..., description="响应文本")
    done: bool = Field(default=True, description="是否完成")
    
    context: Optional[List[int]] = Field(default=None, description="上下�?token")
    usage: TokenUsage = Field(default_factory=TokenUsage, description="Token 使用统计")
    
    total_duration: Optional[float] = Field(default=None, description="总耗时(�?")
    load_duration: Optional[float] = Field(default=None, description="模型加载耗时")
    prompt_eval_duration: Optional[float] = Field(default=None, description="提示评估耗时")
    eval_duration: Optional[float] = Field(default=None, description="推理耗时")


class EmbeddingRequest(BaseModel):
    model: str = Field(..., description="模型 ID")
    input: Union[str, List[str]] = Field(..., description="输入文本")
    truncate: bool = Field(default=True, description="是否截断")


class EmbeddingResponse(BaseModel):
    embeddings: List[List[float]] = Field(..., description="嵌入向量")
    model: str = Field(..., description="模型 ID")
    usage: TokenUsage = Field(default_factory=TokenUsage, description="Token 使用统计")


class SessionInfo(BaseModel):
    id: str = Field(..., description="会话 ID")
    title: Optional[str] = Field(default=None, description="会话标题")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    message_count: int = Field(default=0, description="消息数量")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数�?)
    tags: List[str] = Field(default_factory=list, description="标签")
    starred: bool = Field(default=False, description="是否星标")
    pinned: bool = Field(default=False, description="是否置顶")


class SessionMessage(BaseModel):
    id: str = Field(..., description="消息 ID")
    session_id: str = Field(..., description="会话 ID")
    role: MessageRole = Field(..., description="角色")
    content: str = Field(..., description="内容")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数�?)


class CreateSessionRequest(BaseModel):
    title: Optional[str] = Field(default=None, description="会话标题")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数�?)


class UpdateSessionRequest(BaseModel):
    title: Optional[str] = Field(default=None, description="会话标题")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="元数�?)
    tags: Optional[List[str]] = Field(default=None, description="标签")
    starred: Optional[bool] = Field(default=None, description="是否星标")
    pinned: Optional[bool] = Field(default=None, description="是否置顶")


class ModelInfo(BaseModel):
    id: str = Field(..., description="模型 ID")
    name: str = Field(..., description="模型名称")
    type: str = Field(default="base", description="模型类型: base/merged/finetuned")
    backend: str = Field(default="huggingface", description="后端类型")
    size: Optional[int] = Field(default=None, description="模型大小(字节)")
    quantized: Optional[str] = Field(default=None, description="量化类型")
    modified_at: Optional[datetime] = Field(default=None, description="修改时间")
    digest: Optional[str] = Field(default=None, description="摘要")
    details: Optional[Dict[str, Any]] = Field(default=None, description="详细信息")


class ModelPullRequest(BaseModel):
    name: str = Field(..., description="模型名称")
    insecure: bool = Field(default=False, description="是否允许不安全连�?)
    stream: bool = Field(default=True, description="是否流式输出")


class ModelPushRequest(BaseModel):
    name: str = Field(..., description="模型名称")
    insecure: bool = Field(default=False, description="是否允许不安全连�?)
    stream: bool = Field(default=True, description="是否流式输出")


class BackendInfo(BaseModel):
    id: str = Field(..., description="后端 ID")
    name: str = Field(..., description="后端名称")
    available: bool = Field(default=False, description="是否可用")
    description: str = Field(default="", description="描述")


class BackendListResponse(BaseModel):
    current: str = Field(..., description="当前后端")
    backends: List[BackendInfo] = Field(default_factory=list, description="后端列表")


class BackendSwitchRequest(BaseModel):
    backend: str = Field(..., description="后端类型: huggingface/ollama")


class MemoryInfo(BaseModel):
    id: str = Field(..., description="记忆 ID")
    type: str = Field(..., description="记忆类型")
    content: str = Field(..., description="记忆内容")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    confidence: float = Field(default=1.0, description="置信�?)
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数�?)


class MemoryRecallRequest(BaseModel):
    query: str = Field(..., description="查询文本")
    user_id: str = Field(default="default", description="用户 ID")
    top_k: int = Field(default=5, description="返回数量")
    memory_type: Optional[str] = Field(default=None, description="记忆类型过滤")


class MemoryStoreRequest(BaseModel):
    content: str = Field(..., description="记忆内容")
    memory_type: str = Field(default="fact", description="记忆类型")
    user_id: str = Field(default="default", description="用户 ID")
    confidence: float = Field(default=1.0, description="置信�?)
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数�?)


class KnowledgeDocument(BaseModel):
    id: str = Field(..., description="文档 ID")
    filename: str = Field(..., description="文件�?)
    content: Optional[str] = Field(default=None, description="内容")
    collection_id: str = Field(..., description="集合 ID")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    chunk_count: int = Field(default=0, description="分块数量")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数�?)


class KnowledgeCollection(BaseModel):
    id: str = Field(..., description="集合 ID")
    name: str = Field(..., description="集合名称")
    description: Optional[str] = Field(default=None, description="描述")
    document_count: int = Field(default=0, description="文档数量")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数�?)


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(..., description="查询文本")
    collection_id: str = Field(..., description="集合 ID")
    top_k: int = Field(default=5, ge=1, le=20, description="返回数量")
    min_score: float = Field(default=0.3, ge=0, le=1, description="最小相似度")
    method: str = Field(default="hybrid", description="检索方�? vector/keyword/hybrid")


class KnowledgeSearchResult(BaseModel):
    id: str = Field(..., description="结果 ID")
    content: str = Field(..., description="内容")
    source: str = Field(..., description="来源")
    score: float = Field(..., description="相似度分�?)
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数�?)


class KnowledgeSearchResponse(BaseModel):
    query: str = Field(..., description="查询文本")
    results: List[KnowledgeSearchResult] = Field(default_factory=list, description="搜索结果")
    total_count: int = Field(default=0, description="总数�?)
    retrieval_time: float = Field(default=0, description="检索耗时(�?")
    method: str = Field(default="hybrid", description="检索方�?)


class APIErrorDetail(BaseModel):
    code: str = Field(..., description="错误代码")
    message: str = Field(..., description="错误消息")
    details: Optional[Dict[str, Any]] = Field(default=None, description="详细信息")


class APIErrorResponse(BaseModel):
    error: APIErrorDetail = Field(..., description="错误详情")


class HealthCheckResponse(BaseModel):
    status: str = Field(default="ok", description="状�?)
    version: str = Field(default="1.0.0", description="版本")
    uptime: float = Field(default=0, description="运行时间(�?")
    backends: Dict[str, bool] = Field(default_factory=dict, description="后端状�?)


class VersionInfo(BaseModel):
    version: str = Field(default="1.0.0", description="版本�?)
    build: Optional[str] = Field(default=None, description="构建�?)
    commit: Optional[str] = Field(default=None, description="提交哈希")
    date: Optional[datetime] = Field(default=None, description="构建日期")


class ProgressEvent(BaseModel):
    status: str = Field(..., description="状�?)
    completed: int = Field(default=0, description="已完�?)
    total: int = Field(default=0, description="总数")
    percent: float = Field(default=0, description="百分�?)
    message: Optional[str] = Field(default=None, description="消息")


class StreamChunk(BaseModel):
    model: str = Field(..., description="模型 ID")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    content: str = Field(default="", description="内容")
    done: bool = Field(default=False, description="是否完成")
    
    usage: Optional[TokenUsage] = Field(default=None, description="Token 使用统计")
    total_duration: Optional[float] = Field(default=None, description="总耗时")


class ToolCall(BaseModel):
    name: str = Field(..., description="工具名称")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="参数")


class ToolResult(BaseModel):
    tool_call_id: str = Field(..., description="工具调用 ID")
    name: str = Field(..., description="工具名称")
    content: str = Field(..., description="结果内容")


class AgentAction(BaseModel):
    action_type: str = Field(..., description="动作类型")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="参数")
    confidence: float = Field(default=1.0, description="置信�?)
    requires_confirmation: bool = Field(default=False, description="是否需要确�?)


class AgentIntent(BaseModel):
    intent: str = Field(..., description="意图类型")
    entities: Dict[str, Any] = Field(default_factory=dict, description="实体")
    confidence: float = Field(default=1.0, description="置信�?)
    action: Optional[AgentAction] = Field(default=None, description="动作")
