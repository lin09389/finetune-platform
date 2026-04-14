"""
API 模块初始化文件
导出所有 API 路由
"""
from api.chat import router as chat
from api.cloud_chat import router as cloud_chat
from api.context import router as context
from api.cua import router as cua
from api.datasets import router as datasets
from api.device import router as device
from api.gateway_api.routes import router as gateway
from api.inference import router as inference
from api.knowledge import router as knowledge
from api.mcp import router as mcp
from api.memory_new import router as memory
from api.model_center import router as model_center
from api.models import router as models
from api.training import router as training
from api.workspace import router as workspace

__all__ = [
    "chat",
    "cloud_chat",
    "context",
    "cua",
    "datasets",
    "device",
    "gateway",
    "inference",
    "knowledge",
    "mcp",
    "memory",
    "model_center",
    "models",
    "training",
    "workspace",
]
