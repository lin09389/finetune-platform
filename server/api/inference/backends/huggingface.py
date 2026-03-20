"""
HuggingFace 推理后端实现
"""
import asyncio
import logging
import time
from typing import Dict, Any, Optional, List, AsyncGenerator
from pathlib import Path

from api.inference.backends.base import BaseBackend, InferenceContext
from api.types import (
    ChatRequest, ChatResponse, GenerateRequest, GenerateResponse,
    Message, MessageRole, TokenUsage, KnowledgeSource
)
from api.errors import ModelNotFoundError, ModelLoadFailedError, InferenceFailedError
from core.config import get_settings

logger = logging.getLogger(__name__)


class HuggingFaceBackend(BaseBackend):
    """HuggingFace 推理后端"""
    
    def __init__(self):
        self.settings = get_settings()
        self._model_cache: Dict[str, Dict[str, Any]] = {}
        self._lora_cache: Dict[str, Any] = {}
    
    @property
    def name(self) -> str:
        return "huggingface"
    
    async def is_available(self) -> bool:
        try:
            import torch
            return True
        except ImportError:
            return False
    
    async def list_models(self) -> List[Dict[str, Any]]:
        """列出可用模型"""
        models = []
        models_dir = self.settings.models_dir_resolved
        
        if models_dir.exists():
            for model_path in models_dir.iterdir():
                if model_path.is_dir():
                    config_file = model_path / "config.json"
                    if config_file.exists():
                        try:
                            import json
                            with open(config_file, "r", encoding="utf-8") as f:
                                config = json.load(f)
                            models.append({
                                "id": model_path.name,
                                "name": config.get("model_name", model_path.name),
                                "type": config.get("type", "base"),
                                "quantized": config.get("quantized"),
                                "backend": "huggingface"
                            })
                        except Exception as e:
                            logger.warning(f"读取模型配置失败: {model_path.name}: {e}")
        
        return models
    
    async def is_model_loaded(self, model_id: str) -> bool:
        return model_id in self._model_cache
    
    async def load_model(self, model_id: str) -> Dict[str, Any]:
        """加载模型"""
        if model_id in self._model_cache:
            logger.info(f"模型已缓�? {model_id}")
            return self._model_cache[model_id]
        
        model_path = self.settings.models_dir_resolved / model_id
        if not model_path.exists():
            raise ModelNotFoundError(model_id)
        
        try:
            import torch
            from transformers import AutoTokenizer, AutoModelForCausalLM
            
            logger.info(f"加载 HuggingFace 模型: {model_path}")
            
            tokenizer = AutoTokenizer.from_pretrained(
                str(model_path),
                trust_remote_code=True
            )
            
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token
            
            model = AutoModelForCausalLM.from_pretrained(
                str(model_path),
                device_map="auto",
                torch_dtype=torch.float16,
                trust_remote_code=True,
                low_cpu_mem_usage=True,
            )
            
            model.eval()
            
            model_data = {
                "model": model,
                "tokenizer": tokenizer,
                "loaded_at": time.time(),
                "device": str(model.device) if hasattr(model, 'device') else "unknown"
            }
            
            self._model_cache[model_id] = model_data
            logger.info(f"模型加载完成: {model_id}")
            
            return model_data
            
        except Exception as e:
            logger.error(f"模型加载失败: {model_id}: {e}")
            raise ModelLoadFailedError(model_id, str(e))
    
    async def unload_model(self, model_id: str) -> bool:
        """卸载模型"""
        if model_id not in self._model_cache:
            return False
        
        try:
            import torch
            import gc
            
            model_data = self._model_cache.pop(model_id)
            
            del model_data["model"]
            del model_data["tokenizer"]
            
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
            
            logger.info(f"模型已卸�? {model_id}")
            return True
            
        except Exception as e:
            logger.error(f"卸载模型失败: {model_id}: {e}")
            return False
    
    async def generate(
        self,
        request: GenerateRequest,
        context: Optional[InferenceContext] = None
    ) -> GenerateResponse:
        """生成文本"""
        start_time = time.time()
        
        try:
            model_data = await self.load_model(request.model)
            model = model_data["model"]
            tokenizer = model_data["tokenizer"]
            
            import torch
            
            lora_adapter = getattr(request, 'lora_adapter', None)
            if lora_adapter:
                model = await self._load_lora(model, lora_adapter)
            
            prompt = request.prompt
            if request.system:
                prompt = f"{request.system}\n\n{prompt}"
            
            inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
            input_length = inputs.input_ids.shape[1]
            
            with torch.no_grad():
                outputs = model.generate(
                    **inputs,
                    max_new_tokens=request.options.max_tokens,
                    temperature=request.options.temperature,
                    top_p=request.options.top_p,
                    top_k=request.options.top_k,
                    do_sample=request.options.temperature > 0,
                    repetition_penalty=request.options.repetition_penalty,
                    pad_token_id=tokenizer.pad_token_id,
                    eos_token_id=tokenizer.eos_token,
                )
            
            generated_ids = outputs[0][input_length:]
            response_text = tokenizer.decode(generated_ids, skip_special_tokens=True)
            response_text = self.clean_response(response_text)
            
            elapsed_time = time.time() - start_time
            
            return GenerateResponse(
                model=request.model,
                response=response_text,
                usage=TokenUsage(
                    prompt_tokens=input_length,
                    completion_tokens=len(generated_ids),
                    total_tokens=input_length + len(generated_ids)
                ),
                total_duration=elapsed_time,
                eval_duration=elapsed_time
            )
            
        except Exception as e:
            logger.error(f"生成失败: {e}", exc_info=True)
            raise InferenceFailedError(request.model, str(e))
    
    async def chat(
        self,
        request: ChatRequest,
        context: Optional[InferenceContext] = None
    ) -> ChatResponse:
        """聊天对话"""
        start_time = time.time()
        
        try:
            model_data = await self.load_model(request.model)
            model = model_data["model"]
            tokenizer = model_data["tokenizer"]
            
            import torch
            
            messages_for_template = []
            for msg in request.messages:
                role = msg.role if isinstance(msg.role, str) else msg.role.value
                messages_for_template.append({"role": role, "content": msg.content})
            
            if hasattr(tokenizer, 'apply_chat_template'):
                try:
                    prompt = tokenizer.apply_chat_template(
                        messages_for_template,
                        tokenize=False,
                        add_generation_prompt=True
                    )
                except Exception as e:
                    logger.warning(f"apply_chat_template 失败: {e}")
                    prompt = self._apply_default_template(request.messages)
            else:
                prompt = self._apply_default_template(request.messages)
            
            inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
            input_length = inputs.input_ids.shape[1]
            
            with torch.no_grad():
                outputs = model.generate(
                    **inputs,
                    max_new_tokens=request.options.max_tokens,
                    temperature=request.options.temperature,
                    top_p=request.options.top_p,
                    do_sample=request.options.temperature > 0,
                    pad_token_id=tokenizer.pad_token_id,
                    eos_token_id=tokenizer.eos_token,
                )
            
            generated_ids = outputs[0][input_length:]
            response_text = tokenizer.decode(generated_ids, skip_special_tokens=True)
            response_text = self.clean_response(response_text)
            
            elapsed_time = time.time() - start_time
            
            return ChatResponse(
                message=Message(
                    role=MessageRole.ASSISTANT,
                    content=response_text
                ),
                model=request.model,
                backend="huggingface",
                usage=TokenUsage(
                    prompt_tokens=input_length,
                    completion_tokens=len(generated_ids),
                    total_tokens=input_length + len(generated_ids)
                ),
                total_duration=elapsed_time,
                eval_duration=elapsed_time
            )
            
        except Exception as e:
            logger.error(f"聊天失败: {e}", exc_info=True)
            raise InferenceFailedError(request.model, str(e))
    
    async def generate_stream(
        self,
        request: GenerateRequest,
        context: Optional[InferenceContext] = None
    ) -> AsyncGenerator[str, None]:
        """流式生成"""
        from transformers import TextIteratorStreamer
        from threading import Thread, Event
        import asyncio
        
        try:
            model_data = await self.load_model(request.model)
            model = model_data["model"]
            tokenizer = model_data["tokenizer"]
            
            import torch
            
            inputs = tokenizer(request.prompt, return_tensors="pt").to(model.device)
            
            streamer = TextIteratorStreamer(
                tokenizer,
                skip_prompt=True,
                skip_special_tokens=True,
                timeout=300,
            )
            
            generation_kwargs = {
                **inputs,
                "max_new_tokens": request.options.max_tokens,
                "temperature": request.options.temperature,
                "top_p": request.options.top_p,
                "do_sample": request.options.temperature > 0,
                "streamer": streamer,
                "pad_token_id": tokenizer.pad_token_id,
                "eos_token_id": tokenizer.eos_token,
            }
            
            generation_complete = Event()
            generation_error = None
            
            def generate_thread():
                nonlocal generation_error
                try:
                    model.generate(**generation_kwargs)
                except Exception as e:
                    generation_error = e
                    logger.error(f"生成线程错误: {e}")
                finally:
                    generation_complete.set()
            
            thread = Thread(target=generate_thread, daemon=True)
            thread.start()
            
            while True:
                if generation_error:
                    yield f'data: {{"error": "{str(generation_error)}", "done": true}}\n\n'
                    break
                
                try:
                    text = await asyncio.to_thread(next, streamer)
                    if text:
                        text = text.replace("<|im_end|>", "").replace("<|im_start|>", "")
                        if text:
                            yield f'data: {{"content": "{text}", "done": false}}\n\n'
                except StopIteration:
                    break
                
                if generation_complete.is_set():
                    break
            
            await asyncio.to_thread(thread.join, timeout=5.0)
            yield f'data: {{"done": true}}\n\n'
            
        except Exception as e:
            logger.error(f"流式生成失败: {e}", exc_info=True)
            yield f'data: {{"error": "{str(e)}", "done": true}}\n\n'
    
    async def _load_lora(self, model, lora_path: str):
        """加载 LoRA 适配�?""
        if lora_path in self._lora_cache:
            return self._lora_cache[lora_path]
        
        try:
            from peft import PeftModel
            
            full_path = Path(lora_path)
            if not full_path.is_absolute():
                full_path = self.settings.outputs_dir_resolved / lora_path
            
            if not full_path.exists():
                raise FileNotFoundError(f"LoRA 适配器不存在: {lora_path}")
            
            lora_model = PeftModel.from_pretrained(model, str(full_path))
            self._lora_cache[lora_path] = lora_model
            
            logger.info(f"LoRA 适配器加载完�? {lora_path}")
            return lora_model
            
        except ImportError:
            raise ImportError("peft 库未安装，无法加�?LoRA 适配�?)
        except Exception as e:
            logger.error(f"加载 LoRA 失败: {e}")
            raise
    
    def _apply_default_template(self, messages: List[Message]) -> str:
        """应用默认模板"""
        parts = []
        for msg in messages:
            role = msg.role if isinstance(msg.role, str) else msg.role.value
            parts.append(f"<|im_start|>{role}\n{msg.content}<|im_end|>\n")
        parts.append("<|im_start|>assistant\n")
        return "".join(parts)
