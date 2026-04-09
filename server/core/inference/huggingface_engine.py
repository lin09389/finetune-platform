"""
HuggingFace 推理引擎
使用 Transformers 库进行本地推理
"""
import logging
from collections.abc import AsyncGenerator
from typing import Any

from .engine_base import (
    BaseInferenceEngine,
    ChatRequest,
    InferenceBackend,
    InferenceRequest,
    InferenceResponse,
    StreamChunk,
)

logger = logging.getLogger(__name__)


class HuggingFaceEngine(BaseInferenceEngine):
    """
    HuggingFace 推理引擎

    特性:
    - 支持本地模型加载
    - 支持 LoRA 适配器
    - 支持量化模型 (INT8/INT4)
    - 支持流式生成
    """

    def __init__(
        self,
        model_cache: Any | None = None,
        device: str = "auto",
        default_model: str | None = None,
    ):
        super().__init__()
        self.model_cache = model_cache
        self.device = device
        self.default_model = default_model
        self._tokenizer_cache: dict[str, Any] = {}
        self._model_cache_instances: dict[str, Any] = {}

    @property
    def backend(self) -> InferenceBackend:
        return InferenceBackend.HUGGINGFACE

    @property
    def name(self) -> str:
        return "HuggingFace Transformers"

    def is_available(self) -> bool:
        """检查 Transformers 是否可用"""
        try:
            import importlib.util

            return (
                importlib.util.find_spec("torch") is not None
                and importlib.util.find_spec("transformers") is not None
            )
        except ImportError:
            return False

    def get_available_models(self) -> list[str]:
        """获取已加载的模型列表"""
        return list(self._model_cache_instances.keys())

    def load_model(
        self,
        model_id: str,
        load_in_8bit: bool = False,
        load_in_4bit: bool = False,
        lora_adapter: str | None = None,
        **kwargs,
    ) -> bool:
        """
        加载模型

        Args:
            model_id: 模型 ID 或路径
            load_in_8bit: 是否使用 INT8 量化
            load_in_4bit: 是否使用 INT4 量化
            lora_adapter: LoRA 适配器路径

        Returns:
            是否成功
        """
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            if model_id in self._model_cache_instances:
                self._logger.info(f"模型已加载: {model_id}")
                return True

            self._logger.info(f"正在加载模型: {model_id}")

            tokenizer = AutoTokenizer.from_pretrained(
                model_id,
                trust_remote_code=True,
            )

            model_kwargs = {
                "trust_remote_code": True,
                "device_map": self.device,
            }

            if load_in_8bit:
                model_kwargs["load_in_8bit"] = True
            elif load_in_4bit:
                model_kwargs["load_in_4bit"] = True
            else:
                model_kwargs["torch_dtype"] = torch.float16

            model = AutoModelForCausalLM.from_pretrained(model_id, **model_kwargs)

            if lora_adapter:
                try:
                    from peft import PeftModel
                    model = PeftModel.from_pretrained(model, lora_adapter)
                    self._logger.info(f"LoRA 适配器已加载: {lora_adapter}")
                except ImportError:
                    self._logger.warning("PEFT 未安装，跳过 LoRA 加载")

            self._tokenizer_cache[model_id] = tokenizer
            self._model_cache_instances[model_id] = model
            self._loaded_models[model_id] = {
                "model_id": model_id,
                "lora_adapter": lora_adapter,
                "quantized": load_in_8bit or load_in_4bit,
            }

            self._logger.info(f"模型加载成功: {model_id}")
            return True

        except Exception as e:
            self._logger.error(f"模型加载失败: {e}", exc_info=True)
            return False

    def unload_model(self, model_id: str) -> bool:
        """卸载模型"""
        try:
            if model_id in self._model_cache_instances:
                del self._model_cache_instances[model_id]
            if model_id in self._tokenizer_cache:
                del self._tokenizer_cache[model_id]
            if model_id in self._loaded_models:
                del self._loaded_models[model_id]

            import gc

            import torch
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            self._logger.info(f"模型已卸载: {model_id}")
            return True

        except Exception as e:
            self._logger.error(f"模型卸载失败: {e}")
            return False

    def _get_model_and_tokenizer(self, model_id: str):
        """获取模型和分词器"""
        if model_id not in self._model_cache_instances:
            if not self.load_model(model_id):
                raise RuntimeError(f"无法加载模型: {model_id}")

        return (
            self._model_cache_instances[model_id],
            self._tokenizer_cache[model_id],
        )

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        """生成文本"""
        import torch

        model, tokenizer = self._get_model_and_tokenizer(request.model_id)

        with self._measure_time() as timer:
            inputs = tokenizer(request.prompt, return_tensors="pt")

            if torch.cuda.is_available():
                inputs = {k: v.cuda() for k, v in inputs.items()}

            with torch.no_grad():
                outputs = model.generate(
                    **inputs,
                    max_new_tokens=request.max_tokens,
                    temperature=request.temperature,
                    top_p=request.top_p,
                    top_k=request.top_k,
                    repetition_penalty=request.repetition_penalty,
                    do_sample=request.temperature > 0,
                    pad_token_id=tokenizer.eos_token_id,
                )

            generated_text = tokenizer.decode(
                outputs[0][inputs["input_ids"].shape[1]:],
                skip_special_tokens=True,
            )

            tokens_generated = outputs.shape[1] - inputs["input_ids"].shape[1]

        return InferenceResponse(
            text=generated_text,
            tokens_generated=tokens_generated,
            processing_time_ms=timer.elapsed_ms,
            model_id=request.model_id,
            backend=self.backend.value,
        )

    async def chat(self, request: ChatRequest) -> InferenceResponse:
        """聊天对话"""
        model, tokenizer = self._get_model_and_tokenizer(request.model_id)

        if hasattr(tokenizer, 'apply_chat_template'):
            messages = [{"role": m.role, "content": m.content} for m in request.messages]
            if request.system_prompt:
                messages.insert(0, {"role": "system", "content": request.system_prompt})

            prompt = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        else:
            prompt = "\n".join([f"{m.role}: {m.content}" for m in request.messages])
            prompt += "\nassistant:"

        inference_request = InferenceRequest(
            model_id=request.model_id,
            prompt=prompt,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            top_p=request.top_p,
            metadata=request.metadata,
        )

        return await self.generate(inference_request)

    async def stream(self, request: InferenceRequest) -> AsyncGenerator[StreamChunk, None]:
        """流式生成"""
        import threading

        import torch
        from transformers import TextIteratorStreamer

        model, tokenizer = self._get_model_and_tokenizer(request.model_id)

        inputs = tokenizer(request.prompt, return_tensors="pt")
        if torch.cuda.is_available():
            inputs = {k: v.cuda() for k, v in inputs.items()}

        streamer = TextIteratorStreamer(
            tokenizer,
            skip_prompt=True,
            skip_special_tokens=True,
        )

        generation_kwargs = {
            **inputs,
            "max_new_tokens": request.max_tokens,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "top_k": request.top_k,
            "repetition_penalty": request.repetition_penalty,
            "do_sample": request.temperature > 0,
            "streamer": streamer,
            "pad_token_id": tokenizer.eos_token_id,
        }

        thread = threading.Thread(target=model.generate, kwargs=generation_kwargs)
        thread.start()

        tokens_so_far = 0
        for text in streamer:
            tokens_so_far += 1
            yield StreamChunk(
                content=text,
                done=False,
                tokens_so_far=tokens_so_far,
            )

        thread.join()

        yield StreamChunk(
            content="",
            done=True,
            tokens_so_far=tokens_so_far,
            finish_reason="stop",
        )

    def get_model_info(self, model_id: str) -> dict[str, Any] | None:
        """获取模型信息"""
        info = super().get_model_info(model_id)
        if info and model_id in self._model_cache_instances:
            model = self._model_cache_instances[model_id]
            info.update({
                "parameters": sum(p.numel() for p in model.parameters()),
                "device": str(next(model.parameters()).device),
            })
        return info
