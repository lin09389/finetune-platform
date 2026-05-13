"""
训练策略模块 - 策略模式解耦模型加载和数据集格式化

新增模型加载策略或数据集格式时，只需实现对应接口并注册到 Pipeline。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from core.logging import get_logger
from training_engine.schemas import TrainingConfigInput

logger = get_logger(__name__)


# ============================================================================
# Model Loader Strategy
# ============================================================================
class ModelLoaderStrategy(ABC):
    """模型加载策略接口"""

    @abstractmethod
    def load(self, model_path: str, config: TrainingConfigInput) -> tuple[Any, Any]:
        """
        加载模型和分词器

        Args:
            model_path: 模型路径
            config: 训练配置

        Returns:
            (model, tokenizer)
        """
        ...


class HuggingFaceModelLoader(ModelLoaderStrategy):
    """默认 HuggingFace 模型加载策略"""

    def load(self, model_path: str, config: TrainingConfigInput) -> tuple[Any, Any]:
        from training_engine.model_loader import load_model_and_tokenizer
        return load_model_and_tokenizer(
            model_path=model_path,
            method=config.method,
            quantize=config.quantization,
            resume_from=config.resume_from_adapter,
            rank=config.rank,
            alpha=config.alpha,
            lora_dropout=config.lora_dropout,
            target_modules=config.target_modules,
            use_dora=config.use_dora,
            use_flash_attn=config.use_flash_attn,
            gradient_checkpointing=config.gradient_checkpointing,
            use_lora_plus=config.use_lora_plus,
            lora_plus_lr_ratio=config.lora_plus_lr_ratio,
            bf16=config.bf16,
            batch_size=config.batch_size,
            max_seq_length=config.max_seq_length,
        )


# ============================================================================
# Dataset Formatter Strategy
# ============================================================================
class DatasetFormatterStrategy(ABC):
    """数据集格式化策略接口"""

    @abstractmethod
    def load(self, dataset_path: str, tokenizer, config: TrainingConfigInput, settings=None) -> Any:
        """
        加载并格式化数据集

        Args:
            dataset_path: 数据集路径
            tokenizer: 分词器
            config: 训练配置
            settings: 全局配置对象

        Returns:
            datasets.DatasetDict
        """
        ...


class AutoDatasetFormatter(DatasetFormatterStrategy):
    """自动检测格式并加载数据集的策略"""

    def load(self, dataset_path: str, tokenizer, config: TrainingConfigInput, settings=None) -> Any:
        from training_engine.dataset_loader import load_dataset, load_multiple_datasets
        if config.additional_datasets:
            logger.info(f"使用多数据集混合训练：{len(config.additional_datasets) + 1} 个数据集")
            return load_multiple_datasets(
                dataset_path,
                config.additional_datasets,
                tokenizer,
                config.max_seq_length,
                settings,
            )
        return load_dataset(dataset_path, tokenizer, config.max_seq_length)


# ============================================================================
# Optimizer Builder Strategy
# ============================================================================
class OptimizerBuilderStrategy(ABC):
    """优化器构建策略接口"""

    @abstractmethod
    def build(self, model, trainer, config: TrainingConfigInput) -> None:
        """
        为 Trainer 构建/替换优化器

        Args:
            model: 已加载的模型
            trainer: transformers.Trainer 实例
            config: 训练配置
        """
        ...


class DefaultOptimizerBuilder(OptimizerBuilderStrategy):
    """默认优化器策略：LoRA+、GaLore 等"""

    def build(self, model, trainer, config: TrainingConfigInput) -> None:
        if config.use_lora_plus and config.method not in ["full"] and not config.use_galore:
            self._apply_lora_plus(model, trainer, config)

        if config.use_galore:
            self._apply_galore(model, trainer, config)

    def _apply_lora_plus(self, model, trainer, config: TrainingConfigInput) -> None:
        logger.info(f"应用 LoRA+ 不同学习率配置 ratio={config.lora_plus_lr_ratio}")
        base_lr = config.learning_rate

        lora_a_params = []
        lora_b_params = []
        other_params = []

        for name, param in model.named_parameters():
            if param.requires_grad:
                if "lora_A" in name:
                    lora_a_params.append(param)
                elif "lora_B" in name:
                    lora_b_params.append(param)
                else:
                    other_params.append(param)

        from torch.optim import AdamW
        param_groups = [
            {"params": lora_a_params, "lr": base_lr},
            {"params": lora_b_params, "lr": base_lr * config.lora_plus_lr_ratio},
            {"params": other_params, "lr": base_lr},
        ]
        trainer.optimizer = AdamW(param_groups, weight_decay=config.weight_decay)
        logger.info(f"LoRA+ 优化器配置：A参数 lr={base_lr}, B参数 lr={base_lr * config.lora_plus_lr_ratio}")

    def _apply_galore(self, model, trainer, config: TrainingConfigInput) -> None:
        if config.deepspeed_stage > 0:
            logger.warning("GaLore 与 DeepSpeed 不兼容，已自动禁用 DeepSpeed")
            config.deepspeed_stage = 0

        if config.use_lora_plus:
            logger.warning("GaLore 与 LoRA+ 同时启用可能存在冲突，建议关闭 LoRA+")

        try:
            from galore_torch import GaLoreAdamW
            logger.info(f"配置 GaLore: rank={config.galore_rank}, update_gap={config.galore_update_proj_gap}")

            galore_params = []
            for name, param in model.named_parameters():
                if param.requires_grad and any(x in name for x in ['q_proj', 'k_proj', 'v_proj', 'o_proj', 'gate_proj', 'up_proj', 'down_proj']):
                    galore_params.append(param)

            if len(galore_params) > 0:
                non_galore_params = [p for p in model.parameters() if p.requires_grad and p not in galore_params]
                param_groups = [
                    {"params": galore_params, "rank": config.galore_rank, "update_proj_gap": config.galore_update_proj_gap},
                    {"params": non_galore_params}
                ]
                trainer.optimizer = GaLoreAdamW(
                    param_groups,
                    lr=config.learning_rate,
                    weight_decay=config.weight_decay
                )
                logger.info(f"GaLore 已启用，投影参数: {len(galore_params)} 个")
            else:
                logger.warning("未找到可使用 GaLore 的参数，跳过")

        except ImportError as e:
            logger.warning("GaLore 未安装，请运行: pip install galore-torch")
            logger.warning(f"将跳过 GaLore 优化，继续使用标准训练: {e}")


# ============================================================================
# Post-Load Model Processor Strategy
# ============================================================================
class PostLoadModelProcessor(ABC):
    """模型加载后处理策略（如 torch.compile、TF32 等）"""

    @abstractmethod
    def process(self, model, config: TrainingConfigInput) -> Any:
        """
        对加载后的模型进行额外处理

        Returns:
            处理后的模型
        """
        ...


class DefaultPostLoadModelProcessor(PostLoadModelProcessor):
    """默认后处理：torch.compile、TF32"""

    def process(self, model, config: TrainingConfigInput) -> Any:
        if config.use_torch_compile and hasattr(model, 'forward'):
            model = self._try_torch_compile(model, config)

        if config.use_tf32:
            self._try_enable_tf32()

        return model

    def _try_torch_compile(self, model, config: TrainingConfigInput) -> Any:
        try:
            import torch
            if hasattr(torch, 'compile'):
                logger.info(f"使用 torch.compile 编译模型，模式: {config.torch_compile_mode}")
                model = torch.compile(model, mode=config.torch_compile_mode)
                logger.info("torch.compile 编译成功")
            else:
                logger.warning("PyTorch 版本不支持 torch.compile，需要 PyTorch 2.0+")
        except Exception as e:
            logger.warning(f"torch.compile 编译失败，跳过: {e}")
        return model

    def _try_enable_tf32(self) -> None:
        try:
            import torch
            if torch.cuda.is_available() and hasattr(torch.cuda, 'set_float32_matmul_precision'):
                device_name = torch.cuda.get_device_name(0).lower()
                if any(arch in device_name for arch in ['30', '40', 'a10', 'a100', 'a30', 'l40', 'h100']):
                    torch.backends.cuda.matmul.allow_tf32 = True
                    torch.backends.cudnn.allow_tf32 = True
                    logger.info("已启用 TF32 加速（Ampere+ GPU）")
                else:
                    logger.info(f"GPU {device_name} 不支持 TF32，跳过")
        except Exception as e:
            logger.debug(f"TF32 启用失败: {e}")
