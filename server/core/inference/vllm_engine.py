"""
vLLM 推理引擎实现

基于 vLLM 库的高性能推理引擎，支�?PagedAttention
"""
import asyncio
import time
import logging
from pathlib import Path
from typing import AsyncGenerator, Dict, Any, Optional, List

from .engine_base import (
    InferenceEngine,
    EngineConfig,
    GenerationConfig,
    GenerationResult,
)

logger = logging.getLogger(__name__)


class VLLMEngine(InferenceEngine):
    """
    vLLM 推理引擎
    
    特性：
    - PagedAttention 内存优化
    - 高吞吐量批处�?    - 异步流式生成
    - KV Cache 优化
    """
    
    engine_type: str = "vllm"
    
    def __init__(self, config: EngineConfig):
        super().__init__(config)
        self._llm = None
        self._sampling_params = None
        self._lora_path: Optional[str] = None
        self._vllm_config: Dict[str, Any] = {}
    
    async def load(self) -> None:
        """加载模型"""
        if self._is_loaded:
            logger.info(f"模型已加载：{self.config.model_id}")
            return
        
        model_path = self.config.model_path
        if not model_path or not model_path.exists():
            raise RuntimeError(f"模型路径不存在：{model_path}")
        
        try:
            from vllm import LLM, SamplingParams
            from core.config import get_settings
            
            settings = get_settings()
            
            logger.info(f"加载 vLLM 模型：{model_path}")
            start_time = time.time()
            
            self._vllm_config = self._build_vllm_config(settings)
            
            logger.info(f"vLLM 配置：{self._vllm_config}")
            
            self._llm = LLM(
                model=str(model_path),
                **self._vllm_config
            )
            
            self._is_loaded = True
            self._load_time = time.time() - start_time
            
            logger.info(f"vLLM 模型加载完成：{self.config.model_id}，耗时 {self._load_time:.2f}s")
            
        except ImportError as e:
            raise RuntimeError(f"vLLM 库未安装：{e}。请使用 pip install vllm 安装")
        except Exception as e:
            logger.error(f"vLLM 模型加载失败：{e}", exc_info=True)
            raise RuntimeError(f"vLLM 模型加载失败：{e}")
    
    def _build_vllm_config(self, settings) -> Dict[str, Any]:
        """
        构建 vLLM 配置
        
        �?Settings 转换�?vLLM LLM 参数
        """
        config = {
            "gpu_memory_utilization": settings.vllm_gpu_memory_utilization,
            "max_model_len": settings.vllm_max_model_len,
            "tensor_parallel_size": settings.vllm_tensor_parallel_size,
            "trust_remote_code": self.config.trust_remote_code,
            "dtype": self._get_dtype(),
        }
        
        if settings.enable_flash_attention:
            config["enable_flash_attn"] = True
        
        kv_cache_dtype = settings.kv_cache_dtype
        if kv_cache_dtype != "float16":
            config["kv_cache_dtype"] = kv_cache_dtype
        
        if settings.enable_prefix_caching:
            config["enable_prefix_caching"] = True
        
        return config
    
    def _get_dtype(self) -> str:
        """获取模型数据类型"""
        dtype_map = {
            "float16": "float16",
            "bfloat16": "bfloat16",
            "float32": "float32",
            "auto": "auto",
        }
        return dtype_map.get(self.config.torch_dtype, "auto")
    
    def _build_sampling_params(self, config: GenerationConfig) -> "SamplingParams":
        """构建采样参数"""
        from vllm import SamplingParams
        
        return SamplingParams(
            max_tokens=config.max_new_tokens,
            temperature=config.temperature if config.do_sample else 0.0,
            top_p=config.top_p,
            top_k=config.top_k,
            repetition_penalty=config.repetition_penalty,
        )
    
    async def unload(self) -> None:
        """卸载模型并释放资�?""
        if not self._is_loaded:
            return
        
        try:
            if self._llm is not None:
                del self._llm
                self._llm = None
            
            from core.utils import cleanup_gpu_memory
            cleanup_gpu_memory()
            
            self._is_loaded = False
            self._lora_path = None
            
            logger.info(f"vLLM 模型已卸载：{self.config.model_id}")
            
        except Exception as e:
            logger.warning(f"卸载 vLLM 模型时出错：{e}")
    
    async def generate(
        self,
        prompt: str,
        config: Optional[GenerationConfig] = None,
        **kwargs
    ) -> GenerationResult:
        """同步生成文本"""
        if not self._is_loaded:
            await self.load()
        
        config = config or GenerationConfig()
        start_time = time.time()
        
        try:
            from vllm import SamplingParams
            
            formatted_prompt = await self.apply_chat_template(prompt, kwargs.get("messages"))
            
            sampling_params = self._build_sampling_params(config)
            
            outputs = self._llm.generate(
                [formatted_prompt],
                sampling_params,
                use_tqdm=False,
            )
            
            if not outputs:
                raise RuntimeError("vLLM 生成失败：无输出")
            
            output = outputs[0]
            generated_text = output.outputs[0].text
            tokens_generated = len(output.outputs[0].token_ids)
            
            elapsed_time = time.time() - start_time
            
            return GenerationResult(
                text=generated_text.strip(),
                tokens=tokens_generated,
                time=elapsed_time,
                model_id=self.config.model_id,
                backend=self.engine_type,
                metadata={
                    "prompt_tokens": len(output.prompt_token_ids),
                    "lora_applied": self._lora_path is not None,
                    "finish_reason": output.outputs[0].finish_reason,
                }
            )
            
        except Exception as e:
            logger.error(f"vLLM 生成失败：{e}", exc_info=True)
            raise RuntimeError(f"vLLM 生成失败：{e}")
    
    async def stream(
        self,
        prompt: str,
        config: Optional[GenerationConfig] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """流式生成文本"""
        if not self._is_loaded:
            await self.load()
        
        config = config or GenerationConfig()
        
        try:
            from vllm import SamplingParams, RequestOutput
            from vllm.utils import random_uuid
            
            formatted_prompt = await self.apply_chat_template(prompt, kwargs.get("messages"))
            sampling_params = self._build_sampling_params(config)
            
            request_id = random_uuid()
            
            results_generator = self._llm.generate(
                [formatted_prompt],
                sampling_params,
                request_id=request_id,
                stream=True,
            )
            
            previous_text = ""
            
            async for request_output in self._async_iterate(results_generator):
                if not request_output.outputs:
                    continue
                
                output = request_output.outputs[0]
                new_text = output.text[len(previous_text):]
                previous_text = output.text
                
                if new_text:
                    yield new_text
            
        except Exception as e:
            logger.error(f"vLLM 流式生成失败：{e}", exc_info=True)
            raise RuntimeError(f"vLLM 流式生成失败：{e}")
    
    async def _async_iterate(self, generator):
        """将同步生成器转换为异步迭代器"""
        loop = asyncio.get_event_loop()
        
        def get_next(iter_obj):
            try:
                return next(iter_obj)
            except StopIteration:
                return None
        
        iterator = iter(generator)
        
        while True:
            result = await loop.run_in_executor(None, get_next, iterator)
            if result is None:
                break
            yield result
    
    async def apply_lora(self, lora_path: str) -> None:
        """
        应用 LoRA 适配�?        
        注意：vLLM �?LoRA 支持需要在初始化时配置
        """
        if not self._is_loaded:
            await self.load()
        
        full_lora_path = Path(lora_path)
        if not full_lora_path.is_absolute():
            from core.config import get_settings
            settings = get_settings()
            full_lora_path = settings.outputs_dir_resolved / lora_path
        
        if not full_lora_path.exists():
            raise RuntimeError(f"LoRA 适配器不存在：{lora_path}")
        
        try:
            if hasattr(self._llm, "llm_engine") and hasattr(self._llm.llm_engine, "add_lora"):
                self._llm.llm_engine.add_lora(str(full_lora_path))
                self._lora_path = str(full_lora_path)
                logger.info(f"vLLM LoRA 适配器已应用：{lora_path}")
            else:
                logger.warning("vLLM 当前版本不支持动�?LoRA 加载，请在初始化时配�?)
                self._lora_path = str(full_lora_path)
                
        except Exception as e:
            logger.error(f"应用 vLLM LoRA 适配器失败：{e}", exc_info=True)
            raise RuntimeError(f"应用 vLLM LoRA 适配器失败：{e}")
    
    async def remove_lora(self) -> None:
        """移除 LoRA 适配�?""
        if self._lora_path is None:
            return
        
        try:
            if hasattr(self._llm, "llm_engine") and hasattr(self._llm.llm_engine, "remove_lora"):
                self._llm.llm_engine.remove_lora()
            
            self._lora_path = None
            logger.info("vLLM LoRA 适配器已移除")
            
        except Exception as e:
            logger.warning(f"移除 vLLM LoRA 适配器时出错：{e}")
            self._lora_path = None
    
    @property
    def model_info(self) -> Dict[str, Any]:
        """获取模型信息"""
        info = super().model_info
        info.update({
            "vllm_config": self._vllm_config,
            "lora_applied": self._lora_path is not None,
            "lora_path": self._lora_path,
        })
        return info
