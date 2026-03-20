"""
推理服务 API - 支持 HuggingFace �?Ollama 后端
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, AsyncGenerator
import os
import time
import requests
import threading
import json
import re
from pathlib import Path
from datetime import datetime
import logging
import asyncio

from core.config import get_settings
from core.logging import get_logger
from core.utils import get_vram_usage, cleanup_gpu_memory
from core.model_cache import get_model_cache

logger = get_logger(__name__)

router = APIRouter()

settings = get_settings()
MODELS_DIR = settings.models_dir_resolved
OLLAMA_BASE_URL = settings.ollama_base_url

_model_cache = get_model_cache(max_size=3)
lora_adapter_cache: Dict[str, Any] = {}

merge_state = {
    "is_merging": False,
    "progress": 0,
    "message": "",
}

PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions?",
    r"ignore\s+(all\s+)?(the\s+)?above",
    r"disregard\s+(all\s+)?previous",
    r"forget\s+(all\s+)?(previous\s+)?instructions?",
    r"you\s+are\s+now\s+",
    r"new\s+instructions?:",
    r"system:\s*you\s+are",
    r"<\|im_start\|>system",
    r"jailbreak",
    r"dan\s+mode",
    r"developer\s+mode",
    r"sudo\s+mode",
]

MAX_MESSAGE_LENGTH = 10000
MAX_MESSAGES_COUNT = 100

ERROR_MESSAGES = {
    "model_not_found": "模型不存在，请检查模型名称或先下载模�?,
    "ollama_not_running": "Ollama 服务未运行，请先启动 Ollama",
    "ollama_unavailable": "Ollama 服务暂时不可用，请稍后重�?,
    "inference_failed": "推理生成失败，请稍后重试",
    "model_load_failed": "模型加载失败，请检查模型文件是否完�?,
    "context_too_long": "上下文长度超出限制，请减少对话历�?,
    "rate_limited": "请求过于频繁，请稍后重试",
    "invalid_input": "输入内容无效，请检查后重试",
    "malicious_input": "检测到潜在的恶意输入，请修改内容后重试",
}


def get_friendly_error(error_key: str, original_error: str = "") -> str:
    """获取友好的错误信�?""
    friendly_msg = ERROR_MESSAGES.get(error_key, f"操作失败：{error_key}")
    if original_error and logger.isEnabledFor(logging.DEBUG):
        return f"{friendly_msg}（详情：{original_error}�?
    return friendly_msg


def parse_ollama_error(error_text: str) -> str:
    """解析 Ollama 错误信息并返回友好的中文提示"""
    error_lower = error_text.lower()
    
    if "model" in error_lower and ("not found" in error_lower or "does not exist" in error_lower):
        return get_friendly_error("model_not_found")
    if "connection" in error_lower or "refused" in error_lower:
        return get_friendly_error("ollama_not_running")
    if "timeout" in error_lower:
        return get_friendly_error("ollama_unavailable")
    if "context" in error_lower and ("length" in error_lower or "too long" in error_lower):
        return get_friendly_error("context_too_long")
    
    return error_text


def sanitize_input(text: str) -> str:
    """清理和验证输入文�?""
    if not text:
        return text
    
    text = text.strip()
    
    if len(text) > MAX_MESSAGE_LENGTH:
        text = text[:MAX_MESSAGE_LENGTH]
    
    return text


def detect_prompt_injection(text: str) -> bool:
    """检测潜在的 Prompt 注入攻击"""
    text_lower = text.lower()
    
    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            logger.warning(f"检测到潜在�?Prompt 注入: {pattern}")
            return True
    
    return False


class InferenceRequest(BaseModel):
    """推理请求 - 支持驼峰和下划线两种命名"""
    # 驼峰命名（前端发送）
    modelId: Optional[str] = Field(None, description="模型 ID")
    maxTokens: Optional[int] = Field(None, description="最大生�?token �?)
    topP: Optional[float] = Field(None, description="Top-p 采样")
    topK: Optional[int] = Field(None, description="Top-k 采样")
    repetitionPenalty: Optional[float] = Field(None, description="重复惩罚")
    loraAdapter: Optional[str] = Field(None, description="LoRA 适配器路�?)

    # 下划线命名（后端标准�?    model_id: Optional[str] = Field(None, description="模型 ID")
    prompt: str = Field(...)
    max_tokens: int = Field(1024, ge=1, le=8192, description="最大生�?token �?)
    temperature: float = Field(0.7, ge=0, le=2, description="温度")
    top_p: float = Field(0.9, ge=0, le=1, description="Top-p 采样")
    top_k: int = Field(50, ge=1, description="Top-k 采样")
    repetition_penalty: float = Field(1.1, ge=0.1, le=2, description="重复惩罚")
    backend: Optional[str] = Field(None, description="推理后端：huggingface/ollama")
    lora_adapter: Optional[str] = Field(None, description="LoRA 适配器路�?)

    def get_model_id(self) -> str:
        return self.modelId or self.model_id or ""

    def get_max_tokens(self) -> int:
        return self.maxTokens or self.max_tokens or 1024

    def get_top_p(self) -> float:
        return self.topP if self.topP is not None else self.top_p

    def get_top_k(self) -> int:
        return self.topK if self.topK is not None else self.top_k

    def get_repetition_penalty(self) -> float:
        return self.repetitionPenalty if self.repetitionPenalty is not None else self.repetition_penalty

    def get_lora_adapter(self) -> Optional[str]:
        return self.loraAdapter or self.lora_adapter


class KnowledgeSourceResponse(BaseModel):
    """知识来源响应"""
    id: str
    source: str
    score: float
    content_preview: str = Field(default="", description="内容预览（前100字）")


class InferenceResponse(BaseModel):
    """推理响应"""
    text: str
    tokens: int
    time: float
    model_id: str
    backend: str
    knowledge_sources: Optional[List[KnowledgeSourceResponse]] = Field(default=None, description="知识来源")
    retrieval_info: Optional[Dict[str, Any]] = Field(default=None, description="检索信�?)


class ChatMessage(BaseModel):
    """聊天消息"""
    role: str = Field(..., description="角色：user/assistant/system")
    content: str = Field(..., description="消息内容")


class ChatRequest(BaseModel):
    """聊天请求"""
    model_id: str = Field(..., description="模型 ID")
    messages: List[ChatMessage] = Field(..., description="消息历史")
    max_tokens: int = Field(default=1024, ge=1, description="最大生�?token �?)
    temperature: float = Field(default=0.7, ge=0, le=2, description="温度")
    top_p: float = Field(default=0.9, ge=0, le=1, description="Top-p")
    backend: Optional[str] = Field(default=None, description="推理后端")
    use_context: bool = Field(default=False, description="是否使用项目上下�?)
    project_path: Optional[str] = Field(default=None, description="项目路径")
    collection_id: Optional[str] = Field(default=None, description="知识库集�?ID")
    use_knowledge: bool = Field(default=False, description="是否使用知识库检�?)
    auto_retrieve: bool = Field(default=True, description="是否自动触发知识检�?)
    top_k: int = Field(default=5, ge=1, le=20, description="知识检索返回数�?)
    include_sources: bool = Field(default=True, description="是否在回复中包含知识来源")

    def get_model_id(self) -> str:
        return self.model_id

    def get_max_tokens(self) -> int:
        return self.max_tokens

    def get_top_p(self) -> float:
        return self.top_p


class MergeRequest(BaseModel):
    """合并请求"""
    base_model_id: str = Field(..., description="基础模型 ID")
    lora_path: str = Field(..., description="LoRA 适配器路�?)
    output_name: str = Field(..., description="输出模型名称")


class MergeStatus(BaseModel):
    """合并状�?""
    status: str
    message: str
    progress: int
    output_path: Optional[str] = None


class BackendSwitchRequest(BaseModel):
    """后端切换请求"""
    backend: str = Field(..., description="后端类型：huggingface/ollama")


def check_ollama_running() -> bool:
    """检�?Ollama 是否运行"""
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        return response.status_code == 200
    except Exception:
        return False


def get_ollama_models() -> List[Dict[str, Any]]:
    """获取 Ollama 模型列表"""
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return [
                {
                    "name": m.get("name", ""),
                    "size": m.get("size", 0),
                    "modified_at": m.get("modified_at", ""),
                }
                for m in data.get("models", [])
            ]
        return []
    except Exception as e:
        logger.error(f"获取 Ollama 模型失败：{e}")
        return []


def apply_chat_template(prompt: str, model_id: str, tokenizer) -> str:
    """
    根据模型类型应用正确�?chat template

    Qwen3.5 系列需要使�?<|im_start|>user\n...<|im_end|>\n<|im_start|>assistant\n 格式
    """
    model_lower = model_id.lower()

    # 检查是否是 Qwen3.5 系列模型
    if "qwen3.5" in model_lower or "qwen3_5" in model_lower:
        # 检查提示是否已经包�?chat template
        if "<|im_start|>" in prompt:
            return prompt
        # 应用 Qwen3.5 chat template
        return f"<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n"

    # 检查是否是 Qwen2.5 系列模型
    if "qwen2.5" in model_lower or "qwen2_5" in model_lower:
        if "<|im_start|>" in prompt:
            return prompt
        return f"<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n"

    # 其他模型，尝试使�?tokenizer �?chat template
    if hasattr(tokenizer, 'apply_chat_template'):
        try:
            messages = [{"role": "user", "content": prompt}]
            formatted = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            if formatted:
                return formatted
        except Exception as e:
            logger.warning(f"应用 chat template 失败: {e}")

    # 默认返回原始提示
    return prompt


def load_model_for_inference(model_id: str) -> Dict[str, Any]:
    """加载模型用于推理（使�?LRU 缓存�?""
    # 先检查缓�?    cached = _model_cache.get(model_id)
    if cached is not None:
        logger.info(f"从缓存加载模型：{model_id}")
        return cached

    model_path = MODELS_DIR / model_id
    if not model_path.exists():
        raise HTTPException(status_code=404, detail=f"模型不存在：{model_id}")

    try:
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM

        logger.info(f"加载模型：{model_path}")

        tokenizer = AutoTokenizer.from_pretrained(
            str(model_path), trust_remote_code=True
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
        }

        # 存入 LRU 缓存
        _model_cache.set(model_id, model_data)

        logger.info(f"模型加载完成：{model_id}，当前缓存大小：{_model_cache.size()}")

        return model_data

    except Exception as e:
        logger.error(f"模型加载失败：{e}")
        raise HTTPException(status_code=500, detail=f"模型加载失败：{str(e)}")


def unload_model(model_id: str):
    """卸载模型（使�?LRU 缓存�?""
    if _model_cache.remove(model_id):
        logger.info(f"模型已卸载：{model_id}")
    else:
        logger.warning(f"模型不在缓存中：{model_id}")


def load_lora_adapter(model, lora_path: str):
    """加载 LoRA 适配�?""
    from pathlib import Path
    
    full_lora_path = Path(lora_path)
    if not full_lora_path.is_absolute():
        full_lora_path = settings.outputs_dir_resolved / lora_path
    
    if not full_lora_path.exists():
        raise HTTPException(status_code=404, detail=f"LoRA 适配器不存在：{lora_path}")
    
    cache_key = str(full_lora_path)
    
    if cache_key in lora_adapter_cache:
        logger.info(f"从缓存加�?LoRA 适配器：{lora_path}")
        return lora_adapter_cache[cache_key]
    
    try:
        from peft import PeftModel
        
        logger.info(f"加载 LoRA 适配器：{full_lora_path}")
        lora_model = PeftModel.from_pretrained(model, str(full_lora_path))
        lora_adapter_cache[cache_key] = lora_model
        
        logger.info(f"LoRA 适配器加载完成：{lora_path}")
        return lora_model
    except ImportError:
        raise HTTPException(status_code=500, detail="peft 库未安装，无法加�?LoRA 适配�?)
    except Exception as e:
        logger.error(f"加载 LoRA 适配器失败：{e}")
        raise HTTPException(status_code=500, detail=f"加载 LoRA 适配器失败：{str(e)}")


def clear_cache():
    """清除缓存"""
    _model_cache.clear()
    lora_adapter_cache.clear()
    logger.info("所有缓存已清除")


def clean_think_tags(text: str) -> str:
    """清理 Qwen3 等模型的思考链内容"""
    import re
    
    if not text:
        return ""
    
    text = re.sub(r'<think[^>]*>.*?</think\s*>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<\|im_start\|>.*?<\|im_end\|>', '', text, flags=re.DOTALL)
    text = text.replace('<|im_start|>', '').replace('<|im_end|>', '')
    
    thinking_starters = [
        '嗯，', '�?', 
        '用户发来', '用户�?, '用户可能', '用户�?, '用户没有', '用户�?,
        '我需�?, '我应�?, '我要', '我可�?, '我得',
        '首先�?, '首先,', 
        '接下�?, '然后', '最�?,
        '可能用户', '可能他们',
        '要避�?, '需要避�?,
        '比如�?, '比如,', 
        '不过�?, '不过,', 
        '另外�?, '另外,', 
        '对了�?, '对了,', 
        '检查一�?, '检查有',
        '作为AI', '作为助手',
        '中文�?, '中文环境',
        '接下来，', '接下�?',
        '可能的回�?, '回复结构',
        '还要注意',
    ]
    
    result_sentences = []
    sentences = re.split(r'([。！？\n])', text)
    
    i = 0
    while i < len(sentences):
        sentence = sentences[i]
        
        if i + 1 < len(sentences) and sentences[i + 1] in '。！？\n':
            full_sentence = sentence + sentences[i + 1]
            i += 2
        else:
            full_sentence = sentence
            i += 1
        
        stripped = full_sentence.strip()
        if not stripped:
            continue
        
        is_thinking = False
        for starter in thinking_starters:
            if stripped.startswith(starter):
                is_thinking = True
                break
        
        if is_thinking:
            continue
        
        result_sentences.append(full_sentence)
    
    result = ''.join(result_sentences).strip()
    return result if result else text.strip()


def ollama_inference(
    model: str,
    prompt: str,
    max_tokens: int,
    temperature: float,
    top_p: float,
    top_k: int = 40,
    repetition_penalty: float = 1.1,
) -> Dict[str, Any]:
    """Ollama 推理"""
    try:
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json; charset=utf-8",
        }
        
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            headers=headers,
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": temperature,
                    "top_p": top_p,
                    "top_k": top_k,
                    "repeat_penalty": repetition_penalty,
                }
            },
            timeout=300,
        )

        if response.status_code != 200:
            error_detail = parse_ollama_error(response.text)
            raise HTTPException(
                status_code=response.status_code,
                detail=error_detail
            )

        result = response.json()
        response_text = result.get("response", "")
        response_text = clean_think_tags(response_text)
        
        return {
            "text": response_text,
            "tokens": result.get("eval_count", 0),
            "time": result.get("eval_duration", 0) / 1e9,
        }
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=503, detail=get_friendly_error("ollama_unavailable", str(e)))


def ollama_chat(
    model: str,
    messages: List[Dict[str, str]],
    max_tokens: int,
    temperature: float,
    top_p: float,
) -> Dict[str, Any]:
    """Ollama 聊天"""
    try:
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json; charset=utf-8",
        }
        
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            headers=headers,
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": temperature,
                    "top_p": top_p,
                }
            },
            timeout=300,
        )

        if response.status_code != 200:
            error_detail = parse_ollama_error(response.text)
            raise HTTPException(
                status_code=response.status_code,
                detail=error_detail
            )

        result = response.json()
        message = result.get("message", {})
        response_text = message.get("content", "")
        
        if not response_text and message.get("thinking"):
            response_text = message.get("thinking", "")
            logger.info("使用 thinking 字段作为响应（content 为空�?)
        
        logger.info(f"Ollama chat 原始响应: {response_text[:100] if response_text else 'EMPTY'}...")
        response_text = clean_think_tags(response_text)
        logger.info(f"清理后响�? {response_text[:100] if response_text else 'EMPTY'}...")
        
        return {
            "text": response_text,
            "tokens": result.get("eval_count", 0),
            "time": result.get("eval_duration", 0) / 1e9,
        }
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=503, detail=get_friendly_error("ollama_unavailable", str(e)))


@router.post("/generate", response_model=InferenceResponse)
async def generate(request: InferenceRequest):
    """生成文本"""
    start_time = time.time()
    backend = request.backend or settings.inference_backend

    if not request.prompt or not request.prompt.strip():
        raise HTTPException(status_code=400, detail="提示内容不能为空")

    if detect_prompt_injection(request.prompt):
        raise HTTPException(
            status_code=400,
            detail="检测到潜在的恶意输入，请修改您的提示内�?
        )

    request.prompt = sanitize_input(request.prompt)

    if backend == "ollama":
        if not check_ollama_running():
            raise HTTPException(
                status_code=503,
                detail="Ollama 未运行，请先启动 Ollama 服务"
            )

        result = ollama_inference(
            model=request.get_model_id(),
            prompt=request.prompt,
            max_tokens=request.get_max_tokens(),
            temperature=request.temperature,
            top_p=request.get_top_p(),
            top_k=request.get_top_k(),
            repetition_penalty=request.get_repetition_penalty(),
        )

        return InferenceResponse(
            text=result["text"],
            tokens=result["tokens"],
            time=result["time"],
            model_id=request.get_model_id(),
            backend="ollama",
        )

    # HuggingFace 后端
    try:
        model_data = load_model_for_inference(request.get_model_id())
        model = model_data["model"]
        tokenizer = model_data["tokenizer"]

        import torch

        lora_adapter = request.get_lora_adapter()
        if lora_adapter:
            model = load_lora_adapter(model, lora_adapter)

        formatted_prompt = apply_chat_template(request.prompt, request.get_model_id(), tokenizer)
        logger.info(f"应用 chat template: {formatted_prompt[:100]}...")

        inputs = tokenizer(formatted_prompt, return_tensors="pt").to(model.device)
        input_length = inputs.input_ids.shape[1]

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=request.get_max_tokens(),
                temperature=request.temperature,
                top_p=request.get_top_p(),
                top_k=request.get_top_k(),
                do_sample=request.temperature > 0,
                repetition_penalty=request.get_repetition_penalty(),
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )

        generated_ids = outputs[0][input_length:]
        response_text = tokenizer.decode(generated_ids, skip_special_tokens=True)

        # 清理响应中的特殊标记
        response_text = response_text.replace("<|im_end|>", "").replace("<|im_start|>", "").strip()

        elapsed_time = time.time() - start_time
        tokens_generated = len(generated_ids)

        return InferenceResponse(
            text=response_text.strip(),
            tokens=tokens_generated,
            time=elapsed_time,
            model_id=request.get_model_id(),
            backend="huggingface",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"推理失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"推理失败：{str(e)}")


@router.post("/chat", response_model=InferenceResponse)
async def chat(request: ChatRequest):
    """聊天对话（支持项目上下文和知识库检索）"""
    start_time = time.time()
    backend = request.backend or settings.inference_backend

    if not request.messages or len(request.messages) == 0:
        raise HTTPException(status_code=400, detail="消息列表不能为空")

    if len(request.messages) > MAX_MESSAGES_COUNT:
        raise HTTPException(status_code=400, detail=f"消息数量超过限制（最�?{MAX_MESSAGES_COUNT} 条）")

    for msg in request.messages:
        if not msg.content or not msg.content.strip():
            raise HTTPException(status_code=400, detail="消息内容不能为空")
        
        if detect_prompt_injection(msg.content):
            raise HTTPException(
                status_code=400, 
                detail="检测到潜在的恶意输入，请修改您的消息内�?
            )
        
        msg.content = sanitize_input(msg.content)

    system_prompt = ""
    knowledge_sources_response = None
    retrieval_info = None
    
    last_user_message = ""
    for msg in reversed(request.messages):
        if msg.role == "user":
            last_user_message = msg.content
            break

    if request.use_knowledge and request.collection_id and last_user_message:
        try:
            from context.knowledge_integration import get_knowledge_integrator
            
            integrator = get_knowledge_integrator()
            
            should_retrieve, reason = integrator.should_retrieve_knowledge(
                query=last_user_message,
                collection_id=request.collection_id,
                force_retrieve=not request.auto_retrieve
            )
            
            if should_retrieve:
                retrieval_result = integrator.retrieve_knowledge(
                    query=last_user_message,
                    collection_id=request.collection_id,
                    top_k=request.top_k
                )
                
                if retrieval_result.sources:
                    knowledge_context = retrieval_result.context
                    system_prompt = f"""你是一个有帮助�?AI 助手。请基于以下参考资料回答用户的问题�?
参考资�?
{knowledge_context}

请注�?
1. 优先使用参考资料中的信息回�?2. 如果参考资料中没有相关信息，请明确说明
3. 引用具体内容时，请标注来源编号（�?[参考资�?1]�?4. 保持回答简洁、准确、有帮助"""
                    
                    knowledge_sources_response = [
                        KnowledgeSourceResponse(
                            id=s.id,
                            source=s.source,
                            score=s.score,
                            content_preview=s.content[:100] + "..." if len(s.content) > 100 else s.content
                        )
                        for s in retrieval_result.sources
                    ]
                    
                    retrieval_info = {
                        "query": retrieval_result.query,
                        "method": retrieval_result.retrieval_method,
                        "total_results": retrieval_result.total_results,
                        "retrieval_time": retrieval_result.retrieval_time
                    }
                    
                    logger.info(f"知识库检索完�? {len(retrieval_result.sources)} 个结�? "
                               f"method={retrieval_result.retrieval_method}, "
                               f"time={retrieval_result.retrieval_time:.3f}s")
        except Exception as e:
            logger.warning(f"知识库检索失�? {e}")

    if not system_prompt and request.use_context and request.project_path:
        try:
            from context.service import get_context_service
            from rag.embedder import get_embedder
            from rag.vector_store import get_vector_store

            if last_user_message:
                embedder = get_embedder()
                vector_store = get_vector_store()
                context_service = get_context_service(embedder=embedder, vector_store=vector_store)

                context = context_service.get_context_for_chat(
                    query=last_user_message,
                    project_path=request.project_path,
                    max_length=1500
                )

                if context:
                    system_prompt = f"""你是一个有帮助�?AI 助手，正在协助用户开发项目�?
项目上下文：
{context}

请根据以上项目信息，给用户一个有帮助的回答�?如果问题与项目相关，请考虑项目的技术栈、架构和代码风格�?"""
                    logger.info(f"已注入项目上下文：{request.project_path}")
        except Exception as e:
            logger.warning(f"获取项目上下文失败：{e}")

    if backend == "ollama":
        if not check_ollama_running():
            raise HTTPException(
                status_code=503,
                detail="Ollama 未运�?
            )

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.extend([{"role": m.role, "content": m.content} for m in request.messages])

        result = ollama_chat(
            model=request.get_model_id(),
            messages=messages,
            max_tokens=request.get_max_tokens(),
            temperature=request.temperature,
            top_p=request.get_top_p(),
        )

        response_text = result["text"]
        
        if knowledge_sources_response and request.include_sources:
            from context.knowledge_integration import get_knowledge_integrator
            integrator = get_knowledge_integrator()
            from context.knowledge_integration import KnowledgeSource
            sources = [
                KnowledgeSource(
                    id=s.id,
                    content=s.content_preview,
                    source=s.source,
                    score=s.score
                )
                for s in knowledge_sources_response
            ]
            response_text = integrator.enhance_response_with_sources(
                response=response_text,
                sources=sources,
                include_citation=True
            )

        return InferenceResponse(
            text=response_text,
            tokens=result["tokens"],
            time=result["time"],
            model_id=request.get_model_id(),
            backend="ollama",
            knowledge_sources=knowledge_sources_response,
            retrieval_info=retrieval_info
        )

    try:
        model_data = load_model_for_inference(request.get_model_id())
        model = model_data["model"]
        tokenizer = model_data["tokenizer"]

        import torch

        messages_for_template = []
        if system_prompt:
            messages_for_template.append({"role": "system", "content": system_prompt})
        for msg in request.messages:
            messages_for_template.append({"role": msg.role, "content": msg.content})

        if hasattr(tokenizer, 'apply_chat_template'):
            try:
                prompt = tokenizer.apply_chat_template(
                    messages_for_template,
                    tokenize=False,
                    add_generation_prompt=True
                )
            except Exception as e:
                logger.warning(f"apply_chat_template 失败，使�?fallback: {e}")
                prompt = ""
                if system_prompt:
                    prompt += f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
                for msg in request.messages:
                    prompt += f"<|im_start|>{msg.role}\n{msg.content}<|im_end|>\n"
                prompt += "<|im_start|>assistant\n"
        else:
            prompt = ""
            if system_prompt:
                prompt += f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
            for msg in request.messages:
                prompt += f"<|im_start|>{msg.role}\n{msg.content}<|im_end|>\n"
            prompt += "<|im_start|>assistant\n"

        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        input_length = inputs.input_ids.shape[1]

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=request.get_max_tokens(),
                temperature=request.temperature,
                top_p=request.get_top_p(),
                do_sample=request.temperature > 0,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )

        generated_ids = outputs[0][input_length:]
        response_text = tokenizer.decode(generated_ids, skip_special_tokens=True)
        response_text = clean_think_tags(response_text)

        if knowledge_sources_response and request.include_sources:
            from context.knowledge_integration import get_knowledge_integrator, KnowledgeSource
            integrator = get_knowledge_integrator()
            sources = [
                KnowledgeSource(
                    id=s.id,
                    content=s.content_preview,
                    source=s.source,
                    score=s.score
                )
                for s in knowledge_sources_response
            ]
            response_text = integrator.enhance_response_with_sources(
                response=response_text,
                sources=sources,
                include_citation=True
            )

        elapsed_time = time.time() - start_time

        return InferenceResponse(
            text=response_text.strip(),
            tokens=len(generated_ids),
            time=elapsed_time,
            model_id=request.get_model_id(),
            backend="huggingface",
            knowledge_sources=knowledge_sources_response,
            retrieval_info=retrieval_info
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"聊天失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"聊天失败：{str(e)}")


@router.post("/stream")
async def stream_inference(request: InferenceRequest):
    """流式推理"""
    from core.streaming import create_sse_event, stream_generator, StreamStats

    backend = request.backend or settings.inference_backend
    stats = StreamStats()

    if backend == "ollama":
        if not check_ollama_running():
            raise HTTPException(status_code=503, detail="Ollama 未运�?)

        async def ollama_stream() -> AsyncGenerator[str, None]:
            stats.start()
            in_think_block = False
            try:
                response = requests.post(
                    f"{OLLAMA_BASE_URL}/api/generate",
                    json={
                        "model": request.get_model_id(),
                        "prompt": request.prompt,
                        "max_tokens": request.get_max_tokens(),
                        "temperature": request.temperature,
                        "top_p": request.get_top_p(),
                        "stream": True,
                    },
                    stream=True,
                    timeout=300,
                )

                if response.status_code != 200:
                    yield await create_sse_event({"error": response.text, "done": True}, "error")
                    return

                for line in response.iter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            # 处理 response 字段（正常响应）
                            chunk = data.get("response", "")
                            if chunk:
                                # 过滤 <think>...</think> 标签内容
                                # 检测是否进入思考块
                                if "<think>" in chunk:
                                    in_think_block = True
                                    chunk = chunk.split("<think>")[-1] if "<think>" in chunk else chunk
                                
                                if "</think>" in chunk:
                                    in_think_block = False
                                    chunk = chunk.split("</think>")[-1] if "</think>" in chunk else chunk
                                elif in_think_block:
                                    chunk = ""  # 在思考块内，跳过
                                
                                if chunk:
                                    stats.add_chunk(chunk)
                                    yield await create_sse_event({
                                        "content": chunk,
                                        "done": data.get("done", False)
                                    })
                            # 处理完成状�?                            if data.get("done", False):
                                stats.finish()
                                yield await create_sse_event({
                                    "done": True,
                                    "stats": stats.to_dict()
                                }, "done")
                                break
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                logger.error(f"Ollama 流式错误：{e}", exc_info=True)
                yield await create_sse_event({"error": str(e), "done": True}, "error")

        return StreamingResponse(
            ollama_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            },
        )

    # HuggingFace 后端
    try:
        import torch
        from transformers import TextIteratorStreamer
        from threading import Thread, Event

        model_data = load_model_for_inference(request.get_model_id())
        model = model_data["model"]
        tokenizer = model_data["tokenizer"]

        formatted_prompt = apply_chat_template(request.prompt, request.get_model_id(), tokenizer)
        logger.info(f"流式推理 - 模型: {request.get_model_id()}, chat template: {formatted_prompt[:100]}...")

        inputs = tokenizer(formatted_prompt, return_tensors="pt").to(model.device)

        streamer = TextIteratorStreamer(
            tokenizer,
            skip_prompt=True,
            skip_special_tokens=True,
            timeout=300,
        )

        generation_kwargs = {
            **inputs,
            "max_new_tokens": request.get_max_tokens(),
            "temperature": request.temperature,
            "top_p": request.get_top_p(),
            "do_sample": request.temperature > 0,
            "streamer": streamer,
            "pad_token_id": tokenizer.pad_token_id,
            "eos_token_id": tokenizer.eos_token_id,
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

        async def generate() -> AsyncGenerator[str, None]:
            chunk_count = 0
            stats.start()
            
            try:
                def get_next_token():
                    try:
                        return next(streamer)
                    except StopIteration:
                        return None
                
                while True:
                    if generation_error:
                        logger.error(f"生成过程中检测到错误: {generation_error}")
                        yield await create_sse_event({
                            "error": str(generation_error),
                            "done": True
                        }, "error")
                        return
                    
                    text = await asyncio.to_thread(get_next_token)
                    
                    if text is None:
                        if not generation_complete.is_set():
                            await asyncio.sleep(0.1)
                            continue
                        break
                    
                    if text:
                        text = text.replace("<|im_end|>", "").replace("<|im_start|>", "")
                        
                        if text:
                            chunk_count += 1
                            stats.add_chunk(text)
                            yield await create_sse_event({
                                "content": text,
                                "done": False
                            })
                
                await asyncio.to_thread(thread.join, timeout=5.0)
                
                if generation_error:
                    yield await create_sse_event({
                        "error": str(generation_error),
                        "done": True
                    }, "error")
                else:
                    stats.finish()
                    logger.info(f"流式推理完成 - 模型: {request.get_model_id()}, �?{chunk_count} �?chunks")
                    yield await create_sse_event({
                        "done": True,
                        "stats": stats.to_dict()
                    }, "done")
                    
            except Exception as e:
                logger.error(f"HuggingFace 流式错误：{e}", exc_info=True)
                yield await create_sse_event({"error": str(e), "done": True}, "error")

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"流式推理失败：{e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"流式推理失败：{str(e)}")


@router.get("/backends")
async def get_backends():
    """获取可用后端"""
    ollama_running = check_ollama_running()

    backends = [
        {
            "id": "huggingface",
            "name": "HuggingFace (本地模型)",
            "available": True,
            "description": "使用下载�?HuggingFace 模型",
        },
        {
            "id": "ollama",
            "name": "Ollama",
            "available": ollama_running,
            "description": "Ollama 本地部署" if ollama_running else "Ollama 未运�?,
        },
    ]

    return {
        "current": settings.inference_backend,
        "backends": backends,
    }


@router.post("/backends/switch")
async def switch_backend(request: BackendSwitchRequest):
    """切换推理后端"""
    if request.backend not in ["huggingface", "ollama"]:
        raise HTTPException(status_code=400, detail="无效的后�?)

    settings.inference_backend = request.backend
    logger.info(f"推理后端已切换到：{request.backend}")

    return {
        "message": f"已切换到 {request.backend}",
        "current": settings.inference_backend,
    }


@router.get("/models")
async def get_inference_models():
    """获取可用推理模型"""
    backend = settings.inference_backend

    if backend == "ollama":
        models = get_ollama_models()
        return [
            {
                "id": m["name"],
                "name": m["name"],
                "type": "ollama",
                "size": m["size"],
            }
            for m in models
        ]

    # HuggingFace 模型
    models = []
    if MODELS_DIR.exists():
        for model_path in MODELS_DIR.iterdir():
            if model_path.is_dir():
                config_file = model_path / "config.json"
                if config_file.exists():
                    with open(config_file, "r", encoding="utf-8") as f:
                        config = json.load(f)
                    models.append({
                        "id": model_path.name,
                        "name": config.get("model_name", model_path.name),
                        "type": config.get("type", "base"),
                        "quantized": config.get("quantized"),
                    })
    return models


@router.get("/ollama/status")
async def get_ollama_status():
    """获取 Ollama 状�?""
    running = check_ollama_running()
    models = get_ollama_models() if running else []

    return {
        "running": running,
        "base_url": OLLAMA_BASE_URL,
        "models": [{"name": m["name"], "size": m["size"]} for m in models],
    }


@router.post("/cache/clear")
async def clear_model_cache_endpoint():
    """清除模型缓存"""
    clear_cache()
    return {"message": "模型缓存已清�?}


@router.get("/cache/status")
async def get_cache_status():
    """获取缓存状�?""
    return {
        "cached_models": _model_cache.list_cached(),
        "cache_size": _model_cache.size(),
        "max_size": 3,
    }


@router.post("/merge", response_model=MergeStatus)
async def merge_lora(request: MergeRequest):
    """合并 LoRA 适配器到基础模型"""
    if merge_state["is_merging"]:
        raise HTTPException(status_code=400, detail="合并正在进行�?)

    models_dir = get_settings().models_dir_resolved
    outputs_dir = get_settings().outputs_dir_resolved

    base_model_path = models_dir / request.base_model_id
    if not base_model_path.exists():
        raise HTTPException(status_code=404, detail="基础模型不存�?)

    lora_path = outputs_dir / request.lora_path
    if not lora_path.exists():
        raise HTTPException(status_code=404, detail="LoRA 适配器不存在")

    output_path = models_dir / request.output_name
    if output_path.exists():
        raise HTTPException(status_code=409, detail="输出名称已存�?)

    def merge_thread():
        try:
            import torch
            from peft import PeftModel
            from transformers import AutoModelForCausalLM, AutoTokenizer

            merge_state["is_merging"] = True
            merge_state["progress"] = 10
            merge_state["message"] = "加载基础模型..."

            base_model = AutoModelForCausalLM.from_pretrained(
                str(base_model_path),
                torch_dtype=torch.float16,
                device_map="cpu",
                trust_remote_code=True,
            )

            merge_state["progress"] = 30
            merge_state["message"] = "加载 LoRA 权重..."

            model = PeftModel.from_pretrained(base_model, str(lora_path))

            merge_state["progress"] = 60
            merge_state["message"] = "合并模型..."

            merged_model = model.merge_and_unload()

            merge_state["progress"] = 80
            merge_state["message"] = "保存合并后的模型..."

            merged_model.save_pretrained(str(output_path))

            tokenizer = AutoTokenizer.from_pretrained(
                str(base_model_path), trust_remote_code=True
            )
            tokenizer.save_pretrained(str(output_path))

            config = {
                "model_name": request.output_name,
                "type": "merged",
                "base_model": request.base_model_id,
                "lora_path": request.lora_path,
                "created_at": datetime.now().isoformat(),
            }
            with open(output_path / "config.json", "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            merge_state["progress"] = 100
            merge_state["message"] = "合并完成!"
            merge_state["is_merging"] = False

            logger.info(f"模型合并完成：{request.output_name}")

        except Exception as e:
            logger.error(f"模型合并失败：{e}", exc_info=True)
            merge_state["message"] = f"合并失败：{str(e)}"
            merge_state["is_merging"] = False

    thread = threading.Thread(target=merge_thread, daemon=True)
    thread.start()

    return MergeStatus(
        status="started",
        message="合并已开�?,
        progress=0,
    )


@router.get("/merge/status")
async def get_merge_status():
    """获取合并状�?""
    return merge_state


@router.get("/performance")
async def get_performance_stats(model_id: Optional[str] = None):
    """获取性能统计"""
    from core.performance import get_performance_monitor
    
    monitor = get_performance_monitor()
    stats = monitor.get_stats(model_id)
    streaming_stats = monitor.get_streaming_stats()
    
    return {
        "inference": stats,
        "streaming": streaming_stats,
    }


@router.get("/performance/recommendations")
async def get_performance_recommendations():
    """获取性能优化建议"""
    from core.performance import get_performance_monitor
    from core.utils import get_device_info
    
    monitor = get_performance_monitor()
    device_info = get_device_info()
    vram_total = device_info.get("memory_total", 0)
    
    recommendations = monitor.get_recommendations(vram_total)
    
    return {
        "recommendations": recommendations,
        "device_info": device_info,
    }


@router.post("/performance/clear")
async def clear_performance_history():
    """清空性能历史"""
    from core.performance import get_performance_monitor
    
    monitor = get_performance_monitor()
    monitor.clear_history()
    
    return {"message": "性能历史已清�?}
