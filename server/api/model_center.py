"""
模型下载管理 API
从魔搭社区（ModelScope）下载和管理模型
"""
import os
import ssl
import urllib3

os.environ['CURL_CA_BUNDLE'] = ''
os.environ['REQUESTS_CA_BUNDLE'] = ''
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
ssl._create_default_https_context = ssl._create_unverified_context

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from pathlib import Path
import logging
import json
import threading
import time
from contextlib import contextmanager

logger = logging.getLogger(__name__)

router = APIRouter()

download_tasks: Dict[str, Dict[str, Any]] = {}
download_tasks_lock = threading.Lock()

MAX_DOWNLOAD_TASKS = 50
TASK_EXPIRY_TIME = 3600

from core.config import get_settings
settings = get_settings()
MODELS_DIR = settings.models_dir_resolved


def is_dev_environment() -> bool:
    return os.getenv("ENV", "production").lower() in ("development", "dev", "debug")


@contextmanager
def ssl_verify_context():
    if is_dev_environment():
        import ssl
        import urllib3

        original_create_default_https_context = ssl._create_default_https_context

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        try:
            ssl._create_default_https_context = ssl._create_unverified_context
            yield False
        finally:
            ssl._create_default_https_context = original_create_default_https_context
    else:
        yield True


def cleanup_expired_tasks():
    current_time = time.time()
    with download_tasks_lock:
        expired_tasks = [
            task_id for task_id, task in download_tasks.items()
            if current_time - task.get("created_at", 0) > TASK_EXPIRY_TIME
            and task.get("status") in ("completed", "failed", "cancelled")
        ]
        for task_id in expired_tasks:
            del download_tasks[task_id]
            logger.debug(f"清理过期任务: {task_id}")
    
    return len(expired_tasks)


class ModelSearchRequest(BaseModel):
    query: str = Field(default="", description="搜索关键�?)
    limit: int = Field(default=20, ge=1, le=100, description="返回数量")
    source: str = Field(default="modelscope", description="搜索源：modelscope/huggingface")


class ModelInfo(BaseModel):
    id: str
    modelId: str
    name: str
    downloads: int
    likes: int
    library_name: Optional[str]
    tags: List[str]
    source: str = "modelscope"


class DownloadRequest(BaseModel):
    repo_id: str = Field(..., description="模型仓库 ID，如：Qwen/Qwen2.5-0.5B-Instruct")
    revision: Optional[str] = Field(default="master", description="版本分支")
    source: str = Field(default="modelscope", description="下载源：modelscope/huggingface")


class DownloadProgress(BaseModel):
    task_id: str
    status: str
    progress: float
    downloaded_bytes: int
    total_bytes: int
    speed: str
    error: Optional[str] = None


class ModelLocal(BaseModel):
    id: str
    name: str
    path: str
    size: int
    created_at: str
    config: Optional[Dict[str, Any]] = None


def download_model_from_modelscope(task_id: str, repo_id: str, revision: str):
    """�?ModelScope 下载模型"""
    try:
        from modelscope import snapshot_download

        with download_tasks_lock:
            if task_id in download_tasks:
                download_tasks[task_id]["status"] = "downloading"
                download_tasks[task_id]["source"] = "modelscope"

        local_dir = MODELS_DIR / repo_id.split("/")[-1]
        local_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"开始从 ModelScope 下载模型: {repo_id} -> {local_dir}")

        with download_tasks_lock:
            if task_id in download_tasks:
                download_tasks[task_id]["progress"] = 10

        model_dir = snapshot_download(
            model_id=repo_id,
            revision=revision,
            cache_dir=str(settings.modelscope_cache_dir_resolved),
            local_dir=str(local_dir),
        )

        with download_tasks_lock:
            if task_id in download_tasks:
                download_tasks[task_id]["progress"] = 90

        model_info_path = local_dir / "model_info.json"
        model_info = {
            "repo_id": repo_id,
            "revision": revision,
            "source": "modelscope",
            "downloaded_at": time.time(),
        }
        with open(model_info_path, "w", encoding="utf-8") as f:
            json.dump(model_info, f, indent=2, ensure_ascii=False)

        with download_tasks_lock:
            if task_id in download_tasks:
                download_tasks[task_id]["status"] = "completed"
                download_tasks[task_id]["progress"] = 100
                download_tasks[task_id]["local_path"] = str(local_dir)

        logger.info(f"ModelScope 模型下载完成：{repo_id} -> {local_dir}")

    except Exception as e:
        logger.error(f"ModelScope 模型下载失败：{e}", exc_info=True)
        with download_tasks_lock:
            if task_id in download_tasks:
                download_tasks[task_id]["status"] = "failed"
                download_tasks[task_id]["error"] = str(e)


def download_model_from_huggingface(task_id: str, repo_id: str, revision: str):
    """�?HuggingFace 下载模型（备用）"""
    try:
        import subprocess
        import sys

        endpoint = settings.hf_endpoint
        os.environ["HF_ENDPOINT"] = endpoint

        if settings.http_proxy:
            os.environ["HTTP_PROXY"] = settings.http_proxy
        if settings.https_proxy:
            os.environ["HTTPS_PROXY"] = settings.https_proxy

        with download_tasks_lock:
            if task_id in download_tasks:
                download_tasks[task_id]["status"] = "downloading"
                download_tasks[task_id]["endpoint"] = endpoint
                download_tasks[task_id]["source"] = "huggingface"

        local_dir = MODELS_DIR / repo_id.split("/")[-1]
        local_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"开始从 HuggingFace 下载模型: {repo_id} -> {local_dir}")

        download_script = f'''
import os
import ssl
import urllib3
urllib3.disable_warnings()
os.environ['CURL_CA_BUNDLE'] = ''
os.environ['REQUESTS_CA_BUNDLE'] = ''
os.environ['HF_ENDPOINT'] = '{endpoint}'
ssl._create_default_https_context = ssl._create_unverified_context

from huggingface_hub import snapshot_download
snapshot_download(
    repo_id='{repo_id}',
    revision='{revision}',
    local_dir='{local_dir}',
    resume_download=True,
    force_download=False,
    endpoint='{endpoint}',
    max_workers=4,
)
print('DOWNLOAD_SUCCESS')
'''

        result = subprocess.run(
            [sys.executable, '-c', download_script],
            capture_output=True,
            text=True,
            timeout=3600,
            cwd=str(MODELS_DIR.parent)
        )

        if 'DOWNLOAD_SUCCESS' in result.stdout:
            logger.info(f"HuggingFace 模型下载完成: {local_dir}")

            model_info_path = local_dir / "model_info.json"
            model_info = {
                "repo_id": repo_id,
                "revision": revision,
                "source": "huggingface",
                "downloaded_at": time.time(),
            }
            with open(model_info_path, "w", encoding="utf-8") as f:
                json.dump(model_info, f, indent=2, ensure_ascii=False)

            with download_tasks_lock:
                if task_id in download_tasks:
                    download_tasks[task_id]["status"] = "completed"
                    download_tasks[task_id]["progress"] = 100
                    download_tasks[task_id]["local_path"] = str(local_dir)

            logger.info(f"HuggingFace 模型下载完成：{repo_id} -> {local_dir}")
        else:
            error_msg = result.stderr or result.stdout or "未知错误"
            logger.error(f"下载失败: {error_msg}")
            with download_tasks_lock:
                if task_id in download_tasks:
                    download_tasks[task_id]["status"] = "failed"
                    download_tasks[task_id]["error"] = error_msg[:500]

    except subprocess.TimeoutExpired:
        logger.error("下载超时")
        with download_tasks_lock:
            if task_id in download_tasks:
                download_tasks[task_id]["status"] = "failed"
                download_tasks[task_id]["error"] = "下载超时（超�?小时�?
    except Exception as e:
        logger.error(f"下载失败：{e}", exc_info=True)
        with download_tasks_lock:
            if task_id in download_tasks:
                download_tasks[task_id]["status"] = "failed"
                download_tasks[task_id]["error"] = str(e)


@router.post("/search", response_model=List[ModelInfo])
async def search_models(request: ModelSearchRequest):
    """搜索模型（默认使�?ModelScope�?""
    if request.source == "modelscope":
        return await search_modelscope_models(request)
    else:
        return await search_huggingface_models(request)


async def search_modelscope_models(request: ModelSearchRequest) -> List[ModelInfo]:
    """搜索 ModelScope 模型"""
    try:
        from modelscope.msdatasets import MsDataset
        from modelscope.hub.api import HubApi

        hub_api = HubApi()
        
        models = hub_api.list_models(
            filter=request.query if request.query else None,
            limit=request.limit,
            sort_by="downloads",
        )

        results = []
        for m in models:
            results.append(ModelInfo(
                id=m.id if hasattr(m, 'id') else m.get('id', ''),
                modelId=m.id if hasattr(m, 'id') else m.get('id', ''),
                name=m.name if hasattr(m, 'name') else m.get('name', '').split('/')[-1],
                downloads=m.downloads if hasattr(m, 'downloads') else m.get('downloads', 0),
                likes=m.likes if hasattr(m, 'likes') else m.get('likes', 0),
                library_name=m.library_name if hasattr(m, 'library_name') else m.get('library_name'),
                tags=m.tags if hasattr(m, 'tags') else m.get('tags', []),
                source="modelscope"
            ))

        return results[:request.limit]

    except Exception as e:
        logger.error(f"搜索 ModelScope 模型失败：{e}", exc_info=True)
        try:
            import requests
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

            api_url = "https://modelscope.cn/api/v1/models"
            response = requests.get(
                api_url,
                params={
                    "Name": request.query,
                    "PageSize": request.limit,
                    "SortBy": "Downloads",
                },
                verify=False,
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                models = data.get("Data", {}).get("Models", [])
                
                return [
                    ModelInfo(
                        id=m.get("Id", ""),
                        modelId=m.get("Id", ""),
                        name=m.get("Name", "").split("/")[-1],
                        downloads=m.get("Downloads", 0),
                        likes=m.get("Stars", 0),
                        library_name=m.get("LibraryName"),
                        tags=m.get("Tags", []),
                        source="modelscope"
                    )
                    for m in models
                ]
        except Exception as e2:
            logger.error(f"备用 API 搜索也失败：{e2}", exc_info=True)
        
        raise HTTPException(status_code=500, detail=f"搜索失败：{str(e)}")


async def search_huggingface_models(request: ModelSearchRequest) -> List[ModelInfo]:
    """搜索 HuggingFace 模型（备用）"""
    try:
        import requests
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        endpoint = settings.hf_endpoint
        api_url = f"{endpoint}/api/models"

        response = requests.get(
            api_url,
            params={
                "search": request.query,
                "limit": request.limit,
                "sort": "downloads",
                "direction": "-1"
            },
            verify=False,
            timeout=30
        )

        if response.status_code != 200:
            raise Exception(f"HuggingFace API 错误：{response.status_code}")

        data = response.json()

        return [
            ModelInfo(
                id=m.get("id", ""),
                modelId=m.get("modelId", ""),
                name=m.get("modelId", "").split("/")[-1],
                downloads=m.get("downloads", 0),
                likes=m.get("likes", 0),
                library_name=m.get("library_name"),
                tags=m.get("tags", []),
                source="huggingface"
            )
            for m in data
        ]
    except Exception as e:
        logger.error(f"搜索 HuggingFace 模型失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"搜索失败：{str(e)}")


@router.post("/download", response_model=Dict[str, str])
async def download_model(request: DownloadRequest):
    """下载模型（默认使�?ModelScope�?""
    cleanup_expired_tasks()

    task_id = f"download_{int(time.time())}"

    with download_tasks_lock:
        if len(download_tasks) >= MAX_DOWNLOAD_TASKS:
            raise HTTPException(status_code=503, detail="下载任务队列已满，请稍后重试")

        download_tasks[task_id] = {
            "task_id": task_id,
            "repo_id": request.repo_id,
            "revision": request.revision,
            "status": "pending",
            "progress": 0,
            "downloaded_files": 0,
            "total_files": 0,
            "speed": "0 MB/s",
            "error": None,
            "created_at": time.time(),
            "source": request.source
        }

    if request.source == "modelscope":
        target_func = download_model_from_modelscope
    else:
        target_func = download_model_from_huggingface

    thread = threading.Thread(
        target=target_func,
        args=(task_id, request.repo_id, request.revision),
        daemon=True
    )
    thread.start()

    logger.info(f"开始下载模型：{request.repo_id}, 任务 ID: {task_id}, �? {request.source}")

    return {"task_id": task_id, "message": "下载已开�?, "source": request.source}


@router.get("/download/{task_id}", response_model=DownloadProgress)
async def get_download_progress(task_id: str):
    """获取下载进度"""
    with download_tasks_lock:
        if task_id not in download_tasks:
            raise HTTPException(status_code=404, detail="任务不存�?)

        task = download_tasks[task_id].copy()

    return DownloadProgress(
        task_id=task["task_id"],
        status=task["status"],
        progress=task["progress"],
        downloaded_bytes=task.get("downloaded_files", 0),
        total_bytes=task.get("total_files", 0),
        speed=task.get("speed", "0 MB/s"),
        error=task.get("error")
    )


@router.delete("/download/{task_id}")
async def cancel_download(task_id: str):
    """取消下载任务"""
    with download_tasks_lock:
        if task_id not in download_tasks:
            raise HTTPException(status_code=404, detail="任务不存�?)
        
        task = download_tasks[task_id]
        if task["status"] == "downloading":
            task["status"] = "cancelled"
            task["error"] = "用户取消"
        elif task["status"] == "pending":
            task["status"] = "cancelled"
            task["error"] = "用户取消"
        else:
            raise HTTPException(status_code=400, detail=f"无法取消状态为 {task['status']} 的任�?)

    return {"message": "任务已取�?, "task_id": task_id}


@router.get("/local", response_model=List[ModelLocal])
async def list_local_models():
    """获取本地模型列表"""
    models = []

    if not MODELS_DIR.exists():
        return models

    for model_path in MODELS_DIR.iterdir():
        if not model_path.is_dir():
            continue

        info_path = model_path / "model_info.json"
        config = None

        if info_path.exists():
            try:
                with open(info_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except Exception as e:
                logger.warning(f"读取模型信息失败: {info_path}, 错误: {e}")

        total_size = sum(
            f.stat().st_size for f in model_path.rglob("*") if f.is_file()
        )

        created_at = model_path.stat().st_mtime

        models.append(ModelLocal(
            id=model_path.name,
            name=model_path.name,
            path=str(model_path),
            size=total_size,
            created_at=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(created_at)),
            config=config
        ))

    return models


@router.delete("/local/{model_id}")
async def delete_local_model(model_id: str):
    """删除本地模型"""
    import shutil

    model_path = MODELS_DIR / model_id

    if not model_path.exists():
        raise HTTPException(status_code=404, detail="模型不存�?)

    try:
        shutil.rmtree(model_path)
        logger.info(f"模型已删除：{model_id}")
        return {"message": "删除成功", "model_id": model_id}
    except Exception as e:
        logger.error(f"删除模型失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除失败：{str(e)}")


@router.get("/suggestions")
async def get_model_suggestions():
    """获取推荐模型列表（ModelScope 格式�?""
    suggestions = [
        {
            "repo_id": "Qwen/Qwen2.5-0.5B-Instruct",
            "name": "Qwen2.5 0.5B Instruct",
            "description": "通义千问轻量版，适合中文对话，仅需 4GB 显存",
            "size": "~1GB",
            "category": "chat",
            "source": "modelscope"
        },
        {
            "repo_id": "Qwen/Qwen2.5-1.5B-Instruct",
            "name": "Qwen2.5 1.5B Instruct",
            "description": "通义千问 1.5B 版本，平衡性能与资�?,
            "size": "~3GB",
            "category": "chat",
            "source": "modelscope"
        },
        {
            "repo_id": "Qwen/Qwen2.5-7B-Instruct",
            "name": "Qwen2.5 7B Instruct",
            "description": "通义千问 7B 版本，强大性能，推�?16GB 显存",
            "size": "~15GB",
            "category": "chat",
            "source": "modelscope"
        },
        {
            "repo_id": "THUDM/chatglm3-6b",
            "name": "ChatGLM3-6B",
            "description": "智谱 AI 开源对话模型，中英双语",
            "size": "~7GB",
            "category": "chat",
            "source": "modelscope"
        },
        {
            "repo_id": "01ai/Yi-1.5-6B-Chat",
            "name": "Yi-1.5 6B Chat",
            "description": "零一万物对话模型，支持长上下�?,
            "size": "~12GB",
            "category": "chat",
            "source": "modelscope"
        },
        {
            "repo_id": "damo/nlp_corom_sentence-embedding_chinese-base",
            "name": "中文句子嵌入模型",
            "description": "中文文本嵌入模型（RAG 用）",
            "size": "~400MB",
            "category": "embedding",
            "source": "modelscope"
        },
        {
            "repo_id": "iic/nlp_gte_sentence-embedding_chinese-base",
            "name": "GTE 中文嵌入模型",
            "description": "通义实验�?GTE 中文嵌入模型",
            "size": "~400MB",
            "category": "embedding",
            "source": "modelscope"
        },
        {
            "repo_id": "AI-ModelScope/stable-diffusion-xl-base-1.0",
            "name": "Stable Diffusion XL",
            "description": "图像生成模型",
            "size": "~7GB",
            "category": "image",
            "source": "modelscope"
        }
    ]

    return {"suggestions": suggestions, "default_source": "modelscope"}


class ImportModelRequest(BaseModel):
    model_name: str = Field(..., description="模型名称")
    source_path: str = Field(..., description="源路径（本地目录�?)


class ImportModelScopeRequest(BaseModel):
    model_name: str = Field(default="Qwen2.5-0.5B-Instruct", description="模型名称")
    modelscope_path: Optional[str] = Field(
        default=None,
        description="ModelScope 缓存路径，如不填则使用默认路�?
    )


@router.post("/import")
async def import_local_model(request: ImportModelRequest):
    """导入本地模型"""
    import shutil

    source_path = Path(request.source_path)
    if not source_path.exists():
        raise HTTPException(status_code=404, detail=f"源路径不存在：{request.source_path}")

    if not source_path.is_dir():
        raise HTTPException(status_code=400, detail="源路径必须是目录")

    model_files = list(source_path.glob("*.safetensors")) + \
                  list(source_path.glob("*.bin")) + \
                  list(source_path.glob("*.gguf"))

    config_file = source_path / "config.json"

    if not model_files and not config_file.exists():
        raise HTTPException(
            status_code=400,
            detail="目录中未找到模型文件（需�?.safetensors/.bin/.gguf �?config.json�?
        )

    target_path = MODELS_DIR / request.model_name
    if target_path.exists():
        raise HTTPException(status_code=409, detail=f"模型名称已存在：{request.model_name}")

    try:
        shutil.copytree(source_path, target_path)

        model_info = {
            "name": request.model_name,
            "source_path": str(source_path),
            "imported_at": time.time(),
            "files": [f.name for f in target_path.iterdir()]
        }

        info_path = target_path / "model_info.json"
        with open(info_path, "w", encoding="utf-8") as f:
            json.dump(model_info, f, indent=2, ensure_ascii=False)

        total_size = sum(f.stat().st_size for f in target_path.rglob("*") if f.is_file())

        logger.info(f"模型导入成功：{request.model_name}，大小：{total_size / (1024**3):.2f} GB")

        return {
            "message": "导入成功",
            "model_id": request.model_name,
            "path": str(target_path),
            "size": total_size
        }

    except Exception as e:
        logger.error(f"导入模型失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"导入失败：{str(e)}")


@router.post("/import-modelscope")
async def import_modelscope_model(request: ImportModelScopeRequest):
    """导入 ModelScope 已下载的模型"""
    import shutil
    import getpass

    if request.modelscope_path:
        source_path = Path(request.modelscope_path)
    else:
        username = getpass.getuser()
        source_path = Path(f"C:\\Users\\{username}\\.cache\\modelscope\\hub\\{request.model_name}")

    if not source_path.exists():
        alt_paths = [
            Path(f"C:\\Users\\{username}\\.cache\\modelscope\\hub\\models\\{request.model_name}"),
            Path(f"C:\\Users\\{username}\\.modelscope\\hub\\{request.model_name}"),
            Path(f"C:\\Users\\{username}\\.modelscope\\hub\\models\\{request.model_name}"),
        ]
        for alt_path in alt_paths:
            if alt_path.exists():
                source_path = alt_path
                break
        else:
            raise HTTPException(
                status_code=404,
                detail=f"ModelScope 模型路径不存在：{source_path}\n"
                       f"请确认模型已从魔搭社区下载完成�?
            )

    if not source_path.is_dir():
        raise HTTPException(status_code=400, detail="源路径必须是目录")

    model_files = list(source_path.glob("*.safetensors")) + \
                  list(source_path.glob("*.bin")) + \
                  list(source_path.glob("*.gguf"))

    config_file = source_path / "config.json"

    if not model_files and not config_file.exists():
        raise HTTPException(
            status_code=400,
            detail="目录中未找到模型文件（需�?.safetensors/.bin/.gguf �?config.json�?
        )

    target_path = MODELS_DIR / request.model_name
    if target_path.exists():
        raise HTTPException(status_code=409, detail=f"模型名称已存在：{request.model_name}")

    try:
        logger.info(f"正在�?ModelScope 导入模型：{source_path} -> {target_path}")

        shutil.copytree(source_path, target_path, dirs_exist_ok=True)

        model_info = {
            "name": request.model_name,
            "source": "modelscope",
            "source_path": str(source_path),
            "imported_at": time.time(),
            "files": [f.name for f in target_path.iterdir()]
        }

        info_path = target_path / "model_info.json"
        with open(info_path, "w", encoding="utf-8") as f:
            json.dump(model_info, f, indent=2, ensure_ascii=False)

        total_size = sum(f.stat().st_size for f in target_path.rglob("*") if f.is_file())

        logger.info(f"ModelScope 模型导入成功：{request.model_name}，大小：{total_size / (1024**3):.2f} GB")

        return {
            "message": "导入成功",
            "model_id": request.model_name,
            "path": str(target_path),
            "size": total_size,
            "source": "modelscope"
        }

    except Exception as e:
        logger.error(f"导入 ModelScope 模型失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"导入失败：{str(e)}")


@router.get("/network/status")
async def get_network_status():
    """检查网络连接状�?""
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    results = {}
    
    mirrors = {
        "modelscope.cn": "https://modelscope.cn",
        "huggingface.co": "https://huggingface.co",
        "hf-mirror.com": "https://hf-mirror.com",
    }
    
    for name, url in mirrors.items():
        try:
            resp = requests.get(f"{url}/api/v1/models?PageSize=1" if "modelscope" in url else f"{url}/api/models?limit=1", timeout=5, verify=False)
            results[name] = {
                "status": "ok" if resp.status_code == 200 else f"error:{resp.status_code}",
                "latency": resp.elapsed.total_seconds()
            }
        except Exception as e:
            results[name] = {
                "status": "failed",
                "error": str(e)[:50]
            }
    
    proxy_status = {
        "http_proxy": settings.http_proxy or "未设�?,
        "https_proxy": settings.https_proxy or "未设�?,
    }
    
    return {
        "mirrors": results,
        "proxy": proxy_status,
        "current_source": settings.model_source,
        "default_source": "modelscope"
    }


@router.get("/source")
async def get_model_source():
    """获取当前模型下载源配�?""
    return {
        "current_source": settings.model_source,
        "modelscope_cache": str(settings.modelscope_cache_dir_resolved),
        "models_dir": str(MODELS_DIR),
        "available_sources": ["modelscope", "huggingface"]
    }


@router.post("/source")
async def set_model_source(source: str):
    """切换模型下载�?""
    if source not in ["modelscope", "huggingface"]:
        raise HTTPException(status_code=400, detail="无效的下载源，请选择 modelscope �?huggingface")
    
    settings.model_source = source
    logger.info(f"模型下载源已切换为：{source}")
    
    return {
        "message": "下载源已切换",
        "current_source": source
    }
