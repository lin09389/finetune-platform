"""
云端 AI 聊天 API

支持 Minimax、GLM 等云端服务商
安全增强：
- API Key 加密存储
- 审计日志记录
"""
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ai.gateway import get_provider, list_providers
from security.audit_log import audit_logger
from security.encryption import secure_storage

logger = logging.getLogger(__name__)

router = APIRouter(tags=["云端 AI"])


class CloudChatRequest(BaseModel):
    """云端聊天请求"""
    provider: str = Field(..., description="服务商：minimax/glm")
    model: str | None = Field(None, description="模型名称")
    messages: list[dict[str, str]] = Field(..., description="消息列表")
    temperature: float = Field(default=0.7, ge=0, le=2, description="温度参数")
    max_tokens: int = Field(default=2000, ge=1, le=32000, description="最大生成 token 数")
    stream: bool = Field(default=False, description="是否流式输出")
    extra_params: dict[str, Any] | None = Field(default=None, description="额外参数")
    api_key: str | None = Field(None, description="API Key（可选，如未提供则从安全存储获取）")
    key_id: str | None = Field(None, description="Key ID（可选）")
    group_id: str | None = Field(None, description="Group ID（可选，用于 Minimax）")
    base_url: str | None = Field(None, description="自定义 Base URL（可选）")
    version: str | None = Field(None, description="版本标签（用于灰度分流）")


class CloudChatResponse(BaseModel):
    """云端聊天响应"""
    success: bool
    content: str
    provider: str
    model: str


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
    provider: str = Field(..., description="服务商：minimax/glm")
    api_key: str = Field(..., description="API Key 明文")
    group_id: str | None = Field(None, description="Group ID（可选，用于 Minimax）")
    base_url: str | None = Field(None, description="自定义 Base URL（可选）")
    name: str | None = Field(None, description="可选的名称")


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


@router.get("/providers", response_model=ProviderListResponse)
async def get_providers():
    """获取支持的云端 AI 服务商列表"""
    providers = list_providers()

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


@router.post("/chat", response_model=CloudChatResponse)
async def cloud_chat(request: CloudChatRequest):
    """云端 AI 聊天"""
    try:
        provider = get_provider(
            request.provider,
            group_id=request.group_id or "",
            base_url=request.base_url or "",
            version=request.version or ""
        )

        if provider is None:
            raise HTTPException(status_code=400, detail=f"不支持的服务商：{request.provider}")

        model = request.model or provider.get_default_model()

        response = await provider.chat(
            messages=request.messages,
            model=model,
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
            model=model
        )

    except Exception as e:
        logger.error(f"云端聊天失败：{e}")

        audit_logger.log(
            action="cloud_chat",
            params={"provider": request.provider},
            result={"success": False, "error": str(e)}
        )

        raise HTTPException(status_code=500, detail=f"聊天失败：{str(e)}")


@router.post("/chat/stream")
async def cloud_chat_stream(request: CloudChatRequest):
    """云端 AI 流式聊天"""
    async def generate():
        try:
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

            provider = get_provider(
                request.provider,
                group_id=group_id,
                base_url=base_url,
                version=request.version or ""
            )

            if provider is None:
                yield f"data: {json.dumps({'error': f'不支持的服务商：{request.provider}'})}\n\n"
                return

            model = request.model or provider.get_default_model()

            async for chunk in provider.chat_stream(
                messages=request.messages,
                model=model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                extra_params=request.extra_params,
                api_key=api_key
            ):
                yield f"data: {json.dumps(chunk)}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"流式聊天失败：{e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.post("/api-keys", response_model=APIKeyResponse)
async def set_api_key(request: APIKeyRequest):
    """设置服务商 API Key（加密存储）"""
    try:
        key_data = {
            "api_key": request.api_key,
        }

        if request.group_id:
            key_data["group_id"] = request.group_id

        if request.base_url:
            key_data["base_url"] = request.base_url

        secure_storage.store(f"cloud_{request.provider}_key", key_data)

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

    except Exception as e:
        logger.error(f"存储 API Key 失败：{e}")
        raise HTTPException(status_code=500, detail=f"存储失败：{str(e)}")


@router.get("/api-keys/{provider}", response_model=APIKeyStatus)
async def get_api_key_status(provider: str):
    """获取 API Key 状态"""
    try:
        key_data = secure_storage.get(f"cloud_{provider}_key")

        if key_data is None:
            return APIKeyStatus(
                provider=provider,
                has_key=False
            )

        api_key = key_data.get("api_key", "")
        masked_key = None
        if api_key:
            masked_key = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "****"

        return APIKeyStatus(
            provider=provider,
            has_key=True,
            masked_key=masked_key,
            has_group_id=bool(key_data.get("group_id"))
        )

    except Exception as e:
        logger.error(f"获取 API Key 状态失败：{e}")
        return APIKeyStatus(provider=provider, has_key=False)


@router.get("/api-keys")
async def list_api_keys():
    """列出所有已保存的 API Key"""
    try:
        keys = []
        # 支持的服务商列表
        providers = ["minimax", "glm", "openai", "anthropic"]

        for provider in providers:
            key_data = secure_storage.get(f"cloud_{provider}_key")
            if key_data:
                api_key = key_data.get("api_key", "")
                masked_key = None
                if api_key:
                    masked_key = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "****"

                keys.append({
                    "id": provider,
                    "provider": provider,
                    "masked_key": masked_key,
                    "has_group_id": bool(key_data.get("group_id"))
                })

        return {"keys": keys}

    except Exception as e:
        logger.error(f"获取 API Key 列表失败：{e}")
        return {"keys": []}


@router.get("/api-keys/{provider}/data")
async def get_api_key_data(provider: str):
    """获取 API Key 详细数据"""
    try:
        key_data = secure_storage.get(f"cloud_{provider}_key")
        if key_data:
            # 不返回 API Key 明文
            return {
                "group_id": key_data.get("group_id"),
                "base_url": key_data.get("base_url")
            }
        return {}
    except Exception as e:
        logger.error(f"获取 API Key 数据失败：{e}")
        return {}


@router.delete("/api-keys/{provider}")
async def delete_api_key(provider: str):
    """删除 API Key"""
    try:
        secure_storage.delete(f"cloud_{provider}_key")

        audit_logger.log(
            action="delete_api_key",
            params={"provider": provider},
            result={"success": True}
        )

        return {"success": True, "message": "API Key 已删除"}

    except Exception as e:
        logger.error(f"删除 API Key 失败：{e}")
        raise HTTPException(status_code=500, detail=f"删除失败：{str(e)}")


@router.post("/test/{provider}")
async def test_provider(provider: str, group_id: str = "", base_url: str = "", version: str = ""):
    """测试服务商连接"""
    try:
        provider_instance = get_provider(provider, group_id=group_id, base_url=base_url, version=version)

        if provider_instance is None:
            raise HTTPException(status_code=400, detail=f"不支持的服务商：{provider}")

        result = await provider_instance.test_connection()

        return {
            "success": result.get("success", False),
            "provider": provider,
            "message": result.get("message", ""),
            "latency_ms": result.get("latency_ms", 0)
        }

    except Exception as e:
        logger.error(f"测试服务商连接失败：{e}")
        raise HTTPException(status_code=500, detail=f"测试失败：{str(e)}")


@router.get("/models/{provider}")
async def list_models(provider: str, group_id: str = "", base_url: str = "", version: str = ""):
    """获取服务商支持的模型列表"""
    try:
        provider_instance = get_provider(provider, group_id=group_id, base_url=base_url, version=version)

        if provider_instance is None:
            raise HTTPException(status_code=400, detail=f"不支持的服务商：{provider}")

        models = provider_instance.list_models()

        return {
            "provider": provider,
            "models": models
        }

    except Exception as e:
        logger.error(f"获取模型列表失败：{e}")
        raise HTTPException(status_code=500, detail=f"获取失败：{str(e)}")


@router.post("/completions")
async def cloud_completions(request: CloudChatRequest):
    """兼容 OpenAI 格式的补全接口"""
    return await cloud_chat(request)
