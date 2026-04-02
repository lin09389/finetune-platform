"""
统一类型定义 - 参考 Ollama api/types.go
所有 API 请求/响应类型集中定义
"""
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    FUNCTION = "function"
    TOOL = "tool"


class Message(BaseModel):
    role: MessageRole
    content: str
    name: str | None = None
    timestamp: datetime | None = None
    metadata: dict[str, Any] | None = None

    model_config = ConfigDict(use_enum_values=True)


class InferenceOptions(BaseModel):
    temperature: float = Field(default=0.7, ge=0, le=2, description="温度参数")
    top_p: float = Field(default=0.9, ge=0, le=1, description="Top-p 采样")
    top_k: int = Field(default=50, ge=1, description="Top-k 采样")
    max_tokens: int = Field(default=1024, ge=1, le=8192, description="最大生成 token 数")
    repetition_penalty: float = Field(default=1.1, ge=0.1, le=2, description="重复惩罚")
    stop: list[str] | None = Field(default=None, description="停止词")
    seed: int | None = Field(default=None, description="随机种子")
    num_ctx: int = Field(default=4096, description="上下文窗口大小")
    num_batch: int = Field(default=512, description="批处理大小")
    num_keep: int = Field(default=0, description="保留 token 数")
    backend: str | None = Field(default=None, description="推理后端类型")


class KnowledgeRetrievalOptions(BaseModel):
    use_knowledge: bool = Field(default=False, description="是否使用知识库检索")
    collection_id: str | None = Field(default=None, description="知识库集合 ID")
    top_k: int = Field(default=5, ge=1, le=20, description="检索返回数量")
    min_score: float = Field(default=0.3, ge=0, le=1, description="最小相似度分数")
    auto_retrieve: bool = Field(default=True, description="是否自动触发检索")
    include_sources: bool = Field(default=True, description="是否包含知识来源")


class ProjectContextOptions(BaseModel):
    use_context: bool = Field(default=False, description="是否使用项目上下文")
    project_path: str | None = Field(default=None, description="项目路径")
    max_context_length: int = Field(default=1500, description="最大上下文长度")


class MemoryOptions(BaseModel):
    enabled: bool = Field(default=True, description="是否启用记忆系统")
    auto_extract: bool = Field(default=True, description="是否自动提取记忆")
    auto_retrieve: bool = Field(default=True, description="是否自动检索记忆")
    top_k: int = Field(default=3, ge=1, le=10, description="检索返回数量")
    include_types: list[str] | None = Field(default=None, description="包含的记忆类型")


class SessionOptions(BaseModel):
    session_id: str | None = Field(default=None, description="会话 ID")
    user_id: str = Field(default="default", description="用户 ID")


class UnifiedContextInfo(BaseModel):
    total_sources: int = Field(default=0, description="总来源数")
    memory_count: int = Field(default=0, description="记忆数量")
    knowledge_count: int = Field(default=0, description="知识库数量")
    project_count: int = Field(default=0, description="项目上下文数量")
    retrieval_time: float = Field(default=0, description="检索耗时(秒)")


class MemoryContextInfo(BaseModel):
    retrieved: bool = Field(default=False, description="是否检索了记忆")
    sources_count: int = Field(default=0, description="来源数量")
    context_preview: str = Field(default="", description="上下文预览")


class ChatRequest(BaseModel):
    model: str = Field(
        ...,
        validation_alias=AliasChoices("model", "model_id"),
        description="模型 ID",
    )
    messages: list[Message] = Field(..., description="消息历史")
    options: InferenceOptions = Field(default_factory=InferenceOptions, description="推理选项")
    stream: bool = Field(default=False, description="是否流式输出")
    format: str | None = Field(default=None, description="输出格式: json/text")
    keep_alive: str | None = Field(default=None, description="模型保活时间")

    memory: MemoryOptions = Field(default_factory=MemoryOptions, description="记忆系统选项")
    knowledge: KnowledgeRetrievalOptions = Field(default_factory=KnowledgeRetrievalOptions, description="知识检索选项")
    context: ProjectContextOptions = Field(default_factory=ProjectContextOptions, description="项目上下文选项")
    session: SessionOptions = Field(default_factory=SessionOptions, description="会话选项")

    tools: list[dict[str, Any]] | None = Field(default=None, description="工具列表")

    def get_last_user_message(self) -> str | None:
        for msg in reversed(self.messages):
            if msg.role == MessageRole.USER or msg.role == "user":
                return msg.content
        return None


class KnowledgeSource(BaseModel):
    id: str = Field(..., description="来源 ID")
    source: str = Field(..., description="来源名称")
    score: float = Field(..., description="相似度分数")
    content_preview: str = Field(default="", description="内容预览")
    metadata: dict[str, Any] | None = Field(default=None, description="元数据")


class TokenUsage(BaseModel):
    prompt_tokens: int = Field(default=0, description="提示 token 数")
    completion_tokens: int = Field(default=0, description="完成 token 数")
    total_tokens: int = Field(default=0, description="总 token 数")


class ChatResponse(BaseModel):
    message: Message = Field(..., description="响应消息")
    model: str = Field(..., description="模型 ID")
    backend: str = Field(..., description="推理后端")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    done: bool = Field(default=True, description="是否完成")

    usage: TokenUsage = Field(default_factory=TokenUsage, description="Token 使用统计")
    knowledge_sources: list[KnowledgeSource] | None = Field(default=None, description="知识来源")
    retrieval_info: dict[str, Any] | None = Field(default=None, description="检索信息")

    memory_context: MemoryContextInfo | None = Field(default=None, description="记忆上下文信息")
    unified_context: UnifiedContextInfo | None = Field(default=None, description="统一上下文信息")

    total_duration: float | None = Field(default=None, description="总耗时(秒)")
    load_duration: float | None = Field(default=None, description="模型加载耗时")
    eval_duration: float | None = Field(default=None, description="推理耗时")


class GenerateRequest(BaseModel):
    model: str = Field(
        ...,
        validation_alias=AliasChoices("model", "model_id"),
        description="模型 ID",
    )
    prompt: str = Field(..., description="提示文本")
    system: str | None = Field(default=None, description="系统提示")
    template: str | None = Field(default=None, description="模板")
    context: list[int] | None = Field(default=None, description="上下文 token")
    options: InferenceOptions = Field(default_factory=InferenceOptions, description="推理选项")
    stream: bool = Field(default=False, description="是否流式输出")
    format: str | None = Field(default=None, description="输出格式")
    keep_alive: str | None = Field(default=None, description="模型保活时间")
    raw: bool = Field(default=False, description="是否原始模式")

    lora_adapter: str | None = Field(default=None, description="LoRA 适配器路径")


class GenerateResponse(BaseModel):
    model: str = Field(..., description="模型 ID")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    response: str = Field(..., description="响应文本")
    done: bool = Field(default=True, description="是否完成")

    context: list[int] | None = Field(default=None, description="上下文 token")
    usage: TokenUsage = Field(default_factory=TokenUsage, description="Token 使用统计")

    total_duration: float | None = Field(default=None, description="总耗时(秒)")
    load_duration: float | None = Field(default=None, description="模型加载耗时")
    prompt_eval_duration: float | None = Field(default=None, description="提示评估耗时")
    eval_duration: float | None = Field(default=None, description="推理耗时")


class EmbeddingRequest(BaseModel):
    model: str = Field(..., description="模型 ID")
    input: str | list[str] = Field(..., description="输入文本")
    truncate: bool = Field(default=True, description="是否截断")


class EmbeddingResponse(BaseModel):
    embeddings: list[list[float]] = Field(..., description="嵌入向量")
    model: str = Field(..., description="模型 ID")
    usage: TokenUsage = Field(default_factory=TokenUsage, description="Token 使用统计")


class SessionInfo(BaseModel):
    id: str = Field(..., description="会话 ID")
    title: str | None = Field(default=None, description="会话标题")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    message_count: int = Field(default=0, description="消息数量")
    metadata: dict[str, Any] = Field(default_factory=dict, description="元数据")
    tags: list[str] = Field(default_factory=list, description="标签")
    starred: bool = Field(default=False, description="是否星标")
    pinned: bool = Field(default=False, description="是否置顶")


class SessionMessage(BaseModel):
    id: str = Field(..., description="消息 ID")
    session_id: str = Field(..., description="会话 ID")
    role: MessageRole = Field(..., description="角色")
    content: str = Field(..., description="内容")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    metadata: dict[str, Any] = Field(default_factory=dict, description="元数据")


class CreateSessionRequest(BaseModel):
    title: str | None = Field(default=None, description="会话标题")
    metadata: dict[str, Any] = Field(default_factory=dict, description="元数据")


class UpdateSessionRequest(BaseModel):
    title: str | None = Field(default=None, description="会话标题")
    metadata: dict[str, Any] | None = Field(default=None, description="元数据")
    tags: list[str] | None = Field(default=None, description="标签")
    starred: bool | None = Field(default=None, description="是否星标")
    pinned: bool | None = Field(default=None, description="是否置顶")


class ModelInfo(BaseModel):
    id: str = Field(..., description="模型 ID")
    name: str = Field(..., description="模型名称")
    type: str = Field(default="base", description="模型类型: base/merged/finetuned")
    backend: str = Field(default="huggingface", description="后端类型")
    size: int | None = Field(default=None, description="模型大小(字节)")
    quantized: str | None = Field(default=None, description="量化类型")
    modified_at: datetime | None = Field(default=None, description="修改时间")
    digest: str | None = Field(default=None, description="摘要")
    details: dict[str, Any] | None = Field(default=None, description="详细信息")


class ModelPullRequest(BaseModel):
    name: str = Field(..., description="模型名称")
    insecure: bool = Field(default=False, description="是否允许不安全连接")
    stream: bool = Field(default=True, description="是否流式输出")


class ModelPushRequest(BaseModel):
    name: str = Field(..., description="模型名称")
    insecure: bool = Field(default=False, description="是否允许不安全连接")
    stream: bool = Field(default=True, description="是否流式输出")


class BackendInfo(BaseModel):
    id: str = Field(..., description="后端 ID")
    name: str = Field(..., description="后端名称")
    available: bool = Field(default=False, description="是否可用")
    description: str = Field(default="", description="描述")


class BackendListResponse(BaseModel):
    current: str = Field(..., description="当前后端")
    backends: list[BackendInfo] = Field(default_factory=list, description="后端列表")


class BackendSwitchRequest(BaseModel):
    backend: str = Field(..., description="后端类型: huggingface/ollama")


class MemoryInfo(BaseModel):
    id: str = Field(..., description="记忆 ID")
    type: str = Field(..., description="记忆类型")
    content: str = Field(..., description="记忆内容")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    confidence: float = Field(default=1.0, description="置信度")
    metadata: dict[str, Any] = Field(default_factory=dict, description="元数据")


class MemoryRecallRequest(BaseModel):
    query: str = Field(..., description="查询文本")
    user_id: str = Field(default="default", description="用户 ID")
    top_k: int = Field(default=5, description="返回数量")
    memory_type: str | None = Field(default=None, description="记忆类型过滤")


class MemoryStoreRequest(BaseModel):
    content: str = Field(..., description="记忆内容")
    memory_type: str = Field(default="fact", description="记忆类型")
    user_id: str = Field(default="default", description="用户 ID")
    confidence: float = Field(default=1.0, description="置信度")
    metadata: dict[str, Any] = Field(default_factory=dict, description="元数据")


class KnowledgeDocument(BaseModel):
    id: str = Field(..., description="文档 ID")
    filename: str = Field(..., description="文件名")
    content: str | None = Field(default=None, description="内容")
    collection_id: str = Field(..., description="集合 ID")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    chunk_count: int = Field(default=0, description="分块数量")
    metadata: dict[str, Any] = Field(default_factory=dict, description="元数据")


class KnowledgeCollection(BaseModel):
    id: str = Field(..., description="集合 ID")
    name: str = Field(..., description="集合名称")
    description: str | None = Field(default=None, description="描述")
    document_count: int = Field(default=0, description="文档数量")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    metadata: dict[str, Any] = Field(default_factory=dict, description="元数据")


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(..., description="查询文本")
    collection_id: str = Field(..., description="集合 ID")
    top_k: int = Field(default=5, ge=1, le=20, description="返回数量")
    min_score: float = Field(default=0.3, ge=0, le=1, description="最小相似度")
    method: str = Field(default="hybrid", description="检索方法: vector/keyword/hybrid")


class KnowledgeSearchResult(BaseModel):
    id: str = Field(..., description="结果 ID")
    content: str = Field(..., description="内容")
    source: str = Field(..., description="来源")
    score: float = Field(..., description="相似度分数")
    metadata: dict[str, Any] = Field(default_factory=dict, description="元数据")


class KnowledgeSearchResponse(BaseModel):
    query: str = Field(..., description="查询文本")
    results: list[KnowledgeSearchResult] = Field(default_factory=list, description="搜索结果")
    total_count: int = Field(default=0, description="总数量")
    retrieval_time: float = Field(default=0, description="检索耗时(秒)")
    method: str = Field(default="hybrid", description="检索方法")


class APIErrorDetail(BaseModel):
    code: str = Field(..., description="错误代码")
    message: str = Field(..., description="错误消息")
    details: dict[str, Any] | None = Field(default=None, description="详细信息")


class APIErrorResponse(BaseModel):
    error: APIErrorDetail = Field(..., description="错误详情")


class HealthCheckResponse(BaseModel):
    status: str = Field(default="ok", description="状态")
    version: str = Field(default="1.0.0", description="版本")
    uptime: float = Field(default=0, description="运行时间(秒)")
    backends: dict[str, bool] = Field(default_factory=dict, description="后端状态")


class VersionInfo(BaseModel):
    version: str = Field(default="1.0.0", description="版本号")
    build: str | None = Field(default=None, description="构建号")
    commit: str | None = Field(default=None, description="提交哈希")
    date: datetime | None = Field(default=None, description="构建日期")


class ProgressEvent(BaseModel):
    status: str = Field(..., description="状态")
    completed: int = Field(default=0, description="已完成")
    total: int = Field(default=0, description="总数")
    percent: float = Field(default=0, description="百分比")
    message: str | None = Field(default=None, description="消息")


class StreamChunk(BaseModel):
    model: str = Field(..., description="模型 ID")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    content: str = Field(default="", description="内容")
    done: bool = Field(default=False, description="是否完成")

    usage: TokenUsage | None = Field(default=None, description="Token 使用统计")
    total_duration: float | None = Field(default=None, description="总耗时")


class ToolCall(BaseModel):
    name: str = Field(..., description="工具名称")
    arguments: dict[str, Any] = Field(default_factory=dict, description="参数")


class ToolResult(BaseModel):
    tool_call_id: str = Field(..., description="工具调用 ID")
    name: str = Field(..., description="工具名称")
    content: str = Field(..., description="结果内容")


class AgentAction(BaseModel):
    action_type: str = Field(..., description="动作类型")
    parameters: dict[str, Any] = Field(default_factory=dict, description="参数")
    confidence: float = Field(default=1.0, description="置信度")
    requires_confirmation: bool = Field(default=False, description="是否需要确认")


class AgentIntent(BaseModel):
    intent: str = Field(..., description="意图类型")
    entities: dict[str, Any] = Field(default_factory=dict, description="实体")
    confidence: float = Field(default=1.0, description="置信度")
    action: AgentAction | None = Field(default=None, description="动作")
