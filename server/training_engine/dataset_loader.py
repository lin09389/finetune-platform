"""
数据集加载模块 - 支持多种格式，智能标签掩码，多数据集混合
"""
import json
import os
from pathlib import Path
from typing import Any

from core.logging import get_logger
from training_engine.dataset_formatter import _detect_and_format, _mask_before_assistant, _mask_before_response

logger = get_logger(__name__)


def load_dataset(dataset_path: str, tokenizer, max_length: int = 512):
    """加载数据集 - 支持多种格式，智能标签掩码"""
    from datasets import Dataset
    try:
        from datasets.utils.logging import disable_progress_bar
        disable_progress_bar()
    except Exception:
        os.environ["HF_DATASETS_DISABLE_PROGRESS_BAR"] = "1"
        os.environ["TQDM_DISABLE"] = "1"

    logger.info(f"加载数据集：{dataset_path}")

    if dataset_path.endswith(".jsonl"):
        data = []
        with open(dataset_path, encoding="utf-8") as f:
            for line in f:
                data.append(json.loads(line))
    else:
        with open(dataset_path, encoding="utf-8") as f:
            data = json.load(f)

    dataset = Dataset.from_list(data)
    dataset = dataset.map(lambda ex: _detect_and_format(ex, tokenizer))

    def tokenize_with_labels(examples):
        """Tokenize text and set labels based on sample format."""
        input_ids = tokenizer(
            examples["text"],
            truncation=True,
            max_length=max_length,
            padding="max_length",
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

            pad_id = tokenizer.pad_token_id
            if pad_id is not None:
                for j in range(len(label)):
                    if label[j] == pad_id:
                        label[j] = -100

            labels.append(label)

        input_ids["labels"] = labels
        return input_ids

    original_columns = dataset.column_names
    dataset = dataset.map(tokenize_with_labels, batched=True, remove_columns=original_columns)
    dataset = split_train_test_dataset(dataset)

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
    if sample_count <= 1:
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
