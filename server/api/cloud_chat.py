"""
云端 AI 聊天 API

支持 Minimax、GLM 等云端服务商
安全增强�?- API Key 加密存储
- 审计日志记录
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
import json
import logging
import uuid

from ai.gateway import get_provider, list_providers
from security.encryption import secure_storage
from security.audit_log import audit_logger

logger = logging.getLogger(__name__)
router = APIRouter(tags=["云端 AI"])  # 移除 prefix，由 main.py 统一添加


class CloudChatRequest(BaseModel):
    """云端聊天请求"""
    provider: str = Field(..., description="服务商：minimax/minimax-coding/glm")
    api_key: Optional[str] = Field(None, description="API Key 明文（临时使用）")
    key_id: Optional[str] = Field(None, description="存储�?Key ID（使用加密存储）")
    group_id: Optional[str] = Field(None, description="Group ID（可选，用于 Minimax�?)
    base_url: Optional[str] = Field(None, description="自定�?Base URL（可选）")
    model: str = Field(default="MiniMax-M2.5", description="模型名称")
    messages: List[Dict[str, str]] = Field(..., description="消息历史")
    temperature: float = Field(default=0.7, ge=0, le=2, description="温度")
    max_tokens: Optional[int] = Field(default=None, ge=1, description="最�?tokens")
    stream: bool = Field(default=True, description="是否流式输出")

    def get_api_key(self) -> str:
        """获取 API Key（明文或从加密存储获取）"""
        if self.api_key:
            return self.api_key
        if self.key_id:
            try:
                return secure_storage.get_api_key(self.key_id)
            except KeyError:
                raise ValueError(f"Key ID 不存在：{self.key_id}")
        raise ValueError("必须提供 api_key �?key_id")

    def get_group_id(self) -> str:
        """获取 Group ID（从请求或加密存储获取）"""
        if self.group_id:
            return self.group_id
        if self.key_id:
            try:
                key_data = secure_storage.get_key_data(self.key_id)
                return key_data.get("group_id", "")
            except KeyError:
                pass
        return ""

    def get_base_url(self) -> str:
        """获取 Base URL（从请求或加密存储获取）"""
        if self.base_url:
            return self.base_url
        if self.key_id:
            try:
                key_data = secure_storage.get_key_data(self.key_id)
                return key_data.get("base_url", "")
            except KeyError:
                pass
        return ""


class CloudChatResponse(BaseModel):
    """云端聊天响应"""
    success: bool
    content: str
    provider: str
    model: str


class ProviderInfo(BaseModel):
    """服务商信�?""
    id: str
    name: str
    description: str
    models: List[str]


class ProviderListResponse(BaseModel):
    """服务商列表响�?""
    providers: List[ProviderInfo]


class APIKeyRequest(BaseModel):
    """API Key 请求"""
    provider: str = Field(..., description="服务商：minimax/minimax-coding/glm")
    api_key: str = Field(..., description="API Key 明文")
    group_id: Optional[str] = Field(None, description="Group ID（可选，用于 Minimax�?)
    base_url: Optional[str] = Field(None, description="自定�?Base URL（可选）")
    name: Optional[str] = Field(None, description="可选的名称")


class APIKeyResponse(BaseModel):
    """API Key 响应"""
    key_id: str
    provider: str
    name: Optional[str]
    created_at: str


class APIKeyTestRequest(BaseModel):
    """API Key 测试请求"""
    provider: str = Field(..., description="服务商：minimax/minimax-coding/glm")
    api_key: str = Field(..., description="API Key 明文")
    group_id: Optional[str] = Field(None, description="Group ID（可选，用于 Minimax�?)
    base_url: Optional[str] = Field(None, description="自定�?Base URL（可选）")


class APIKeyListResponse(BaseModel):
    """API Key 列表响应"""
    keys: List[Dict[str, str]]


@router.post("/test")
async def test_api_key_direct(request: APIKeyTestRequest):
    """
    直接测试 API Key（无需存储�?    
    用于验证 API Key 是否有效，返回可用模型列�?    """
    try:
        provider_instance = await get_provider(
            request.provider,
            group_id=request.group_id or "",
            base_url=request.base_url or ""
        )
        
        await provider_instance.test_connection(
            api_key=request.api_key,
            group_id=request.group_id or "",
            base_url=request.base_url or ""
        )
        
        models = await provider_instance.models(request.api_key)
        
        return {
            "success": True,
            "provider": request.provider,
            "models": models,
            "message": "API Key 验证成功"
        }
        
    except ValueError as e:
        error_msg = str(e)
        logger.error(f"API Key 测试失败：{error_msg}")
        raise HTTPException(401, detail={
            "error": "authentication_failed",
            "message": error_msg,
            "provider": request.provider,
            "troubleshooting": _get_troubleshooting_tips(request.provider)
        })
    except Exception as e:
        logger.error(f"API Key 测试失败：{e}")
        raise HTTPException(500, detail={
            "error": "test_failed",
            "message": f"测试失败：{str(e)}",
            "suggestion": "请检查网络连接和代理设置"
        })


def _get_troubleshooting_tips(provider: str) -> Dict[str, List[str]]:
    """获取故障排除提示"""
    tips = {
        "minimax": [
            "检�?API Key 格式是否正确（通常�?32 位字符串�?,
            "确认 Group ID 是否匹配（如果使�?Coding Plan�?,
            "验证 API Key 是否已过期或被禁�?,
            "检查账户余额是否充�?,
            "确认 Base URL 是否正确（默认：https://api.minimax.chat/v1�?
        ],
        "minimax-coding": [
            "检�?API Key 格式是否正确",
            "确认 Group ID 是否匹配（Coding Plan 必须提供 Group ID�?,
            "验证 Coding Plan 套餐是否有效",
            "检查账户余额是否充�?
        ],
        "glm": [
            "检�?API Key 格式是否正确",
            "验证 API Key 是否已过�?,
            "检查账户余额是否充�?,
            "确认 Base URL 是否正确（默认：https://open.bigmodel.cn/api/paas/v4�?
        ]
    }
    return tips.get(provider, tips["minimax"])


@router.post("/api-keys", response_model=APIKeyResponse)
async def create_api_key(request: APIKeyRequest):
    """
    创建 API Key（加密存储）

    API Key 会被加密存储�?.vault 文件�?    """
    try:
        # 生成 Key ID
        key_id = f"key_{uuid.uuid4().hex[:12]}"

        # 加密存储（包�?group_id �?base_url�?        secure_storage.store_api_key(
            key_id,
            request.provider,
            request.api_key,
            group_id=request.group_id,
            base_url=request.base_url
        )

        # 记录审计日志
        audit_logger.log_api_key_created(key_id, request.provider)

        return APIKeyResponse(
            key_id=key_id,
            provider=request.provider,
            name=request.name or request.provider,
            created_at=secure_storage._get_timestamp()
        )

    except Exception as e:
        logger.error(f"创建 API Key 失败：{e}")
        raise HTTPException(500, detail=f"创建失败：{str(e)}")


@router.get("/api-keys", response_model=APIKeyListResponse)
async def list_api_keys():
    """列出所�?API Key（不返回明文�?""
    try:
        keys = secure_storage.list_api_keys()
        return APIKeyListResponse(keys=keys)
    except Exception as e:
        logger.error(f"列出 API Key 失败：{e}")
        raise HTTPException(500, detail=f"获取失败：{str(e)}")


@router.get("/api-keys/{key_id}/data")
async def get_api_key_data(key_id: str):
    """获取 API Key 的配置数据（不含明文 key�?""
    try:
        key_data = secure_storage.get_key_data(key_id)
        return {
            "key_id": key_id,
            "provider": key_data.get("provider", ""),
            "group_id": key_data.get("group_id", ""),
            "base_url": key_data.get("base_url", "")
        }
    except KeyError:
        raise HTTPException(404, detail="Key 不存�?)
    except Exception as e:
        logger.error(f"获取 API Key 数据失败：{e}")
        raise HTTPException(500, detail=f"获取失败：{str(e)}")


@router.delete("/api-keys/{key_id}")
async def delete_api_key(key_id: str):
    """删除 API Key"""
    try:
        secure_storage.delete_api_key(key_id)
        audit_logger.log_api_key_deleted(key_id)
        return {"success": True, "message": "已删�?}
    except KeyError:
        raise HTTPException(404, detail="Key 不存�?)
    except Exception as e:
        logger.error(f"删除 API Key 失败：{e}")
        raise HTTPException(500, detail=f"删除失败：{str(e)}")


@router.get("/api-keys/{key_id}/test")
async def test_api_key(key_id: str):
    """测试 API Key 是否有效"""
    try:
        api_key = secure_storage.get_api_key(key_id)
        provider = secure_storage.get_provider(key_id)
        
        key_data = secure_storage.get_key_data(key_id)
        group_id = key_data.get("group_id", "")
        base_url = key_data.get("base_url", "")

        provider_instance = await get_provider(provider, group_id=group_id, base_url=base_url)
        
        await provider_instance.test_connection(
            api_key=api_key,
            group_id=group_id,
            base_url=base_url
        )

        models = await provider_instance.models(api_key)

        audit_logger.log_api_key_access(key_id, provider, success=True)

        return {
            "success": True,
            "provider": provider,
            "models": models,
            "message": "API Key 验证成功"
        }

    except KeyError:
        raise HTTPException(404, detail="Key 不存�?)
    except ValueError as e:
        audit_logger.log_api_key_access(key_id, "unknown", success=False)
        error_msg = str(e)
        logger.error(f"测试 API Key 失败：{error_msg}")
        raise HTTPException(401, detail={
            "error": "authentication_failed",
            "message": error_msg,
            "troubleshooting": {
                "minimax": [
                    "检�?API Key 格式是否正确",
                    "确认 Group ID 是否匹配（如果使用）",
                    "验证 API Key 是否已过期或被禁�?,
                    "检查账户余额是否充�?
                ],
                "glm": [
                    "检�?API Key 格式是否正确",
                    "验证 API Key 是否已过�?,
                    "检查账户余额是否充�?
                ]
            }
        })
    except Exception as e:
        audit_logger.log_api_key_access(key_id, "unknown", success=False)
        logger.error(f"测试 API Key 失败：{e}")
        raise HTTPException(500, detail={
            "error": "test_failed",
            "message": f"测试失败：{str(e)}",
            "suggestion": "请检查网络连接和代理设置"
        })


@router.get("/providers", response_model=ProviderListResponse)
async def list_cloud_providers():
    """列出所有可用的云端 AI 服务�?""
    providers = list_providers()
    return ProviderListResponse(providers=providers)


@router.post("/chat", response_model=CloudChatResponse)
async def cloud_chat(request: CloudChatRequest):
    """
    云端聊天（非流式�?
    支持两种 API Key 方式�?    1. api_key: 直接传递明�?Key（临时使用）
    2. key_id: 使用加密存储�?Key ID
    """
    try:
        # 获取 API Key
        api_key = request.get_api_key()
        provider = request.provider

        # �?key_id 获取存储�?group_id �?base_url（如果有�?        group_id = request.group_id
        base_url = request.base_url
        if request.key_id:
            try:
                stored_data = secure_storage.get_key_data(request.key_id)
                group_id = group_id or stored_data.get("group_id")
                base_url = base_url or stored_data.get("base_url")
            except (KeyError, AttributeError):
                pass

        provider_instance = await get_provider(provider, group_id=group_id or "", base_url=base_url or "")

        content = await provider_instance.chat(
            messages=request.messages,
            model=request.model,
            api_key=api_key,
            group_id=group_id or "",
            base_url=base_url or "",
            temperature=request.temperature,
            max_tokens=request.max_tokens
        )

        # 记录审计日志
        if request.key_id:
            audit_logger.log_cloud_chat_access(provider, request.model, user_id=request.key_id)

        return CloudChatResponse(
            success=True,
            content=content,
            provider=provider,
            model=request.model
        )


    except ValueError as e:
        error_msg = str(e)
        logger.warning(f"参数错误：{error_msg}")
        raise HTTPException(400, detail={
            "error": "invalid_parameter",
            "message": error_msg,
            "troubleshooting": _get_troubleshooting_tips(request.provider)
        })
    except Exception as e:
        logger.error(f"云端聊天失败：{e}", exc_info=True)
        error_msg = str(e)
        if "认证失败" in error_msg or "401" in error_msg:
            raise HTTPException(401, detail={
                "error": "authentication_failed",
                "message": error_msg,
                "troubleshooting": _get_troubleshooting_tips(request.provider)
            })
        elif "权限不足" in error_msg or "403" in error_msg:
            raise HTTPException(403, detail={
                "error": "permission_denied",
                "message": error_msg,
                "suggestion": "请检�?API Key 权限或套餐是否有�?
            })
        elif "请求过于频繁" in error_msg or "429" in error_msg:
            raise HTTPException(429, detail={
                "error": "rate_limit_exceeded",
                "message": error_msg,
                "suggestion": "请稍后重�?
            })
        else:
            raise HTTPException(500, detail={
                "error": "chat_failed",
                "message": f"聊天失败：{error_msg}",
                "suggestion": "请检查网络连接或查看服务器日�?
            })


@router.post("/chat/stream")
async def cloud_chat_stream(request: CloudChatRequest):
    """
    云端聊天（流式）

    支持两种 API Key 方式�?    1. api_key: 直接传递明�?Key（临时使用）
    2. key_id: 使用加密存储�?Key ID

    性能优化�?    - 压缩响应
    - 批量发�?chunks
    """
    try:
        # 获取 API Key
        api_key = request.get_api_key()
        provider = request.provider

        # �?key_id 获取存储�?group_id �?base_url（如果有�?        group_id = request.group_id
        base_url = request.base_url
        if request.key_id:
            try:
                stored_data = secure_storage.get_key_data(request.key_id)
                group_id = group_id or stored_data.get("group_id")
                base_url = base_url or stored_data.get("base_url")
            except (KeyError, AttributeError):
                pass

        provider_instance = await get_provider(provider, group_id=group_id or "", base_url=base_url or "")

        async def generate():
            """生成流式响应"""
            buffer = []
            buffer_size = 3  # �?3 �?chunk 发送一次，减少网络往�?
            try:
                async for chunk in provider_instance.stream(
                    messages=request.messages,
                    model=request.model,
                    api_key=api_key,
                    group_id=group_id or "",
                    base_url=base_url or "",
                    temperature=request.temperature,
                    max_tokens=request.max_tokens
                ):
                    buffer.append(chunk)

                    # 达到缓冲大小或遇到标点符号时发�?                    if len(buffer) >= buffer_size or chunk in ['�?, '�?, '�?, '.', '!', '?', '\n']:
                        combined = ''.join(buffer)
                        yield f"data: {json.dumps({'content': combined}, ensure_ascii=False)}\n\n"
                        buffer = []

                # 发送剩余内�?                if buffer:
                    combined = ''.join(buffer)
                    yield f"data: {json.dumps({'content': combined}, ensure_ascii=False)}\n\n"

                # 记录审计日志
                if request.key_id:
                    audit_logger.log_cloud_chat_access(
                        provider, request.model,
                        user_id=request.key_id,
                        success=True
                    )

            except Exception as e:
                logger.error(f"流式生成错误：{e}")
                if request.key_id:
                    audit_logger.log_cloud_chat_access(
                        provider, request.model,
                        user_id=request.key_id,
                        success=False
                    )
                yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            finally:
                yield "data: [DONE]\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
            }
        )

    except ValueError as e:
        error_msg = str(e)
        logger.warning(f"参数错误：{error_msg}")
        raise HTTPException(400, detail={
            "error": "invalid_parameter",
            "message": error_msg,
            "troubleshooting": _get_troubleshooting_tips(request.provider)
        })
    except Exception as e:
        logger.error(f"流式聊天失败：{e}", exc_info=True)
        error_msg = str(e)
        if "认证失败" in error_msg or "401" in error_msg:
            raise HTTPException(401, detail={
                "error": "authentication_failed",
                "message": error_msg,
                "troubleshooting": _get_troubleshooting_tips(request.provider)
            })
        elif "权限不足" in error_msg or "403" in error_msg:
            raise HTTPException(403, detail={
                "error": "permission_denied",
                "message": error_msg,
                "suggestion": "请检�?API Key 权限或套餐是否有�?
            })
        elif "请求过于频繁" in error_msg or "429" in error_msg:
            raise HTTPException(429, detail={
                "error": "rate_limit_exceeded",
                "message": error_msg,
                "suggestion": "请稍后重�?
            })
        else:
            raise HTTPException(500, detail={
                "error": "stream_failed",
                "message": f"流式聊天失败：{error_msg}",
                "suggestion": "请检查网络连接或查看服务器日�?
            })


@router.get("/models/{provider}")
async def get_provider_models(provider: str):
    """
    获取指定服务商的可用模型列表

    Args:
        provider: 服务�?ID (minimax/minimax-coding/glm)
    """
    try:
        provider_instance = await get_provider(provider)
        # 注意：这里需要实际的 API Key 才能获取模型列表
        # 暂时返回静态列�?        models = provider_instance.models("")
        return {"provider": provider, "models": models}
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    except Exception as e:
        logger.error(f"获取模型列表失败：{e}")
        raise HTTPException(500, detail=f"获取失败：{str(e)}")
