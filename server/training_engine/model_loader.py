"""
模型加载模块 - 支持 LoRA/QLoRA/Full/DoRA，量化，Flash Attention

优化点：
- 职责拆分：量化配置、模型加载、Tokenizer、LoRA 配置、检查点恢复各自独立
- 并发安全：加载锁防止同时加载同一模型导致 OOM
- 优雅降级：Flash Attention / bitsandbytes 失败自动回退
- 显存预检：加载前检查可用显存，提前失败
- 修复 DoRA：配置中设置 use_dora=True
- BF16 支持：根据 GPU 架构自动选择 bfloat16/float16
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from typing import Any

from core.logging import get_logger
from core.utils import cleanup_gpu_memory, get_available_memory

logger = get_logger(__name__)

# 全局加载锁：防止并发加载同一模型导致 OOM
_model_load_locks: dict[str, threading.Lock] = {}
_model_load_master_lock = threading.Lock()


def _get_load_lock(cache_key: str) -> threading.Lock:
    """获取指定模型的加载锁"""
    with _model_load_master_lock:
        if cache_key not in _model_load_locks:
            _model_load_locks[cache_key] = threading.Lock()
        return _model_load_locks[cache_key]


@dataclass
class ModelLoadConfig:
    """模型加载配置数据类"""
    model_path: str = ""
    method: str = "qlora"
    quantize: int = 4
    resume_from: str | None = None
    rank: int = 8
    alpha: int = 16
    lora_dropout: float = 0.05
    target_modules: str = "all"
    use_dora: bool = False
    use_flash_attn: bool = False
    gradient_checkpointing: bool = True
    deepspeed_config: dict[str, Any] | None = None
    use_lora_plus: bool = False
    lora_plus_lr_ratio: float = 16.0
    trust_remote_code: bool = True
    torch_dtype: Any = None
    bf16: bool = True

    # 内部生成字段
    quantization_config: Any = field(default=None, repr=False)
    target_modules_list: list[str] = field(default_factory=list, repr=False)


def _build_cache_key(config: ModelLoadConfig) -> str:
    """构建缓存键，确保相同配置的模型可以复用"""
    parts = [
        config.model_path,
        config.method,
        str(config.quantize),
        str(config.rank),
        str(config.alpha),
        config.target_modules,
        str(config.use_dora),
        str(config.use_flash_attn),
    ]
    return "|".join(parts)


def _resolve_target_modules(target_modules: str) -> list[str]:
    """解析目标模块字符串为模块列表"""
    if target_modules == "all":
        return [
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ]
    elif target_modules == "attn":
        return ["q_proj", "v_proj", "k_proj", "o_proj"]
    elif target_modules == "mlp":
        return ["gate_proj", "up_proj", "down_proj"]
    else:
        return [m.strip() for m in target_modules.split(",") if m.strip()]


def _build_quantization_config(config: ModelLoadConfig) -> Any:
    """构建量化配置，失败时优雅降级为普通 LoRA"""
    if config.method != "qlora" or config.quantize not in [4, 8]:
        return None

    try:
        import torch
        from bitsandbytes import BitsAndBytesConfig

        q_config = BitsAndBytesConfig(
            load_in_4bit=(config.quantize == 4),
            load_in_8bit=(config.quantize == 8),
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
        )
        logger.info(f"量化配置已创建：{config.quantize}-bit")
        return q_config
    except Exception as e:
        logger.warning(f"bitsandbytes 不可用，将降级为标准 LoRA: {e}")
        config.method = "lora"
        return None


def _check_vram_before_load(config: ModelLoadConfig) -> None:
    """加载前检查显存，提前发现 OOM 风险"""
    available = get_available_memory()
    if available is None:
        return

    estimated_gb = _estimate_vram_required(config)
    if available < estimated_gb:
        logger.warning(
            f"可用显存 {available:.2f}GB 可能不足，预估需要 {estimated_gb:.2f}GB"
        )
        if available < estimated_gb * 0.5:
            raise RuntimeError(
                f"显存严重不足：可用 {available:.2f}GB，预估需要 {estimated_gb:.2f}GB。"
                f"建议降低量化位数、减小 batch_size 或关闭其他 GPU 程序。"
            )


def _estimate_vram_required(config: ModelLoadConfig) -> float:
    """粗略估算模型加载所需显存（GB）"""
    base = 2.0
    if config.method == "qlora" and config.quantize == 4:
        base += 4.0
    elif config.method == "qlora" and config.quantize == 8:
        base += 6.0
    elif config.method in ["lora", "dora"]:
        base += 10.0
    else:
        base += 14.0

    if config.use_flash_attn:
        base *= 0.85
    return base


def _load_base_model(config: ModelLoadConfig):
    """加载基础模型（不含 LoRA）"""
    import torch
    from transformers import AutoModelForCausalLM

    if config.torch_dtype is not None:
        dtype = config.torch_dtype
    elif config.bf16 and torch.cuda.is_available():
        dev_caps = torch.cuda.get_device_properties(0)
        if dev_caps.major >= 8:
            dtype = torch.bfloat16
        else:
            dtype = torch.float16
            logger.info("GPU 不支持 BF16（需 Ampere+），回退到 FP16")
    else:
        dtype = torch.float16

    load_kwargs = {
        "pretrained_model_name_or_path": config.model_path,
        "quantization_config": config.quantization_config,
        "device_map": "auto",
        "torch_dtype": dtype,
        "trust_remote_code": config.trust_remote_code,
    }

    if config.use_flash_attn and config.quantize == 0:
        try:
            load_kwargs["attn_implementation"] = "flash_attention_2"
            model = AutoModelForCausalLM.from_pretrained(**load_kwargs)
            logger.info("已启用 Flash Attention 2")
            return model
        except Exception as e:
            logger.warning(f"Flash Attention 2 不可用，回退到标准 attention: {e}")
            load_kwargs["attn_implementation"] = "eager"
            return AutoModelForCausalLM.from_pretrained(**load_kwargs)
    else:
        if config.use_flash_attn and config.quantize > 0:
            logger.warning("量化模式下无法使用 Flash Attention 2，回退到标准 attention")
        return AutoModelForCausalLM.from_pretrained(**load_kwargs)


def _load_tokenizer(config: ModelLoadConfig):
    """加载分词器并修复 pad_token"""
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        config.model_path,
        trust_remote_code=config.trust_remote_code,
    )

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        logger.debug("pad_token 已设置为 eos_token")

    return tokenizer


def _prepare_model_for_training(model, config: ModelLoadConfig):
    """为训练准备模型（梯度检查点、缓存设置）"""
    if config.gradient_checkpointing and hasattr(model, "config"):
        model.config.use_cache = False

    if config.method == "qlora" and config.quantization_config is not None:
        try:
            from peft import prepare_model_for_kbit_training

            model = prepare_model_for_kbit_training(
                model, use_gradient_checkpointing=config.gradient_checkpointing
            )
            logger.info("QLoRA: 已完成 k-bit 训练准备")
        except Exception as prep_error:
            logger.warning(
                f"QLoRA: prepare_model_for_kbit_training 失败，继续尝试训练: {prep_error}"
            )

    return model


def _build_lora_config(config: ModelLoadConfig):
    """构建 LoRA / DoRA 配置"""
    from peft import LoraConfig, TaskType

    lora_kwargs = {
        "task_type": TaskType.CAUSAL_LM,
        "r": config.rank,
        "lora_alpha": config.alpha,
        "lora_dropout": config.lora_dropout,
        "target_modules": config.target_modules_list,
        "bias": "none",
        "inference_mode": False,
    }

    if config.use_dora or config.method == "dora":
        lora_kwargs["use_dora"] = True
        logger.info("已启用 DoRA 权重分解")

    return LoraConfig(**lora_kwargs)


def _apply_lora_to_model(model, config: ModelLoadConfig):
    """将 LoRA 配置应用到模型"""
    from peft import get_peft_model

    lora_config = _build_lora_config(config)
    model = get_peft_model(model, lora_config)

    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    if trainable_params == 0:
        raise RuntimeError(
            "LoRA 配置后可训练参数为 0，请检查 target_modules 与模型结构是否匹配"
        )
    logger.info(f"可训练参数量：{trainable_params:,}")
    return model


def _resume_from_checkpoint(model, config: ModelLoadConfig):
    """从检查点恢复模型"""
    from peft import PeftModel

    if not config.resume_from or not os.path.exists(config.resume_from):
        return model

    logger.info(f"从检查点恢复：{config.resume_from}")
    model = PeftModel.from_pretrained(
        model, config.resume_from, is_trainable=True
    )
    return model


def _enable_gradient_checkpointing(model, config: ModelLoadConfig):
    """启用梯度检查点"""
    if not config.gradient_checkpointing:
        return model

    if hasattr(model, "enable_input_require_grads"):
        model.enable_input_require_grads()
    if hasattr(model, "gradient_checkpointing_enable"):
        model.gradient_checkpointing_enable()
    return model


def _apply_lora_plus(model, config: ModelLoadConfig):
    """应用 LoRA+ 配置（仅标记，优化器在后续阶段配置）"""
    if not config.use_lora_plus or config.method == "full":
        return

    logger.info(f"应用 LoRA+ 配置: lr_ratio={config.lora_plus_lr_ratio}")
    for name, param in model.named_parameters():
        if "lora_B" in name or "lora_A" in name:
            param.requires_grad = True


def load_model_and_tokenizer(
    model_path: str,
    method: str = "qlora",
    quantize: int = 4,
    resume_from: str | None = None,
    rank: int = 8,
    alpha: int = 16,
    lora_dropout: float = 0.05,
    target_modules: str = "all",
    use_dora: bool = False,
    use_flash_attn: bool = False,
    gradient_checkpointing: bool = True,
    deepspeed_config: dict[str, Any] | None = None,
    use_lora_plus: bool = False,
    lora_plus_lr_ratio: float = 16.0,
    bf16: bool = True,
):
    """加载模型和分词器（优化版）

    Args:
        model_path: 模型路径
        method: 微调方法 (lora/qlora/full/dora)
        quantize: 量化位数 (4/8/0)
        resume_from: 从检查点恢复的路径
        rank: LoRA rank
        alpha: LoRA alpha
        lora_dropout: LoRA dropout
        target_modules: 目标模块 (all/attn/mlp/自定义)
        use_dora: 是否使用 DoRA
        use_flash_attn: 是否使用 Flash Attention
        deepspeed_config: DeepSpeed 配置字典
        use_lora_plus: 是否使用 LoRA+
        lora_plus_lr_ratio: LoRA+ B/A 学习率比例
        bf16: 是否使用 BF16 精度

    Returns:
        (model, tokenizer)
    """
    config = ModelLoadConfig(
        model_path=model_path,
        method=method,
        quantize=quantize,
        resume_from=resume_from,
        rank=rank,
        alpha=alpha,
        lora_dropout=lora_dropout,
        target_modules=target_modules,
        use_dora=use_dora,
        use_flash_attn=use_flash_attn,
        gradient_checkpointing=gradient_checkpointing,
        deepspeed_config=deepspeed_config,
        use_lora_plus=use_lora_plus,
        lora_plus_lr_ratio=lora_plus_lr_ratio,
        bf16=bf16,
    )
    return _load_model_and_tokenizer_internal(config)


def _load_model_and_tokenizer_internal(config: ModelLoadConfig):
    """内部实现：带并发控制的模型加载

    注意：训练场景下不缓存模型，因为训练会修改权重导致缓存污染。
    缓存仅用于推理场景（通过 ModelCache 直接调用）。
    """
    cache_key = _build_cache_key(config)

    lock = _get_load_lock(cache_key)
    with lock:
        logger.info(
            f"加载模型：{config.model_path}, 方法：{config.method}, "
            f"量化：{config.quantize}, rank={config.rank}, alpha={config.alpha}, "
            f"flash_attn={config.use_flash_attn}"
        )

        model = None
        tokenizer = None

        try:
            config.target_modules_list = _resolve_target_modules(config.target_modules)
            if not config.target_modules_list:
                raise ValueError(f"无效的目标模块配置：{config.target_modules}")

            _check_vram_before_load(config)
            config.quantization_config = _build_quantization_config(config)

            model = _load_base_model(config)
            tokenizer = _load_tokenizer(config)
            model = _prepare_model_for_training(model, config)

            if config.method == "full":
                logger.info("全参数微调模式，不应用 LoRA")
                model = _enable_gradient_checkpointing(model, config)
                return model, tokenizer

            model = _apply_lora_to_model(model, config)
            model = _resume_from_checkpoint(model, config)
            model = _enable_gradient_checkpointing(model, config)
            _apply_lora_plus(model, config)

            return model, tokenizer

        except Exception as e:
            logger.error(f"模型加载失败：{e}")
            if model is not None:
                del model
            if tokenizer is not None:
                del tokenizer
            cleanup_gpu_memory()
            raise
