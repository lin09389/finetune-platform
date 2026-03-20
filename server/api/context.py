"""
项目上下�?API

提供项目扫描、索引、检索等功能�?HTTP 接口
以及上下文理解增强功能（代词消解、省略补全、对话摘要、窗口管理）
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

from context.service import get_context_service, ContextService
from context.models import ProjectInfo, ContextResult
from core.context_understanding import (
    get_context_engine,
    ContextUnderstandingEngine,
    Message,
    ConversationSummary
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["项目上下�?])  # 移除 prefix，由 main.py 统一添加


# ============ 请求/响应模型 ============

class ScanRequest(BaseModel):
    """扫描项目请求"""
    project_path: str = Field(..., description="项目根路�?)


class ScanResponse(BaseModel):
    """扫描项目响应"""
    success: bool
    project: Optional[Dict[str, Any]] = None
    message: str = ""


class IndexRequest(BaseModel):
    """索引项目请求"""
    project_path: str = Field(..., description="项目根路�?)
    force_reindex: bool = Field(default=False, description="是否强制重新索引")


class IndexResponse(BaseModel):
    """索引项目响应"""
    success: bool
    summary: Optional[Dict[str, Any]] = None
    message: str = ""


class RetrieveRequest(BaseModel):
    """检索上下文请求"""
    query: str = Field(..., description="查询文本")
    project_path: Optional[str] = Field(None, description="项目路径")
    top_k: int = Field(default=5, ge=1, le=20, description="返回结果数量")


class RetrieveResponse(BaseModel):
    """检索上下文响应"""
    success: bool
    context: List[Dict[str, Any]]
    project_info: Optional[Dict[str, Any]] = None


class RemoveRequest(BaseModel):
    """移除项目请求"""
    project_path: str = Field(..., description="项目根路�?)


# ============ API 端点 ============

@router.post("/scan", response_model=ScanResponse)
async def scan_project(
    request: ScanRequest,
    service: ContextService = Depends(get_context_service)
):
    """
    扫描项目

    - 检测技术栈
    - 分析项目结构
    - 解析依赖
    - 识别关键文件
    """
    try:
        project_info = service.scan_project(request.project_path)

        return ScanResponse(
            success=True,
            project=project_info.model_dump(),
            message=f"扫描完成：{project_info.name}"
        )
    except FileNotFoundError as e:
        return ScanResponse(
            success=False,
            message=str(e)
        )
    except Exception as e:
        logger.error(f"扫描项目失败：{e}", exc_info=True)
        return ScanResponse(
            success=False,
            message=f"扫描失败：{str(e)}"
        )


@router.post("/index", response_model=IndexResponse)
async def index_project(
    request: IndexRequest,
    service: ContextService = Depends(get_context_service)
):
    """
    索引项目

    - 提取代码符号
    - 向量化存�?    - 构建 searchable 索引
    """
    try:
        summary = service.index_project(
            project_path=request.project_path,
            force_reindex=request.force_reindex
        )

        return IndexResponse(
            success=True,
            summary=summary,
            message=f"索引完成：{summary.get('files_indexed', 0)} 个文�?
        )
    except Exception as e:
        logger.error(f"索引项目失败：{e}", exc_info=True)
        return IndexResponse(
            success=False,
            message=f"索引失败：{str(e)}"
        )


@router.post("/retrieve", response_model=RetrieveResponse)
async def retrieve_context(
    request: RetrieveRequest,
    service: ContextService = Depends(get_context_service)
):
    """
    检索项目上下文

    根据查询文本检索最相关的代码文件和项目信息
    """
    try:
        results = service.retrieve(
            query=request.query,
            project_path=request.project_path,
            top_k=request.top_k
        )

        # 获取项目信息
        project_info = None
        if request.project_path and request.project_path in service.projects:
            project_info = service.projects[request.project_path].model_dump()

        return RetrieveResponse(
            success=True,
            context=[r.model_dump() for r in results],
            project_info=project_info
        )
    except Exception as e:
        logger.error(f"检索上下文失败：{e}", exc_info=True)
        return RetrieveResponse(
            success=False,
            context=[],
            message=f"检索失败：{str(e)}"
        )


@router.get("/projects")
async def list_projects(
    service: ContextService = Depends(get_context_service)
):
    """列出已索引的项目"""
    try:
        projects = service.list_projects()
        return {
            "success": True,
            "projects": projects
        }
    except Exception as e:
        logger.error(f"列出项目失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取失败：{str(e)}")


@router.post("/remove")
async def remove_project(
    request: RemoveRequest,
    service: ContextService = Depends(get_context_service)
):
    """移除项目索引"""
    try:
        success = service.remove_project(request.project_path)
        return {
            "success": success,
            "message": "已移�? if success else "移除失败"
        }
    except Exception as e:
        logger.error(f"移除项目失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"移除失败：{str(e)}")


@router.get("/project/{project_path:path}/stats")
async def get_project_stats(
    project_path: str,
    service: ContextService = Depends(get_context_service)
):
    """获取项目统计信息"""
    try:
        # URL 编码的路径需要解�?        import urllib.parse
        decoded_path = urllib.parse.unquote(project_path)

        stats = service.get_project_stats(decoded_path)

        if stats:
            return {
                "success": True,
                "stats": stats
            }
        else:
            return {
                "success": False,
                "message": "项目未找�?
            }
    except Exception as e:
        logger.error(f"获取统计失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取失败：{str(e)}")


# ============ 聊天集成辅助端点 ============

class ChatContextRequest(BaseModel):
    """聊天上下文请�?""
    query: str = Field(..., description="用户问题")
    project_path: Optional[str] = Field(None, description="项目路径")
    max_length: int = Field(default=2000, description="最大上下文长度")


class ChatContextResponse(BaseModel):
    """聊天上下文响�?""
    success: bool
    context: str = Field(..., description="格式化的上下�?)
    has_context: bool = Field(..., description="是否有相关上下文")


@router.post("/chat-context", response_model=ChatContextResponse)
async def get_chat_context(
    request: ChatContextRequest,
    service: ContextService = Depends(get_context_service)
):
    """
    获取聊天用的上下�?
    用于集成到聊天接口中，自动注入项目上下文
    """
    try:
        context = service.get_context_for_chat(
            query=request.query,
            project_path=request.project_path,
            max_length=request.max_length
        )

        return ChatContextResponse(
            success=True,
            context=context,
            has_context=bool(context)
        )
    except Exception as e:
        logger.error(f"获取聊天上下文失败：{e}", exc_info=True)
        return ChatContextResponse(
            success=False,
            context="",
            has_context=False
        )


# ============ 上下文理解增强端�?============

class ProcessMessageRequest(BaseModel):
    """处理消息请求"""
    message: str = Field(..., description="当前消息内容")
    role: str = Field(default="user", description="消息角色")
    history: List[Dict[str, Any]] = Field(default_factory=list, description="历史消息列表")


class ProcessMessageResponse(BaseModel):
    """处理消息响应"""
    success: bool
    original_text: str
    resolved_text: str
    pronoun_resolutions: List[Dict[str, Any]] = Field(default_factory=list)
    omission_completion: Dict[str, Any] = Field(default_factory=dict)
    entities: List[Dict[str, Any]] = Field(default_factory=list)


class EnhanceContextRequest(BaseModel):
    """增强上下文请�?""
    query: str = Field(..., description="用户查询")
    messages: List[Dict[str, Any]] = Field(default_factory=list, description="对话历史")
    max_context_tokens: int = Field(default=4096, description="最大上下文Token�?)


class EnhanceContextResponse(BaseModel):
    """增强上下文响�?""
    success: bool
    enhanced_query: str
    context_messages: List[Dict[str, Any]] = Field(default_factory=list)
    summary: Optional[str] = None
    entities: List[Dict[str, Any]] = Field(default_factory=list)
    pronoun_resolutions: List[Dict[str, Any]] = Field(default_factory=list)
    window_stats: Dict[str, Any] = Field(default_factory=dict)


class SummarizeRequest(BaseModel):
    """摘要请求"""
    messages: List[Dict[str, Any]] = Field(..., description="对话消息列表")
    max_length: int = Field(default=500, description="最大摘要长�?)
    use_llm: bool = Field(default=False, description="是否使用LLM生成摘要")


class SummarizeResponse(BaseModel):
    """摘要响应"""
    success: bool
    summary_text: str
    key_points: List[str] = Field(default_factory=list)
    entities_mentioned: List[str] = Field(default_factory=list)
    topics: List[str] = Field(default_factory=list)
    token_count: int
    message_range: List[int] = Field(default_factory=list)


class ManageWindowRequest(BaseModel):
    """窗口管理请求"""
    messages: List[Dict[str, Any]] = Field(..., description="消息列表")
    max_tokens: int = Field(default=4096, description="最大Token�?)
    keep_recent: int = Field(default=3, description="保留最近消息数")


class ManageWindowResponse(BaseModel):
    """窗口管理响应"""
    success: bool
    window_messages: List[Dict[str, Any]] = Field(default_factory=list)
    total_tokens: int
    max_tokens: int
    utilization: float
    overflow_count: int
    summary: Optional[str] = None


class ResolvePronounsRequest(BaseModel):
    """代词消解请求"""
    text: str = Field(..., description="待处理的文本")
    history: List[Dict[str, Any]] = Field(default_factory=list, description="历史消息")


class ResolvePronounsResponse(BaseModel):
    """代词消解响应"""
    success: bool
    original_text: str
    resolved_text: str
    resolutions: List[Dict[str, Any]] = Field(default_factory=list)


class CompleteOmissionRequest(BaseModel):
    """省略补全请求"""
    text: str = Field(..., description="待处理的文本")
    history: List[Dict[str, Any]] = Field(default_factory=list, description="历史消息")


class CompleteOmissionResponse(BaseModel):
    """省略补全响应"""
    success: bool
    original_text: str
    completed_text: str
    omitted_parts: List[str] = Field(default_factory=list)
    confidence: float
    source_message_idx: Optional[int] = None


def _convert_to_messages(message_dicts: List[Dict[str, Any]]) -> List[Message]:
    """将字典列表转换为Message对象列表"""
    messages = []
    for i, msg_dict in enumerate(message_dicts):
        msg = Message(
            id=msg_dict.get("id", f"msg_{i}"),
            role=msg_dict.get("role", "user"),
            content=msg_dict.get("content", ""),
            timestamp=msg_dict.get("timestamp", datetime.now().isoformat()),
            token_count=msg_dict.get("token_count", 0),
            importance=msg_dict.get("importance", 0.5),
            metadata=msg_dict.get("metadata", {})
        )
        messages.append(msg)
    return messages


def get_engine() -> ContextUnderstandingEngine:
    """获取上下文理解引�?""
    return get_context_engine()


@router.post("/understanding/process", response_model=ProcessMessageResponse)
async def process_message(
    request: ProcessMessageRequest,
    engine: ContextUnderstandingEngine = Depends(get_engine)
):
    """
    处理单条消息

    执行�?    - 代词消解
    - 省略补全
    - 实体提取
    """
    try:
        current_message = Message(
            id="current",
            role=request.role,
            content=request.message,
            timestamp=datetime.now().isoformat()
        )

        history = _convert_to_messages(request.history)

        result = engine.process_message(current_message, history)

        return ProcessMessageResponse(
            success=True,
            original_text=result["original_text"],
            resolved_text=result["resolved_text"],
            pronoun_resolutions=result["pronoun_resolutions"],
            omission_completion=result["omission_completion"],
            entities=result["entities"]
        )
    except Exception as e:
        logger.error(f"处理消息失败：{e}", exc_info=True)
        return ProcessMessageResponse(
            success=False,
            original_text=request.message,
            resolved_text=request.message,
            pronoun_resolutions=[],
            omission_completion={"original": request.message, "completed": request.message, "confidence": 0.0},
            entities=[]
        )


@router.post("/understanding/enhance", response_model=EnhanceContextResponse)
async def enhance_context(
    request: EnhanceContextRequest,
    engine: ContextUnderstandingEngine = Depends(get_engine)
):
    """
    增强上下�?
    综合处理�?    - 窗口管理
    - 代词消解
    - 省略补全
    - 摘要生成
    """
    try:
        messages = _convert_to_messages(request.messages)

        result = engine.enhance_context(messages, request.query)

        return EnhanceContextResponse(
            success=True,
            enhanced_query=result["enhanced_query"],
            context_messages=result["context_messages"],
            summary=result["summary"],
            entities=result["entities"],
            pronoun_resolutions=result["pronoun_resolutions"],
            window_stats=result["window_stats"]
        )
    except Exception as e:
        logger.error(f"增强上下文失败：{e}", exc_info=True)
        return EnhanceContextResponse(
            success=False,
            enhanced_query=request.query,
            context_messages=[],
            summary=None,
            entities=[],
            pronoun_resolutions=[],
            window_stats={"error": str(e)}
        )


@router.post("/understanding/summarize", response_model=SummarizeResponse)
async def summarize_conversation(
    request: SummarizeRequest,
    engine: ContextUnderstandingEngine = Depends(get_engine)
):
    """
    生成对话摘要

    支持�?    - 基于规则的摘�?    - LLM 摘要（可选）
    """
    try:
        messages = _convert_to_messages(request.messages)

        summary = engine.get_conversation_summary(
            messages,
            use_llm=request.use_llm
        )

        return SummarizeResponse(
            success=True,
            summary_text=summary.summary_text,
            key_points=summary.key_points,
            entities_mentioned=summary.entities_mentioned,
            topics=summary.topics,
            token_count=summary.token_count,
            message_range=list(summary.message_range)
        )
    except Exception as e:
        logger.error(f"生成摘要失败：{e}", exc_info=True)
        return SummarizeResponse(
            success=False,
            summary_text="",
            key_points=[],
            entities_mentioned=[],
            topics=[],
            token_count=0,
            message_range=[]
        )


@router.post("/understanding/window", response_model=ManageWindowResponse)
async def manage_context_window(
    request: ManageWindowRequest,
    engine: ContextUnderstandingEngine = Depends(get_engine)
):
    """
    管理上下文窗�?
    功能�?    - Token 预算管理
    - 滑动窗口策略
    - 溢出消息摘要
    """
    try:
        messages = _convert_to_messages(request.messages)

        result = engine.window_manager.manage_window(
            messages,
            keep_recent=request.keep_recent
        )

        return ManageWindowResponse(
            success=True,
            window_messages=[
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "importance": m.importance,
                    "timestamp": m.timestamp
                }
                for m in result["window_messages"]
            ],
            total_tokens=result["total_tokens"],
            max_tokens=result["max_tokens"],
            utilization=result["utilization"],
            overflow_count=result["overflow_count"],
            summary=result["summary"].summary_text if result["summary"] else None
        )
    except Exception as e:
        logger.error(f"管理窗口失败：{e}", exc_info=True)
        return ManageWindowResponse(
            success=False,
            window_messages=[],
            total_tokens=0,
            max_tokens=request.max_tokens,
            utilization=0.0,
            overflow_count=0,
            summary=None
        )


@router.post("/understanding/resolve-pronouns", response_model=ResolvePronounsResponse)
async def resolve_pronouns(
    request: ResolvePronounsRequest,
    engine: ContextUnderstandingEngine = Depends(get_engine)
):
    """
    代词消解

    识别并解析文本中的代词：
    - 人称代词（他、她、它�?    - 指示代词（这、那�?    """
    try:
        history = _convert_to_messages(request.history)

        resolved_text, resolutions = engine.pronoun_resolver.resolve_all(
            request.text, history
        )

        return ResolvePronounsResponse(
            success=True,
            original_text=request.text,
            resolved_text=resolved_text,
            resolutions=[
                {
                    "pronoun": r.pronoun,
                    "type": r.pronoun_type.value,
                    "resolved_to": r.resolved_entity.text if r.resolved_entity else None,
                    "confidence": r.confidence,
                    "position": list(r.position)
                }
                for r in resolutions
            ]
        )
    except Exception as e:
        logger.error(f"代词消解失败：{e}", exc_info=True)
        return ResolvePronounsResponse(
            success=False,
            original_text=request.text,
            resolved_text=request.text,
            resolutions=[]
        )


@router.post("/understanding/complete-omission", response_model=CompleteOmissionResponse)
async def complete_omission(
    request: CompleteOmissionRequest,
    engine: ContextUnderstandingEngine = Depends(get_engine)
):
    """
    省略补全

    检测并补全省略句：
    - 单字回答（是、对、好�?    - 简短确�?    """
    try:
        history = _convert_to_messages(request.history)

        completion = engine.omission_completer.complete_omission(
            request.text, history
        )

        return CompleteOmissionResponse(
            success=True,
            original_text=completion.original_text,
            completed_text=completion.completed_text,
            omitted_parts=completion.omitted_parts,
            confidence=completion.confidence,
            source_message_idx=completion.source_message_idx
        )
    except Exception as e:
        logger.error(f"省略补全失败：{e}", exc_info=True)
        return CompleteOmissionResponse(
            success=False,
            original_text=request.text,
            completed_text=request.text,
            omitted_parts=[],
            confidence=0.0,
            source_message_idx=None
        )


@router.get("/understanding/status")
async def get_understanding_status(
    engine: ContextUnderstandingEngine = Depends(get_engine)
):
    """获取上下文理解引擎状�?""
    return {
        "success": True,
        "status": {
            "window_manager": {
                "max_tokens": engine.window_manager.max_tokens,
                "reserved_tokens": engine.window_manager.reserved_tokens
            },
            "pronoun_resolver": {
                "personal_pronouns": len(engine.pronoun_resolver.PERSONAL_PRONOUNS),
                "demonstrative_pronouns": len(engine.pronoun_resolver.DEMONSTRATIVE_PRONOUNS),
                "entity_patterns": sum(len(p) for p in engine.pronoun_resolver.ENTITY_PATTERNS.values())
            },
            "omission_completer": {
                "patterns": len(engine.omission_completer.OMISSION_PATTERNS),
                "question_patterns": len(engine.omission_completer.QUESTION_PATTERNS)
            },
            "summarizer": {
                "keyword_weights": len(engine.summarizer.KEYWORD_WEIGHTS),
                "llm_enabled": engine.summarizer.llm_client is not None
            }
        }
    }
