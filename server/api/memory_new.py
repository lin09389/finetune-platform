"""
记忆 API 路由
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/memory", tags=["Memory"])


class MemoryItem(BaseModel):
    """记忆项"""
    id: str
    content: str
    type: str
    importance: float
    created_at: str


class MemoryCreateRequest(BaseModel):
    """创建记忆请求"""
    content: str = Field(..., description="记忆内容")
    memory_type: str = Field(default="knowledge", description="记忆类型")
    importance: float = Field(default=0.5, ge=0, le=1, description="重要性")


@router.get("/")
async def list_memories(
    memory_type: str | None = None,
    limit: int = 50
):
    """列出记忆"""
    return {"memories": [], "total": 0}


@router.post("/")
async def create_memory(request: MemoryCreateRequest):
    """创建记忆"""
    return {
        "id": "mem_001",
        "content": request.content,
        "type": request.memory_type,
        "importance": request.importance
    }


@router.get("/{memory_id}")
async def get_memory(memory_id: str):
    """获取记忆"""
    return {"id": memory_id, "content": "", "type": "knowledge"}


@router.delete("/{memory_id}")
async def delete_memory(memory_id: str):
    """删除记忆"""
    return {"success": True, "memory_id": memory_id}


@router.post("/recall")
async def recall_memories(query: str, top_k: int = 5):
    """检索记忆"""
    return {"memories": [], "query": query}


@router.get("/stats/summary")
async def get_memory_stats():
    """获取记忆统计"""
    return {
        "total_memories": 0,
        "by_type": {},
        "avg_importance": 0.0
    }
