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


def _release_load_lock(cache_key: str) -> None:
    """加载完成后清理不再需要的锁，防止字典无限增长"""
    with _model_load_master_lock:
        lock = _model_load_locks.get(cache_key)
        if lock is not None and not lock.locked():
            _model_load_locks.pop(cache_key, None)


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
    batch_size: int = 1
    max_seq_length: int = 512

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
    """加载前检查显存，提前发现 OOM 风险。

    Also claims the cross-process training GPU lease (released in pipeline cleanup).
    """
    # Cross-process GPU coordination: refuse train load while inference holds lease.
    try:
        from core.gpu_coordination import (
            GpuCoordinationError,
            assert_training_gpu_available,
            claim_training_gpu,
        )

        assert_training_gpu_available()
        claim_training_gpu(
            owner=f"training:{getattr(config, 'model_name', None) or getattr(config, 'model_path', 'model')}"
        )
    except GpuCoordinationError:
        raise
    except Exception as exc:
        logger.debug("GPU coordination precheck skipped: %s", exc)

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


def _estimate_model_params(model_path: str) -> float:
    """从模型配置估算参数量

    三级回退策略：
    1. 从 config.json 精确计算（支持 MHA/GQA/MQA/MoE）
    2. 从 safetensors / pytorch_bin 文件大小推算
    3. 从模型名称字符串匹配

    返回参数数量（float，如 7e9 表示 70 亿参数）。
    """
    import json
    from pathlib import Path

    if not model_path or not str(model_path).strip():
        return 2.73e9

    model_dir = Path(model_path)

    config_file = model_dir / "config.json"
    if config_file.exists():
        try:
            with open(config_file, encoding="utf-8") as f:
                cfg = json.load(f)

            explicit = cfg.get("num_params") or cfg.get("model_params")
            if explicit and isinstance(explicit, (int, float)):
                return float(explicit)

            if "num_hidden_layers" in cfg and "hidden_size" in cfg:
                hidden = cfg.get("hidden_size", 4096)
                layers = cfg.get("num_hidden_layers", 32)
                heads = cfg.get("num_attention_heads", hidden // 128)
                kv_heads = cfg.get("num_key_value_heads", heads)
                intermediate = cfg.get("intermediate_size", hidden * 4)
                vocab = cfg.get("vocab_size", 32000)

                head_dim = hidden // heads
                q_params = hidden * (heads * head_dim)
                k_params = hidden * (kv_heads * head_dim)
                v_params = hidden * (kv_heads * head_dim)
                o_params = (heads * head_dim) * hidden
                attn_params = q_params + k_params + v_params + o_params

                num_experts = cfg.get("num_local_experts", None)
                if num_experts and num_experts > 1:
                    gate_params = hidden * num_experts
                    expert_mlp_params = 3 * hidden * intermediate
                    mlp_params = gate_params + num_experts * expert_mlp_params
                else:
                    mlp_params = 3 * hidden * intermediate

                norm_params = hidden * 2

                emb_params = vocab * hidden
                if cfg.get("tie_word_embeddings", True) is False:
                    lm_head_params = vocab * hidden
                else:
                    lm_head_params = 0

                total = emb_params + layers * (attn_params + mlp_params + norm_params) + lm_head_params
                logger.debug(f"从 config.json 计算参数量: {total / 1e9:.2f}B")
                return float(total)

            if "n_layer" in cfg and "n_embd" in cfg:
                layers = cfg.get("n_layer", 24)
                hidden = cfg.get("n_embd", 2048)
                heads = cfg.get("n_head", hidden // 64)
                intermediate = cfg.get("n_inner", hidden * 4) or hidden * 4
                vocab = cfg.get("vocab_size", 50257)

                head_dim = hidden // heads
                attn_params = 4 * hidden * hidden
                mlp_params = 2 * hidden * intermediate
                total = vocab * hidden + layers * (attn_params + mlp_params + 2 * hidden)
                logger.debug(f"从 config.json (GPT-2 格式) 计算参数量: {total / 1e9:.2f}B")
                return float(total)

        except Exception as e:
            logger.debug(f"解析模型配置失败，使用回退估算: {e}")

    safetensors_files = list(model_dir.glob("*.safetensors"))
    if not safetensors_files:
        safetensors_files = list(model_dir.glob("model*.safetensors"))
    if safetensors_files:
        total_size = sum(f.stat().st_size for f in safetensors_files)
        param_count = total_size / 2.0
        logger.debug(f"从 safetensors 文件大小估算参数量: {param_count / 1e9:.2f}B (假设 fp16)")
        return param_count

    bin_files = list(model_dir.glob("pytorch_model*.bin"))
    if not bin_files:
        bin_files = list(model_dir.glob("pytorch_model*.pth"))
    if bin_files:
        total_size = sum(f.stat().st_size for f in bin_files)
        param_count = total_size / 2.0
        logger.debug(f"从 pytorch bin 文件大小估算参数量: {param_count / 1e9:.2f}B")
        return param_count

    if model_dir.is_dir():
        weight_extensions = {".safetensors", ".bin", ".pt", ".pth"}
        dir_size = sum(
            f.stat().st_size
            for f in model_dir.rglob("*")
            if f.is_file() and f.suffix in weight_extensions
        )
        if dir_size > 0:
            param_count = dir_size / 2.0  # 假设 fp16
            logger.debug(f"从权重文件大小估算参数量: {param_count / 1e9:.2f}B")
            return param_count

    name_lower = model_path.lower()
    size_map = [
        (0.5, ["0.5b", "500m"]),
        (1.5, ["1.5b", "1b5"]),
        (1.8, ["1.8b"]),
        (2.7, ["2.7b"]),
        (3.0, ["3b"]),
        (6.0, ["6b", "7b", "8b"]),
        (13.0, ["13b", "14b"]),
        (20.0, ["20b"]),
        (30.0, ["30b", "32b", "34b"]),
        (65.0, ["65b", "70b", "72b"]),
    ]
    for params_b, keywords in size_map:
        for kw in keywords:
            if kw in name_lower:
                return params_b * 1e9

    return 7e9


def estimate_training_vram(
    param_count: float,
    method: str = "qlora",
    quantization: int = 4,
    batch_size: int = 1,
    max_seq_length: int = 512,
    gradient_checkpointing: bool = True,
    use_flash_attn: bool = False,
    bf16: bool = True,
    lora_rank: int = 8,
    hidden_size: int = 4096,
    num_layers: int = 32,
) -> float:
    """统一显存估算函数

    基于参数量和配置精确估算训练所需显存（GB）。
    ROI: 模型权重 + LoRA 适配器 + 优化器状态 + 梯度 + 激活值 + CUDA 开销

    Args:
        param_count: 模型参数数量
        method: 微调方法 (qlora/lora/dora/full)
        quantization: 量化位数 (4/8/0)
        batch_size: 批次大小
        max_seq_length: 最大序列长度
        gradient_checkpointing: 是否启用梯度检查点
        use_flash_attn: 是否启用 Flash Attention
        bf16: 是否使用 bf16 精度
        lora_rank: LoRA 秩
        hidden_size: 模型隐藏层维度
        num_layers: Transformer 层数

    Returns:
        估算显存需求（GB）
    """
    BYTES_PER_GB = 1024 ** 3

    # 1) 模型权重显存
    if method == "qlora" and quantization == 4:
        param_bytes = 0.5
        compute_dtype_bytes = 2.0
    elif method == "qlora" and quantization == 8:
        param_bytes = 1.0
        compute_dtype_bytes = 2.0
    elif method in ("full",) and not bf16:
        param_bytes = 4.0
        compute_dtype_bytes = 4.0
    else:
        param_bytes = 2.0
        compute_dtype_bytes = 2.0

    weights_gb = param_count * param_bytes / BYTES_PER_GB

    # QLoRA 量化权重之外还有 compute dtype 的 overhead（double quant 约占 0.4 bytes/param）
    if method == "qlora" and quantization == 4:
        weights_gb += param_count * 0.4 / BYTES_PER_GB

    # 2) LoRA/DoRA 适配器显存
    # 可训练参数 ≈ rank × 2 × target_modules 总维度
    # 默认 target_modules="all" 约覆盖所有线性层 ≈ 总参数 × 0.6 维度
    if method in ("lora", "dora", "qlora"):
        fraction_trainable = 0.6
        trainable_params = param_count * fraction_trainable / hidden_size * lora_rank * 2
        adapter_gb = trainable_params * compute_dtype_bytes / BYTES_PER_GB
    else:
        trainable_params = param_count
        adapter_gb = 0.0

    # 3) 优化器状态显存 (AdamW: momentum + variance, 各用 fp32)
    if method == "full":
        optimizer_gb = trainable_params * 2 * 4 / BYTES_PER_GB
    else:
        optimizer_gb = trainable_params * 2 * 4 / BYTES_PER_GB

    # 4) 梯度显存
    if method == "full" and not bf16:
        gradient_gb = trainable_params * 4 / BYTES_PER_GB
    else:
        gradient_gb = trainable_params * 2 / BYTES_PER_GB

    # 5) 激活值显存
    # 每层激活 ≈ batch_size × seq_length × hidden_size × 常数
    # 常数 ≈ 5 (attention + mlp intermediates) for standard transformers
    activation_bytes_per_element = 2.0 if bf16 else 4.0
    activation_constant = 5.0

    if use_flash_attn:
        activation_constant *= 0.55

    base_activation_gb = (
        batch_size * max_seq_length * hidden_size * activation_constant * activation_bytes_per_element * num_layers / BYTES_PER_GB
    )

    if gradient_checkpointing:
        activation_gb = base_activation_gb * 0.3
        recompute_gb = base_activation_gb * 0.15
        activation_gb += recompute_gb
    else:
        activation_gb = base_activation_gb

    # 6) CUDA 内核开销（临时缓冲区、cuBLAS workspace 等）
    cuda_overhead_gb = 0.5

    total = weights_gb + adapter_gb + optimizer_gb + gradient_gb + activation_gb + cuda_overhead_gb

    logger.debug(
        f"显存估算明细: weights={weights_gb:.2f}GB, adapter={adapter_gb:.3f}GB, "
        f"optimizer={optimizer_gb:.2f}GB, gradient={gradient_gb:.2f}GB, "
        f"activation={activation_gb:.2f}GB, cuda={cuda_overhead_gb:.2f}GB, "
        f"total={total:.2f}GB"
    )
    return max(total, 2.0)


def _estimate_vram_required(config: ModelLoadConfig) -> float:
    """估算模型加载 + 训练所需显存（GB）

    委托给统一的 estimate_training_vram 函数。
    """
    model_path = config.model_path
    param_count = _estimate_model_params(model_path)

    config_json_hidden, config_json_layers = _read_model_hidden_and_layers(model_path)

    return estimate_training_vram(
        param_count=param_count,
        method=config.method,
        quantization=config.quantize,
        batch_size=config.batch_size,
        max_seq_length=config.max_seq_length,
        gradient_checkpointing=config.gradient_checkpointing,
        use_flash_attn=config.use_flash_attn,
        bf16=config.bf16,
        lora_rank=config.rank,
        hidden_size=config_json_hidden,
        num_layers=config_json_layers,
    )


def _read_model_hidden_and_layers(model_path: str) -> tuple[int, int]:
    """从 config.json 读取 hidden_size 和 num_hidden_layers，用于激活值估算"""
    import json
    from pathlib import Path

    defaults = (4096, 32)

    model_dir = Path(model_path)
    config_file = model_dir / "config.json"
    if config_file.exists():
        try:
            with open(config_file, encoding="utf-8") as f:
                cfg = json.load(f)
            hidden = cfg.get("hidden_size", cfg.get("n_embd", defaults[0]))
            layers = cfg.get("num_hidden_layers", cfg.get("n_layer", defaults[1]))
            return (hidden, layers)
        except Exception:
            pass

    return defaults


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
    import torch.nn as nn
    from peft import get_peft_model

    # auto 模式：自动检测模型中所有 Linear 层名称
    if config.target_modules_list == ["auto"]:
        linear_modules = set()
        for name, module in model.named_modules():
            if isinstance(module, nn.Linear):
                # 取最后一段名称，如 "model.layers.0.self_attn.q_proj" -> "q_proj"
                short_name = name.split(".")[-1]
                linear_modules.add(short_name)
        if not linear_modules:
            raise RuntimeError("模型中未找到 nn.Linear 层，无法自动检测 target_modules")
        config.target_modules_list = sorted(linear_modules)
        logger.info(f"自动检测到 Linear 层: {config.target_modules_list}")

    lora_config = _build_lora_config(config)
    model = get_peft_model(model, lora_config)

    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    if trainable_params == 0:
        raise RuntimeError(
            f"LoRA 配置后可训练参数为 0。"
            f"当前 target_modules={config.target_modules_list}，可能与模型架构不匹配。"
            f"请尝试设置 target_modules 为模型中实际存在的 Linear 层名称，或使用 'auto' 自动检测。"
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
    batch_size: int = 1,
    max_seq_length: int = 512,
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
        batch_size=batch_size,
        max_seq_length=max_seq_length,
    )
    return _load_model_and_tokenizer_internal(config)


def _load_model_and_tokenizer_internal(config: ModelLoadConfig):
    """内部实现：带并发控制的模型加载

    优化：模型权重和分词器并行加载，减少等待时间。
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

            tokenizer = _load_tokenizer(config)
            model = _load_base_model(config)

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
        finally:
            _release_load_lock(cache_key)
