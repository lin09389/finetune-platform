"""
Llama.cpp 推理后端实现
基于 llama-cpp-python 原生支持 GGUF 格式，极低显存占用，支持动态挂载 LoRA 适配器
"""
import asyncio
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from .base import BackendType, GenerationConfig, GenerationResult, InferenceBackend

logger = logging.getLogger(__name__)

try:
    from llama_cpp import Llama
    HAS_LLAMA_CPP = True
except ImportError:
    HAS_LLAMA_CPP = False


class LlamaCppBackend(InferenceBackend):
    """Llama-cpp 推理后端"""

    backend_type = BackendType.LLAMACPP

    def __init__(self, config: dict[str, Any] = None):
        super().__init__(config or {})
        
        config = config or {}
        self.n_gpu_layers = config.get("n_gpu_layers", -1)
        self.n_ctx = config.get("n_ctx", 2048)
        self.lora_base = config.get("lora_base", None)
        self.lora_path = config.get("lora_path", None)
        self.verbose = config.get("verbose", False)
        
        self._llm: Llama | None = None
        self._model_name = ""

    async def load_model(self, model_name: str, **kwargs) -> bool:
        """加载模型"""
        if not HAS_LLAMA_CPP:
            logger.error("llama-cpp-python 未安装")
            return False

        try:
            logger.info(f"Loading Llama.cpp model: {model_name}")

            load_kwargs = {
                "model_path": model_name,
                "n_gpu_layers": self.n_gpu_layers,
                "n_ctx": self.n_ctx,
                "verbose": self.verbose,
            }

            if self.lora_base:
                load_kwargs["lora_base"] = self.lora_base
            if self.lora_path:
                load_kwargs["lora_path"] = self.lora_path
                logger.info(f"动态挂载 LoRA: {self.lora_path}")

            # 初始化 LLM (由于阻塞，放到线程池中)
            def _load_sync():
                return Llama(**load_kwargs)

            self._llm = await asyncio.to_thread(_load_sync)
            self._model_name = model_name
            self._is_loaded = True
            
            logger.info(f"Llama.cpp model loaded: {model_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to load Llama.cpp model: {e}", exc_info=True)
            self._is_loaded = False
            return False

    async def unload_model(self) -> bool:
        """卸载模型"""
        try:
            if self._llm:
                del self._llm
                self._llm = None
            
            import gc
            gc.collect()

            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass

            self._is_loaded = False
            logger.info("Llama.cpp model unloaded")
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
        if not self._is_loaded or not self._llm:
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
            def _generate_sync():
                return self._llm(
                    prompt,
                    max_tokens=config.max_tokens,
                    temperature=config.temperature,
                    top_p=config.top_p,
                    top_k=config.top_k,
                    repeat_penalty=config.repetition_penalty,
                    stop=config.stop_sequences,
                )

            output = await asyncio.to_thread(_generate_sync)

            text = output["choices"][0]["text"]
            tokens_generated = output["usage"]["completion_tokens"]
            prompt_tokens = output["usage"]["prompt_tokens"]
            finish_reason = output["choices"][0].get("finish_reason", "stop")

            latency_ms = (time.time() - start_time) * 1000

            return GenerationResult(
                text=text,
                tokens_generated=tokens_generated,
                finish_reason=finish_reason,
                model=self._model_name,
                prompt_tokens=prompt_tokens,
                total_tokens=prompt_tokens + tokens_generated,
                latency_ms=latency_ms
            )

        except Exception as e:
            logger.error(f"Llama.cpp generation failed: {e}")
            return GenerationResult(
                text="",
                tokens_generated=0,
                finish_reason="error",
                model=self._model_name,
                metadata={"error": str(e)}
            )

    async def generate_stream(
        self,
        prompt: str,
        config: GenerationConfig = None
    ) -> AsyncIterator[str]:
        """流式生成文本"""
        if not self._is_loaded or not self._llm:
            yield "[Error: Model not loaded]"
            return

        config = config or GenerationConfig()

        try:
            def _do_stream():
                return self._llm(
                    prompt,
                    max_tokens=config.max_tokens,
                    temperature=config.temperature,
                    top_p=config.top_p,
                    top_k=config.top_k,
                    repeat_penalty=config.repetition_penalty,
                    stop=config.stop_sequences,
                    stream=True,
                )

            streamer = await asyncio.to_thread(_do_stream)

            while True:
                try:
                    chunk = await asyncio.to_thread(next, streamer)
                    text = chunk["choices"][0]["text"]
                    if text:
                        yield text
                    
                    if chunk["choices"][0].get("finish_reason") is not None:
                        break
                except StopIteration:
                    break

        except Exception as e:
            logger.error(f"Llama.cpp stream generation failed: {e}")
            yield f"[Error: {str(e)}]"

    async def chat(
        self,
        messages: list[dict[str, str]],
        config: GenerationConfig = None
    ) -> GenerationResult:
        """对话生成"""
        if not self._is_loaded or not self._llm:
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
            # 转换消息格式
            formatted_messages = []
            for msg in messages:
                formatted_messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", "")
                })

            def _chat_sync():
                return self._llm.create_chat_completion(
                    messages=formatted_messages,
                    max_tokens=config.max_tokens,
                    temperature=config.temperature,
                    top_p=config.top_p,
                    top_k=config.top_k,
                    repeat_penalty=config.repetition_penalty,
                    stop=config.stop_sequences,
                )

            output = await asyncio.to_thread(_chat_sync)

            text = output["choices"][0]["message"]["content"]
            tokens_generated = output["usage"]["completion_tokens"]
            prompt_tokens = output["usage"]["prompt_tokens"]
            finish_reason = output["choices"][0].get("finish_reason", "stop")

            latency_ms = (time.time() - start_time) * 1000

            return GenerationResult(
                text=text,
                tokens_generated=tokens_generated,
                finish_reason=finish_reason,
                model=self._model_name,
                prompt_tokens=prompt_tokens,
                total_tokens=prompt_tokens + tokens_generated,
                latency_ms=latency_ms
            )

        except Exception as e:
            logger.error(f"Llama.cpp chat failed: {e}")
            return GenerationResult(
                text="",
                tokens_generated=0,
                finish_reason="error",
                model=self._model_name,
                metadata={"error": str(e)}
            )

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        config: GenerationConfig = None
    ) -> AsyncIterator[str]:
        """流式对话生成"""
        if not self._is_loaded or not self._llm:
            yield "[Error: Model not loaded]"
            return

        config = config or GenerationConfig()

        try:
            # 转换消息格式
            formatted_messages = []
            for msg in messages:
                formatted_messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", "")
                })

            def _chat_stream_sync():
                return self._llm.create_chat_completion(
                    messages=formatted_messages,
                    max_tokens=config.max_tokens,
                    temperature=config.temperature,
                    top_p=config.top_p,
                    top_k=config.top_k,
                    repeat_penalty=config.repetition_penalty,
                    stop=config.stop_sequences,
                    stream=True,
                )

            streamer = await asyncio.to_thread(_chat_stream_sync)

            while True:
                try:
                    chunk = await asyncio.to_thread(next, streamer)
                    if "content" in chunk["choices"][0].get("delta", {}):
                        text = chunk["choices"][0]["delta"]["content"]
                        if text:
                            yield text
                    
                    if chunk["choices"][0].get("finish_reason") is not None:
                        break
                except StopIteration:
                    break

        except Exception as e:
            logger.error(f"Llama.cpp stream chat failed: {e}")
            yield f"[Error: {str(e)}]"

    def get_model_info(self) -> dict[str, Any]:
        """获取模型信息"""
        return {
            "backend_type": self.backend_type.value,
            "is_loaded": self._is_loaded,
            "n_gpu_layers": self.n_gpu_layers,
            "n_ctx": self.n_ctx,
            "lora_base": self.lora_base,
            "lora_path": self.lora_path
        }

    async def count_tokens(self, text: str) -> int:
        """计算 token 数量"""
        if not self._llm:
            return len(text) // 4
            
        def _count():
            # llama-cpp-python 使用 tokenize 计算 token
            return len(self._llm.tokenize(text.encode("utf-8")))
            
        return await asyncio.to_thread(_count)
