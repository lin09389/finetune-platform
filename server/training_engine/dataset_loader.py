"""
数据集加载模块 - 支持多种格式，智能标签掩码，多数据集混合

性能优化：
- 使用动态填充（padding=False）替代 padding="max_length"，减少 20-40% 训练耗时
- 添加 map 缓存，避免重复 tokenize
- 标签掩码中 pad token 统一在 DataCollator 阶段处理
"""
import hashlib
import json
import os
import random
from pathlib import Path
from typing import Any

from core.logging import get_logger
from training_engine.dataset_formatter import (
    _detect_and_format,
    _mask_before_assistant,
    _mask_before_response,
)

logger = get_logger(__name__)


def load_raw_dataset_records(dataset_path: str) -> list[dict[str, Any]]:
    """Load source records without tokenization for immutable evaluation snapshots."""
    if dataset_path.endswith(".jsonl"):
        records: list[dict[str, Any]] = []
        with open(dataset_path, encoding="utf-8") as stream:
            for line in stream:
                line = line.strip()
                if not line:
                    continue
                item = json.loads(line)
                if isinstance(item, dict):
                    records.append(item)
        return records

    with open(dataset_path, encoding="utf-8") as stream:
        payload = json.load(stream)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return [payload] if isinstance(payload, dict) else []


def split_raw_dataset_records(
    records: list[dict[str, Any]],
    test_size: float = 0.1,
    seed: int = 42,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Mirror the stable train/test policy while preserving original examples."""
    sample_count = len(records)
    if sample_count < 5:
        return list(records), []
    test_items = 1 if sample_count < 10 else max(1, int(round(sample_count * test_size)))
    test_items = min(test_items, sample_count - 1)
    indices = list(range(sample_count))
    random.Random(seed).shuffle(indices)
    test_indices = set(indices[:test_items])
    train = [item for index, item in enumerate(records) if index not in test_indices]
    test = [item for index, item in enumerate(records) if index in test_indices]
    return train, test


def write_evaluation_snapshot(dataset_path: str, output_dir: str | Path) -> tuple[str | None, str | None]:
    """Persist the held-out source examples next to the release."""
    from training_engine.reporter import hash_path

    records = load_raw_dataset_records(dataset_path)
    _, test_records = split_raw_dataset_records(records)
    if not test_records:
        return None, None
    destination = Path(output_dir) / "evaluation_snapshot.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(test_records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(destination), hash_path(destination)


def _dataset_cache_dir(dataset_path: str) -> str:
    """基于数据集路径+大小+修改时间生成缓存目录，避免内容变化后缓存失效。"""
    file_stat = os.stat(dataset_path)
    content_key = f"{dataset_path}:{file_stat.st_size}:{file_stat.st_mtime}"
    path_hash = hashlib.md5(content_key.encode()).hexdigest()[:12]
    cache_root = os.path.join(os.path.dirname(dataset_path), ".cache", "datasets")
    cache_dir = os.path.join(cache_root, path_hash)
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def load_dataset(dataset_path: str, tokenizer, max_length: int = 512):
    """加载数据集 - 支持多种格式，智能标签掩码，动态填充"""
    from datasets import Dataset, DatasetDict
    try:
        from datasets.utils.logging import disable_progress_bar
        disable_progress_bar()
    except Exception:
        os.environ["HF_DATASETS_DISABLE_PROGRESS_BAR"] = "1"
        os.environ["TQDM_DISABLE"] = "1"

    logger.info(f"加载数据集：{dataset_path}")

    cache_dir = _dataset_cache_dir(dataset_path)

    source_records = load_raw_dataset_records(dataset_path)
    train_records, test_records = split_raw_dataset_records(source_records)

    def tokenize_with_labels(examples):
        """Tokenize text and set labels based on sample format.

        使用 padding=False 进行 tokenize，动态填充交给 DataCollator 处理，
        避免将所有样本填充到 max_length 造成的冗余计算。
        """
        input_ids = tokenizer(
            examples["text"],
            truncation=True,
            max_length=max_length,
            padding=False,
        )

        batch_size = len(examples["text"])
        labels = []

        for i in range(batch_size):
            label = list(input_ids["input_ids"][i])
            fmt = examples.get("sample_format", ["text"] * batch_size)[i]
            text = examples["text"][i]

            if fmt == "instruction":
                _mask_before_response(label, text, tokenizer)
            elif fmt == "messages":
                _mask_before_assistant(label, text, tokenizer)

            labels.append(label)

        input_ids["labels"] = labels
        return input_ids

    def prepare_split(records: list[dict[str, Any]], name: str):
        split = Dataset.from_list(records)
        split = split.map(
            lambda ex: _detect_and_format(ex, tokenizer),
            cache_file_name=os.path.join(cache_dir, f"{name}_format_cache.arrow"),
        )
        original_columns = split.column_names
        return split.map(
            tokenize_with_labels,
            batched=True,
            remove_columns=original_columns,
            cache_file_name=os.path.join(cache_dir, f"{name}_tokenize_cache.arrow"),
        )

    dataset = DatasetDict({
        "train": prepare_split(train_records, "train"),
        "test": prepare_split(test_records, "test") if test_records else Dataset.from_list([]),
    })

    logger.info(f"数据集大小：训练={len(dataset['train'])}, 测试={len(dataset.get('test', []))}")
    return dataset


def load_multiple_datasets(
    dataset_path: str,
    additional_datasets: list[dict[str, Any]],
    tokenizer,
    max_length: int = 512,
    settings=None
):
    """加载多个数据集并进行混合训练

    Args:
        dataset_path: 主数据集路径
        additional_datasets: 额外数据集列表[{"dataset_id": "xxx", "weight": 0.3}, ...]
        tokenizer: 分词器
        max_length: 最大序列长度
        settings: 配置对象

    Returns:
        混合后的数据集
    """
    from datasets import interleave_datasets

    logger.info(f"加载主数据集：{dataset_path}")

    main_dataset = load_dataset(dataset_path, tokenizer, max_length)
    main_train = main_dataset["train"]

    if not additional_datasets:
        return main_dataset

    weights = [1.0]
    dataset_list = [main_train]

    for ds_config in additional_datasets:
        ds_id = ds_config.get("dataset_id")
        weight = ds_config.get("weight", 1.0)

        ds_path = None
        if settings:
            ds_dir = settings.datasets_dir_resolved / ds_id
            for ext in [".json", ".jsonl"]:
                for f in ds_dir.glob(f"*{ext}"):
                    ds_path = str(f)
                    break
                if ds_path:
                    break

        if ds_path and os.path.exists(ds_path):
            logger.info(f"加载额外数据集：{ds_id}, weight={weight}")
            ds = load_dataset(ds_path, tokenizer, max_length)
            dataset_list.append(ds["train"])
            weights.append(weight)
        else:
            logger.warning(f"数据集不存在，跳过：{ds_id}")

    if len(dataset_list) == 1:
        return main_dataset

    total_weight = sum(weights)
    normalized_weights = [w / total_weight for w in weights]

    logger.info(f"混合数据集：{len(dataset_list)} 个，权重={normalized_weights}")

    interleaved = interleave_datasets(
        dataset_list,
        probabilities=normalized_weights,
        seed=42
    )

    interleaved = split_train_test_dataset(interleaved)
    logger.info(f"混合数据集大小：训练={len(interleaved['train'])}, 测试={len(interleaved.get('test', []))}")
    return interleaved


def split_train_test_dataset(dataset, test_size: float = 0.1):
    """Create a stable train/test split even for very small datasets."""
    from datasets import DatasetDict

    sample_count = len(dataset)
    if sample_count < 5:
        return DatasetDict({
            "train": dataset,
            "test": dataset.select([]),
        })

    if sample_count < 10:
        test_items = 1
    else:
        test_items = max(1, int(round(sample_count * test_size)))

    test_items = min(test_items, sample_count - 1)
    return dataset.train_test_split(test_size=test_items, seed=42)
