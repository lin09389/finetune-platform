"""
API 模块初始化文件
导出所有 API 路由（保持与 main.py 注册项一致）
"""
from api.agent_sessions import action_router as agent_session_actions
from api.agent_sessions import permission_router as agent_session_permissions
from api.agent_sessions import router as agent_sessions
from api.agents import router as agents
from api.chat.routes import router as chat
from api.chat_agent import router as chat_agent
from api.cloud_chat import router as cloud_chat
from api.context import router as context
from api.cua import router as cua
from api.datasets import router as datasets
from api.deployment import router as deployment
from api.device import router as device
from api.evaluation import router as evaluation
from api.gateway_api.routes import router as gateway
from api.heartbeat import router as heartbeat
from api.inference import router as inference
from api.knowledge import router as knowledge
from api.mcp import router as mcp
from api.memory import router as memory
from api.model_center import router as model_center
from api.models import router as models
from api.training import router as training
from api.workspace import router as workspace

__all__ = [
    "agent_session_actions",
    "agent_session_permissions",
    "agent_sessions",
    "agents",
    "chat",
    "chat_agent",
    "cloud_chat",
    "context",
    "cua",
    "datasets",
    "deployment",
    "device",
    "evaluation",
    "gateway",
    "heartbeat",
    "inference",
    "knowledge",
    "mcp",
    "memory",
    "model_center",
    "models",
    "training",
    "workspace",
]
