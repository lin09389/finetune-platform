# -*- coding: utf-8 -*-
"""
聊天 API 路由
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

router = APIRouter(prefix="/chat", tags=["Chat"])


class ChatMessage(BaseModel):
    """聊天消息"""
    role: str = Field(..., description="角色: user/assistant/system")
    content: str = Field(..., description="消息内容")


class ChatRequest(BaseModel):
    """聊天请求"""
    messages: List[ChatMessage] = Field(..., description="消息列表")
    model: Optional[str] = Field(default=None, description="模型名称")
    temperature: float = Field(default=0.7, ge=0, le=2, description="温度参数")
    max_tokens: Optional[int] = Field(default=None, description="最大 token 数")


class ChatResponse(BaseModel):
    """聊天响应"""
    message: ChatMessage
    model: str
    usage: Dict[str, int]


@router.post("/completions", response_model=ChatResponse)
async def chat_completions(request: ChatRequest):
    """聊天补全"""
    return ChatResponse(
        message=ChatMessage(role="assistant", content="聊天功能暂未实现"),
        model=request.model or "default",
        usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    )


@router.get("/history/{session_id}")
async def get_chat_history(session_id: str):
    """获取聊天历史"""
    return {"session_id": session_id, "messages": []}
