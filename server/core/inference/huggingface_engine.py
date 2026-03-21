"""
HuggingFace 推理引擎实现

基于 transformers 库的本地推理引擎
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
from .flash_attention import (
    is_flash_attn_2_available,
    get_attention_implementation,
    get_flash_attention_info,
)

logger = logging.getLogger(__name__)


class HuggingFaceEngine(InferenceEngine):
    """
    HuggingFace 推理引擎
    
    支持：
    - 模型加载与卸载
    - 同步/流式生成
    - LoRA 适配器
    - Chat Template
    """
    
    engine_type: str = "huggingface"
    
    def __init__(self, config: EngineConfig):
        super().__init__(config)
        self._lora_model = None
        self._lora_path: Optional[str] = None
        self._device = None
        self._attention_backend: str = "eager"
    
    async def load(self) -> None:
        """加载模型和分词器"""
        if self._is_loaded:
            logger.info(f"模型已加载：{self.config.model_id}")
            return
        
        model_path = self.config.model_path
        if not model_path or not model_path.exists():
            raise RuntimeError(f"模型路径不存在：{model_path}")
        
        try:
            import torch
            from transformers import AutoTokenizer, AutoModelForCausalLM
            
            logger.info(f"加载模型：{model_path}")
            start_time = time.time()
            
            self._tokenizer = AutoTokenizer.from_pretrained(
                str(model_path),
                trust_remote_code=self.config.trust_remote_code,
            )
            
            if self._tokenizer.pad_token is None:
                self._tokenizer.pad_token = self._tokenizer.eos_token
            
            torch_dtype = self._get_torch_dtype()
            
            attn_implementation = self._get_attention_implementation()
            
            load_kwargs = {
                "pretrained_model_name_or_path": str(model_path),
                "device_map": self.config.device,
                "torch_dtype": torch_dtype,
                "trust_remote_code": self.config.trust_remote_code,
                "low_cpu_mem_usage": self.config.low_cpu_mem_usage,
            }
            
            if attn_implementation:
                load_kwargs["attn_implementation"] = attn_implementation
            
            try:
                self._model = AutoModelForCausalLM.from_pretrained(**load_kwargs)
                self._attention_backend = attn_implementation or "eager"
                if attn_implementation == "flash_attention_2":
                    logger.info("Flash Attention 2 加载成功")
            except Exception as e:
                if attn_implementation == "flash_attention_2":
                    logger.warning(f"Flash Attention 2 初始化失败，降级为 eager：{e}")
                    load_kwargs["attn_implementation"] = "eager"
                    self._model = AutoModelForCausalLM.from_pretrained(**load_kwargs)
                    self._attention_backend = "eager"
                else:
                    raise
            
            self._model.eval()
            self._device = self._model.device
            
            self._is_loaded = True
            self._load_time = time.time() - start_time
            
            logger.info(f"模型加载完成：{self.config.model_id}，耗时 {self._load_time:.2f}s，attention 后端：{self._attention_backend}")
            
        except ImportError as e:
            raise RuntimeError(f"缺少依赖库：{e}")
        except Exception as e:
            logger.error(f"模型加载失败：{e}", exc_info=True)
            raise RuntimeError(f"模型加载失败：{e}")
    
    def _get_attention_implementation(self) -> Optional[str]:
        """
        获取 attention 实现方式
        
        Returns:
            Optional[str]: "flash_attention_2"、"eager" 或 None（使用默认）
        """
        from core.config import get_settings
        settings = get_settings()
        
        if not settings.enable_flash_attention:
            logger.debug("Flash Attention 已在配置中禁用")
            return "eager"
        
        if is_flash_attn_2_available():
            logger.debug("检测到 Flash Attention 2 可用")
            return "flash_attention_2"
        
        logger.debug("Flash Attention 2 不可用，使用 eager 实现")
        return "eager"
    
    def _get_torch_dtype(self):
        """获取 torch 数据类型"""
        import torch
        dtype_map = {
            "float16": torch.float16,
            "bfloat16": torch.bfloat16,
            "float32": torch.float32,
            "auto": "auto",
        }
        return dtype_map.get(self.config.torch_dtype, torch.float16)
    
    async def unload(self) -> None:
        """卸载模型并释放资源"""
        if not self._is_loaded:
            return
        
        try:
            if self._lora_model is not None:
                del self._lora_model
                self._lora_model = None
                self._lora_path = None
            
            if self._model is not None:
                if hasattr(self._model, "cpu"):
                    self._model.cpu()
                del self._model
                self._model = None
            
            if self._tokenizer is not None:
                del self._tokenizer
                self._tokenizer = None
            
            from core.utils import cleanup_gpu_memory
            cleanup_gpu_memory()
            
            self._is_loaded = False
            logger.info(f"模型已卸载：{self.config.model_id}")
            
        except Exception as e:
            logger.warning(f"卸载模型时出错：{e}")
    
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
            import torch
            
            model = self._lora_model or self._model
            
            formatted_prompt = await self.apply_chat_template(prompt, kwargs.get("messages"))
            
            inputs = self._tokenizer(formatted_prompt, return_tensors="pt").to(model.device)
            input_length = inputs.input_ids.shape[1]
            
            with torch.no_grad():
                outputs = model.generate(
                    **inputs,
                    max_new_tokens=config.max_new_tokens,
                    temperature=config.temperature,
                    top_p=config.top_p,
                    top_k=config.top_k,
                    do_sample=config.do_sample and config.temperature > 0,
                    repetition_penalty=config.repetition_penalty,
                    pad_token_id=self._tokenizer.pad_token_id,
                    eos_token_id=self._tokenizer.eos_token_id,
                )
            
            generated_ids = outputs[0][input_length:]
            response_text = self._tokenizer.decode(generated_ids, skip_special_tokens=True)
            
            response_text = self._clean_response(response_text)
            
            elapsed_time = time.time() - start_time
            tokens_generated = len(generated_ids)
            
            return GenerationResult(
                text=response_text.strip(),
                tokens=tokens_generated,
                time=elapsed_time,
                model_id=self.config.model_id,
                backend=self.engine_type,
                metadata={
                    "input_length": input_length,
                    "lora_applied": self._lora_path is not None,
                }
            )
            
        except Exception as e:
            logger.error(f"生成失败：{e}", exc_info=True)
            raise RuntimeError(f"生成失败：{e}")
    
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
            import torch
            import asyncio
            from transformers import TextIteratorStreamer
            from threading import Thread, Event
            
            model = self._lora_model or self._model
            
            formatted_prompt = await self.apply_chat_template(prompt, kwargs.get("messages"))
            
            inputs = self._tokenizer(formatted_prompt, return_tensors="pt").to(model.device)
            
            streamer = TextIteratorStreamer(
                self._tokenizer,
                skip_prompt=True,
                skip_special_tokens=True,
                timeout=300,
            )
            
            generation_kwargs = {
                **inputs,
                "max_new_tokens": config.max_new_tokens,
                "temperature": config.temperature,
                "top_p": config.top_p,
                "do_sample": config.do_sample and config.temperature > 0,
                "streamer": streamer,
                "pad_token_id": self._tokenizer.pad_token_id,
                "eos_token_id": self._tokenizer.eos_token_id,
            }
            
            generation_error = None
            generation_complete = Event()
            
            def generate_with_error_handling():
                nonlocal generation_error
                try:
                    model.generate(**generation_kwargs)
                except Exception as e:
                    generation_error = e
                    logger.error(f"生成线程错误: {e}", exc_info=True)
                finally:
                    generation_complete.set()
            
            thread = Thread(target=generate_with_error_handling, daemon=True)
            thread.start()
            
            def get_next_token():
                try:
                    return next(streamer)
                except StopIteration:
                    return None
            
            while True:
                if generation_error:
                    raise generation_error
                
                text = await asyncio.to_thread(get_next_token)
                
                if text is None:
                    if not generation_complete.is_set():
                        await asyncio.sleep(0.05)
                        continue
                    break
                
                if text:
                    text = self._clean_response(text)
                    if text:
                        yield text
            
            await asyncio.to_thread(thread.join, timeout=5.0)
            
            if generation_error:
                raise generation_error
            
        except Exception as e:
            logger.error(f"流式生成失败：{e}", exc_info=True)
            raise RuntimeError(f"流式生成失败：{e}")
    
    async def apply_lora(self, lora_path: str) -> None:
        """应用 LoRA 适配器"""
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
            from peft import PeftModel
            
            logger.info(f"加载 LoRA 适配器：{full_lora_path}")
            
            self._lora_model = PeftModel.from_pretrained(self._model, str(full_lora_path))
            self._lora_path = str(full_lora_path)
            
            logger.info(f"LoRA 适配器加载完成：{lora_path}")
            
        except ImportError:
            raise RuntimeError("peft 库未安装，无法加载 LoRA 适配器")
        except Exception as e:
            logger.error(f"加载 LoRA 适配器失败：{e}", exc_info=True)
            raise RuntimeError(f"加载 LoRA 适配器失败：{e}")
    
    async def remove_lora(self) -> None:
        """移除 LoRA 适配器"""
        if self._lora_model is not None:
            del self._lora_model
            self._lora_model = None
            self._lora_path = None
            
            from core.utils import cleanup_gpu_memory
            cleanup_gpu_memory()
            
            logger.info("LoRA 适配器已移除")
    
    def _clean_response(self, text: str) -> str:
        """清理响应文本"""
        text = text.replace("<|im_end|>", "").replace("<|im_start|>", "")
        
        THINK_START = "<think"
        THINK_END = "</think"
        
        while THINK_START in text and THINK_END in text:
            start_idx = text.find(THINK_START)
            end_idx = text.find(THINK_END)
            if start_idx < end_idx:
                gt_pos = text.find('>', end_idx)
                if gt_pos != -1:
                    text = text[:start_idx] + text[gt_pos + 1:]
                else:
                    text = text[:start_idx] + text[end_idx + len(THINK_END):]
            else:
                break
        
        if THINK_START in text:
            idx = text.find(THINK_START)
            text = text[:idx]
        
        return text
    
    @property
    def model_info(self) -> Dict[str, Any]:
        """获取模型信息"""
        info = super().model_info
        info.update({
            "device": str(self._device) if self._device else None,
            "lora_applied": self._lora_path is not None,
            "lora_path": self._lora_path,
            "attention_backend": self._attention_backend,
            "flash_attention_info": get_flash_attention_info(),
        })
        return info
