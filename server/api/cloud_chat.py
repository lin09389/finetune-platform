"""
云端 AI 聊天 API

支持 Minimax、GLM 等云端服务商
安全增强：
- API Key 加密存储
- 审计日志记录
"""
import json
import logging
import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ai.gateway import AnthropicMessagesProvider, OpenAICompatibleProvider, get_provider, list_providers
from api.types import KnowledgeSource, MemoryContextInfo, UnifiedContextInfo
from security.audit_log import audit_logger
from security.encryption import secure_storage

logger = logging.getLogger(__name__)

router = APIRouter(tags=["云端 AI"])

LOCAL_CLIENT_HOSTS = {"127.0.0.1", "::1", "localhost"}


class CloudChatRequest(BaseModel):
    """云端聊天请求"""
    provider: str = Field(..., description="服务商：minimax/glm")
    model: str | None = Field(None, description="模型名称")
    messages: list[dict[str, Any]] = Field(..., description="消息列表")
    temperature: float = Field(default=0.7, ge=0, le=2, description="温度参数")
    max_tokens: int = Field(default=2000, ge=1, le=32000, description="最大生成 token 数")
    stream: bool = Field(default=False, description="是否流式输出")
    extra_params: dict[str, Any] | None = Field(default=None, description="额外参数")
    api_key: str | None = Field(None, description="API Key（可选，如未提供则从安全存储获取）")
    key_id: str | None = Field(None, description="Key ID（可选）")
    group_id: str | None = Field(None, description="Group ID（可选，用于 Minimax）")
    base_url: str | None = Field(None, description="自定义 Base URL（可选）")
    version: str | None = Field(None, description="版本标签（用于灰度分流）")
    system_prompt: str | None = Field(default=None, description="System prompt")
    attachments: list[dict[str, Any]] = Field(default_factory=list, description="Prompt attachments")
    response_format: str | None = Field(default=None, description="Response format")
    memory: dict[str, Any] | None = Field(default=None, description="记忆配置")
    knowledge: dict[str, Any] | None = Field(default=None, description="知识库配置")
    context: dict[str, Any] | None = Field(default=None, description="项目上下文配置")
    session: dict[str, Any] | None = Field(default=None, description="会话配置")


class CloudChatResponse(BaseModel):
    """云端聊天响应"""
    success: bool
    content: str
    provider: str
    model: str
    knowledge_sources: list[KnowledgeSource] | None = None
    retrieval_info: dict[str, Any] | None = None
    memory_context: MemoryContextInfo | None = None
    unified_context: UnifiedContextInfo | None = None
    raw_response: dict[str, Any] | None = None
    duration_ms: int | None = None


class ProviderInfo(BaseModel):
    """服务商信息"""
    id: str
    name: str
    description: str
    models: list[str]


class ProviderListResponse(BaseModel):
    """服务商列表响应"""
    providers: list[ProviderInfo]


class APIKeyRequest(BaseModel):
    """API Key 请求"""
    provider: str = Field(..., description="服务商唯一标识")
    api_key: str = Field("", description="API Key 明文；编辑已有供应商时可留空以保留旧 Key")
    group_id: str | None = Field(None, description="Group ID（可选，用于 Minimax）")
    base_url: str | None = Field(None, description="自定义 Base URL（可选）")
    name: str | None = Field(None, description="可选的名称")
    note: str | None = Field(None, description="备注")
    official_url: str | None = Field(None, description="官网链接")
    interface_format: str = Field("openai-compatible", description="接口格式")
    default_model: str | None = Field(None, description="默认模型")
    models: list[str] = Field(default_factory=list, description="模型列表")


class APIKeyResponse(BaseModel):
    """API Key 响应"""
    success: bool
    message: str
    provider: str


class APIKeyStatus(BaseModel):
    """API Key 状态"""
    provider: str
    has_key: bool
    masked_key: str | None = None
    has_group_id: bool = False


def require_local_request(request: Request) -> None:
    client_host = request.client.host if request.client else ""
    if client_host and client_host not in LOCAL_CLIENT_HOSTS:
        raise HTTPException(status_code=403, detail="Cloud API key operations are only allowed from localhost")


def _mask_secret(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}...{value[-4:]}"


def _sanitize_error_message(message: str, *secrets: str | None) -> str:
    sanitized = message
    for secret in secrets:
        if secret:
            sanitized = sanitized.replace(secret, _mask_secret(secret))
    return sanitized


def _custom_provider_ids() -> list[str]:
    index = secure_storage.get("cloud_custom_provider_index") or {}
    ids = index.get("providers", [])
    return [provider_id for provider_id in ids if isinstance(provider_id, str)]


def _save_custom_provider_id(provider_id: str) -> None:
    ids = set(_custom_provider_ids())
    ids.add(provider_id)
    secure_storage.store("cloud_custom_provider_index", {"providers": sorted(ids)})


def _delete_custom_provider_id(provider_id: str) -> None:
    ids = [item for item in _custom_provider_ids() if item != provider_id]
    secure_storage.store("cloud_custom_provider_index", {"providers": ids})


def _custom_provider_infos() -> list[dict[str, Any]]:
    providers: list[dict[str, Any]] = []
    for provider_id in _custom_provider_ids():
        key_data = secure_storage.get(f"cloud_{provider_id}_key") or {}
        if not key_data:
            continue
        providers.append({
            "id": provider_id,
            "name": key_data.get("name") or provider_id,
            "description": key_data.get("note") or "自定义云端模型供应商",
            "models": key_data.get("models") or ([key_data.get("default_model")] if key_data.get("default_model") else []),
            "interface_format": key_data.get("interface_format", "openai-compatible"),
            "official_url": key_data.get("official_url"),
            "base_url": key_data.get("base_url"),
        })
    return providers


def _resolve_provider_instance(
    provider_id: str,
    key_data: dict[str, Any],
    group_id: str = "",
    base_url: str = "",
    version: str = "",
):
    provider_instance = get_provider(
        provider_id,
        group_id=group_id or key_data.get("group_id", ""),
        base_url=base_url or key_data.get("base_url", ""),
        version=version,
    )
    if provider_instance is not None:
        return provider_instance

    interface_format = key_data.get("interface_format", "openai-compatible")
    provider_base_url = base_url or key_data.get("base_url", "")
    if interface_format in {"openai-compatible", "openai-chat-completions"} and provider_base_url:
        return OpenAICompatibleProvider(
            base_url=provider_base_url,
            default_model=key_data.get("default_model", ""),
        )
    if interface_format == "anthropic-messages":
        return AnthropicMessagesProvider(
            base_url=provider_base_url,
            default_model=key_data.get("default_model", ""),
        )
    return None


async def _build_cloud_context(request: CloudChatRequest) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    messages = [dict(message) for message in request.messages]
    if request.attachments:
        attachment_notes: list[str] = []
        image_attachments = [attachment for attachment in request.attachments if attachment.get("type") == "image"]

        for attachment in request.attachments:
            if attachment.get("type") == "image":
                continue

            snippet = (attachment.get("content") or "").strip()
            if len(snippet) > 2000:
                snippet = snippet[:2000] + "..."
            attachment_notes.append(
                f"[{attachment.get('name', 'attachment')}]\n{snippet or 'No readable text content provided.'}"
            )

        if attachment_notes and messages:
            for message in reversed(messages):
                if message.get("role") == "user":
                    message["content"] = (
                        f"{message.get('content', '').strip()}\n\nAttached context:\n\n"
                        + "\n\n".join(attachment_notes)
                    ).strip()
                    break

        if image_attachments:
            supports_image = request.provider == "glm" and request.model == "glm-4v"
            if not supports_image:
                raise HTTPException(
                    status_code=400,
                    detail="Image attachments currently require the GLM provider with the glm-4v model.",
                )

            for message in reversed(messages):
                if message.get("role") != "user":
                    continue

                image_blocks = []
                for attachment in image_attachments:
                    preview_url = attachment.get("preview_url") or attachment.get("content")
                    if preview_url:
                        image_blocks.append(
                            {
                                "type": "image_url",
                                "image_url": {"url": preview_url},
                            }
                        )

                message["content"] = [
                    {"type": "text", "text": message.get("content", "")},
                    *image_blocks,
                ]
                break

    last_user_message = next((msg.get("content", "") for msg in reversed(messages) if msg.get("role") == "user"), "")
    if isinstance(last_user_message, list):
        last_user_message = next(
            (
                part.get("text", "")
                for part in last_user_message
                if isinstance(part, dict) and part.get("type") == "text"
            ),
            "",
        )
    if not last_user_message:
        return messages, {}

    memory_options = request.memory or {}
    knowledge_options = request.knowledge or {}
    context_options = request.context or {}
    session_options = request.session or {}

    from context.unified_manager import ContextOptions, get_unified_context_manager

    manager = get_unified_context_manager()
    unified_context = await manager.build_context(
        query=last_user_message,
        user_id=session_options.get("user_id", "default"),
        session_id=session_options.get("session_id"),
        options=ContextOptions(
            use_memory=bool(memory_options.get("enabled", True) and memory_options.get("auto_retrieve", True)),
            use_knowledge=bool(knowledge_options.get("use_knowledge", False)),
            use_project_context=bool(context_options.get("use_context", False)),
            memory_top_k=int(memory_options.get("top_k", 3)),
            memory_include_types=memory_options.get("include_types"),
            knowledge_collection_id=knowledge_options.get("collection_id"),
            knowledge_top_k=int(knowledge_options.get("top_k", 5)),
            knowledge_auto_retrieve=bool(knowledge_options.get("auto_retrieve", True)),
            project_path=context_options.get("project_path"),
            project_max_length=int(context_options.get("max_context_length", 1500)),
        ),
    )

    metadata: dict[str, Any] = {}
    if unified_context.total_sources > 0:
        system_prompt = unified_context.build_system_prompt(
            base_prompt=request.system_prompt or "你是一个有帮助的 AI 助手。"
        )
        if messages and messages[0].get("role") == "system":
            messages[0]["content"] = f"{system_prompt}\n\n{messages[0].get('content', '')}".strip()
        else:
            messages.insert(0, {"role": "system", "content": system_prompt})

        if unified_context.knowledge_sources:
            metadata["knowledge_sources"] = [
                {
                    "id": source.id,
                    "source": source.source,
                    "score": source.score,
                    "content_preview": source.content[:100] + "..." if len(source.content) > 100 else source.content,
                }
                for source in unified_context.knowledge_sources
            ]
            metadata["retrieval_info"] = {
                "query": last_user_message,
                "method": "unified",
                "total_results": unified_context.knowledge_count,
                "retrieval_time": unified_context.knowledge_retrieval_time,
            }

        if unified_context.memory_count > 0:
            metadata["memory_context"] = {
                "retrieved": True,
                "sources_count": unified_context.memory_count,
                "context_preview": unified_context.context_text[:200] if unified_context.context_text else "",
            }

        metadata["unified_context"] = {
            "total_sources": unified_context.total_sources,
            "memory_count": unified_context.memory_count,
            "knowledge_count": unified_context.knowledge_count,
            "project_count": unified_context.project_count,
            "retrieval_time": unified_context.retrieval_time,
        }

    if request.system_prompt and (
        not messages or messages[0].get("role") != "system"
    ):
        messages.insert(0, {"role": "system", "content": request.system_prompt})

    return messages, metadata


@router.get("/providers", response_model=ProviderListResponse, dependencies=[Depends(require_local_request)])
async def get_providers():
    """获取支持的云端 AI 服务商列表"""
    providers = [*list_providers(), *_custom_provider_infos()]

    provider_list = [
        ProviderInfo(
            id=p.get("id", "unknown"),
            name=p.get("name", "Unknown"),
            description=p.get("description", ""),
            models=p.get("models", [])
        )
        for p in providers
    ]

    return ProviderListResponse(providers=provider_list)


@router.post("/chat", response_model=CloudChatResponse, dependencies=[Depends(require_local_request)])
async def cloud_chat(request: CloudChatRequest):
    """云端 AI 聊天"""
    try:
        start_time = time.time()
        api_key = request.api_key
        group_id = request.group_id or ""
        base_url = request.base_url or ""

        if not api_key:
            key_data = secure_storage.get(f"cloud_{request.provider}_key")
            if key_data:
                api_key = key_data.get("api_key", "")
                group_id = group_id or key_data.get("group_id", "")
                base_url = base_url or key_data.get("base_url", "")

        if not api_key:
            raise HTTPException(status_code=400, detail=f"未配置 {request.provider} 的 API Key")

        key_data = secure_storage.get(f"cloud_{request.provider}_key") or {}
        provider = _resolve_provider_instance(
            request.provider,
            key_data,
            group_id=group_id,
            base_url=base_url,
            version=request.version or "",
        )

        if provider is None:
            raise HTTPException(status_code=400, detail=f"不支持的服务商：{request.provider}")

        model = request.model or key_data.get("default_model") or provider.get_default_model()
        messages, metadata = await _build_cloud_context(request)

        response = await provider.chat(
            messages=messages,
            model=model,
            api_key=api_key,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            extra_params=request.extra_params
        )

        audit_logger.log(
            action="cloud_chat",
            params={
                "provider": request.provider,
                "model": model,
                "message_count": len(request.messages)
            },
            result={"success": True}
        )

        return CloudChatResponse(
            success=True,
            content=response.get("content", ""),
            provider=request.provider,
            model=model,
            knowledge_sources=[KnowledgeSource(**source) for source in metadata.get("knowledge_sources", [])] or None,
            retrieval_info=metadata.get("retrieval_info"),
            memory_context=MemoryContextInfo(**metadata["memory_context"]) if metadata.get("memory_context") else None,
            unified_context=UnifiedContextInfo(**metadata["unified_context"]) if metadata.get("unified_context") else None,
            raw_response=response,
            duration_ms=int((time.time() - start_time) * 1000),
        )

    except HTTPException:
        raise
    except Exception as e:
        safe_error = _sanitize_error_message(str(e), request.api_key)
        logger.error("云端聊天失败：%s", safe_error)

        audit_logger.log(
            action="cloud_chat",
            params={"provider": request.provider},
            result={"success": False, "error": safe_error}
        )

        raise HTTPException(status_code=500, detail=f"聊天失败：{safe_error}")


@router.post("/chat/stream", dependencies=[Depends(require_local_request)])
async def cloud_chat_stream(request: CloudChatRequest):
    """云端 AI 流式聊天"""
    async def generate():
        try:
            start_time = time.time()
            # 获取 API Key（优先使用请求中的，否则从安全存储获取）
            api_key = request.api_key
            group_id = request.group_id or ""
            base_url = request.base_url or ""

            if not api_key:
                # 从安全存储获取
                key_data = secure_storage.get(f"cloud_{request.provider}_key")
                if key_data:
                    api_key = key_data.get("api_key", "")
                    group_id = group_id or key_data.get("group_id", "")
                    base_url = base_url or key_data.get("base_url", "")

            if not api_key:
                yield f"data: {json.dumps({'error': f'未配置 {request.provider} 的 API Key，请先在设置中配置'})}\n\n"
                return

            key_data = secure_storage.get(f"cloud_{request.provider}_key") or {}
            provider = _resolve_provider_instance(
                request.provider,
                key_data,
                group_id=group_id,
                base_url=base_url,
                version=request.version or "",
            )

            if provider is None:
                yield f"data: {json.dumps({'error': f'不支持的服务商：{request.provider}'})}\n\n"
                return

            model = request.model or key_data.get("default_model") or provider.get_default_model()
            messages, metadata = await _build_cloud_context(request)
            if metadata:
                yield f"data: {json.dumps({'type': 'metadata', 'model': model, 'backend': 'cloud', **metadata}, ensure_ascii=False)}\n\n"
            yield ": stream-ready\n\n"

            async for chunk in provider.chat_stream(
                messages=messages,
                model=model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                extra_params=request.extra_params,
                api_key=api_key
            ):
                if isinstance(chunk, dict):
                    if "error" in chunk:
                        yield f"data: {json.dumps({'type': 'error', 'error': chunk.get('error')}, ensure_ascii=False)}\n\n"
                        continue
                    if "content" in chunk:
                        text = chunk.get("content", "")
                        if text:
                            yield f"data: {json.dumps({'type': 'delta', 'content': text}, ensure_ascii=False)}\n\n"
                        continue
                elif isinstance(chunk, str):
                    if chunk:
                        yield f"data: {json.dumps({'type': 'delta', 'content': chunk}, ensure_ascii=False)}\n\n"
                    continue
                else:
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                    continue

            last_user_message = next(
                (message.get("content", "") for message in reversed(request.messages) if message.get("role") == "user"),
                "",
            )
            if request.memory and request.memory.get("enabled", True) and request.memory.get("auto_extract", True) and last_user_message:
                try:
                    from context.unified_manager import get_unified_context_manager

                    manager = get_unified_context_manager()
                    session_options = request.session or {}
                    await manager.extract_and_store_memory(
                        message=last_user_message,
                        role="user",
                        user_id=session_options.get("user_id", "default"),
                        session_id=session_options.get("session_id"),
                    )
                except Exception as memory_error:
                    logger.warning(f"cloud chat memory extraction failed: {memory_error}")

            yield f"data: {json.dumps({'type': 'metadata', 'model': model, 'backend': 'cloud', 'duration_ms': int((time.time() - start_time) * 1000)}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as e:
            safe_error = _sanitize_error_message(str(e), request.api_key)
            logger.error("流式聊天失败：%s", safe_error)
            yield f"data: {json.dumps({'error': safe_error}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/api-keys", response_model=APIKeyResponse, dependencies=[Depends(require_local_request)])
async def set_api_key(request: APIKeyRequest):
    """设置服务商 API Key（加密存储）"""
    try:
        existing_key_data = secure_storage.get(f"cloud_{request.provider}_key") or {}
        api_key = request.api_key.strip() if request.api_key else existing_key_data.get("api_key", "")
        if not api_key:
            raise HTTPException(status_code=400, detail="新增供应商时必须填写 API Key")

        key_data = {
            "api_key": api_key,
            "name": request.name or request.provider,
            "created_at": existing_key_data.get("created_at") or datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "note": request.note or "",
            "official_url": request.official_url or "",
            "interface_format": request.interface_format,
            "default_model": request.default_model or (request.models[0] if request.models else ""),
            "models": request.models,
        }

        if request.group_id:
            key_data["group_id"] = request.group_id

        if request.base_url:
            key_data["base_url"] = request.base_url

        secure_storage.store(f"cloud_{request.provider}_key", key_data)
        built_in_ids = {provider.get("id") for provider in list_providers()}
        if request.provider not in built_in_ids:
            _save_custom_provider_id(request.provider)

        audit_logger.log(
            action="set_api_key",
            params={"provider": request.provider},
            result={"success": True}
        )

        return APIKeyResponse(
            success=True,
            message="API Key 已安全存储",
            provider=request.provider
        )

    except HTTPException:
        raise
    except Exception as e:
        safe_error = _sanitize_error_message(str(e), request.api_key)
        logger.error("存储 API Key 失败：%s", safe_error)
        raise HTTPException(status_code=500, detail=f"存储失败：{safe_error}")


@router.get("/api-keys/{provider}", response_model=APIKeyStatus, dependencies=[Depends(require_local_request)])
async def get_api_key_status(provider: str):
    """获取 API Key 状态"""
    try:
        key_data = secure_storage.get(f"cloud_{provider}_key")

        if key_data is None:
            return APIKeyStatus(
                provider=provider,
                has_key=False
            )

        masked_key = _mask_secret(key_data.get("api_key", "")) or None

        return APIKeyStatus(
            provider=provider,
            has_key=True,
            masked_key=masked_key,
            has_group_id=bool(key_data.get("group_id"))
        )

    except Exception as e:
        logger.error(f"获取 API Key 状态失败：{e}")
        return APIKeyStatus(provider=provider, has_key=False)


@router.get("/api-keys", dependencies=[Depends(require_local_request)])
async def list_api_keys():
    """列出所有已保存的 API Key"""
    try:
        keys = []
        providers = sorted({
            provider.get("id")
            for provider in [*list_providers(), *_custom_provider_infos()]
            if provider.get("id")
        })

        for provider in providers:
            key_data = secure_storage.get(f"cloud_{provider}_key")
            if key_data:
                masked_key = _mask_secret(key_data.get("api_key", "")) or None

                keys.append({
                    "id": provider,
                    "provider": provider,
                    "name": key_data.get("name") or provider,
                    "created_at": key_data.get("created_at") or "",
                    "masked_key": masked_key,
                    "has_group_id": bool(key_data.get("group_id")),
                    "note": key_data.get("note") or "",
                    "official_url": key_data.get("official_url") or "",
                    "interface_format": key_data.get("interface_format") or "native",
                    "base_url": key_data.get("base_url") or "",
                    "default_model": key_data.get("default_model") or "",
                    "models": key_data.get("models") or [],
                })

        return {"keys": keys}

    except Exception as e:
        logger.error(f"获取 API Key 列表失败：{e}")
        return {"keys": []}


@router.get("/api-keys/{provider}/data", dependencies=[Depends(require_local_request)])
async def get_api_key_data(provider: str):
    """获取 API Key 详细数据"""
    try:
        key_data = secure_storage.get(f"cloud_{provider}_key")
        if key_data:
            # 不返回 API Key 明文
            return {
                "group_id": key_data.get("group_id"),
                "base_url": key_data.get("base_url"),
                "name": key_data.get("name"),
                "note": key_data.get("note"),
                "official_url": key_data.get("official_url"),
                "interface_format": key_data.get("interface_format"),
                "default_model": key_data.get("default_model"),
                "models": key_data.get("models") or [],
            }
        return {}
    except Exception as e:
        logger.error(f"获取 API Key 数据失败：{e}")
        return {}


@router.delete("/api-keys/{provider}", dependencies=[Depends(require_local_request)])
async def delete_api_key(provider: str):
    """删除 API Key"""
    try:
        secure_storage.delete(f"cloud_{provider}_key")
        _delete_custom_provider_id(provider)

        audit_logger.log(
            action="delete_api_key",
            params={"provider": provider},
            result={"success": True}
        )

        return {"success": True, "message": "API Key 已删除"}

    except Exception as e:
        logger.error(f"删除 API Key 失败：{e}")
        raise HTTPException(status_code=500, detail=f"删除失败：{str(e)}")


@router.post("/test/{provider}", dependencies=[Depends(require_local_request)])
async def test_provider(provider: str, group_id: str = "", base_url: str = "", version: str = ""):
    """测试服务商连接"""
    try:
        key_data = secure_storage.get(f"cloud_{provider}_key") or {}
        provider_instance = _resolve_provider_instance(provider, key_data, group_id=group_id, base_url=base_url, version=version)

        if provider_instance is None:
            raise HTTPException(status_code=400, detail=f"不支持的服务商：{provider}")

        api_key = key_data.get("api_key", "")
        if not api_key:
            raise HTTPException(status_code=400, detail=f"未配置 {provider} 的 API Key")
        model = key_data.get("default_model") or provider_instance.get_default_model()
        response = await provider_instance.chat(
            messages=[{"role": "user", "content": "Hi"}],
            model=model,
            api_key=api_key,
            max_tokens=8,
            temperature=0,
        )

        return {
            "success": True,
            "provider": provider,
            "message": "连接成功",
            "latency_ms": 0,
            "model": response.get("model", model),
        }

    except HTTPException:
        raise
    except Exception as e:
        api_key = (secure_storage.get(f"cloud_{provider}_key") or {}).get("api_key", "")
        safe_error = _sanitize_error_message(str(e), api_key)
        logger.error("测试服务商连接失败：%s", safe_error)
        raise HTTPException(status_code=500, detail=f"测试失败：{safe_error}")


@router.get("/models/{provider}", dependencies=[Depends(require_local_request)])
async def list_models(provider: str, group_id: str = "", base_url: str = "", version: str = ""):
    """获取服务商支持的模型列表"""
    try:
        key_data = secure_storage.get(f"cloud_{provider}_key") or {}
        provider_instance = _resolve_provider_instance(provider, key_data, group_id=group_id, base_url=base_url, version=version)

        if provider_instance is None:
            raise HTTPException(status_code=400, detail=f"不支持的服务商：{provider}")

        models = provider_instance.list_models()

        return {
            "provider": provider,
            "models": models
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取模型列表失败：{e}")
        raise HTTPException(status_code=500, detail=f"获取失败：{str(e)}")


@router.post("/completions", dependencies=[Depends(require_local_request)])
async def cloud_completions(request: CloudChatRequest):
    """兼容 OpenAI 格式的补全接口"""
    return await cloud_chat(request)
