"""
Finetune Platform Backend - Main Application
大模型微调平台后端主应用
"""
import json
import logging
import os
import re
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Force UTF-8 console IO on Windows to avoid mojibake in subprocess logs.
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from api import (
    agent,
    cloud_chat,
    context,
    cua,
    datasets,
    device,
    mcp,
    model_center,
    models,
    skills,
    training,
    workspace,
)
from api.compat import router as compat_router
from api.agent_executor import router as agent_executor
from api.chat.routes import router as chat
from api.chat_branch import router as chat_branch
from api.chat_share import router as chat_share
from api.code_executor import router as code_executor
from api.entity import router as entity
from api.feedback import router as feedback
from api.file_parser import router as file_parser
from api.gateway_api.routes import router as gateway
from api.heartbeat import router as heartbeat
from api.help import router as help_router
from api.inference import router as inference
from api.inference_engine import router as inference_engine
from api.knowledge import router as knowledge
from api.memory_new import router as memory
from api.ocr import router as ocr
from api.smart_agent import router as smart_agent
from core.config import settings
from core.logging import setup_logging
from core.tracing import trace_id_var, user_id_var
from workspace.file_api import router as file_api_router
from workspace.task_api import router as task_api_router


class UnicodeJSONResponse(JSONResponse):
    """支持中文的 JSON 响应"""
    def render(self, content) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")


LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logger = setup_logging(
    log_dir=LOG_DIR,
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    enable_json=os.getenv("LOG_FORMAT", "text") == "json"
)

logger.info("=" * 50)
logger.info("Finetune Platform Backend Starting")
logger.info("=" * 50)
logger.info(f"Python: {sys.version}")
logger.info(f"Working Directory: {os.getcwd()}")
logger.info(f"Log Level: {logging.getLevelName(logger.level)}")

security = HTTPBearer(auto_error=False)
ALLOWED_ORIGINS = settings.allowed_origins
DEBUG_MODE = os.getenv("DEBUG", "false").lower() == "true"
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

from security.rate_limiter import get_rate_limiter

rate_limiter = get_rate_limiter()


def check_rate_limit(client_ip: str, path: str = "") -> tuple[bool, dict]:
    """
    检查是否超过速率限制

    Args:
        client_ip: 客户端 IP
        path: API 路径

    Returns:
        (是否允许, 限制信息)
    """
    return rate_limiter.is_allowed(client_ip, endpoint=path)


async def verify_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials = None
) -> bool:
    """验证 JWT 认证"""
    if os.getenv("ENABLE_AUTH", "false").lower() != "true":
        return True

    if credentials is None:
        return False

    from security.jwt_auth import get_jwt_manager
    jwt_manager = get_jwt_manager()

    try:
        payload = jwt_manager.verify_token(credentials.credentials)
        return payload is not None
    except Exception as e:
        logger.warning(f"JWT verification failed: {e}")
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("Initializing application...")
    
    # 初始化数据库表
    from core.db_manager import get_db_pool
    db_pool = get_db_pool()
    db_pool.execute_update("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trace_id TEXT,
            user_id TEXT,
            action TEXT,
            params TEXT,
            status TEXT,
            latency REAL,
            error TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    logger.info("审计日志表已准备就绪")
    
    logger.info(f"Models directory: {settings.models_dir_resolved}")
    logger.info(f"Datasets directory: {settings.datasets_dir_resolved}")
    logger.info(f"Outputs directory: {settings.outputs_dir_resolved}")

    settings.models_dir_resolved.mkdir(parents=True, exist_ok=True)
    settings.datasets_dir_resolved.mkdir(parents=True, exist_ok=True)
    settings.outputs_dir_resolved.mkdir(parents=True, exist_ok=True)

    from core.training_queue import get_training_queue
    queue = get_training_queue(
        max_concurrent=settings.max_concurrent_training,
        max_queue_size=10
    )
    logger.info(f"训练队列已初始化：max_concurrent={settings.max_concurrent_training}")

    try:
        from api.chat.session import get_session_manager
        session_manager = get_session_manager()
        logger.info("会话存储已初始化")
    except Exception as e:
        logger.warning(f"会话存储初始化失败：{e}")

    try:
        from context.service import get_context_service
        from rag.embedder import get_embedder
        from rag.vector_store import get_vector_store

        embedder = get_embedder()
        vector_store = get_vector_store()
        context_service = get_context_service(embedder=embedder, vector_store=vector_store)
        logger.info("项目上下文服务已初始化")
    except Exception as e:
        logger.warning(f"上下文服务初始化失败：{e}")

    # try:
    #     logger.info("预加载嵌入模型...")
    #     from rag.embedder import get_embedder
    #     embedder = get_embedder()
    #     _ = embedder.dimension
    #     logger.info("嵌入模型预加载完成")
    # except Exception as e:
    #     logger.warning(f"嵌入模型预加载失败（将使用懒加载）：{e}")

    try:
        logger.info("预初始化记忆服务...")
        from memory.memory_service import MemoryService
        memory_service = MemoryService()
        logger.info("记忆服务已初始化")
    except Exception as e:
        logger.warning(f"记忆服务初始化失败：{e}")

    yield

    logger.info("Shutting down application...")


app = FastAPI(
    title="Finetune Platform API",
    description="大模型微调平台后端 API - 支持 LoRA/QLoRA 微调，消费级显卡优化",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
    default_response_class=UnicodeJSONResponse,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    """Trace ID 中间件"""
    trace_id = request.headers.get("X-Trace-Id", str(uuid.uuid4()))
    trace_id_var.set(trace_id)
    
    # 模拟获取 User ID (实际应从 JWT 中获取)
    user_id = request.headers.get("X-User-Id", "anonymous")
    user_id_var.set(user_id)
    
    response = await call_next(request)
    response.headers["X-Trace-Id"] = trace_id
    return response


# 黑名单列表
IP_BLACKLIST = {"1.2.3.4", "5.6.7.8"}

# WAF 规则 (简单正则)
WAF_RULES = [
    re.compile(r"union\s+select", re.I),
    re.compile(r"<script>.*?</script>", re.I),
    re.compile(r"(\.\./){3,}", re.I),
]


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    """
    安全中间件
    - IP 黑名单
    - WAF 过滤
    - 速率限制
    - 请求日志
    - 错误处理
    """
    client_ip = request.client.host
    path = request.url.path

    # IP 黑名单检查
    if client_ip in IP_BLACKLIST:
        logger.warning(f"Blocked request from blacklisted IP: {client_ip}")
        return JSONResponse(status_code=403, content={"error": "Forbidden", "detail": "Your IP is blacklisted"})

    # WAF 规则检查
    query_params = str(request.query_params)
    body = await request.body()
    payload = query_params + body.decode("utf-8", errors="ignore")
    for rule in WAF_RULES:
        if rule.search(payload):
            logger.warning(f"Blocked malicious payload from IP: {client_ip}")
            return JSONResponse(status_code=400, content={"error": "Bad Request", "detail": "Malicious payload detected"})

    skip_paths = ["/health", "/", "/favicon.ico"]

    if path not in skip_paths:
        allowed, rate_info = check_rate_limit(client_ip, path)
        if not allowed:
            logger.warning(f"Rate limit exceeded for IP: {client_ip}, path: {path}")
            retry_after = rate_info.get('retry_after', 60)
            return JSONResponse(
                status_code=429,
                content={
                    "error": rate_info.get('error', 'rate_limit_exceeded'),
                    "detail": rate_info.get('message', '请求过于频繁，请稍后再试'),
                    "retry_after": retry_after
                },
                headers={
                    "Retry-After": str(retry_after),
                    "Access-Control-Allow-Origin": request.headers.get("origin", "*"),
                    "Access-Control-Allow-Credentials": "true"
                }
            )

    try:
        response = await call_next(request)
        return response
    except Exception as e:
        logger.error(f"Request error: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "detail": str(e) if os.getenv("DEBUG", "false") == "true" else "An unexpected error occurred"
            },
            headers={
                "Access-Control-Allow-Origin": request.headers.get("origin", "*"),
                "Access-Control-Allow-Credentials": "true"
            }
        )


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """日志中间件"""
    import time

    start_time = time.time()

    response = await call_next(request)

    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = f"{process_time:.4f}"

    return response


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """安全头中间件"""
    response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    if not DEBUG_MODE and "server" in response.headers:
        del response.headers["server"]

    return response


app.include_router(device, prefix="/device", tags=["设备管理"])
app.include_router(models, prefix="/models", tags=["模型管理"])
app.include_router(datasets, prefix="/datasets", tags=["数据集管理"])
app.include_router(training, prefix="/training", tags=["训练管理"])
app.include_router(inference, prefix="/inference", tags=["推理服务"])
app.include_router(chat, tags=["对话管理"])
app.include_router(knowledge, prefix="/knowledge", tags=["知识库"])
app.include_router(workspace, prefix="/workspace", tags=["工作空间管理"])
app.include_router(model_center, prefix="/model-center", tags=["模型中心"])
app.include_router(memory, tags=["智能记忆"])
app.include_router(agent, prefix="/agent", tags=["Agent 操作"])
app.include_router(compat_router, tags=["兼容路由"])
app.include_router(context, prefix="/context", tags=["项目上下文"])
app.include_router(file_api_router, prefix="/files", tags=["文件操作"])
app.include_router(task_api_router, prefix="/tasks", tags=["任务追踪"])
app.include_router(cloud_chat, prefix="/cloud", tags=["云端 AI"])
app.include_router(skills, tags=["技能管理"])
app.include_router(cua, tags=["CUA - Computer Use Agent"])
app.include_router(mcp, tags=["MCP"])
app.include_router(smart_agent, prefix="/smart-agent", tags=["智能 Agent"])
app.include_router(gateway, tags=["Gateway"])
app.include_router(heartbeat, tags=["Heartbeat"])
app.include_router(code_executor, prefix="/code", tags=["代码执行"])
app.include_router(file_parser, tags=["文件解析"])
app.include_router(chat_branch, tags=["对话分支"])
app.include_router(chat_share, tags=["对话分享"])
app.include_router(entity, tags=["实体识别"])
app.include_router(ocr, tags=["OCR识别"])
app.include_router(feedback, tags=["用户反馈"])
app.include_router(help_router, tags=["帮助系统"])
app.include_router(inference_engine, tags=["推理引擎"])
app.include_router(agent_executor, tags=["Agent执行器"])


@app.get("/")
async def root():
    """根路由"""
    return {
        "message": "Finetune Platform API",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    import torch
    from agent.intent.methods.bert_classifier import bert_classifier

    health = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0",
        "cuda_available": torch.cuda.is_available() if hasattr(torch, "cuda") else False,
        "intent_backend_status": "loaded" if bert_classifier.is_available() else "degraded",
    }

    if torch.cuda.is_available():
        try:
            health["gpu_info"] = {
                "device_name": torch.cuda.get_device_properties(0).name,
                "memory": {
                    "total_gb": round(torch.cuda.get_device_properties(0).total_memory / (1024 ** 3), 2),
                    "allocated_gb": round(torch.cuda.memory_allocated(0) / (1024 ** 3), 2),
                    "reserved_gb": round(torch.cuda.memory_reserved(0) / (1024 ** 3), 2),
                },
            }
        except Exception as e:
            logger.warning(f"获取 GPU 信息失败：{e}")
            health["gpu_info"] = {"error": str(e)}

    return health


@app.get("/api/info")
async def api_info():
    """API 信息"""
    return {
        "name": "Finetune Platform API",
        "version": "2.0.0",
        "description": "大模型微调平台后端 API",
        "features": [
            "LoRA/QLoRA 微调",
            "模型管理",
            "数据集管理",
            "训练监控",
            "推理服务",
            "Ollama 集成"
        ],
        "endpoints": {
            "device": "/device",
            "models": "/models",
            "datasets": "/datasets",
            "training": "/training",
            "inference": "/inference",
            "chat": "/v2/chat",
            "knowledge": "/v2/knowledge",
            "memory": "/v2/memory"
        }
    }


from api.errors import APIError


@app.exception_handler(APIError)
async def custom_api_error_handler(request: Request, exc: APIError):
    """API 错误处理"""
    logger.warning(f"API Error: {exc.code} - {exc.message}")
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict()
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """HTTP 异常处理"""
    logger.warning(f"HTTP Exception: {exc.status_code} - {exc.detail}")
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": "http_error",
                "message": str(exc.detail),
                "details": {}
            }
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """通用异常处理"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": "服务器内部错误，请查看日志获取详情"
        }
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=os.getenv("DEBUG", "false") == "true",
        log_level=os.getenv("LOG_LEVEL", "info").lower()
    )
