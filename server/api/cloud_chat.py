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

from ai.gateway import list_providers
from api.types import KnowledgeSource, MemoryContextInfo, UnifiedContextInfo
from agent_session.service import AgentSessionService
from agent_session.project_chat import DeepAgentsProjectChatRunner, ProjectChatResult, can_use_deepagents_project_chat
from context.deepagents import build_deepagents_context_pack
from security.audit_log import audit_logger
from security.auth_middleware import get_current_user_optional
from security.encryption import secure_storage
from security.jwt_auth import TokenPayload
from cloud_models import CloudModelService, CloudProviderRepository
from cloud_models.resolver import resolve_provider

logger = logging.getLogger(__name__)

router = APIRouter(tags=["云端 AI"])
cloud_model_service = CloudModelService(CloudProviderRepository(secure_storage))

LOCAL_CLIENT_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


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
    streaming_status: str | None = None
    streaming_supported: bool | None = None


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
    streaming_status: str | None = None
    streaming_supported: bool | None = None
    streaming_tested_at: str | None = None
    streaming_error: str | None = None


def require_local_request(request: Request) -> None:
    client_host = request.client.host if request.client else ""
    if client_host and client_host not in LOCAL_CLIENT_HOSTS:
        # Tests and non-networked API clients often run without a client host.
        # Only block explicit non-local remote callers.
        raise HTTPException(status_code=403, detail="Cloud API key operations are only allowed from localhost")


def _extract_source_ip(request: Request) -> str | None:
    """从 Request 中提取来源 IP，兼容反向代理 X-Forwarded-For。"""
    forwarded = request.headers.get("x-forwarded-for") if request else None
    if forwarded:
        # X-Forwarded-For 可能是逗号分隔的链条，取第一个
        return forwarded.split(",")[0].strip() or None
    if request and request.client and request.client.host:
        return request.client.host
    return None


def _audit_user_id(current_user: TokenPayload | None) -> str | None:
    """从可选的 JWT 上下文中解析 user_id / username，None 表示匿名本地调用。

    该函数需能容忍非 FastAPI 调用路径下 ``current_user`` 仍是 ``Depends``
    对象或其它非 TokenPayload 值的场景（例如现存的 pytest 直接调用协程）。
    """
    if not isinstance(current_user, TokenPayload):
        return None
    return current_user.username or getattr(current_user, "user_id", None)


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


def _sse_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _format_deep_context(context_options: dict[str, Any]) -> str:
    active_context = context_options.get("active_context") if isinstance(context_options, dict) else None
    explicit_context = context_options.get("explicit_context") if isinstance(context_options, dict) else None
    sections: list[str] = []
    if isinstance(active_context, dict):
        file_path = active_context.get("file_path") or "unknown"
        cursor = active_context.get("cursor") or {}
        selection = active_context.get("selection") or {}
        lines = [
            f"Current file: {file_path}",
            f"Cursor: line {cursor.get('line', 1)}, column {cursor.get('column', 1)}",
        ]
        selected_text = str(selection.get("text") or "").strip() if isinstance(selection, dict) else ""
        if selected_text:
            lines.append("Selected code:\n```text\n" + selected_text[:4000] + "\n```")
        else:
            preview = str(active_context.get("content_preview") or "").strip()
            if preview:
                lines.append("File preview:\n```text\n" + preview[:4000] + "\n```")
        sections.append("\n".join(lines))
    mention_lines: list[str] = []
    if isinstance(explicit_context, list):
        for item in explicit_context:
            if not isinstance(item, dict):
                continue
            label = item.get("label") or item.get("path") or "context"
            kind = item.get("type") or "context"
            path = item.get("path")
            line = item.get("line")
            location = f"{path or ''}{':' + str(line) if line else ''}".strip()
            mention_lines.append(f"- @{label} ({kind}) {location}".strip())
            content = str(item.get("content") or "").strip()
            if content:
                mention_lines.append(f"  context: {content[:1200]}")
    if mention_lines:
        sections.append("Explicit @ context:\n" + "\n".join(mention_lines))
    return "Deep Context Retrieval:\n" + "\n\n".join(sections) if sections else ""


def _last_user_text(messages: list[dict[str, Any]]) -> str:
    last_user_message = next((msg.get("content", "") for msg in reversed(messages) if msg.get("role") == "user"), "")
    if isinstance(last_user_message, list):
        return next(
            (
                str(part.get("text", ""))
                for part in last_user_message
                if isinstance(part, dict) and part.get("type") == "text"
            ),
            "",
        )
    return str(last_user_message or "")


def _validated_cloud_project_path(project_path: str | None) -> str:
    value = str(project_path or "").strip()
    if not value:
        return ""
    try:
        return AgentSessionService().validate_project_path(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _should_use_deepagents_project_chat(request: CloudChatRequest, model: str, context_options: dict[str, Any]) -> bool:
    project_path = str(context_options.get("project_path") or "").strip()
    if not project_path:
        return False
    if not bool(context_options.get("use_context", False)):
        return False
    if context_options.get("project_chat") is not True:
        return False
    return can_use_deepagents_project_chat(request.provider, model)


async def _build_project_chat_context_files(
    *,
    goal: str,
    context_options: dict[str, Any],
    project_path: str,
    session_options: dict[str, Any],
) -> tuple[str, dict[str, str], dict[str, Any]]:
    pack = await build_deepagents_context_pack(
        goal=goal,
        active_context=context_options.get("active_context"),
        explicit_context=context_options.get("explicit_context") or [],
        project_path=project_path,
        session_id=session_options.get("session_id"),
        user_id=session_options.get("user_id", "default"),
    )
    return pack.prompt, pack.files, pack.metadata


async def _try_project_chat(
    request: CloudChatRequest,
    *,
    model: str,
    api_key: str | None,
    base_url: str | None,
) -> ProjectChatResult | None:
    context_options = request.context or {}
    session_options = request.session or {}
    if not _should_use_deepagents_project_chat(request, model, context_options):
        return None
    project_path = _validated_cloud_project_path(context_options.get("project_path"))
    goal = _last_user_text(request.messages)
    if not goal:
        return None
    try:
        prompt, context_files, pack_metadata = await _build_project_chat_context_files(
            goal=goal,
            context_options=context_options,
            project_path=project_path,
            session_options=session_options,
        )
        messages = [dict(message) for message in request.messages]
        for message in reversed(messages):
            if message.get("role") == "user":
                message["content"] = prompt
                break
        runner = DeepAgentsProjectChatRunner(
            provider=request.provider,
            model=model,
            project_path=project_path,
            metadata={
                "api_key": api_key,
                "base_url": base_url,
                "model_params": request.extra_params or {},
            },
        )
        result = await runner.run(messages, context_files=context_files)
        result.metadata["deep_context"] = pack_metadata
        return result
    except Exception:
        logger.debug("DeepAgents project chat unavailable; falling back to regular cloud chat", exc_info=True)
        return None


def _custom_provider_ids() -> list[str]:
    return cloud_model_service.repository.custom_provider_ids()


def _save_custom_provider_id(provider_id: str) -> None:
    cloud_model_service.repository.add_custom_provider_id(provider_id)


def _delete_custom_provider_id(provider_id: str) -> None:
    cloud_model_service.repository.remove_custom_provider_id(provider_id)


def _custom_provider_infos() -> list[dict[str, Any]]:
    providers: list[dict[str, Any]] = []
    for provider_id in _custom_provider_ids():
        key_data = cloud_model_service.repository.get(provider_id)
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
            "streaming_status": key_data.get("streaming_status") or "untested",
            "streaming_supported": key_data.get("streaming_supported"),
        })
    return providers


def _streaming_metadata_from_key(key_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "streaming_status": key_data.get("streaming_status") or "untested",
        "streaming_supported": key_data.get("streaming_supported"),
        "streaming_tested_at": key_data.get("streaming_tested_at"),
        "streaming_error": key_data.get("streaming_error") or "",
        "streaming_chunks": key_data.get("streaming_chunks"),
        "streaming_model": key_data.get("streaming_model") or "",
    }


def _merge_streaming_metadata(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in _streaming_metadata_from_key(source).items():
        if value is not None and value != "":
            target[key] = value


def _resolve_provider_instance(
    provider_id: str,
    key_data: dict[str, Any],
    group_id: str = "",
    base_url: str = "",
    version: str = "",
):
    return resolve_provider(provider_id, key_data, group_id=group_id, base_url=base_url, version=version)


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

    from context.builder import get_context_builder
    from context.budget import ContextBuildOptions

    project_path = context_options.get("project_path")
    use_project_context = bool(context_options.get("use_context", False))
    if use_project_context and not project_path:
        try:
            from context.service import get_context_service as _get_ctx_svc
            _ctx_svc = _get_ctx_svc()
            _registered = list(_ctx_svc.projects.keys()) if _ctx_svc else []
            if _registered:
                project_path = _registered[0]
                logger.info(f"project_path 为空，自动使用已注册项目: {project_path}")
            else:
                logger.warning("project_path 为空且无已注册项目，项目上下文将不可用。请先扫描并索引项目。")
        except Exception as _e:
            logger.warning(f"查找已注册项目失败: {_e}")
    if use_project_context and project_path:
        project_path = _validated_cloud_project_path(str(project_path))

    max_context_tokens = max(
        512,
        int(context_options.get("max_context_tokens") or 4096) - int(request.max_tokens or 0),
    )
    unified_context = await get_context_builder().build(
        query=last_user_message,
        user_id=session_options.get("user_id", "default"),
        session_id=session_options.get("session_id"),
        options=ContextBuildOptions(
            use_memory=bool(memory_options.get("enabled", True) and memory_options.get("auto_retrieve", True)),
            use_knowledge=bool(knowledge_options.get("use_knowledge", False)),
            use_project_context=use_project_context,
            max_context_tokens=max_context_tokens,
            reserved_output_tokens=int(request.max_tokens or 0),
            memory_top_k=int(memory_options.get("top_k", 3)),
            memory_include_types=memory_options.get("include_types"),
            knowledge_collection_id=knowledge_options.get("collection_id"),
            knowledge_top_k=int(knowledge_options.get("top_k", 5)),
            knowledge_auto_retrieve=bool(knowledge_options.get("auto_retrieve", True)),
            project_path=project_path,
            project_max_tokens=int(context_options.get("max_context_length", 1500)),
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

        context_payload = unified_context.to_dict()
        metadata["unified_context"] = {
            "total_sources": unified_context.total_sources,
            "memory_count": unified_context.memory_count,
            "knowledge_count": unified_context.knowledge_count,
            "project_count": unified_context.project_count,
            "retrieval_time": unified_context.retrieval_time,
            "budget": context_payload.get("budget"),
            "warnings": getattr(unified_context, "warnings", None) or None,
            "trace": context_payload.get("trace"),
        }

    if use_project_context and unified_context.project_count == 0:
        metadata.setdefault("context_warnings", []).append(
            "project_context_unavailable" if not project_path
            else "project_context_no_results"
        )

    deep_context_text = _format_deep_context(context_options)
    if deep_context_text:
        try:
            from context.service import get_context_service
            related = get_context_service().expand_deep_context(
                context_options.get("active_context"),
                context_options.get("explicit_context") or [],
                project_path,
            )
            if related:
                related_lines = [
                    f"- {item.get('relation')}: {item.get('path')} {':' + str(item.get('line')) if item.get('line') else ''}\n  {str(item.get('content') or '')[:800]}"
                    for item in related
                ]
                deep_context_text = f"{deep_context_text}\n\nDependency topology expansion:\n" + "\n".join(related_lines)
        except Exception:
            logger.debug("failed to expand cloud deep context topology", exc_info=True)
        system_prompt = f"{request.system_prompt or '你是一个有帮助的 AI 助手。'}\n\n{deep_context_text}"
        if messages and messages[0].get("role") == "system":
            messages[0]["content"] = f"{system_prompt}\n\n{messages[0].get('content', '')}".strip()
        else:
            messages.insert(0, {"role": "system", "content": system_prompt})
        metadata.setdefault("unified_context", {})
        metadata["unified_context"]["explicit_context_count"] = len(context_options.get("explicit_context") or [])
        metadata["unified_context"]["has_active_context"] = bool(context_options.get("active_context"))

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
        try:
            resolved = cloud_model_service.resolve(
                request.provider,
                model=request.model,
                api_key=request.api_key,
                group_id=request.group_id or "",
                base_url=request.base_url or "",
                version=request.version or "",
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        api_key, base_url, provider, model = resolved.api_key, resolved.base_url, resolved.provider, resolved.model
        project_chat = await _try_project_chat(request, model=model, api_key=api_key, base_url=base_url)
        if project_chat is not None:
            audit_logger.log(
                action="cloud_chat",
                params={
                    "provider": request.provider,
                    "model": model,
                    "message_count": len(request.messages),
                    "project_chat": True,
                },
                result={"success": True},
            )
            unified_context = {
                "total_sources": 0,
                "memory_count": 0,
                "knowledge_count": 0,
                "project_count": len(project_chat.metadata.get("project_chat_tools") or []),
                "retrieval_time": 0,
                "trace": {
                    "mode": "deepagents_project_chat",
                    "readonly": True,
                    "root": project_chat.metadata.get("project_chat_root"),
                    "tools": project_chat.metadata.get("project_chat_tools") or [],
                    "deep_context": project_chat.metadata.get("deep_context"),
                },
            }
            return CloudChatResponse(
                success=True,
                content=project_chat.content,
                provider=request.provider,
                model=model,
                unified_context=UnifiedContextInfo(**unified_context),
                raw_response={"project_chat": True, "readonly": True, "tools": project_chat.metadata.get("project_chat_tools") or []},
                duration_ms=int((time.time() - start_time) * 1000),
            )
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
            # Keep the resolver seam for existing SSE integrations while the
            # repository owns all persisted configuration access.
            key_data = cloud_model_service.repository.get(request.provider)
            api_key = str(request.api_key or key_data.get("api_key") or "")
            if not api_key:
                yield f"data: {_sse_json({'error': f'未配置 {request.provider} 的 API Key，请先在设置中配置'})}\n\n"
                return
            base_url = str(request.base_url or key_data.get("base_url") or "")
            provider = _resolve_provider_instance(
                request.provider,
                key_data,
                group_id=request.group_id or key_data.get("group_id", ""),
                base_url=base_url,
                version=request.version or "",
            )
            if provider is None:
                yield f"data: {_sse_json({'error': f'不支持的服务商：{request.provider}'})}\n\n"
                return
            model = request.model or key_data.get("default_model") or provider.get_default_model()
            context_options = request.context or {}
            session_options = request.session or {}
            if _should_use_deepagents_project_chat(request, model, context_options):
                project_path = _validated_cloud_project_path(context_options.get("project_path"))
                try:
                    goal = _last_user_text(request.messages)
                    prompt, context_files, pack_metadata = await _build_project_chat_context_files(
                        goal=goal,
                        context_options=context_options,
                        project_path=project_path,
                        session_options=session_options,
                    )
                    messages = [dict(message) for message in request.messages]
                    for message in reversed(messages):
                        if message.get("role") == "user":
                            message["content"] = prompt
                            break
                    runner = DeepAgentsProjectChatRunner(
                        provider=request.provider,
                        model=model,
                        project_path=project_path,
                        metadata={
                            "api_key": api_key,
                            "base_url": base_url,
                            "model_params": request.extra_params or {},
                        },
                    )
                    yield f"data: {_sse_json({'type': 'metadata', 'model': model, 'backend': 'cloud', 'project_chat': True, 'project_chat_readonly': True, 'deep_context': pack_metadata})}\n\n"
                    yield ": stream-ready\n\n"
                    async for event in runner.astream_events(messages, context_files=context_files):
                        if event.get("type") == "text_delta":
                            yield f"data: {json.dumps({'type': 'text_delta', 'content': event.get('content', '')}, ensure_ascii=False)}\n\n"
                        elif event.get("type") == "metadata":
                            yield f"data: {_sse_json({'type': 'metadata', 'model': model, 'backend': 'cloud', **event})}\n\n"
                    yield f"data: {json.dumps({'type': 'metadata', 'model': model, 'backend': 'cloud', 'duration_ms': int((time.time() - start_time) * 1000)}, ensure_ascii=False)}\n\n"
                    yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
                    yield "data: [DONE]\n\n"
                    return
                except Exception as project_chat_error:
                    logger.debug("DeepAgents project chat stream unavailable; falling back to regular cloud stream: %s", project_chat_error, exc_info=True)

            messages, metadata = await _build_cloud_context(request)
            if metadata:
                yield f"data: {_sse_json({'type': 'metadata', 'model': model, 'backend': 'cloud', **metadata})}\n\n"
            yield ": stream-ready\n\n"

            async for chunk in provider.chat_stream(
                messages=messages,
                model=model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                extra_params=request.extra_params,
                api_key=api_key
            ):
                event = provider.emit_event(chunk) if hasattr(provider, 'emit_event') else None
                if event is not None:
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    continue
                if isinstance(chunk, dict):
                    if "error" in chunk:
                        yield f"data: {json.dumps({'type': 'error', 'error': chunk.get('error')}, ensure_ascii=False)}\n\n"
                        continue
                    event_type = chunk.get("type")
                    if event_type in {"workflow_event", "tool_call_started", "tool_call_completed", "tool_call_failed", "approval_needed", "approval_granted"}:
                        payload = dict(chunk)
                        payload.setdefault("type", event_type)
                        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                        continue
                    if "content" in chunk:
                        text = chunk.get("content", "")
                        if text:
                            yield f"data: {json.dumps({'type': 'text_delta', 'content': text}, ensure_ascii=False)}\n\n"
                        continue
                elif isinstance(chunk, str):
                    if chunk:
                        yield f"data: {json.dumps({'type': 'text_delta', 'content': chunk}, ensure_ascii=False)}\n\n"
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
                    from memory.service import extract_and_store_memory

                    session_options = request.session or {}
                    await extract_and_store_memory(
                        message=last_user_message,
                        role="user",
                        user_id=session_options.get("user_id", "default"),
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
async def set_api_key(
    request: APIKeyRequest,
    http_request: Request,
    current_user: TokenPayload | None = Depends(get_current_user_optional),
):
    """设置服务商 API Key（加密存储）"""
    try:
        existing_key_data = cloud_model_service.repository.get(request.provider)
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
        _merge_streaming_metadata(key_data, existing_key_data)

        if request.group_id:
            key_data["group_id"] = request.group_id

        if request.base_url:
            key_data["base_url"] = request.base_url

        built_in_ids = {provider.get("id") for provider in list_providers()}
        cloud_model_service.repository.save(
            request.provider,
            key_data,
            custom=request.provider not in built_in_ids,
        )

        audit_logger.log(
            action="set_api_key",
            params={"provider": request.provider},
            result={"success": True},
            user_id=_audit_user_id(current_user),
            source_ip=_extract_source_ip(http_request) if http_request else None,
            resource_type="cloud_api_key",
            resource_id=request.provider,
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
        key_data = cloud_model_service.repository.get(provider)

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
            has_group_id=bool(key_data.get("group_id")),
            streaming_status=key_data.get("streaming_status") or "untested",
            streaming_supported=key_data.get("streaming_supported"),
            streaming_tested_at=key_data.get("streaming_tested_at"),
            streaming_error=key_data.get("streaming_error") or "",
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
            key_data = cloud_model_service.repository.get(provider)
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
                    **_streaming_metadata_from_key(key_data),
                })

        return {"keys": keys}

    except Exception as e:
        logger.error(f"获取 API Key 列表失败：{e}")
        return {"keys": []}


@router.get("/api-keys/{provider}/data", dependencies=[Depends(require_local_request)])
async def get_api_key_data(provider: str):
    """获取 API Key 详细数据"""
    try:
        key_data = cloud_model_service.repository.get(provider)
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
                **_streaming_metadata_from_key(key_data),
            }
        return {}
    except Exception as e:
        logger.error(f"获取 API Key 数据失败：{e}")
        return {}


@router.delete("/api-keys/{provider}", dependencies=[Depends(require_local_request)])
async def delete_api_key(
    provider: str,
    http_request: Request,
    current_user: TokenPayload | None = Depends(get_current_user_optional),
):
    """删除 API Key"""
    try:
        cloud_model_service.repository.delete(provider)

        audit_logger.log(
            action="delete_api_key",
            params={"provider": provider},
            result={"success": True},
            user_id=_audit_user_id(current_user),
            source_ip=_extract_source_ip(http_request) if http_request else None,
            resource_type="cloud_api_key",
            resource_id=provider,
        )

        return {"success": True, "message": "API Key 已删除"}

    except Exception as e:
        logger.error(f"删除 API Key 失败：{e}")
        raise HTTPException(status_code=500, detail=f"删除失败：{str(e)}")


@router.post("/test/{provider}", dependencies=[Depends(require_local_request)])
async def test_provider(provider: str, group_id: str = "", base_url: str = "", version: str = ""):
    """测试服务商连接"""
    try:
        key_data = cloud_model_service.repository.get(provider)
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
        api_key = cloud_model_service.repository.get(provider).get("api_key", "")
        safe_error = _sanitize_error_message(str(e), api_key)
        logger.error("测试服务商连接失败：%s", safe_error)
        raise HTTPException(status_code=500, detail=f"测试失败：{safe_error}")


@router.post("/test/{provider}/stream", dependencies=[Depends(require_local_request)])
async def test_provider_stream(provider: str, group_id: str = "", base_url: str = "", version: str = ""):
    """测试服务商是否能返回真实流式增量。"""
    key_data = cloud_model_service.repository.get(provider)
    api_key = key_data.get("api_key", "")
    if not api_key:
        raise HTTPException(status_code=400, detail=f"未配置 {provider} 的 API Key")

    provider_instance = _resolve_provider_instance(provider, key_data, group_id=group_id, base_url=base_url, version=version)
    if provider_instance is None:
        raise HTTPException(status_code=400, detail=f"不支持的服务商：{provider}")

    model = key_data.get("default_model") or provider_instance.get_default_model()
    started = time.time()
    chunks = 0
    preview = ""
    status = "failed"
    supported = False
    error = ""

    try:
        async for chunk in provider_instance.chat_stream(
            messages=[{"role": "user", "content": "请只输出：stream-ok"}],
            model=model,
            api_key=api_key,
            max_tokens=24,
            temperature=0,
            timeout=30,
        ):
            content = str(chunk.get("content") or "")
            if not content:
                continue
            chunks += 1
            preview += content
            if chunks >= 8 or len(preview) >= 48:
                break
        supported = chunks > 0
        status = "supported" if supported else "unsupported"
        if not supported:
            error = "provider.chat_stream 未返回任何 content delta"
    except Exception as exc:
        error = _sanitize_error_message(str(exc), api_key)
        logger.error("测试服务商流式能力失败：%s", error)

    updated_key_data = dict(key_data)
    updated_key_data.update({
        "streaming_status": status,
        "streaming_supported": supported,
        "streaming_tested_at": datetime.now().isoformat(),
        "streaming_error": error,
        "streaming_chunks": chunks,
        "streaming_model": model,
    })
    cloud_model_service.repository.update(provider, **updated_key_data)

    response = {
        "success": supported,
        "provider": provider,
        "model": model,
        "message": "流式测试通过" if supported else "流式测试未通过",
        "streaming_status": status,
        "streaming_supported": supported,
        "streaming_tested_at": updated_key_data["streaming_tested_at"],
        "streaming_error": error,
        "streaming_chunks": chunks,
        "streaming_preview": preview[:80],
        "latency_ms": int((time.time() - started) * 1000),
    }
    if not supported:
        raise HTTPException(status_code=502, detail=response)
    return response


@router.get("/models/{provider}", dependencies=[Depends(require_local_request)])
async def list_models(provider: str, group_id: str = "", base_url: str = "", version: str = ""):
    """获取服务商支持的模型列表"""
    try:
        key_data = cloud_model_service.repository.get(provider)
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
