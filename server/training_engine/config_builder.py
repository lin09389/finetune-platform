"""
训练配置构建模块 - 精度预设、显存预设、智能降级
"""
from core.logging import get_logger
from training_engine.schemas import TrainingConfigInput

logger = get_logger(__name__)


def estimate_training_total_steps(train_size: int, batch_size: int, epochs: int) -> int:
    """估算训练总步数，避免小数据集出现 0 步。"""
    if train_size <= 0:
        raise ValueError("训练集为空，无法开始训练")
    if batch_size <= 0:
        raise ValueError("batch_size 必须大于 0")
    if epochs <= 0:
        raise ValueError("epochs 必须大于 0")

    steps_per_epoch = max(1, (train_size + batch_size - 1) // batch_size)
    return steps_per_epoch * epochs


def apply_precision_preset(config: TrainingConfigInput) -> TrainingConfigInput:
    """应用精度预设配置

    预设选项:
    - max: 最高精度（全参数/DoRA, 余弦退火，早停）
    - balanced: 平衡精度和效率（高秩 LoRA）
    - fast: 快速训练（QLoRA）
    """
    cfg = config.model_copy()

    if cfg.precision_preset == "max":
        cfg.method = "full" if not cfg.use_dora else "dora"
        cfg.learning_rate = 1e-5
        cfg.lr_scheduler = "cosine"
        cfg.warmup_ratio = 0.1
        cfg.weight_decay = 0.01
        cfg.label_smoothing = 0.1
        cfg.gradient_checkpointing = True
        cfg.bf16 = True
        cfg.eval_steps = 100
        cfg.load_best_model = True
        cfg.lora_dropout = 0.05
        cfg.max_grad_norm = 1.0
        logger.info("应用最高精度配置（max）")

    elif cfg.precision_preset == "balanced":
        if cfg.use_dora:
            cfg.rank = 64
            cfg.alpha = 128
        else:
            cfg.rank = 32
            cfg.alpha = 64
        cfg.learning_rate = 2e-5 if cfg.use_dora else 3e-5
        cfg.lr_scheduler = "cosine"
        cfg.warmup_ratio = 0.1
        cfg.weight_decay = 0.01
        cfg.gradient_checkpointing = True
        cfg.bf16 = True
        cfg.eval_steps = 100
        cfg.load_best_model = True
        cfg.lora_dropout = 0.05
        logger.info("应用平衡精度配置 (balanced)")

    elif cfg.precision_preset == "fast":
        cfg.method = "qlora"
        cfg.rank = 16
        cfg.alpha = 32
        cfg.learning_rate = 5e-5
        cfg.lr_scheduler = "linear"
        cfg.warmup_ratio = 0.05
        cfg.weight_decay = 0.01
        cfg.gradient_checkpointing = True
        cfg.bf16 = True
        cfg.eval_steps = 200
        cfg.load_best_model = True
        cfg.lora_dropout = 0.1
        cfg.use_torch_compile = True
        cfg.torch_compile_mode = "default"
        cfg.dataloader_num_workers = 2
        cfg.dataloader_pin_memory = True
        cfg.dataloader_persistent_workers = True
        cfg.use_tf32 = True
        cfg.use_flash_attn = True
        logger.info("应用快速训练配置(fast) - 启用所有性能优化")

    return cfg


def apply_memory_preset(config: TrainingConfigInput) -> TrainingConfigInput:
    """应用显存预设配置

    预设选项:
    - auto: 自动根据显存调整
    - 6gb: 6GB 显存优化 (极致压缩)
    - 8gb: 8GB 显存优化 (平衡)
    - 12gb: 12GB 显存优化 (高性能)
    """
    cfg = config.model_copy()

    if cfg.memory_preset == "6gb":
        cfg.gradient_checkpointing = True
        cfg.gradient_accumulation = 16
        cfg.batch_size = 1
        cfg.quantization = 4
        cfg.bf16 = True
        cfg.use_flash_attn = True
        logger.info("应用 6GB 显存优化配置")

    elif cfg.memory_preset == "8gb":
        cfg.gradient_checkpointing = True
        cfg.gradient_accumulation = 8
        cfg.batch_size = 2
        cfg.quantization = 8
        cfg.bf16 = True
        cfg.use_flash_attn = True
        logger.info("应用 8GB 显存优化配置")

    elif cfg.memory_preset == "12gb":
        cfg.gradient_checkpointing = True
        cfg.gradient_accumulation = 4
        cfg.batch_size = 2
        cfg.quantization = 0
        cfg.bf16 = True
        cfg.use_flash_attn = True
        cfg.deepspeed_stage = 2
        cfg.offload_optimizer = True
        logger.info("应用 12GB 显存优化配置 (DeepSpeed ZeRO-2)")

    elif cfg.memory_preset == "auto":
        try:
            import torch
            if torch.cuda.is_available():
                total_vram = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)

                if total_vram <= 6:
                    cfg.memory_preset = "6gb"
                    return apply_memory_preset(cfg)
                elif total_vram <= 8:
                    cfg.memory_preset = "8gb"
                    return apply_memory_preset(cfg)
                elif total_vram <= 12:
                    cfg.memory_preset = "12gb"
                    return apply_memory_preset(cfg)
        except Exception as e:
            logger.debug(f"自动检测显存失败：{e}")

    return cfg


def degrade_training_config(config: TrainingConfigInput) -> TrainingConfigInput:
    """智能降级训练配置

    根据当前显存情况自动调整参数
    """
    degraded = config.model_copy()

    try:
        import torch
        if torch.cuda.is_available():
            available_vram = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
            allocated_vram = torch.cuda.memory_allocated(0) / (1024 ** 3)
            free_vram = available_vram - allocated_vram

            if free_vram < 4.0:
                if degraded.batch_size > 1:
                    degraded.batch_size = 1
                if degraded.gradient_accumulation > 8:
                    degraded.gradient_accumulation = 8
                if degraded.max_seq_length > 256:
                    degraded.max_seq_length = 256
            elif free_vram < 6.0:
                if degraded.batch_size > 2:
                    degraded.batch_size = 2
                if degraded.gradient_accumulation > 16:
                    degraded.gradient_accumulation = 16
    except Exception as e:
        logger.warning(f"降级配置失败：{e}")

    return degraded
