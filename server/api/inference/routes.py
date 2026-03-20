"""
推理模块路由 - 参�?Ollama server/routes.go 设计模式
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import Optional, List, Dict, Any
import logging
import time
import asyncio

from api.types import (
    ChatRequest, ChatResponse, GenerateRequest, GenerateResponse,
    BackendListResponse, BackendInfo, BackendSwitchRequest,
    ModelInfo, HealthCheckResponse, StreamChunk, TokenUsage,
    Message, MessageRole, KnowledgeSource
)
from api.errors import (
    APIError, InvalidInputError, MaliciousInputError,
    OllamaNotRunningError, ModelNotFoundError
)
from api.inference.scheduler import get_scheduler, BackendType
from core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter()

settings = get_settings()

PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions?",
    r"ignore\s+(all\s+)?(the\s+)?above",
    r"disregard\s+(all\s+)?previous",
    r"forget\s+(all\s+)?(previous\s+)?instructions?",
    r"you\s+are\s+now\s+",
    r"new\s+instructions?:",
    r"system:\s*you\s+are",
    r"<\|im_start\|>system",
    r"jailbreak",
    r"dan\s+mode",
    r"developer\s+mode",
    r"sudo\s+mode",
]

MAX_MESSAGE_LENGTH = 10000
MAX_MESSAGES_COUNT = 100


def detect_prompt_injection(text: str) -> bool:
    """检测潜在的 Prompt 注入"""
    import re
    text_lower = text.lower()
    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            logger.warning(f"检测到潜在�?Prompt 注入: {pattern}")
            return True
    return False


def sanitize_input(text: str) -> str:
    """清理输入文本"""
    if not text:
        return text
    text = text.strip()
    if len(text) > MAX_MESSAGE_LENGTH:
        text = text[:MAX_MESSAGE_LENGTH]
    return text


@router.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest):
    """生成文本 - 参�?Ollama /api/generate"""
    start_time = time.time()
    
    if not request.prompt or not request.prompt.strip():
        raise InvalidInputError("prompt", "提示内容不能为空")
    
    if detect_prompt_injection(request.prompt):
        raise MaliciousInputError()
    
    request.prompt = sanitize_input(request.prompt)
    
    try:
        scheduler = get_scheduler()
        backend = await scheduler.get_backend(request.options.backend)
        
        response = await backend.generate(request)
        return response
        
    except APIError:
        raise
    except Exception as e:
        logger.error(f"生成失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"生成失败: {str(e)}")


@router.post("/generate/stream")
async def generate_stream(request: GenerateRequest):
    """流式生成 - 参�?Ollama 流式生成"""
    if not request.prompt or not request.prompt.strip():
        raise InvalidInputError("prompt", "提示内容不能为空")
    
    if detect_prompt_injection(request.prompt):
        raise MaliciousInputError()
    
    request.prompt = sanitize_input(request.prompt)
    
    try:
        scheduler = get_scheduler()
        backend = await scheduler.get_backend(request.options.backend)
        
        return StreamingResponse(
            backend.generate_stream(request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
        
    except APIError:
        raise
    except Exception as e:
        logger.error(f"流式生成失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"流式生成失败: {str(e)}")


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """聊天对话 - 参�?Ollama /api/chat"""
    start_time = time.time()
    
    if not request.messages or len(request.messages) == 0:
        raise InvalidInputError("messages", "消息列表不能为空")
    
    if len(request.messages) > MAX_MESSAGES_COUNT:
        raise InvalidInputError("messages", f"消息数量超过限制（最�?{MAX_MESSAGES_COUNT} 条）")
    
    for msg in request.messages:
        if not msg.content or not msg.content.strip():
            raise InvalidInputError("messages", "消息内容不能为空")
        
        if detect_prompt_injection(msg.content):
            raise MaliciousInputError()
        
        msg.content = sanitize_input(msg.content)
    
    system_prompt = ""
    knowledge_sources_response = None
    retrieval_info = None
    
    last_user_message = request.get_last_user_message()
    
    if request.knowledge.use_knowledge and request.knowledge.collection_id and last_user_message:
        try:
            from context.knowledge_integration import get_knowledge_integrator
            
            integrator = get_knowledge_integrator()
            
            should_retrieve, reason = integrator.should_retrieve_knowledge(
                query=last_user_message,
                collection_id=request.knowledge.collection_id,
                force_retrieve=not request.knowledge.auto_retrieve
            )
            
            if should_retrieve:
                retrieval_result = integrator.retrieve_knowledge(
                    query=last_user_message,
                    collection_id=request.knowledge.collection_id,
                    top_k=request.knowledge.top_k
                )
                
                if retrieval_result.sources:
                    knowledge_context = retrieval_result.context
                    system_prompt = f"""你是一个有帮助�?AI 助手。请基于以下参考资料回答用户的问题�?
参考资�?
{knowledge_context}

请注�?
1. 优先使用参考资料中的信息回�?2. 如果参考资料中没有相关信息，请明确说明
3. 引用具体内容时，请标注来源编号（�?[参考资�?1]�?4. 保持回答简洁、准确、有帮助"""
                    
                    knowledge_sources_response = [
                        KnowledgeSource(
                            id=s.id,
                            source=s.source,
                            score=s.score,
                            content_preview=s.content[:100] + "..." if len(s.content) > 100 else s.content
                        )
                        for s in retrieval_result.sources
                    ]
                    
                    retrieval_info = {
                        "query": retrieval_result.query,
                        "method": retrieval_result.retrieval_method,
                        "total_results": retrieval_result.total_results,
                        "retrieval_time": retrieval_result.retrieval_time
                    }
                    
        except Exception as e:
            logger.warning(f"知识库检索失�? {e}")
    
    if not system_prompt and request.context.use_context and request.context.project_path:
        try:
            from context.service import get_context_service
            from rag.embedder import get_embedder
            from rag.vector_store import get_vector_store
            
            if last_user_message:
                embedder = get_embedder()
                vector_store = get_vector_store()
                context_service = get_context_service(embedder=embedder, vector_store=vector_store)
                
                context = context_service.get_context_for_chat(
                    query=last_user_message,
                    project_path=request.context.project_path,
                    max_length=request.context.max_context_length
                )
                
                if context:
                    system_prompt = f"""你是一个有帮助�?AI 助手，正在协助用户开发项目�?
项目上下文：
{context}

请根据以上项目信息，给用户一个有帮助的回答�?如果问题与项目相关，请考虑项目的技术栈、架构和代码风格�?"""
                    
        except Exception as e:
            logger.warning(f"获取项目上下文失�? {e}")
    
    try:
        scheduler = get_scheduler()
        backend = await scheduler.get_backend(request.options.backend)
        
        if system_prompt:
            from api.inference.backends.base import InferenceContext
            context = InferenceContext(
                model_id=request.model,
                prompt="",
                system_prompt=system_prompt,
                messages=request.messages,
                temperature=request.options.temperature,
                top_p=request.options.top_p,
                top_k=request.options.top_k,
                max_tokens=request.options.max_tokens,
                repetition_penalty=request.options.repetition_penalty,
            )
            response = await backend.chat(request, context)
        else:
            response = await backend.chat(request)
        
        if knowledge_sources_response and request.knowledge.include_sources:
            from context.knowledge_integration import get_knowledge_integrator
            integrator = get_knowledge_integrator()
            from context.knowledge_integration import KnowledgeSource as KSSource
            sources = [
                KSSource(
                    id=s.id,
                    content=s.content_preview,
                    source=s.source,
                    score=s.score
                )
                for s in knowledge_sources_response
            ]
            response.message.content = integrator.enhance_response_with_sources(
                response=response.message.content,
                sources=sources,
                include_citation=True
            )
        
        response.knowledge_sources = knowledge_sources_response
        response.retrieval_info = retrieval_info
        
        return response
        
    except APIError:
        raise
    except Exception as e:
        logger.error(f"聊天失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"聊天失败: {str(e)}")


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """流式聊天"""
    if not request.messages or len(request.messages) == 0:
        raise InvalidInputError("messages", "消息列表不能为空")
    
    for msg in request.messages:
        if detect_prompt_injection(msg.content):
            raise MaliciousInputError()
        msg.content = sanitize_input(msg.content)
    
    try:
        scheduler = get_scheduler()
        backend = await scheduler.get_backend(request.options.backend)
        
        if hasattr(backend, 'chat_stream'):
            return StreamingResponse(
                backend.chat_stream(request),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )
        else:
            return StreamingResponse(
                backend.generate_stream(GenerateRequest(
                    model=request.model,
                    prompt=request.messages[-1].content,
                    options=request.options
                )),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )
        
    except APIError:
        raise
    except Exception as e:
        logger.error(f"流式聊天失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"流式聊天失败: {str(e)}")


@router.get("/models")
async def list_models(backend: Optional[str] = Query(None, description="后端类型")):
    """列出可用模型 - 参�?Ollama /api/tags"""
    try:
        scheduler = get_scheduler()
        models = await scheduler.list_models(backend)
        return {"models": models}
    except Exception as e:
        logger.error(f"获取模型列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取模型列表失败: {str(e)}")


@router.get("/backends", response_model=BackendListResponse)
async def list_backends():
    """列出可用后端"""
    scheduler = get_scheduler()
    
    backends = [
        BackendInfo(
            id=BackendType.HUGGINGFACE.value,
            name="HuggingFace (本地模型)",
            available=await scheduler.is_backend_available(BackendType.HUGGINGFACE.value),
            description="使用下载�?HuggingFace 模型"
        ),
        BackendInfo(
            id=BackendType.OLLAMA.value,
            name="Ollama",
            available=await scheduler.is_backend_available(BackendType.OLLAMA.value),
            description="Ollama 本地部署"
        ),
    ]
    
    return BackendListResponse(
        current=scheduler._default_backend,
        backends=backends
    )


@router.post("/backends/switch")
async def switch_backend(request: BackendSwitchRequest):
    """切换推理后端"""
    try:
        scheduler = get_scheduler()
        scheduler.set_default_backend(request.backend)
        return {"message": f"已切换到 {request.backend}", "current": request.backend}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/cache/status")
async def get_cache_status():
    """获取缓存状�?""
    scheduler = get_scheduler()
    return await scheduler.get_stats()


@router.post("/cache/clear")
async def clear_cache():
    """清除模型缓存"""
    scheduler = get_scheduler()
    await scheduler.unload_all()
    return {"message": "模型缓存已清�?}


@router.get("/ollama/status")
async def get_ollama_status():
    """获取 Ollama 状�?""
    scheduler = get_scheduler()
    available = await scheduler.is_backend_available(BackendType.OLLAMA.value)
    
    models = []
    if available:
        try:
            ollama_models = await scheduler.list_models(BackendType.OLLAMA.value)
            models = [{"name": m.get("name", ""), "size": m.get("size", 0)} for m in ollama_models]
        except Exception:
            pass
    
    return {
        "running": available,
        "base_url": settings.ollama_base_url,
        "models": models
    }


@router.get("/performance")
async def get_performance_stats(model_id: Optional[str] = Query(None)):
    """获取性能统计"""
    from core.performance import get_performance_monitor
    
    monitor = get_performance_monitor()
    stats = monitor.get_stats(model_id)
    streaming_stats = monitor.get_streaming_stats()
    
    return {
        "inference": stats,
        "streaming": streaming_stats,
    }


@router.get("/performance/recommendations")
async def get_performance_recommendations():
    """获取性能优化建议"""
    from core.performance import get_performance_monitor
    from core.utils import get_device_info
    
    monitor = get_performance_monitor()
    device_info = get_device_info()
    vram_total = device_info.get("memory_total", 0)
    
    recommendations = monitor.get_recommendations(vram_total)
    
    return {
        "recommendations": recommendations,
        "device_info": device_info,
    }
