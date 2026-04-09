import logging
import urllib.parse
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from context.service import ContextService, get_context_service
from core.context_understanding import ContextUnderstandingEngine, Message, get_context_engine

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Project Context"])


class ScanRequest(BaseModel):
    project_path: str | None = Field(default=None, description="Project root path")
    path: str | None = Field(default=None, description="Compatibility alias for project path")


class ScanResponse(BaseModel):
    success: bool
    project: dict[str, Any] | None = None
    message: str = ""


class IndexRequest(BaseModel):
    project_path: str | None = Field(default=None, description="Project root path")
    path: str | None = Field(default=None, description="Compatibility alias for project path")
    force_reindex: bool = False


class IndexResponse(BaseModel):
    success: bool
    summary: dict[str, Any] | None = None
    message: str = ""


class RetrieveRequest(BaseModel):
    query: str
    project_path: str | None = None
    path: str | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class RetrieveResponse(BaseModel):
    success: bool
    context: list[dict[str, Any]]
    project_info: dict[str, Any] | None = None


class RemoveRequest(BaseModel):
    project_path: str | None = None
    path: str | None = None


class ChatContextRequest(BaseModel):
    query: str
    project_path: str | None = None
    path: str | None = None
    max_length: int = 2000


class ChatContextResponse(BaseModel):
    success: bool
    context: str
    has_context: bool


class ProcessMessageRequest(BaseModel):
    message: str
    role: str = "user"
    history: list[dict[str, Any]] = Field(default_factory=list)


class ProcessMessageResponse(BaseModel):
    success: bool
    original_text: str
    resolved_text: str
    pronoun_resolutions: list[dict[str, Any]] = Field(default_factory=list)
    omission_completion: dict[str, Any] = Field(default_factory=dict)
    entities: list[dict[str, Any]] = Field(default_factory=list)


class EnhanceContextRequest(BaseModel):
    query: str
    messages: list[dict[str, Any]] = Field(default_factory=list)
    max_context_tokens: int = 4096


class EnhanceContextResponse(BaseModel):
    success: bool
    enhanced_query: str
    context_messages: list[dict[str, Any]] = Field(default_factory=list)
    summary: str | None = None
    entities: list[dict[str, Any]] = Field(default_factory=list)
    pronoun_resolutions: list[dict[str, Any]] = Field(default_factory=list)
    window_stats: dict[str, Any] = Field(default_factory=dict)


class SummarizeRequest(BaseModel):
    messages: list[dict[str, Any]]
    max_length: int = 500
    use_llm: bool = False


class SummarizeResponse(BaseModel):
    success: bool
    summary_text: str
    key_points: list[str] = Field(default_factory=list)
    entities_mentioned: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    token_count: int
    message_range: list[int] = Field(default_factory=list)


class ManageWindowRequest(BaseModel):
    messages: list[dict[str, Any]]
    max_tokens: int = 4096
    keep_recent: int = 3


class ManageWindowResponse(BaseModel):
    success: bool
    window_messages: list[dict[str, Any]] = Field(default_factory=list)
    total_tokens: int
    max_tokens: int
    utilization: float
    overflow_count: int
    summary: str | None = None


class ResolvePronounsRequest(BaseModel):
    text: str
    history: list[dict[str, Any]] = Field(default_factory=list)


class ResolvePronounsResponse(BaseModel):
    success: bool
    original_text: str
    resolved_text: str
    resolutions: list[dict[str, Any]] = Field(default_factory=list)


class CompleteOmissionRequest(BaseModel):
    text: str
    history: list[dict[str, Any]] = Field(default_factory=list)


class CompleteOmissionResponse(BaseModel):
    success: bool
    original_text: str
    completed_text: str
    omitted_parts: list[str] = Field(default_factory=list)
    confidence: float
    source_message_idx: int | None = None


def _convert_to_messages(message_dicts: list[dict[str, Any]]) -> list[Message]:
    messages: list[Message] = []
    for i, msg_dict in enumerate(message_dicts):
        messages.append(
            Message(
                id=msg_dict.get("id", f"msg_{i}"),
                role=msg_dict.get("role", "user"),
                content=msg_dict.get("content", ""),
                timestamp=msg_dict.get("timestamp", datetime.now().isoformat()),
                token_count=msg_dict.get("token_count", 0),
                importance=msg_dict.get("importance", 0.5),
                metadata=msg_dict.get("metadata", {}),
            )
        )
    return messages


def get_engine() -> ContextUnderstandingEngine:
    return get_context_engine()


def _resolve_project_path(request: Any) -> str:
    project_path = getattr(request, "project_path", None) or getattr(request, "path", None)
    if not project_path:
        raise HTTPException(status_code=400, detail="project_path or path is required")
    return project_path


@router.post("/scan", response_model=ScanResponse)
async def scan_project(request: ScanRequest, service: ContextService = Depends(get_context_service)):
    try:
        project_info = service.scan_project(_resolve_project_path(request))
        return ScanResponse(success=True, project=project_info.model_dump(), message=f"scanned: {project_info.name}")
    except FileNotFoundError as e:
        return ScanResponse(success=False, message=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("scan project failed: %s", e, exc_info=True)
        return ScanResponse(success=False, message=str(e))


@router.post("/index", response_model=IndexResponse)
async def index_project(request: IndexRequest, service: ContextService = Depends(get_context_service)):
    try:
        summary = service.index_project(project_path=_resolve_project_path(request), force_reindex=request.force_reindex)
        return IndexResponse(success=True, summary=summary, message=f"indexed {summary.get('files_indexed', 0)} files")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("index project failed: %s", e, exc_info=True)
        return IndexResponse(success=False, message=str(e))


@router.post("/retrieve", response_model=RetrieveResponse)
async def retrieve_context(request: RetrieveRequest, service: ContextService = Depends(get_context_service)):
    try:
        project_path = request.project_path or request.path
        results = service.retrieve(query=request.query, project_path=project_path, top_k=request.top_k)
        project_info = None
        if project_path and project_path in service.projects:
            project_info = service.projects[project_path].model_dump()
        return RetrieveResponse(success=True, context=[r.model_dump() for r in results], project_info=project_info)
    except Exception as e:
        logger.error("retrieve context failed: %s", e, exc_info=True)
        return RetrieveResponse(success=False, context=[], project_info=None)


@router.get("/projects")
async def list_projects(service: ContextService = Depends(get_context_service)):
    return {"success": True, "projects": service.list_projects()}


@router.post("/remove")
async def remove_project(request: RemoveRequest, service: ContextService = Depends(get_context_service)):
    project_path = _resolve_project_path(request)
    success = service.remove_project(project_path)
    return {"success": success, "message": "removed" if success else "not found"}


@router.get("/project/{project_path:path}/stats")
async def get_project_stats(project_path: str, service: ContextService = Depends(get_context_service)):
    decoded_path = urllib.parse.unquote(project_path)
    stats = service.get_project_stats(decoded_path)
    if stats is None:
        return {"success": False, "message": "project not found"}
    return {"success": True, "stats": stats}


@router.post("/chat-context", response_model=ChatContextResponse)
async def get_chat_context(request: ChatContextRequest, service: ContextService = Depends(get_context_service)):
    try:
        context = service.get_context_for_chat(query=request.query, project_path=request.project_path or request.path, max_length=request.max_length)
        return ChatContextResponse(success=True, context=context, has_context=bool(context))
    except Exception as e:
        logger.error("get chat context failed: %s", e, exc_info=True)
        return ChatContextResponse(success=False, context="", has_context=False)


@router.post("/understanding/process", response_model=ProcessMessageResponse)
async def process_message(request: ProcessMessageRequest, engine: ContextUnderstandingEngine = Depends(get_engine)):
    try:
        current_message = Message(id="current", role=request.role, content=request.message, timestamp=datetime.now().isoformat())
        history = _convert_to_messages(request.history)
        result = engine.process_message(current_message, history)
        return ProcessMessageResponse(
            success=True,
            original_text=result.get("original_text", request.message),
            resolved_text=result.get("resolved_text", request.message),
            pronoun_resolutions=result.get("pronoun_resolutions", []),
            omission_completion=result.get("omission_completion", {}),
            entities=result.get("entities", []),
        )
    except Exception as e:
        logger.error("process message failed: %s", e, exc_info=True)
        return ProcessMessageResponse(success=False, original_text=request.message, resolved_text=request.message, pronoun_resolutions=[], omission_completion={}, entities=[])


@router.post("/understanding/enhance", response_model=EnhanceContextResponse)
async def enhance_context(request: EnhanceContextRequest, engine: ContextUnderstandingEngine = Depends(get_engine)):
    try:
        messages = _convert_to_messages(request.messages)
        result = engine.enhance_context(messages, request.query)
        summary = result.get("summary")
        return EnhanceContextResponse(
            success=True,
            enhanced_query=result.get("enhanced_query", request.query),
            context_messages=result.get("context_messages", []),
            summary=summary,
            entities=result.get("entities", []),
            pronoun_resolutions=result.get("pronoun_resolutions", []),
            window_stats=result.get("window_stats", {}),
        )
    except Exception as e:
        logger.error("enhance context failed: %s", e, exc_info=True)
        return EnhanceContextResponse(success=False, enhanced_query=request.query, context_messages=[], summary=None, entities=[], pronoun_resolutions=[], window_stats={"error": str(e)})


@router.post("/understanding/summarize", response_model=SummarizeResponse)
async def summarize_conversation(request: SummarizeRequest, engine: ContextUnderstandingEngine = Depends(get_engine)):
    try:
        messages = _convert_to_messages(request.messages)
        summary = engine.get_conversation_summary(messages, use_llm=request.use_llm)
        return SummarizeResponse(
            success=True,
            summary_text=summary.summary_text,
            key_points=summary.key_points,
            entities_mentioned=summary.entities_mentioned,
            topics=summary.topics,
            token_count=summary.token_count,
            message_range=list(summary.message_range),
        )
    except Exception as e:
        logger.error("summarize conversation failed: %s", e, exc_info=True)
        return SummarizeResponse(success=False, summary_text="", key_points=[], entities_mentioned=[], topics=[], token_count=0, message_range=[])


@router.post("/understanding/window", response_model=ManageWindowResponse)
async def manage_context_window(request: ManageWindowRequest, engine: ContextUnderstandingEngine = Depends(get_engine)):
    try:
        messages = _convert_to_messages(request.messages)
        result = engine.window_manager.manage_window(messages, keep_recent=request.keep_recent)
        summary = result.get("summary")
        return ManageWindowResponse(
            success=True,
            window_messages=[
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "importance": m.importance,
                    "timestamp": m.timestamp,
                }
                for m in result.get("window_messages", [])
            ],
            total_tokens=result.get("total_tokens", 0),
            max_tokens=result.get("max_tokens", request.max_tokens),
            utilization=result.get("utilization", 0.0),
            overflow_count=result.get("overflow_count", 0),
            summary=summary.summary_text if hasattr(summary, "summary_text") else summary,
        )
    except Exception as e:
        logger.error("manage context window failed: %s", e, exc_info=True)
        return ManageWindowResponse(success=False, window_messages=[], total_tokens=0, max_tokens=request.max_tokens, utilization=0.0, overflow_count=0, summary=None)


@router.post("/understanding/resolve-pronouns", response_model=ResolvePronounsResponse)
async def resolve_pronouns(request: ResolvePronounsRequest, engine: ContextUnderstandingEngine = Depends(get_engine)):
    try:
        history = _convert_to_messages(request.history)
        resolved_text, resolutions = engine.pronoun_resolver.resolve_all(request.text, history)
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
                    "position": list(r.position),
                }
                for r in resolutions
            ],
        )
    except Exception as e:
        logger.error("resolve pronouns failed: %s", e, exc_info=True)
        return ResolvePronounsResponse(success=False, original_text=request.text, resolved_text=request.text, resolutions=[])


@router.post("/understanding/complete-omission", response_model=CompleteOmissionResponse)
async def complete_omission(request: CompleteOmissionRequest, engine: ContextUnderstandingEngine = Depends(get_engine)):
    try:
        history = _convert_to_messages(request.history)
        completion = engine.omission_completer.complete_omission(request.text, history)
        return CompleteOmissionResponse(
            success=True,
            original_text=completion.original_text,
            completed_text=completion.completed_text,
            omitted_parts=completion.omitted_parts,
            confidence=completion.confidence,
            source_message_idx=completion.source_message_idx,
        )
    except Exception as e:
        logger.error("complete omission failed: %s", e, exc_info=True)
        return CompleteOmissionResponse(success=False, original_text=request.text, completed_text=request.text, omitted_parts=[], confidence=0.0, source_message_idx=None)


@router.get("/understanding/status")
async def get_understanding_status(engine: ContextUnderstandingEngine = Depends(get_engine)):
    return {
        "success": True,
        "status": {
            "window_manager": {
                "max_tokens": getattr(engine.window_manager, "max_tokens", None),
                "reserved_tokens": getattr(engine.window_manager, "reserved_tokens", None),
            },
            "pronoun_resolver": {
                "personal_pronouns": len(getattr(engine.pronoun_resolver, "PERSONAL_PRONOUNS", {})),
                "demonstrative_pronouns": len(getattr(engine.pronoun_resolver, "DEMONSTRATIVE_PRONOUNS", {})),
            },
            "summarizer": {
                "llm_enabled": getattr(getattr(engine, "summarizer", None), "llm_client", None) is not None,
            },
        },
    }
