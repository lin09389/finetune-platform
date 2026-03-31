"""
推理引擎 API 路由
集成重构后的推理引擎模块
"""
import asyncio
import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.inference.engine_base import ChatMessage, ChatRequest, InferenceRequest
from core.inference.engine_factory import get_engine, get_engine_factory

router = APIRouter(prefix="/inference-engine", tags=["Inference Engine"])


class GenerateRequest(BaseModel):
    """生成请求"""
    model_id: str
    prompt: str
    max_tokens: int = Field(default=1024, ge=1, le=8192)
    temperature: float = Field(default=0.7, ge=0, le=2)
    top_p: float = Field(default=0.9, ge=0, le=1)
    top_k: int = Field(default=50, ge=1)
    repetition_penalty: float = Field(default=1.1, ge=0.1, le=2)
    backend: str | None = None


class ChatGenerateRequest(BaseModel):
    """聊天生成请求"""
    model_id: str
    messages: list[dict[str, str]]
    max_tokens: int = Field(default=1024, ge=1, le=8192)
    temperature: float = Field(default=0.7, ge=0, le=2)
    top_p: float = Field(default=0.9, ge=0, le=1)
    system_prompt: str | None = None
    backend: str | None = None


@router.get("/engines")
async def list_engines():
    """列出可用引擎"""
    factory = get_engine_factory()

    engines = []
    for name in factory.get_registered_engines():
        try:
            engine = factory.get_or_create(name)
            engines.append({
                "name": name,
                "backend": engine.backend.value,
                "available": engine.is_available(),
                "supports_streaming": engine.supports_streaming(),
                "supports_chat": engine.supports_chat(),
            })
        except Exception as e:
            engines.append({
                "name": name,
                "error": str(e),
            })

    return {
        "engines": engines,
        "default_engine": factory._default_engine,
    }


@router.get("/engines/{engine_name}")
async def get_engine_info(engine_name: str):
    """获取引擎详情"""
    factory = get_engine_factory()

    if engine_name not in factory.get_registered_engines():
        raise HTTPException(status_code=404, detail=f"Engine not found: {engine_name}")

    engine = factory.get_or_create(engine_name)

    return {
        "name": engine_name,
        "backend": engine.backend.value,
        "display_name": engine.name,
        "available": engine.is_available(),
        "models": engine.get_available_models(),
        "stats": engine.get_stats(),
    }


@router.post("/generate")
async def generate_text(request: GenerateRequest):
    """生成文本"""
    engine = get_engine(request.backend)

    inference_request = InferenceRequest(
        model_id=request.model_id,
        prompt=request.prompt,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        top_p=request.top_p,
        top_k=request.top_k,
        repetition_penalty=request.repetition_penalty,
    )

    try:
        response = await engine.generate(inference_request)
        return response.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat")
async def chat_generate(request: ChatGenerateRequest):
    """聊天生成"""
    engine = get_engine(request.backend)

    messages = [
        ChatMessage(role=m["role"], content=m["content"])
        for m in request.messages
    ]

    chat_request = ChatRequest(
        model_id=request.model_id,
        messages=messages,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        top_p=request.top_p,
        system_prompt=request.system_prompt,
    )

    try:
        response = await engine.chat(chat_request)
        return response.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stream")
async def stream_generate(request: GenerateRequest):
    """流式生成"""
    engine = get_engine(request.backend)

    if not engine.supports_streaming():
        raise HTTPException(status_code=400, detail="Engine does not support streaming")

    inference_request = InferenceRequest(
        model_id=request.model_id,
        prompt=request.prompt,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        top_p=request.top_p,
        top_k=request.top_k,
        repetition_penalty=request.repetition_penalty,
    )

    async def generate_stream():
        try:
            async for chunk in engine.stream(inference_request):
                data = {
                    "content": chunk.content,
                    "done": chunk.done,
                    "tokens_so_far": chunk.tokens_so_far,
                    "finish_reason": chunk.finish_reason,
                }
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
    )


@router.post("/models/{model_id}/load")
async def load_model(
    model_id: str,
    backend: str | None = None,
    load_in_8bit: bool = False,
    load_in_4bit: bool = False,
):
    """加载模型"""
    engine = get_engine(backend)

    success = engine.load_model(
        model_id,
        load_in_8bit=load_in_8bit,
        load_in_4bit=load_in_4bit,
    )

    if success:
        return {"success": True, "model_id": model_id}
    else:
        raise HTTPException(status_code=500, detail=f"Failed to load model: {model_id}")


@router.delete("/models/{model_id}")
async def unload_model(model_id: str, backend: str | None = None):
    """卸载模型"""
    engine = get_engine(backend)

    success = engine.unload_model(model_id)

    if success:
        return {"success": True, "model_id": model_id}
    else:
        raise HTTPException(status_code=500, detail=f"Failed to unload model: {model_id}")


@router.get("/models/{model_id}/info")
async def get_model_info(model_id: str, backend: str | None = None):
    """获取模型信息"""
    engine = get_engine(backend)

    info = engine.get_model_info(model_id)

    if info:
        return info
    else:
        raise HTTPException(status_code=404, detail=f"Model not found: {model_id}")


@router.get("/stats")
async def get_inference_stats():
    """获取推理统计"""
    factory = get_engine_factory()
    return factory.get_stats()
