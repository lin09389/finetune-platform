"""
数据集管理 API - 增强安全校验和统计功能
"""
import json
import random
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


class DatasetAnalyzeRequest(BaseModel):
    """Analyze an existing dataset by id."""
    dataset_id: str | None = None
    target_goal: str | None = None


class DatasetIssue(BaseModel):
    line: int
    message: str
    severity: str = "error"


class DatasetLengthStats(BaseModel):
    min_chars: int
    max_chars: int
    avg_chars: float
    overlong_ratio: float


class DatasetAnalysisResponse(BaseModel):
    detected_format: str
    field_candidates: dict[str, list[str]]
    sample_count: int
    valid_count: int
    errors: list[DatasetIssue]
    warnings: list[DatasetIssue]
    length_stats: DatasetLengthStats
    recommended_target_format: str
    health: dict[str, Any]


class DatasetTransformRequest(BaseModel):
    target_format: str = "openai_messages"
    task_goal: str = "qa_assistant"
    output_name: str | None = None


class DatasetTransformResponse(BaseModel):
    message: str
    dataset_id: str
    target_format: str
    output_path: str
    sample_count: int


class DatasetSplitRequest(BaseModel):
    train_ratio: float = 0.8
    validation_ratio: float = 0.1
    test_ratio: float = 0.1
    seed: int = 42


class DatasetSplitResponse(BaseModel):
    message: str
    dataset_id: str
    output_dir: str
    splits: dict[str, dict[str, Any]]


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


def _find_dataset_file(dataset_path: Path) -> Path | None:
    for ext in [".jsonl", ".json"]:
        for data_file in dataset_path.glob(f"*{ext}"):
            if data_file.name != "info.json":
                return data_file
    return None


def _load_dataset_samples(file_path: Path, limit: int | None = None) -> tuple[list[dict[str, Any]], list[DatasetIssue]]:
    samples: list[dict[str, Any]] = []
    errors: list[DatasetIssue] = []

    try:
        with open(file_path, encoding="utf-8") as f:
            if file_path.suffix.lower() == ".jsonl":
                for line_number, line in enumerate(f, start=1):
                    if limit is not None and len(samples) >= limit:
                        break
                    if not line.strip():
                        continue
                    try:
                        value = json.loads(line)
                    except json.JSONDecodeError as exc:
                        errors.append(DatasetIssue(line=line_number, message=f"Invalid JSON: {exc}"))
                        continue
                    if isinstance(value, dict):
                        samples.append(value)
                    else:
                        errors.append(DatasetIssue(line=line_number, message="Sample must be an object"))
            else:
                value = json.load(f)
                raw_samples = value if isinstance(value, list) else [value]
                for index, item in enumerate(raw_samples, start=1):
                    if limit is not None and len(samples) >= limit:
                        break
                    if isinstance(item, dict):
                        samples.append(item)
                    else:
                        errors.append(DatasetIssue(line=index, message="Sample must be an object"))
    except json.JSONDecodeError as exc:
        errors.append(DatasetIssue(line=1, message=f"Invalid JSON: {exc}"))
    except Exception as exc:
        errors.append(DatasetIssue(line=1, message=f"Read failed: {exc}"))

    return samples, errors


def _sample_text(sample: dict[str, Any]) -> str:
    if isinstance(sample.get("messages"), list):
        return "\n".join(str(message.get("content", "")) for message in sample["messages"] if isinstance(message, dict))
    values = []
    for key in ["question", "context", "answer", "instruction", "input", "output", "text", "content"]:
        if key in sample:
            values.append(str(sample.get(key) or ""))
    return "\n".join(values)


def _detect_dataset_format(samples: list[dict[str, Any]]) -> str:
    if not samples:
        return "unknown"

    keys = set().union(*(sample.keys() for sample in samples[:100]))
    if {"question", "answer"}.issubset(keys):
        return "faq_qa" if "context" not in keys else "qa_with_context"
    if "messages" in keys:
        first_messages = next((sample.get("messages") for sample in samples if isinstance(sample.get("messages"), list)), [])
        roles = {
            message.get("role")
            for message in first_messages
            if isinstance(message, dict)
        }
        return "sharegpt" if {"human", "gpt"} & roles else "openai_messages"
    if {"instruction", "output"}.issubset(keys):
        return "alpaca"
    if {"input", "schema", "output"}.issubset(keys):
        return "structured_extraction"
    if {"text"} & keys:
        return "plain_text"
    return "unknown"


def _field_candidates(samples: list[dict[str, Any]]) -> dict[str, list[str]]:
    keys = sorted(set().union(*(sample.keys() for sample in samples[:100]))) if samples else []
    return {
        "prompt": [key for key in keys if key in {"question", "instruction", "input", "text", "content"}],
        "context": [key for key in keys if key in {"context", "document", "knowledge"}],
        "response": [key for key in keys if key in {"answer", "output", "response", "completion"}],
        "schema": [key for key in keys if key in {"schema", "json_schema", "fields"}],
        "messages": [key for key in keys if key == "messages"],
    }


def _is_valid_for_training(sample: dict[str, Any]) -> bool:
    if isinstance(sample.get("messages"), list) and sample["messages"]:
        return True
    keys = sample.keys()
    return bool(
        {"question", "answer"}.issubset(keys)
        or {"instruction", "output"}.issubset(keys)
        or {"input", "output"}.issubset(keys)
        or "text" in keys
        or "content" in keys
    )


def _analyze_samples(samples: list[dict[str, Any]], parse_errors: list[DatasetIssue], target_goal: str | None = None) -> DatasetAnalysisResponse:
    warnings: list[DatasetIssue] = []
    valid_count = 0
    lengths: list[int] = []
    fingerprints: set[str] = set()
    duplicate_count = 0

    for index, sample in enumerate(samples, start=1):
        text = _sample_text(sample)
        lengths.append(len(text))
        fingerprint = json.dumps(sample, ensure_ascii=False, sort_keys=True)
        if fingerprint in fingerprints:
            duplicate_count += 1
        fingerprints.add(fingerprint)

        if _is_valid_for_training(sample):
            valid_count += 1
        else:
            warnings.append(DatasetIssue(line=index, message="Missing trainable fields", severity="warning"))

        if len(text) > 8000:
            warnings.append(DatasetIssue(line=index, message="Sample is longer than 8000 characters", severity="warning"))

    sample_count = len(samples)
    detected_format = _detect_dataset_format(samples)
    overlong_count = sum(1 for length in lengths if length > 8000)
    recommended = "input_schema_output_jsonl" if target_goal == "structured_extraction" or detected_format == "structured_extraction" else "openai_messages"
    json_valid_ratio = sample_count / (sample_count + len(parse_errors)) if sample_count or parse_errors else 1.0
    field_completeness = valid_count / sample_count if sample_count else 0.0

    return DatasetAnalysisResponse(
        detected_format=detected_format,
        field_candidates=_field_candidates(samples),
        sample_count=sample_count + len(parse_errors),
        valid_count=valid_count,
        errors=parse_errors[:100],
        warnings=warnings[:100],
        length_stats=DatasetLengthStats(
            min_chars=min(lengths) if lengths else 0,
            max_chars=max(lengths) if lengths else 0,
            avg_chars=round(sum(lengths) / len(lengths), 2) if lengths else 0.0,
            overlong_ratio=round(overlong_count / sample_count, 4) if sample_count else 0.0,
        ),
        recommended_target_format=recommended,
        health={
            "json_valid_ratio": round(json_valid_ratio, 4),
            "field_completeness": round(field_completeness, 4),
            "overlong_sample_ratio": round(overlong_count / sample_count, 4) if sample_count else 0.0,
            "duplicate_sample_ratio": round(duplicate_count / sample_count, 4) if sample_count else 0.0,
            "trainable_sample_count": valid_count,
        },
    )


def _to_openai_messages(sample: dict[str, Any], task_goal: str) -> dict[str, Any]:
    if isinstance(sample.get("messages"), list):
        return {"messages": sample["messages"]}

    if task_goal == "structured_extraction":
        schema = sample.get("schema") or sample.get("json_schema") or sample.get("fields") or {}
        user_content = sample.get("input") or sample.get("instruction") or sample.get("text") or sample.get("content") or ""
        if schema:
            user_content = f"请从输入中抽取字段并严格输出 JSON。\nSchema: {json.dumps(schema, ensure_ascii=False)}\nInput: {user_content}"
        return {
            "messages": [
                {"role": "user", "content": str(user_content)},
                {"role": "assistant", "content": json.dumps(sample.get("output", {}), ensure_ascii=False) if not isinstance(sample.get("output"), str) else sample.get("output", "")},
            ]
        }

    question = sample.get("question") or sample.get("instruction") or sample.get("input") or sample.get("text") or sample.get("content") or ""
    context = sample.get("context")
    if context:
        question = f"参考资料：\n{context}\n\n问题：{question}"
    answer = sample.get("answer") or sample.get("output") or sample.get("response") or ""
    return {
        "messages": [
            {"role": "user", "content": str(question)},
            {"role": "assistant", "content": str(answer)},
        ]
    }


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


@router.post("/analyze", response_model=DatasetAnalysisResponse)
async def analyze_dataset(request: DatasetAnalyzeRequest):
    """Analyze an existing dataset for training readiness."""
    request = request or DatasetAnalyzeRequest()
    if not request.dataset_id:
        raise HTTPException(status_code=400, detail="dataset_id 是必填项")

    dataset_path = get_datasets_dir() / request.dataset_id
    if not dataset_path.exists():
        raise HTTPException(status_code=404, detail="数据集不存在")
    if not validate_path_security(get_datasets_dir(), dataset_path):
        raise HTTPException(status_code=400, detail="无效的数据集路径")

    data_file = _find_dataset_file(dataset_path)
    if not data_file:
        raise HTTPException(status_code=404, detail="数据文件不存在")

    samples, errors = _load_dataset_samples(data_file)
    return _analyze_samples(samples, errors, request.target_goal)


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


@router.post("/{dataset_id}/transform", response_model=DatasetTransformResponse)
async def transform_dataset(dataset_id: str, request: DatasetTransformRequest):
    """Transform a dataset into a standard training JSONL file."""
    datasets_dir = get_datasets_dir()
    dataset_path = datasets_dir / dataset_id
    if not dataset_path.exists():
        raise HTTPException(status_code=404, detail="数据集不存在")
    if not validate_path_security(datasets_dir, dataset_path):
        raise HTTPException(status_code=400, detail="无效的数据集路径")

    data_file = _find_dataset_file(dataset_path)
    if not data_file:
        raise HTTPException(status_code=404, detail="数据文件不存在")

    samples, errors = _load_dataset_samples(data_file)
    if errors and not samples:
        raise HTTPException(status_code=400, detail=f"数据集无法解析：{errors[0].message}")

    target_format = request.target_format
    output_name = safe_filename(request.output_name or f"{dataset_id}-{target_format}.jsonl")
    if not output_name.endswith(".jsonl"):
        output_name += ".jsonl"
    output_path = dataset_path / output_name

    transformed: list[dict[str, Any]] = []
    for sample in samples:
        if not _is_valid_for_training(sample):
            continue
        if target_format in {"openai_messages", "messages"}:
            transformed.append(_to_openai_messages(sample, request.task_goal))
        elif target_format in {"input_schema_output_jsonl", "structured_extraction"}:
            transformed.append({
                "input": sample.get("input") or sample.get("question") or sample.get("instruction") or sample.get("text") or "",
                "schema": sample.get("schema") or sample.get("json_schema") or sample.get("fields") or {},
                "output": sample.get("output") or sample.get("answer") or sample.get("response") or "",
            })
        else:
            raise HTTPException(status_code=400, detail=f"不支持的目标格式：{target_format}")

    with open(output_path, "w", encoding="utf-8") as f:
        for item in transformed:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    return DatasetTransformResponse(
        message="数据集转换完成",
        dataset_id=dataset_id,
        target_format=target_format,
        output_path=str(output_path),
        sample_count=len(transformed),
    )


@router.post("/{dataset_id}/split", response_model=DatasetSplitResponse)
async def split_dataset(dataset_id: str, request: DatasetSplitRequest):
    """Create train/validation/test JSONL splits for a dataset."""
    total_ratio = request.train_ratio + request.validation_ratio + request.test_ratio
    if abs(total_ratio - 1.0) > 0.001:
        raise HTTPException(status_code=400, detail="train/validation/test 比例之和必须等于 1")

    datasets_dir = get_datasets_dir()
    dataset_path = datasets_dir / dataset_id
    if not dataset_path.exists():
        raise HTTPException(status_code=404, detail="数据集不存在")
    if not validate_path_security(datasets_dir, dataset_path):
        raise HTTPException(status_code=400, detail="无效的数据集路径")

    data_file = _find_dataset_file(dataset_path)
    if not data_file:
        raise HTTPException(status_code=404, detail="数据文件不存在")

    samples, errors = _load_dataset_samples(data_file)
    if errors and not samples:
        raise HTTPException(status_code=400, detail=f"数据集无法解析：{errors[0].message}")

    rng = random.Random(request.seed)
    shuffled = list(samples)
    rng.shuffle(shuffled)

    train_end = int(len(shuffled) * request.train_ratio)
    validation_end = train_end + int(len(shuffled) * request.validation_ratio)
    split_payloads = {
        "train": shuffled[:train_end],
        "validation": shuffled[train_end:validation_end],
        "test": shuffled[validation_end:],
    }

    output_dir = dataset_path / "splits"
    output_dir.mkdir(exist_ok=True)
    splits: dict[str, dict[str, Any]] = {}
    for split_name, split_samples in split_payloads.items():
        output_path = output_dir / f"{split_name}.jsonl"
        with open(output_path, "w", encoding="utf-8") as f:
            for item in split_samples:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        splits[split_name] = {
            "path": str(output_path),
            "sample_count": len(split_samples),
        }

    return DatasetSplitResponse(
        message="数据集切分完成",
        dataset_id=dataset_id,
        output_dir=str(output_dir),
        splits=splits,
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
