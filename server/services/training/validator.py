"""
训练验证服务 - 配置校验、资源估算、预检
"""
from core.config import Settings
from core.logging import get_logger
from training_engine.dataset_formatter import detect_dataset_sample_format
from training_engine.schemas import (
    RELEASE_EXPERIMENTAL_FEATURE_MESSAGES,
    TrainingConfigInput,
    TrainingPreflightCheck,
    ValidationResult,
)

logger = get_logger(__name__)


def validate_release_supported_features(
    config: TrainingConfigInput,
    backend: str = "standard",
) -> None:
    """Reject experimental fine-tuning options from the public release path."""
    from fastapi import HTTPException
    for field_name, detail in RELEASE_EXPERIMENTAL_FEATURE_MESSAGES.items():
        if getattr(config, field_name, False):
            raise HTTPException(status_code=400, detail=detail)

    if config.method == "dora":
        raise HTTPException(
            status_code=400,
            detail=RELEASE_EXPERIMENTAL_FEATURE_MESSAGES["use_dora"],
        )

    if backend == "swift" and config.method not in {"lora", "qlora"}:
        raise HTTPException(
            status_code=400,
            detail="SWIFT 发布路径当前仅开放 LoRA / QLoRA",
        )


class TrainingValidator:
    """训练验证器"""

    @staticmethod
    async def validate_config(config: TrainingConfigInput, settings: Settings) -> ValidationResult:
        """验证训练配置"""
        result = ValidationResult()

        TrainingValidator._validate_resources(config, result)
        await TrainingValidator._validate_dataset(config, settings, result)
        await TrainingValidator._validate_model(config, settings, result)
        TrainingValidator._validate_parameters(config, result)

        return result

    @staticmethod
    def _validate_resources(config: TrainingConfigInput, result: ValidationResult):
        """资源验证"""
        try:
            import torch

            if not torch.cuda.is_available():
                result.errors.append("CUDA 不可用，无法进行 GPU 训练")
                return

            estimated_vram = TrainingValidator._estimate_vram(
                config.model_id,
                config.method,
                config.batch_size,
                config.max_seq_length
            )

            available_vram = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
            allocated_vram = torch.cuda.memory_allocated(0) / (1024 ** 3)
            free_vram = available_vram - allocated_vram

            if free_vram < estimated_vram * 0.9:
                result.warnings.append(
                    f"预计需要 {estimated_vram:.1f}GB VRAM, 可用 {free_vram:.1f}GB"
                )
        except Exception as e:
            result.warnings.append(f"资源检查失败：{e}")

    @staticmethod
    def _estimate_vram(model_id: str, method: str, batch_size: int, max_seq_length: int) -> float:
        """估算 VRAM 需求 - 委托给统一的 estimate_training_vram 函数"""
        from training_engine.model_loader import _estimate_model_params, _read_model_hidden_and_layers, estimate_training_vram

        param_count = _estimate_model_params(model_id)
        hidden_size, num_layers = _read_model_hidden_and_layers(model_id)

        quantization = 0
        if method == "qlora":
            quantization = 4

        return estimate_training_vram(
            param_count=param_count,
            method=method,
            quantization=quantization,
            batch_size=batch_size,
            max_seq_length=max_seq_length,
            gradient_checkpointing=True,
            use_flash_attn=False,
            bf16=True,
            lora_rank=8,
            hidden_size=hidden_size,
            num_layers=num_layers,
        )

    @staticmethod
    async def _validate_dataset(config: TrainingConfigInput, settings: Settings, result: ValidationResult):
        """数据集验证"""
        try:
            dataset_path = settings.datasets_dir_resolved / config.dataset_id

            if not dataset_path.exists():
                result.errors.append(f"数据集不存在：{config.dataset_id}")
                return

            dataset_file = None
            for ext in [".json", ".jsonl"]:
                for f in dataset_path.glob(f"*{ext}"):
                    dataset_file = f
                    break
                if dataset_file:
                    break

            if not dataset_file:
                result.errors.append("不支持的数据集格式，需要 .json 或 .jsonl")
                return

            import json
            is_jsonl = dataset_file.suffix == ".jsonl"

            if is_jsonl:
                MAX_VALIDATE_LINES = 5
                first_item = None
                line_errors = []
                with open(dataset_file, encoding='utf-8') as f:
                    for i, line in enumerate(f):
                        if i >= MAX_VALIDATE_LINES:
                            break
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            item = json.loads(line)
                            if first_item is None:
                                first_item = item
                        except json.JSONDecodeError as e:
                            line_errors.append(f"Line {i + 1}: {e}")

                if line_errors:
                    result.errors.append(f"JSONL 格式错误（前 {MAX_VALIDATE_LINES} 行）：{'; '.join(line_errors)}")
                elif first_item is None:
                    result.errors.append("数据集至少需要包含一条样本")
                else:
                    try:
                        detect_dataset_sample_format(first_item)
                    except ValueError as e:
                        result.errors.append(str(e))
            else:
                with open(dataset_file, encoding='utf-8') as f:
                    content = f.read()
                    try:
                        data = json.loads(content)

                        if isinstance(data, list) and len(data) > 0:
                            first_item = data[0]
                            try:
                                detect_dataset_sample_format(first_item)
                            except ValueError as e:
                                result.errors.append(str(e))
                        elif isinstance(data, list):
                            result.errors.append("数据集至少需要包含一条样本")
                        elif isinstance(data, dict):
                            try:
                                detect_dataset_sample_format(data)
                            except ValueError as e:
                                result.errors.append(str(e))
                        else:
                            result.errors.append("数据集根节点必须是 JSON 对象或对象数组")
                    except json.JSONDecodeError as e:
                        result.errors.append(f"JSON 格式错误：{e}")
        except Exception as e:
            result.errors.append(f"数据集验证失败：{e}")

    @staticmethod
    async def _validate_model(config: TrainingConfigInput, settings: Settings, result: ValidationResult):
        """模型验证"""
        try:
            model_path = settings.models_dir_resolved / config.model_id

            if not model_path.exists():
                result.errors.append(f"模型不存在：{config.model_id}")
                return

            config_file = model_path / "config.json"
            if config_file.exists():
                import json
                with open(config_file) as f:
                    model_config = json.load(f)

                model_type = model_config.get("model_type", "")
                supported_types = ["llama", "mistral", "gemma", "qwen", "chatglm", "baichuan"]
                if model_type and model_type not in supported_types:
                    result.warnings.append(
                        f"模型类型 '{model_type}' 可能不受支持，已知支持：{supported_types}"
                    )
        except Exception as e:
            result.warnings.append(f"模型验证失败：{e}")

    @staticmethod
    def _validate_parameters(config: TrainingConfigInput, result: ValidationResult):
        """参数合理性验证"""
        if not (1e-6 <= config.learning_rate <= 1e-3):
            result.warnings.append(
                f"学习率 {config.learning_rate} 可能不合理，推荐范围 1e-6 ~ 1e-3"
            )

        effective_batch = config.batch_size * config.gradient_accumulation
        if effective_batch < 4:
            result.warnings.append(
                f"有效批次大小 {effective_batch} 过小，可能影响训练稳定性"
            )
        elif effective_batch > 128:
            result.warnings.append(
                f"有效批次大小 {effective_batch} 过大，可能导致 OOM"
            )

        if config.rank > 64:
            result.warnings.append(
                f"LoRA rank={config.rank} 较高，可能导致过拟合"
            )

        if config.epochs > 10:
            result.warnings.append(
                f"训练轮数 {config.epochs} 较多，注意过拟合风险"
            )


def estimate_preflight_required_vram(config: TrainingConfigInput) -> float:
    """预检 VRAM 需求估算 - 委托给统一函数"""
    from training_engine.model_loader import _estimate_model_params, _read_model_hidden_and_layers, estimate_training_vram

    param_count = _estimate_model_params(config.model_id)
    hidden_size, num_layers = _read_model_hidden_and_layers(config.model_id)

    estimated = estimate_training_vram(
        param_count=param_count,
        method=config.method,
        quantization=config.quantization if config.method == "qlora" else 0,
        batch_size=config.batch_size,
        max_seq_length=config.max_seq_length,
        gradient_checkpointing=config.gradient_checkpointing,
        use_flash_attn=config.use_flash_attn,
        bf16=config.bf16,
        lora_rank=config.rank,
        hidden_size=hidden_size,
        num_layers=num_layers,
    )
    return max(0.5, round(estimated, 1))


def preflight_check(
    checks: list,
    key: str,
    label: str,
    status: str,
    message: str,
    detail: str | None = None,
) -> None:
    checks.append(
        TrainingPreflightCheck(
            key=key,
            label=label,
            status=status,
            message=message,
            detail=detail,
        )
    )
