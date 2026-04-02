"""
数据集管理 API - 增强安全校验和统计功能
"""
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from core.config import get_settings
from core.logging import get_logger
from core.utils import (
    calculate_file_hash,
    format_bytes,
    safe_filename,
)

logger = get_logger(__name__)

router = APIRouter()

_datasets_dir: Path | None = None
_max_upload_size: int = 100 * 1024 * 1024  # 100MB
_allowed_types: list[str] = [".json", ".jsonl"]


def get_datasets_dir() -> Path:
    """获取数据集目录"""
    global _datasets_dir
    if _datasets_dir is None:
        settings = get_settings()
        _datasets_dir = settings.datasets_dir_resolved
        _datasets_dir.mkdir(parents=True, exist_ok=True)
    return _datasets_dir


def get_settings_config():
    """获取配置"""
    settings = get_settings()
    return settings


class DatasetInfo(BaseModel):
    """数据集信息"""
    id: str
    name: str
    path: str
    size: int
    size_formatted: str
    format: str
    samples: int
    created_at: str
    updated_at: str | None = None
    file_hash: str | None = None
    statistics: dict[str, Any] | None = None


class DatasetStatistics(BaseModel):
    """数据集统计信息"""
    total_samples: int
    avg_message_length: float
    avg_turns: float
    role_distribution: dict[str, int]
    message_length_distribution: dict[str, str]
    sample_length_distribution: dict[str, int]


class DatasetUploadResponse(BaseModel):
    """数据集上传响应"""
    id: str
    name: str
    path: str
    size: int
    format: str
    samples: int
    created_at: str
    message: str


def validate_path_security(base_dir: Path, target_path: Path) -> bool:
    """
    验证路径安全性，防止路径遍历攻击
    
    Args:
        base_dir: 基础目录
        target_path: 目标路径
    
    Returns:
        是否安全
    """
    try:
        base_resolved = base_dir.resolve()
        target_resolved = target_path.resolve()
        return base_resolved in target_resolved.parents or base_resolved == target_resolved
    except Exception as e:
        logger.error(f"路径验证失败：{e}")
        return False


def validate_file_content(file_path: Path) -> tuple[bool, str]:
    """
    验证文件内容
    
    Args:
        file_path: 文件路径
    
    Returns:
        (是否有效，错误消息)
    """
    try:
        if file_path.suffix.lower() in [".json", ".jsonl"]:
            try:
                with open(file_path, encoding="utf-8") as f:
                    if file_path.suffix.lower() == ".jsonl":
                        for i, line in enumerate(f):
                            if i >= 10:
                                break
                            json.loads(line)
                    else:
                        json.load(f)
                return True, ""
            except json.JSONDecodeError as e:
                return False, f"Invalid JSON format: {str(e)}"
        return True, ""
    except Exception as e:
        logger.warning(f"文件内容验证失败：{e}")
        return True, ""


def validate_dataset_format(file_path: Path) -> tuple[bool, str, int]:
    """
    验证数据集格式
    
    Args:
        file_path: 文件路径
    
    Returns:
        (是否有效，错误消息，样本数)
    """
    try:
        sample_count = 0

        with open(file_path, encoding="utf-8") as f:
            if file_path.suffix.lower() == ".jsonl":
                for i, line in enumerate(f):
                    try:
                        data = json.loads(line)
                        has_valid_field = (
                            "messages" in data or
                            "text" in data or
                            "content" in data or
                            "instruction" in data
                        )
                        if not has_valid_field:
                            return False, f"Line {i+1}: Missing required field", 0
                        if "messages" in data and not isinstance(data["messages"], list):
                            return False, f"Line {i+1}: 'messages' must be a list", 0
                        sample_count += 1
                    except json.JSONDecodeError as e:
                        return False, f"Line {i+1}: Invalid JSON - {str(e)}", 0
            else:
                data = json.load(f)
                if isinstance(data, list):
                    for i, item in enumerate(data):
                        has_valid_field = (
                            "messages" in item or
                            "text" in item or
                            "content" in item or
                            "instruction" in item
                        )
                        if not has_valid_field:
                            return False, f"Item {i}: Missing required field", 0
                        if "messages" in item and not isinstance(item["messages"], list):
                            return False, f"Item {i}: 'messages' must be a list", 0
                    sample_count = len(data)
                else:
                    return False, "JSON root must be a list of conversations", 0

        if sample_count == 0:
            return False, "No valid samples found", 0

        return True, "", sample_count
    except Exception as e:
        return False, f"Validation error: {str(e)}", 0


def compute_statistics(file_path: Path, sample_limit: int = 1000) -> DatasetStatistics:
    """
    计算数据集统计信息
    
    Args:
        file_path: 文件路径
        sample_limit: 采样上限
    
    Returns:
        统计信息
    """
    samples = []

    try:
        with open(file_path, encoding="utf-8") as f:
            if file_path.suffix.lower() == ".jsonl":
                for i, line in enumerate(f):
                    if i >= sample_limit:
                        break
                    samples.append(json.loads(line))
            else:
                data = json.load(f)
                if isinstance(data, list):
                    samples = data[:sample_limit]
                else:
                    samples = [data]
    except Exception as e:
        logger.error(f"计算统计失败：{e}")
        return DatasetStatistics(
            total_samples=0,
            avg_message_length=0,
            avg_turns=0,
            role_distribution={},
            message_length_distribution={},
            sample_length_distribution={}
        )

    total_messages = 0
    total_length = 0
    total_turns = 0
    role_counts = {}
    length_buckets = {"0-100": 0, "100-500": 0, "500-1000": 0, "1000-2000": 0, "2000+": 0}

    for sample in samples:
        messages = sample.get("messages", [])
        total_turns += len(messages)
        sample_length = 0

        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            role_counts[role] = role_counts.get(role, 0) + 1
            msg_length = len(content)
            total_length += msg_length
            sample_length += msg_length
            total_messages += 1

        if sample_length < 100:
            length_buckets["0-100"] += 1
        elif sample_length < 500:
            length_buckets["100-500"] += 1
        elif sample_length < 1000:
            length_buckets["500-1000"] += 1
        elif sample_length < 2000:
            length_buckets["1000-2000"] += 1
        else:
            length_buckets["2000+"] += 1

    avg_length = total_length / total_messages if total_messages > 0 else 0
    avg_turns = total_turns / len(samples) if samples else 0

    msg_length_dist = {}
    for role, count in role_counts.items():
        pct = (count / total_messages * 100) if total_messages > 0 else 0
        msg_length_dist[role] = f"{pct:.1f}%"

    return DatasetStatistics(
        total_samples=len(samples),
        avg_message_length=round(avg_length, 2),
        avg_turns=round(avg_turns, 2),
        role_distribution=role_counts,
        message_length_distribution=msg_length_dist,
        sample_length_distribution=length_buckets
    )


def get_datasets_list() -> list[DatasetInfo]:
    """获取数据集列表"""
    datasets_dir = get_datasets_dir()
    datasets = []

    if not datasets_dir.exists():
        return datasets

    for dataset_path in datasets_dir.iterdir():
        if not dataset_path.is_dir():
            continue

        info_file = dataset_path / "info.json"
        if not info_file.exists():
            continue

        try:
            with open(info_file, encoding="utf-8") as f:
                info = json.load(f)

            total_size = sum(
                f.stat().st_size for f in dataset_path.rglob("*") if f.is_file()
            )

            dataset_info = DatasetInfo(
                id=dataset_path.name,
                name=info.get("name", dataset_path.name),
                path=str(dataset_path),
                size=total_size,
                size_formatted=format_bytes(total_size),
                format=info.get("format", "json"),
                samples=info.get("samples", 0),
                created_at=info.get("created_at", "2024-01-01T00:00:00"),
                updated_at=info.get("updated_at"),
                file_hash=info.get("file_hash"),
                statistics=info.get("statistics"),
            )
            datasets.append(dataset_info)
        except Exception as e:
            logger.error(f"加载数据集失败 {dataset_path}: {e}")
            continue

    return datasets


@router.get("")
async def list_datasets():
    """列出所有数据集"""
    return get_datasets_list()


@router.get("/list")
async def list_datasets_compat():
    return get_datasets_list()


@router.post("/upload", response_model=DatasetUploadResponse)
async def upload_dataset(
    file: UploadFile = File(..., description="数据集文件"),
    name: str | None = Form(None, description="数据集名称"),
    description: str | None = Form(None, description="数据集描述")
):
    """
    上传数据集
    
    安全校验:
    - 文件类型验证
    - 文件大小限制
    - 路径遍历防护
    - 内容格式验证
    """
    settings = get_settings_config()
    datasets_dir = get_datasets_dir()

    original_filename = safe_filename(file.filename or "dataset")

    file_ext = Path(original_filename).suffix.lower()
    if file_ext not in _allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"不允许的文件类型：{file_ext}，允许：{', '.join(_allowed_types)}"
        )

    try:
        content = await file.read()
        file_size = len(content)

        if file_size > settings.max_upload_size:
            raise HTTPException(
                status_code=400,
                detail=f"文件过大：{format_bytes(file_size)}，最大允许：{format_bytes(settings.max_upload_size)}"
            )

        if file_size == 0:
            raise HTTPException(status_code=400, detail="空文件")
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=f"读取文件失败：{str(e)}")

    dataset_name = name or Path(original_filename).stem
    dataset_id = safe_filename(dataset_name).replace(" ", "_").lower()

    dataset_path = datasets_dir / dataset_id
    if dataset_path.exists():
        raise HTTPException(
            status_code=409,
            detail=f"数据集 '{dataset_name}' 已存在，请使用其他名称"
        )

    dataset_path.mkdir(parents=True, exist_ok=True)

    dest_file = dataset_path / original_filename
    try:
        with open(dest_file, "wb") as f:
            f.write(content)
    except Exception as e:
        shutil.rmtree(dataset_path)
        raise HTTPException(status_code=500, detail=f"保存文件失败：{str(e)}")

    is_valid, error_msg = validate_file_content(dest_file)
    if not is_valid:
        shutil.rmtree(dataset_path)
        raise HTTPException(status_code=400, detail=f"文件内容无效：{error_msg}")

    is_valid, error_msg, sample_count = validate_dataset_format(dest_file)
    if not is_valid:
        shutil.rmtree(dataset_path)
        raise HTTPException(status_code=400, detail=f"数据集格式错误：{error_msg}")

    file_hash = calculate_file_hash(dest_file)

    statistics = compute_statistics(dest_file)
    stats_dict = statistics.model_dump()

    created_at = datetime.now().isoformat()
    info = {
        "id": dataset_id,
        "name": dataset_name,
        "description": description or "",
        "format": file_ext[1:],
        "samples": sample_count,
        "created_at": created_at,
        "file_hash": file_hash,
        "original_filename": original_filename,
        "statistics": stats_dict,
    }

    info_file = dataset_path / "info.json"
    with open(info_file, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)

    logger.info(f"数据集上传成功：{dataset_id}, 样本数：{sample_count}")

    return DatasetUploadResponse(
        id=dataset_id,
        name=dataset_name,
        path=str(dataset_path),
        size=file_size,
        format=file_ext[1:],
        samples=sample_count,
        created_at=created_at,
        message="数据集上传成功"
    )


@router.delete("/{dataset_id}")
async def delete_dataset(dataset_id: str):
    """删除数据集"""
    datasets_dir = get_datasets_dir()
    dataset_path = datasets_dir / dataset_id

    if not dataset_path.exists():
        raise HTTPException(status_code=404, detail="数据集不存在")

    if not validate_path_security(datasets_dir, dataset_path):
        raise HTTPException(status_code=400, detail="无效的数据集路径")

    try:
        shutil.rmtree(dataset_path)
        logger.info(f"数据集已删除：{dataset_id}")
        return {"message": "数据集删除成功"}
    except Exception as e:
        logger.error(f"删除数据集失败：{e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{dataset_id}", response_model=DatasetInfo)
async def get_dataset(dataset_id: str):
    """获取数据集详情"""
    datasets = get_datasets_list()
    dataset = next((d for d in datasets if d.id == dataset_id), None)

    if not dataset:
        raise HTTPException(status_code=404, detail="数据集不存在")

    return dataset


@router.get("/{dataset_id}/preview")
async def preview_dataset(dataset_id: str, limit: int = Query(default=10, ge=1, le=100)):
    """预览数据集"""
    datasets_dir = get_datasets_dir()
    dataset_path = datasets_dir / dataset_id

    if not dataset_path.exists():
        raise HTTPException(status_code=404, detail="数据集不存在")

    data_files = []
    for ext in [".json", ".jsonl"]:
        data_files.extend(list(dataset_path.glob(f"*{ext}")))

    if not data_files:
        raise HTTPException(status_code=404, detail="数据文件不存在")

    data_file = data_files[0]

    max_preview_size = 10 * 1024 * 1024  # 10MB
    file_size = data_file.stat().st_size

    if file_size > max_preview_size:
        raise HTTPException(
            status_code=400,
            detail=f"文件过大 ({file_size / (1024*1024):.1f}MB)，无法预览。请使用 JSONL 格式或减小文件大小"
        )

    try:
        with open(data_file, encoding="utf-8") as f:
            if data_file.suffix.lower() == ".jsonl":
                samples = []
                for i, line in enumerate(f):
                    if i >= limit:
                        break
                    samples.append(json.loads(line))
            else:
                data = json.load(f)
                if isinstance(data, list):
                    samples = data[:limit]
                else:
                    samples = [data]

        return {"samples": samples, "total_shown": len(samples)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取失败：{str(e)}")


@router.get("/{dataset_id}/statistics", response_model=DatasetStatistics)
async def get_dataset_statistics(dataset_id: str):
    """获取数据集统计信息"""
    datasets_dir = get_datasets_dir()
    dataset_path = datasets_dir / dataset_id

    if not dataset_path.exists():
        raise HTTPException(status_code=404, detail="数据集不存在")

    data_files = []
    for ext in [".json", ".jsonl"]:
        data_files.extend(list(dataset_path.glob(f"*{ext}")))

    if not data_files:
        raise HTTPException(status_code=404, detail="数据文件不存在")

    data_file = data_files[0]
    statistics = compute_statistics(data_file)

    return statistics.model_dump()


@router.post("/{dataset_id}/refresh-stats")
async def refresh_dataset_statistics(dataset_id: str):
    """刷新数据集统计信息"""
    datasets_dir = get_datasets_dir()
    dataset_path = datasets_dir / dataset_id

    if not dataset_path.exists():
        raise HTTPException(status_code=404, detail="数据集不存在")

    data_files = []
    for ext in [".json", ".jsonl"]:
        data_files.extend(list(dataset_path.glob(f"*{ext}")))

    if not data_files:
        raise HTTPException(status_code=404, detail="数据文件不存在")

    data_file = data_files[0]
    statistics = compute_statistics(data_file)

    info_file = dataset_path / "info.json"
    info = {}
    if info_file.exists():
        with open(info_file, encoding="utf-8") as f:
            info = json.load(f)

    info["statistics"] = statistics.model_dump()
    info["updated_at"] = datetime.now().isoformat()

    with open(info_file, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)

    return {
        "message": "统计信息已更新",
        "statistics": statistics.model_dump()
    }
