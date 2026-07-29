"""
llama.cpp 推理引擎
基于 llama-cpp-python 实现，原生支持 GGUF 格式，极低显存占用，完美契合 4GB 显卡
支持动态挂载 LoRA 适配器
"""
import asyncio
import logging
from collections.abc import AsyncGenerator

from .engine_base import (
    BaseInferenceEngine,
    ChatRequest,
    InferenceBackend,
    InferenceRequest,
    InferenceResponse,
    StreamChunk,
)

logger = logging.getLogger(__name__)

try:
    from llama_cpp import Llama
    HAS_LLAMA_CPP = True
except ImportError:
    HAS_LLAMA_CPP = False


class LlamaCppEngine(BaseInferenceEngine):
    """llama-cpp-python 推理引擎"""

    def __init__(
        self,
        default_model: str | None = None,
        n_gpu_layers: int = -1,  # 默认尽可能卸载到 GPU
        n_ctx: int = 2048,
        lora_base: str | None = None,
        lora_path: str | None = None,
        **kwargs,
    ):
        super().__init__()
        self.default_model = default_model
        self.n_gpu_layers = n_gpu_layers
        self.n_ctx = n_ctx
        self.lora_base = lora_base
        self.lora_path = lora_path
        self._llm: Llama | None = None
        self._extra_kwargs = kwargs

        if default_model:
            self.load_model(default_model)

    @property
    def backend(self) -> InferenceBackend:
        return InferenceBackend.LLAMACPP

    @property
    def name(self) -> str:
        return "Llama.cpp Engine"

    def is_available(self) -> bool:
        return HAS_LLAMA_CPP

    def get_available_models(self) -> list[str]:
        # 实际项目中应从本地目录或数据库获取，此处简化
        if self._llm:
            return [self.default_model] if self.default_model else []
        return []

    def load_model(self, model_id: str) -> bool:
        if not self.is_available():
            logger.error("llama-cpp-python 未安装")
            return False

        try:
            # 如果已有模型，先卸载
            if self._llm:
                self.unload_model(self.default_model)

            logger.info(f"正在加载 GGUF 模型: {model_id}, GPU layers: {self.n_gpu_layers}")

            load_kwargs = {
                "model_path": model_id,
                "n_gpu_layers": self.n_gpu_layers,
                "n_ctx": self.n_ctx,
                "verbose": False,
            }

            if self.lora_base:
                load_kwargs["lora_base"] = self.lora_base
            if self.lora_path:
                load_kwargs["lora_path"] = self.lora_path
                logger.info(f"动态挂载 LoRA: {self.lora_path}")

            # 合并其他参数
            load_kwargs.update(self._extra_kwargs)

            self._llm = Llama(**load_kwargs)
            self.default_model = model_id
            self._loaded_models[model_id] = {
                "id": model_id,
                "type": "gguf",
                "backend": self.backend.value,
            }
            logger.info("模型加载成功")
            return True
        except Exception as e:
            logger.error(f"加载模型失败: {e}", exc_info=True)
            return False

    def unload_model(self, model_id: str) -> bool:
        if self._llm:
            del self._llm
            self._llm = None

        if model_id in self._loaded_models:
            del self._loaded_models[model_id]

        # 强制释放内存
        import gc
        gc.collect()

        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

        return True

    def _ensure_model(self, model_id: str):
        if not self._llm:
            self.load_model(model_id)
        elif self.default_model != model_id:
            self.load_model(model_id)

        if not self._llm:
            raise RuntimeError(f"无法加载模型: {model_id}")

    async def generate(self, request: InferenceRequest) -> InferenceResponse:
        self._ensure_model(request.model_id)

        with self._measure_time() as timer:
            # Llama.cpp 是同步阻塞的，所以通过 asyncio.to_thread 放入线程池运行
            def _do_generate():
                return self._llm(
                    request.prompt,
                    max_tokens=request.max_tokens,
                    temperature=request.temperature,
                    top_p=request.top_p,
                    top_k=request.top_k,
                    repeat_penalty=request.repetition_penalty,
                    stop=request.stop_sequences,
                )

            output = await asyncio.to_thread(_do_generate)

            text = output["choices"][0]["text"]
            tokens_generated = output["usage"]["completion_tokens"]
            finish_reason = output["choices"][0].get("finish_reason", "stop")

        return InferenceResponse(
            text=text,
            tokens_generated=tokens_generated,
            processing_time_ms=timer.elapsed_ms,
            model_id=request.model_id,
            backend=self.backend.value,
            finish_reason=finish_reason,
            metadata={"usage": output.get("usage", {})},
        )

    async def chat(self, request: ChatRequest) -> InferenceResponse:
        self._ensure_model(request.model_id)

        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})

        for msg in request.messages:
            messages.append({"role": msg.role, "content": msg.content})

        with self._measure_time() as timer:
            def _do_chat():
                return self._llm.create_chat_completion(
                    messages=messages,
                    max_tokens=request.max_tokens,
                    temperature=request.temperature,
                    top_p=request.top_p,
                    top_k=int(request.metadata.get("top_k", 50)) if "top_k" in request.metadata else None,
                    repeat_penalty=request.metadata.get("repetition_penalty", 1.1) if "repetition_penalty" in request.metadata else None,
                )

            output = await asyncio.to_thread(_do_chat)

            text = output["choices"][0]["message"]["content"]
            tokens_generated = output["usage"]["completion_tokens"]
            finish_reason = output["choices"][0].get("finish_reason", "stop")

        return InferenceResponse(
            text=text,
            tokens_generated=tokens_generated,
            processing_time_ms=timer.elapsed_ms,
            model_id=request.model_id,
            backend=self.backend.value,
            finish_reason=finish_reason,
            metadata={"usage": output.get("usage", {})},
        )

    async def stream(self, request: InferenceRequest) -> AsyncGenerator[StreamChunk, None]:
        self._ensure_model(request.model_id)

        def _do_stream():
            return self._llm(
                request.prompt,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                top_p=request.top_p,
                top_k=request.top_k,
                repeat_penalty=request.repetition_penalty,
                stop=request.stop_sequences,
                stream=True,
            )

        streamer = await asyncio.to_thread(_do_stream)

        # 封装流式迭代器
        tokens_so_far = 0
        while True:
            try:
                # 每次取一个 token，防止阻塞主线程太久
                chunk = await asyncio.to_thread(next, streamer)
                text = chunk["choices"][0]["text"]
                finish_reason = chunk["choices"][0].get("finish_reason")

                tokens_so_far += 1
                done = finish_reason is not None

                yield StreamChunk(
                    content=text,
                    done=done,
                    tokens_so_far=tokens_so_far,
                    finish_reason=finish_reason,
                )

                if done:
                    break
            except StopIteration:
                break
