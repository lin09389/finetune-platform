"""
Finetune Platform Backend - Main Application
大模型微调平台后端应用
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

from api.cloud_chat import router as cloud_chat
from api.chat_agent import router as chat_agent
from api.datasets import router as datasets
from api.deployment import router as deployment
from api.device import router as device
from api.digital_team import router as digital_team
from api.evaluation import router as evaluation
from api.workflows import router as workflows
from api.chat.routes import router as chat
from api.chat_branch import router as chat_branch
from api.chat_share import router as chat_share
from api.code_executor import router as code_executor
from api.compat import router as compat_router
from api.context import router as context
from api.cua import router as cua
from api.entity import router as entity
from api.file_parser import router as file_parser
from api.gateway_api.routes import router as gateway
from api.heartbeat import router as heartbeat
from api.inference import router as inference
from api.inference_engine import router as inference_engine
from api.knowledge import router as knowledge
from api.memory_new import router as memory
from api.mcp import router as mcp
from api.model_center import router as model_center
from api.models import router as models
from api.ocr import router as ocr
from api.runtime import router as runtime
from api.training import router as training
from api.workspace import router as workspace
from core.config import settings
from core.logging import setup_logging
from core.tracing import trace_id_var, user_id_var
from workspace.file_api import router as file_api_router
from workspace.task_api import router as task_api_router


class UnicodeJSONResponse(JSONResponse):
    """????? JSON ???"""
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

from security.rate_limiter import get_rate_limiter  # noqa: E402

rate_limiter = get_rate_limiter()


def check_rate_limit(client_ip: str, path: str = "") -> tuple[bool, dict]:
    """
    ???????????

    Args:
        client_ip: ??? IP
        path: API ??

    Returns:
        (????, ????)
    """
    return rate_limiter.is_allowed(client_ip, endpoint=path)


async def verify_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials = None
) -> bool:
    """?? JWT ???"""
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
    """?????????"""
    logger.info("Initializing application...")

    from core.storage import init_storage, migrate_json_state, storage_json_migrate_on_startup
    init_storage()
    if storage_json_migrate_on_startup():
        migrated = migrate_json_state()
        logger.info("SQLite storage initialized, migrated=%s", migrated)
    else:
        logger.info("SQLite storage initialized, JSON data migration skipped on startup")

    logger.info(f"Models directory: {settings.models_dir_resolved}")
    logger.info(f"Datasets directory: {settings.datasets_dir_resolved}")
    logger.info(f"Outputs directory: {settings.outputs_dir_resolved}")

    settings.models_dir_resolved.mkdir(parents=True, exist_ok=True)
    settings.datasets_dir_resolved.mkdir(parents=True, exist_ok=True)
    settings.outputs_dir_resolved.mkdir(parents=True, exist_ok=True)

    from core.training_context import init_training_context
    init_training_context(
        settings=settings,
        max_concurrent_training=settings.max_concurrent_training,
        max_queue_size=10,
    )
    logger.info(f"TrainingContext 初始化完成，max_concurrent={settings.max_concurrent_training}")

    try:
        from api.chat.session import get_session_manager
        get_session_manager()
        logger.info("????????")
    except Exception as e:
        logger.warning(f"Session manager init failed: {e}")

    try:
        from context.service import get_context_service
        from rag.embedder import get_embedder
        from rag.vector_store import get_vector_store

        embedder = get_embedder()
        vector_store = get_vector_store()
        get_context_service(embedder=embedder, vector_store=vector_store)
        logger.info("项目上下文服务已初始化")
    except Exception as e:
        logger.warning(f"Context service init failed: {e}")

    # try:
    #     logger.info("???????...")
    #     from rag.embedder import get_embedder
    #     embedder = get_embedder()
    #     _ = embedder.dimension
    #     logger.info("?????????")
    # except Exception as e:
    #     logger.warning(f"Context service init failed: {e}")

    try:
        logger.info("???????...")
        from memory.memory_service import MemoryService
        MemoryService()
        logger.info("????????")
    except Exception as e:
        logger.warning(f"Memory service init failed: {e}")

    storage_worker = None
    try:
        from core.storage_worker import get_storage_outbox_worker
        storage_worker = get_storage_outbox_worker()
        await storage_worker.start()
    except Exception as e:
        logger.warning(f"Storage outbox worker start failed: {e}")

    yield

    logger.info("Shutting down application...")

    if storage_worker:
        try:
            await storage_worker.stop()
        except Exception as e:
            logger.warning(f"Storage outbox worker shutdown failed: {e}")
    
    try:
        from api.inference.routes import get_scheduler
        await get_scheduler().shutdown()
        logger.info("Inference scheduler shutdown complete")
    except Exception as e:
        logger.warning(f"Inference scheduler shutdown failed: {e}")

    try:
        from core.training_context import shutdown_training_context
        shutdown_training_context()
        logger.info("TrainingContext 已关闭")
    except Exception as e:
        logger.warning(f"TrainingContext shutdown failed: {e}")

    try:
        from ai.gateway import close_http_clients
        await close_http_clients()
        logger.info("AI gateway HTTP clients closed")
    except Exception as e:
        logger.warning(f"AI gateway HTTP client shutdown failed: {e}")

    try:
        from core.db_manager import close_all_pools
        close_all_pools()
        logger.info("SQLite connection pools closed")
    except Exception as e:
        logger.warning(f"SQLite pool shutdown failed: {e}")


app = FastAPI(
    title="Finetune Platform API",
    description="????????? API - ?? LoRA/QLoRA ????????????",
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
    """Trace middleware."""
    trace_id = request.headers.get("X-Trace-Id", str(uuid.uuid4()))
    trace_id_var.set(trace_id)

    # ???? User ID????? JWT ?????
    user_id = request.headers.get("X-User-Id", "anonymous")
    user_id_var.set(user_id)

    response = await call_next(request)
    response.headers["X-Trace-Id"] = trace_id
    return response


# ??????
IP_BLACKLIST = {"1.2.3.4", "5.6.7.8"}

# WAF ????????
WAF_RULES = [
    re.compile(r"union\s+select", re.I),
    re.compile(r"<script>.*?</script>", re.I),
    re.compile(r"(\.\./){3,}", re.I),
]

WAF_BODY_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
WAF_BODY_CONTENT_TYPES = (
    "application/json",
    "application/x-www-form-urlencoded",
    "text/plain",
    "application/xml",
    "text/xml",
)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    """
    ??????
    - IP ???
    - WAF ??
    - ????
    - ????
    - ????
    """
    client_ip = request.client.host if request.client else "unknown"
    path = request.url.path

    # IP ??????
    if client_ip in IP_BLACKLIST:
        logger.warning(f"Blocked request from blacklisted IP: {client_ip}")
        return JSONResponse(status_code=403, content={"error": "Forbidden", "detail": "Your IP is blacklisted"})

    # WAF ?????
    query_params = str(request.query_params)
    payload = query_params
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    should_scan_body = (
        request.method.upper() in WAF_BODY_METHODS
        and content_type in WAF_BODY_CONTENT_TYPES
    )
    if should_scan_body:
        body = await request.body()
        if body:
            payload += body.decode("utf-8", errors="ignore")
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
                    "detail": rate_info.get('message', '????????????'),
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
    """Logging middleware."""
    import time

    start_time = time.time()

    response = await call_next(request)

    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = f"{process_time:.4f}"

    return response


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """???????"""
    response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    if not DEBUG_MODE and "server" in response.headers:
        del response.headers["server"]

    return response


app.include_router(device, prefix="/device", tags=["Device"])
app.include_router(models, prefix="/models", tags=["Models"])
app.include_router(datasets, prefix="/datasets", tags=["Datasets"])
app.include_router(training, prefix="/training", tags=["Training"])
app.include_router(evaluation, prefix="/evaluation", tags=["Evaluation"])
app.include_router(deployment, prefix="/deployment", tags=["Deployment"])
app.include_router(inference, prefix="/inference", tags=["Inference"])
app.include_router(chat, tags=["Chat"])
app.include_router(knowledge, prefix="/knowledge", tags=["Knowledge"])
# Backward compatibility for legacy frontend paths.
app.include_router(knowledge, prefix="/v2/knowledge", tags=["Knowledge v2"])
app.include_router(workspace, prefix="/workspace", tags=["Workspace"])
app.include_router(digital_team, tags=["Digital Team"])
app.include_router(workflows, tags=["Workflows"])
app.include_router(chat_agent)
app.include_router(model_center, prefix="/model-center", tags=["Model Center"])
app.include_router(memory, tags=["Memory"])
app.include_router(compat_router, tags=["Compatibility"])
app.include_router(context, prefix="/context", tags=["Context"])
app.include_router(file_api_router, prefix="/files", tags=["Files"])
app.include_router(task_api_router, prefix="/tasks", tags=["Tasks"])
app.include_router(cloud_chat, prefix="/cloud", tags=["Cloud"])
app.include_router(cua, tags=["CUA"])
app.include_router(mcp, tags=["MCP"])
app.include_router(gateway, tags=["Gateway"])
app.include_router(heartbeat, tags=["Heartbeat"])
app.include_router(code_executor, prefix="/code", tags=["Code"])
app.include_router(file_parser, tags=["File Parser"])
app.include_router(chat_branch, tags=["Chat Branch"])
app.include_router(chat_share, tags=["Chat Share"])
app.include_router(entity, tags=["Entity"])
app.include_router(ocr, tags=["OCR"])
app.include_router(inference_engine, tags=["Inference Engine"])
app.include_router(runtime, prefix="/runtime", tags=["Runtime"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Finetune Platform API",
        "version": "1.0.0",
        "api_version": "2.0.0",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    import torch

    intent_backend_status = "disabled"

    health = {
        "status": "ok",
        "service_status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0",
        "cuda_available": torch.cuda.is_available() if hasattr(torch, "cuda") else False,
        "intent_backend_status": intent_backend_status,
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
            logger.warning(f"Failed to get GPU info: {e}")
            health["gpu_info"] = {"error": str(e)}

    return health


@app.get("/api/info")
async def api_info():
    """API metadata."""
    return {
        "name": "Finetune Platform API",
        "version": "2.1.0",
        "description": "Finetune Platform backend API with core, beta, and experimental capability tiers",
        "features": [
            "LoRA/QLoRA fine-tuning",
            "Model and dataset lifecycle",
            "Inference service with backend switching",
            "Chat sessions and knowledge retrieval",
            "Workspace and local AI tooling",
            "Digital team workflow orchestration",
            "Multi-agent workflow orchestration",
        ],
        "capability_tiers": {
            "ga": [
                "device",
                "models",
                "datasets",
                "training",
                "inference",
                "chat_sessions",
                "knowledge_base",
            ],
            "beta": [
                "project_context",
                "memory",
                "model_center",
                "workspace",
                "workflows",
                "digital_team",
            ],
            "experimental": [
                "cua",
                "heartbeat",
                "mcp",
                "gateway",
                "ocr_fallbacks",
                "action_recorder",
            ],
        },
        "endpoints": {
            "device": "/device",
            "models": "/models",
            "datasets": "/datasets",
            "training": "/training",
            "inference": "/inference",
            "chat": "/chat/sessions",
            "knowledge": "/knowledge",
            "runtime": "/runtime/bootstrap",
            "memory": "/memory",
            "workspace": "/workspace",
            "workflows": "/workflows",
            "digital_team": "/digital-team",
            "context": "/context",
            "model_center": "/model-center",
            "experimental": {
                "cua": "/cua",
                "mcp": "/mcp",
                "gateway": "/gateway",
                "heartbeat": "/heartbeat",
                "ocr": "/ocr",
            },
        },
    }


from api.errors import APIError  # noqa: E402


@app.exception_handler(APIError)
async def custom_api_error_handler(request: Request, exc: APIError):
    """Handle custom API errors."""
    logger.warning(f"API Error: {exc.code} - {exc.message}")
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict()
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions."""
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
    """Handle uncaught exceptions."""
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



