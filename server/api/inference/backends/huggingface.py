"""
HuggingFace 推理后端实现
"""
import asyncio
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from .base import BackendType, GenerationConfig, GenerationResult, InferenceBackend

logger = logging.getLogger(__name__)


class HuggingFaceBackend(InferenceBackend):
    """HuggingFace 推理后端"""

    backend_type = BackendType.HUGGINGFACE

    def __init__(self, config: dict[str, Any] = None):
        super().__init__(config or {})

        config = config or {}
        self.device = config.get("device", "auto")
        self.torch_dtype = config.get("torch_dtype", "auto")
        self.load_in_8bit = config.get("load_in_8bit", False)
        self.load_in_4bit = config.get("load_in_4bit", False)
        self.trust_remote_code = config.get("trust_remote_code", False)

        self._pipeline = None

    async def load_model(self, model_name: str, **kwargs) -> bool:
        """加载模型"""
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

            logger.info(f"Loading HuggingFace model: {model_name}")

            torch_dtype = self.torch_dtype
            if torch_dtype == "auto":
                torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
            elif isinstance(torch_dtype, str):
                torch_dtype = getattr(torch, torch_dtype, torch.float32)

            self._tokenizer = AutoTokenizer.from_pretrained(
                model_name,
                trust_remote_code=self.trust_remote_code
            )

            model_kwargs = {
                "pretrained_model_name_or_path": model_name,
                "torch_dtype": torch_dtype,
                "device_map": self.device,
                "trust_remote_code": self.trust_remote_code,
            }

            if self.load_in_8bit:
                model_kwargs["load_in_8bit"] = True
            elif self.load_in_4bit:
                model_kwargs["load_in_4bit"] = True

            self._model = AutoModelForCausalLM.from_pretrained(**model_kwargs)

            self._pipeline = pipeline(
                "text-generation",
                model=self._model,
                tokenizer=self._tokenizer,
                device_map=self.device
            )

            self._is_loaded = True
            logger.info(f"HuggingFace model loaded: {model_name}")

            return True

        except Exception as e:
            logger.error(f"Failed to load HuggingFace model: {e}")
            self._is_loaded = False
            return False

    async def unload_model(self) -> bool:
        """卸载模型"""
        try:
            import gc

            import torch

            del self._model
            del self._tokenizer
            del self._pipeline

            self._model = None
            self._tokenizer = None
            self._pipeline = None

            gc.collect()

            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            self._is_loaded = False
            logger.info("HuggingFace model unloaded")

            return True

        except Exception as e:
            logger.error(f"Failed to unload model: {e}")
            return False

    async def generate(
        self,
        prompt: str,
        config: GenerationConfig = None
    ) -> GenerationResult:
        """生成文本"""
        if not self._is_loaded:
            return GenerationResult(
                text="",
                tokens_generated=0,
                finish_reason="error",
                model="",
                metadata={"error": "Model not loaded"}
            )

        config = config or GenerationConfig()
        start_time = time.time()

        try:
            input_ids = self._tokenizer.encode(prompt, return_tensors="pt")
            prompt_tokens = len(input_ids[0])

            outputs = await asyncio.to_thread(
                self._pipeline,
                prompt,
                max_new_tokens=config.max_tokens,
                temperature=config.temperature,
                top_p=config.top_p,
                top_k=config.top_k,
                repetition_penalty=config.repetition_penalty,
                do_sample=config.temperature > 0,
                num_return_sequences=1,
                pad_token_id=self._tokenizer.eos_token_id
            )

            generated_text = outputs[0]["generated_text"]
            new_text = generated_text[len(prompt):]

            output_ids = self._tokenizer.encode(new_text, return_tensors="pt")
            tokens_generated = len(output_ids[0])

            latency_ms = (time.time() - start_time) * 1000

            return GenerationResult(
                text=new_text,
                tokens_generated=tokens_generated,
                finish_reason="stop",
                model="huggingface",
                prompt_tokens=prompt_tokens,
                total_tokens=prompt_tokens + tokens_generated,
                latency_ms=latency_ms
            )

        except Exception as e:
            logger.error(f"HuggingFace generation failed: {e}")
            return GenerationResult(
                text="",
                tokens_generated=0,
                finish_reason="error",
                model="huggingface",
                metadata={"error": str(e)}
            )

    async def generate_stream(
        self,
        prompt: str,
        config: GenerationConfig = None
    ) -> AsyncIterator[str]:
        """流式生成文本"""
        result = await self.generate(prompt, config)

        for word in result.text.split():
            yield word + " "
            await asyncio.sleep(0.01)

    async def chat(
        self,
        messages: list[dict[str, str]],
        config: GenerationConfig = None
    ) -> GenerationResult:
        """对话生成"""
        if not self._is_loaded:
            return GenerationResult(
                text="",
                tokens_generated=0,
                finish_reason="error",
                model="",
                metadata={"error": "Model not loaded"}
            )

        prompt = self._format_chat_prompt(messages)
        return await self.generate(prompt, config)

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        config: GenerationConfig = None
    ) -> AsyncIterator[str]:
        """流式对话生成"""
        result = await self.chat(messages, config)

        for word in result.text.split():
            yield word + " "
            await asyncio.sleep(0.01)

    def get_model_info(self) -> dict[str, Any]:
        """获取模型信息"""
        return {
            "backend_type": self.backend_type.value,
            "is_loaded": self._is_loaded,
            "device": self.device,
            "load_in_8bit": self.load_in_8bit,
            "load_in_4bit": self.load_in_4bit
        }

    async def count_tokens(self, text: str) -> int:
        """计算 token 数量"""
        if not self._tokenizer:
            return len(text) // 4

        return len(self._tokenizer.encode(text))

    def _format_chat_prompt(self, messages: list[dict[str, str]]) -> str:
        """格式化对话提示"""
        formatted = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                formatted.append(f"System: {content}")
            elif role == "user":
                formatted.append(f"User: {content}")
            elif role == "assistant":
                formatted.append(f"Assistant: {content}")

        formatted.append("Assistant:")

        return "\n".join(formatted)

    async def get_memory_usage(self) -> dict[str, Any]:
        """获取内存使用情况"""
        import torch

        if torch.cuda.is_available() and self._is_loaded:
            memory_allocated = torch.cuda.memory_allocated() / (1024 ** 2)
            memory_reserved = torch.cuda.memory_reserved() / (1024 ** 2)

            return {
                "backend_type": self.backend_type.value,
                "memory_used_mb": memory_allocated,
                "memory_reserved_mb": memory_reserved,
                "device": torch.cuda.get_device_name(0)
            }

        return await super().get_memory_usage()
