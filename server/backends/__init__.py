import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import torch

logger = logging.getLogger(__name__)


@dataclass
class DeviceInfo:
    platform: str
    device_name: str
    vram_total: float
    vram_used: float
    vram_free: float
    memory_total: float
    memory_used: float
    memory_free: float
    cuda_available: bool
    mps_available: bool = False


@dataclass
class ModelInfo:
    id: str
    name: str
    path: str
    size: int
    type: str
    quantized: int | None = None


@dataclass
class TrainConfig:
    model_path: str
    dataset_path: str
    method: str = "qlora"
    rank: int = 8
    alpha: int = 16
    learning_rate: float = 5e-5
    epochs: int = 3
    batch_size: int = 1
    gradient_accumulation: int = 16
    max_seq_length: int = 512
    warmup_steps: int = 100
    save_steps: int = 500
    logging_steps: int = 10


@dataclass
class TrainResult:
    output_path: str
    status: str
    message: str


class BaseBackend(ABC):
    """后端抽象基类"""

    @abstractmethod
    def get_device_info(self) -> DeviceInfo:
        """获取设备信息"""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """检查后端是否可用"""
        pass

    @abstractmethod
    def load_model(self, model_path: str, quantize: int = 4):
        """加载模型"""
        pass

    @abstractmethod
    def train(self, config: TrainConfig) -> TrainResult:
        """执行训练"""
        pass

    @abstractmethod
    def infer(
        self, prompt: str, max_tokens: int = 1024, temperature: float = 0.7
    ) -> str:
        """推理"""
        pass

    @abstractmethod
    def get_vram_usage(self) -> float:
        """获取显存使用情况"""
        pass


class CUDABackend(BaseBackend):
    """NVIDIA CUDA 后端"""

    def __init__(self):
        self.model = None
        self.tokenizer = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def is_available(self) -> bool:
        return torch.cuda.is_available()

    def get_device_info(self) -> DeviceInfo:
        import psutil

        if not torch.cuda.is_available():
            return DeviceInfo(
                platform="cpu",
                device_name="CPU",
                vram_total=0,
                vram_used=0,
                vram_free=0,
                memory_total=psutil.virtual_memory().total / (1024**3),
                memory_used=psutil.virtual_memory().used / (1024**3),
                memory_free=psutil.virtual_memory().available / (1024**3),
                cuda_available=False,
            )

        return DeviceInfo(
            platform="cuda",
            device_name=torch.cuda.get_device_name(0),
            vram_total=torch.cuda.get_device_properties(0).total_memory / (1024**3),
            vram_used=torch.cuda.memory_allocated(0) / (1024**3),
            vram_free=(
                torch.cuda.get_device_properties(0).total_memory
                - torch.cuda.memory_allocated(0)
            )
            / (1024**3),
            memory_total=psutil.virtual_memory().total / (1024**3),
            memory_used=psutil.virtual_memory().used / (1024**3),
            memory_free=psutil.virtual_memory().available / (1024**3),
            cuda_available=True,
        )

    def load_model(self, model_path: str, quantize: int = 4):
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        quantization_config = None
        if quantize in [4, 8]:
            quantization_config = BitsAndBytesConfig(
                load_in_4bit=quantize == 4,
                load_in_8bit=quantize == 8,
                bnb_4bit_compute_dtype=torch.float16,
            )

        self.model = AutoModelForCausalLM.from_pretrained(
            model_path,
            quantization_config=quantization_config,
            device_map="auto",
            torch_dtype=torch.float16,
        )

        self.tokenizer = AutoTokenizer.from_pretrained(model_path)

        return self.model

    def train(self, config: TrainConfig) -> TrainResult:
        from peft import LoraConfig, TaskType, get_peft_model
        from transformers import (
            DataCollatorForLanguageModeling,
            Trainer,
            TrainingArguments,
        )

        from datasets import load_dataset

        if not self.model:
            raise RuntimeError("Model not loaded")

        lora_config = LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=config.rank,
            lora_alpha=config.alpha,
            lora_dropout=0.1,
            target_modules=["q_proj", "v_proj"],
        )

        self.model = get_peft_model(self.model, lora_config)

        dataset = load_dataset("json", data_files=config.dataset_path)

        def tokenize_function(examples):
            return self.tokenizer(
                examples["text"], truncation=True, max_length=config.max_seq_length
            )

        dataset = dataset.map(tokenize_function, batched=True)

        training_args = TrainingArguments(
            output_dir=config.model_path + "_output",
            num_train_epochs=config.epochs,
            per_device_train_batch_size=config.batch_size,
            gradient_accumulation_steps=config.gradient_accumulation,
            learning_rate=config.learning_rate,
            warmup_steps=config.warmup_steps,
            logging_steps=config.logging_steps,
            save_steps=config.save_steps,
            fp16=True,
            remove_unused_columns=False,
        )

        trainer = Trainer(
            model=self.model,
            args=training_args,
            train_dataset=dataset["train"],
            data_collator=DataCollatorForLanguageModeling(
                tokenizer=self.tokenizer, mlm=False
            ),
        )

        trainer.train()

        return TrainResult(
            output_path=config.model_path + "_output",
            status="completed",
            message="Training completed successfully",
        )

    def infer(
        self, prompt: str, max_tokens: int = 1024, temperature: float = 0.7
    ) -> str:
        if not self.model or not self.tokenizer:
            raise RuntimeError("Model not loaded")

        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)

        outputs = self.model.generate(
            **inputs, max_new_tokens=max_tokens, temperature=temperature, do_sample=True
        )

        return self.tokenizer.decode(outputs[0], skip_special_tokens=True)

    def get_vram_usage(self) -> float:
        if torch.cuda.is_available():
            return torch.cuda.memory_allocated(0) / (1024**3)
        return 0.0


class MLXBackend(BaseBackend):
    """Apple MLX 后端"""

    def __init__(self):
        self.model = None
        self.mlx = None

    def is_available(self) -> bool:
        try:
            import mlx.core as mx

            self.mlx = mx
            return True
        except ImportError:
            return False

    def get_device_info(self) -> DeviceInfo:
        import psutil

        mps_available = False
        try:
            import torch

            mps_available = torch.backends.mps.is_available()
        except Exception as e:
            logger.debug(f"MPS 检查失败: {e}")

        return DeviceInfo(
            platform="mac",
            device_name="Apple Silicon",
            vram_total=0,
            vram_used=0,
            vram_free=0,
            memory_total=psutil.virtual_memory().total / (1024**3),
            memory_used=psutil.virtual_memory().used / (1024**3),
            memory_free=psutil.virtual_memory().available / (1024**3),
            cuda_available=False,
            mps_available=mps_available,
        )

    def load_model(self, model_path: str, quantize: int = 4):
        raise NotImplementedError(
            "MLX loading not implemented yet. Use llama.cpp for now."
        )

    def train(self, config: TrainConfig) -> TrainResult:
        raise NotImplementedError("MLX training not implemented yet. Use CPU training.")

    def infer(
        self, prompt: str, max_tokens: int = 1024, temperature: float = 0.7
    ) -> str:
        raise NotImplementedError("MLX inference not implemented yet.")

    def get_vram_usage(self) -> float:
        return 0.0


def get_backend() -> BaseBackend:
    """获取可用的后端"""
    cuda_backend = CUDABackend()
    if cuda_backend.is_available():
        return cuda_backend

    mlx_backend = MLXBackend()
    if mlx_backend.is_available():
        return mlx_backend

    raise RuntimeError("No available backend found")
