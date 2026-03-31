"""
模型管理 API - 支持下载、管理和导出
"""
import json
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from core.config import get_settings
from core.logging import get_logger
from core.utils import format_bytes, safe_filename

logger = get_logger(__name__)

router = APIRouter()

_models_dir: Path | None = None

download_state = {
    "is_downloading": False,
    "model_name": "",
    "progress": 0,
    "message": "",
    "error": None,
}


def get_models_dir() -> Path:
    """获取模型目录"""
    global _models_dir
    if _models_dir is None:
        settings = get_settings()
        _models_dir = settings.models_dir_resolved
        _models_dir.mkdir(parents=True, exist_ok=True)
    return _models_dir


class ModelDownloadRequest(BaseModel):
    """模型下载请求"""
    model_name: str = Field(..., description="模型名称，如：Qwen/Qwen2.5-0.5B-Instruct")
    revision: str | None = Field(default="main", description="模型版本")
    quantize: int | None = Field(default=4, description="量化位数 (4/8/None)")
    use_safetensors: bool = Field(default=True, description="使用 safetensors 格式")


class ModelInfo(BaseModel):
    """模型信息"""
    id: str
    name: str
    path: str
    size: int
    size_formatted: str
    type: str
    quantized: int | None = None
    created_at: str
    updated_at: str | None = None
    config: dict[str, Any] | None = None


class ModelConvertRequest(BaseModel):
    """模型转换请求"""
    model_id: str
    target_format: str = Field(..., description="目标格式：onnx/gguf/fp16/int8")
    output_name: str | None = None


class ExportProgress(BaseModel):
    """导出进度"""
    progress: int
    message: str
    completed: bool


def get_models_list() -> list[ModelInfo]:
    """获取模型列表"""
    models_dir = get_models_dir()
    models = []

    if not models_dir.exists():
        return models

    for model_path in models_dir.iterdir():
        if not model_path.is_dir():
            continue

        config_file = model_path / "config.json"
        if not config_file.exists():
            continue

        try:
            with open(config_file, encoding="utf-8") as f:
                config = json.load(f)

            total_size = sum(
                f.stat().st_size for f in model_path.rglob("*") if f.is_file()
            )

            model_info = ModelInfo(
                id=model_path.name,
                name=config.get("model_name", model_path.name),
                path=str(model_path),
                size=total_size,
                size_formatted=format_bytes(total_size),
                type=config.get("type", "base"),
                quantized=config.get("quantized"),
                created_at=config.get("created_at", "2024-01-01T00:00:00"),
                updated_at=config.get("updated_at"),
                config=config,
            )
            models.append(model_info)
        except Exception as e:
            logger.error(f"加载模型失败 {model_path}: {e}")
            continue

    return models


def download_thread(request: ModelDownloadRequest):
    """下载线程（支持 ModelScope 和 HuggingFace）"""
    from core.config import get_settings
    settings = get_settings()

    models_dir = get_models_dir()
    model_folder_name = safe_filename(request.model_name.replace("/", "--"))
    local_dir = models_dir / model_folder_name

    try:
        download_state["is_downloading"] = True
        download_state["model_name"] = request.model_name
        download_state["progress"] = 0
        download_state["message"] = "Starting download..."
        download_state["error"] = None

        logger.info(f"开始下载模型：{request.model_name}")

        local_dir.mkdir(parents=True, exist_ok=True)

        download_state["progress"] = 10
        download_state["message"] = "Downloading config.json..."

        download_state["progress"] = 20
        download_state["message"] = f"Downloading {request.model_name}..."

        if settings.model_source == "modelscope":
            try:
                from modelscope import snapshot_download as ms_snapshot_download

                ms_snapshot_download(
                    model_id=request.model_name,
                    revision=request.revision or "master",
                    cache_dir=str(settings.modelscope_cache_dir_resolved),
                    local_dir=str(local_dir),
                )
                source = "modelscope"
            except Exception as e:
                logger.warning(f"ModelScope 下载失败，尝试 HuggingFace: {e}")
                from huggingface_hub import snapshot_download
                snapshot_download(
                    repo_id=request.model_name,
                    revision=request.revision,
                    local_dir=str(local_dir),
                    local_dir_use_symlinks=False,
                    use_safetensors=request.use_safetensors,
                )
                source = "huggingface"
        else:
            from huggingface_hub import snapshot_download
            snapshot_download(
                repo_id=request.model_name,
                revision=request.revision,
                local_dir=str(local_dir),
                local_dir_use_symlinks=False,
                use_safetensors=request.use_safetensors,
            )
            source = "huggingface"

        download_state["progress"] = 90
        download_state["message"] = "Saving metadata..."

        config = {
            "model_name": request.model_name,
            "revision": request.revision,
            "type": "base",
            "quantized": request.quantize,
            "created_at": datetime.now().isoformat(),
            "use_safetensors": request.use_safetensors,
            "source": source,
        }

        with open(local_dir / "config.json", "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        download_state["progress"] = 100
        download_state["message"] = "Download completed!"
        download_state["is_downloading"] = False

        logger.info(f"模型下载完成：{request.model_name} (来源: {source})")

    except Exception as e:
        logger.error(f"模型下载失败：{e}", exc_info=True)
        download_state["error"] = str(e)
        download_state["message"] = f"Download failed: {str(e)}"
        download_state["is_downloading"] = False

        if local_dir.exists():
            try:
                shutil.rmtree(local_dir)
            except Exception as cleanup_error:
                logger.warning(f"清理未完成下载失败: {cleanup_error}")


@router.get("")
async def list_models():
    """列出所有模型"""
    return get_models_list()


@router.post("/download")
async def download_model(request: ModelDownloadRequest):
    """下载模型"""
    if download_state["is_downloading"]:
        raise HTTPException(status_code=400, detail="Another download is in progress")

    models_dir = get_models_dir()
    model_folder_name = safe_filename(request.model_name.replace("/", "--"))

    local_dir = models_dir / model_folder_name
    if local_dir.exists():
        config_file = local_dir / "config.json"
        if config_file.exists():
            try:
                with open(config_file, encoding="utf-8") as f:
                    config = json.load(f)
                if config.get("model_name") == request.model_name:
                    models = get_models_list()
                    model = next((m for m in models if m.id == model_folder_name), None)
                    if model:
                        return {
                            **model.model_dump(),
                            "message": "Model already exists"
                        }
            except Exception as e:
                logger.debug(f"读取模型配置失败: {e}")

    thread = threading.Thread(target=download_thread, args=(request,), daemon=True)
    thread.start()

    return {
        "status": "started",
        "message": "Download started",
        "model_name": request.model_name
    }


@router.get("/download/status")
async def get_download_status():
    """获取下载状态"""
    return download_state


@router.get("/stats")
async def get_models_stats():
    """获取模型统计信息"""
    models = get_models_list()

    total_size = sum(m.size for m in models)
    quantized_count = sum(1 for m in models if m.quantized)

    return {
        "total_models": len(models),
        "total_size": total_size,
        "total_size_formatted": format_bytes(total_size),
        "quantized_models": quantized_count,
        "base_models": len(models) - quantized_count,
    }


@router.delete("/{model_id}")
async def delete_model(model_id: str):
    """删除模型"""
    models_dir = get_models_dir()
    model_path = models_dir / model_id

    if not model_path.exists():
        raise HTTPException(status_code=404, detail="模型不存在")

    models = get_models_list()
    model = next((m for m in models if m.id == model_id), None)

    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")

    try:
        shutil.rmtree(model_path)
        logger.info(f"模型已删除：{model_id}")
        return {"message": "Model deleted successfully"}
    except Exception as e:
        logger.error(f"删除模型失败：{e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{model_id}")
async def get_model(model_id: str):
    """获取模型详情"""
    models = get_models_list()
    model = next((m for m in models if m.id == model_id), None)

    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")

    return model


@router.post("/convert")
async def convert_model(request: ModelConvertRequest):
    """转换模型格式"""
    models_dir = get_models_dir()
    model_path = models_dir / request.model_id

    if not model_path.exists():
        raise HTTPException(status_code=404, detail="模型不存在")

    target_format = request.target_format.lower()

    if target_format not in ["onnx", "gguf", "fp16", "int8"]:
        raise HTTPException(status_code=400, detail=f"不支持的目标格式：{target_format}")

    raise HTTPException(
        status_code=501,
        detail=f"Model conversion to {target_format} not implemented yet. "
               "Please use the export endpoint for ONNX/GGUF export."
    )


@router.post("/{model_id}/export/onnx")
async def export_model_onnx(model_id: str, output_name: str | None = None):
    """导出模型为 ONNX 格式"""
    models_dir = get_models_dir()
    settings = get_settings()

    model_path = models_dir / model_id
    if not model_path.exists():
        raise HTTPException(status_code=404, detail="模型不存在")

    output_name = output_name or f"{model_id}_onnx"
    output_dir = settings.outputs_dir_resolved / "exports" / output_name
    output_dir.mkdir(parents=True, exist_ok=True)

    async def export_thread():
        try:
            import torch
            from torch.onnx import export
            from transformers import AutoModelForCausalLM, AutoTokenizer

            logger.info(f"开始导出 ONNX: {model_id}")

            tokenizer = AutoTokenizer.from_pretrained(
                str(model_path), trust_remote_code=True
            )
            model = AutoModelForCausalLM.from_pretrained(
                str(model_path),
                torch_dtype=torch.float16,
                device_map="cpu",
                trust_remote_code=True,
            )
            model.eval()

            dummy_input = tokenizer("example input", return_tensors="pt")

            onnx_path = output_dir / "model.onnx"
            export(
                model,
                (dummy_input.input_ids, dummy_input.attention_mask),
                str(onnx_path),
                input_names=["input_ids", "attention_mask"],
                output_names=["logits"],
                dynamic_axes={
                    "input_ids": {0: "batch_size", 1: "sequence_length"},
                    "attention_mask": {0: "batch_size", 1: "sequence_length"},
                    "logits": {0: "batch_size"},
                },
                opset_version=14,
            )

            tokenizer.save_pretrained(output_dir)

            config = {
                "source_model": model_id,
                "format": "onnx",
                "exported_at": datetime.now().isoformat(),
            }
            with open(output_dir / "export_config.json", "w") as f:
                json.dump(config, f, indent=2)

            logger.info(f"ONNX 导出完成：{output_dir}")

            return {
                "status": "success",
                "path": str(output_dir),
                "message": "Export completed"
            }

        except Exception as e:
            logger.error(f"ONNX 导出失败：{e}", exc_info=True)
            return {
                "status": "error",
                "message": str(e)
            }

    result = await export_thread()

    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["message"])

    return result


@router.post("/{model_id}/quantize")
async def quantize_model(model_id: str, bits: int = Query(default=8, ge=4, le=8, description="量化位数")):
    """量化模型"""
    models_dir = get_models_dir()
    settings = get_settings()

    model_path = models_dir / model_id
    if not model_path.exists():
        raise HTTPException(status_code=404, detail="模型不存在")

    if bits not in [4, 8]:
        raise HTTPException(status_code=400, detail="只支持 4 位或 8 位量化")

    output_name = f"{model_id}_int{bits}"
    output_dir = settings.outputs_dir_resolved / "quantized" / output_name
    output_dir.mkdir(parents=True, exist_ok=True)

    raise HTTPException(
        status_code=501,
        detail=f"Model quantization to {bits}-bit not implemented yet. "
               "Please use bitsandbytes or GGUF for quantization."
    )
